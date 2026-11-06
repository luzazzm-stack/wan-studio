# ------------------------------------------------------------------ extra AI features (NVIDIA free models only; never Gemini)
NV_CHAT = "https://integrate.api.nvidia.com/v1/chat/completions"
NV_FLUX = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
FLUX_SIZES = {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024)}
NV_TEXT_MODELS = ["meta/llama-3.2-90b-vision-instruct", "nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3-super-120b-a12b",
                  "meta/llama-3.2-11b-vision-instruct"]
NV_VISION_MODELS = ["meta/llama-3.2-90b-vision-instruct", "meta/llama-3.2-11b-vision-instruct"]


def nv_headers():
    k = llm_key("nvidia")
    if not k:
        raise RuntimeError("Add an NVIDIA key in Settings → API keys to use this")
    return {"Authorization": f"Bearer {k}", "Content-Type": "application/json", "Accept": "application/json"}


async def nv_chat(models, messages, max_tokens=900, timeout=60):
    errors = []
    for m in models:
        try:
            async with http.post(NV_CHAT, json={"model": m, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                                 headers=nv_headers(), timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                txt = await r.text()
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
            out = (json.loads(txt)["choices"][0]["message"].get("content") or "").strip()
            if out:
                return out, m
            errors.append(f"{m}: empty")
        except Exception as e:
            errors.append(f"{m.split('/')[-1]}: {str(e)[:60]}")
            if "Add an NVIDIA key" in str(e):
                raise
    raise RuntimeError("NVIDIA models are busy right now (" + "; ".join(errors)[:200] + ")")


def small_jpeg_b64(path, width=448):
    """NVIDIA's vision models need small images: shrink to ~25 KB."""
    out = os.path.join(UPLOADS, "_vision_tmp.jpg")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, "-vf", f"scale={width}:-2", "-q:v", "6", out],
                   timeout=60, creationflags=NOWIN)
    import base64
    return base64.b64encode(open(out, "rb").read()).decode()


async def api_make_image(req):
    """1) Picture first: FLUX.1-dev makes starting images from the prompt."""
    d = await req.json()
    prompt = (d.get("prompt") or "").strip()
    if not prompt:
        return web.json_response({"error": "Describe the picture first"}, status=400)
    w, h = FLUX_SIZES.get(d.get("aspect"), FLUX_SIZES["16:9"])
    count = max(1, min(4, int(d.get("count", 2))))
    import base64
    names, errors = [], []
    for i in range(count):
        seed = random.randint(1, 2 ** 31 - 1)
        try:
            async with http.post(NV_FLUX, json={"prompt": prompt[:1800], "width": w, "height": h, "steps": 28, "seed": seed},
                                 headers=nv_headers(), timeout=aiohttp.ClientTimeout(total=120)) as r:
                txt = await r.text()
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}: {txt[:100]}")
            art = json.loads(txt)["artifacts"][0]
            if art.get("finishReason") not in (None, "SUCCESS"):
                raise RuntimeError(f"image blocked ({art.get('finishReason')})")
            name = f"img_{uuid.uuid4().hex[:10]}.jpg"
            with open(os.path.join(UPLOADS, name), "wb") as f:
                f.write(base64.b64decode(art["base64"]))
            names.append(name)
        except Exception as e:
            errors.append(str(e)[:120])
            if "Add an NVIDIA key" in str(e):
                break
    if not names:
        return web.json_response({"error": errors[0] if errors else "No image was made"}, status=502)
    return web.json_response({"images": names, "width": w, "height": h})


async def api_suggest_motion(req):
    """5) Look at the photo and suggest what could move (3 versions)."""
    d = await req.json()
    path = os.path.join(UPLOADS, os.path.basename(d.get("image") or ""))
    if not d.get("image") or not os.path.exists(path):
        return web.json_response({"error": "Choose a photo first"}, status=400)
    b64 = await blocking(small_jpeg_b64, path)
    idea = (d.get("prompt") or "").strip()
    ask = ("Look at this photo, which will be the first frame of a 5-second video. Suggest 3 different, natural ways it could come "
           "to life: what moves in the scene and how the camera moves. Keep everything that is in the photo; do not add new people or objects. "
           + (f"The user's own idea: {idea}. " if idea else "")
           + 'Write exactly 3 versions, each 30 to 60 words, each on its own line starting with "1.", "2." and "3.". Output nothing else.')
    try:
        text, model = await nv_chat(NV_VISION_MODELS, [{"role": "user", "content": [
            {"type": "text", "text": ask}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}])
    except Exception as e:
        return web.json_response({"error": str(e)}, status=502)
    opts = parse_options(text)
    if not opts:
        return web.json_response({"error": "The AI gave an unusable answer. Try again."}, status=502)
    return web.json_response({"options": opts, "model": model.split("/")[-1]})


async def api_social_kit(req):
    """4) Title, caption and hashtags for a finished video."""
    d = await req.json()
    x = lib_by_id(d.get("id"))
    if not x:
        return web.json_response({"error": "Unknown video"}, status=404)
    platform = d.get("platform") or {"9:16": "Instagram Reels / TikTok", "1:1": "Instagram post"}.get(x.get("aspect"), "YouTube / Facebook")
    ask = (f"Write social media text for a short video made from this description: \"{x.get('prompt', '')}\". Platform: {platform}. "
           "Return JSON only, with keys: title (max 60 characters), caption (2 to 3 short sentences, friendly, no hashtags), "
           "hashtags (list of 10 relevant hashtags without the # sign), hook (one punchy first line for the first second of the video).")
    try:
        text, model = await nv_chat(NV_TEXT_MODELS, [{"role": "user", "content": ask}], max_tokens=600)
        m = re.search(r"\{.*\}", text, re.S)
        kit = json.loads(m.group(0)) if m else None
        if not kit or not kit.get("caption"):
            raise RuntimeError("The AI gave an unusable answer. Try again.")
        tags = [("#" + str(t).lstrip("#").replace(" ", "")) for t in (kit.get("hashtags") or [])][:15]
        return web.json_response({"title": kit.get("title", ""), "caption": kit.get("caption", ""), "hook": kit.get("hook", ""),
                                  "hashtags": tags, "platform": platform, "model": model.split("/")[-1]})
    except Exception as e:
        return web.json_response({"error": str(e)[:200]}, status=502)
