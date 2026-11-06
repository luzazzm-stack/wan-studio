# "Improve my prompt" via cloud models with fallback: OpenRouter qwen3.8-27b -> gemma-4-26b -> NVIDIA GLM-5.3
# -> NVIDIA llama-3.2-90b-vision -> NVIDIA nemotron-3-ultra -> Kaggle qwen2.5:3b -> built-in ideas (in the app).
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
s = open("server.py", encoding="utf-8").read()
a0 = s.index("async def api_improve(req):")
a1 = s.index("async def api_settings(req):")
s = s[:a0] + r'''# Cloud models for "Improve my prompt", tried in order. vision=True models also get the photo for "From a photo".
LLM_CHAIN = [
    {"name": "Qwen3.8 27B", "provider": "openrouter", "model": "qwen/qwen3.8-27b:free", "vision": True, "timeout": 60},
    {"name": "Gemma 4 26B", "provider": "openrouter", "model": "google/gemma-4-26b-a4b-it:free", "vision": True, "timeout": 60},
    {"name": "GLM-5.3", "provider": "nvidia", "model": "z-ai/glm-5.3", "vision": False, "timeout": 150},
    {"name": "Llama 3.2 90B Vision", "provider": "nvidia", "model": "meta/llama-3.2-90b-vision-instruct", "vision": True, "timeout": 60},
    {"name": "Nemotron 3 Ultra", "provider": "nvidia", "model": "nvidia/nemotron-3-ultra-550b-a55b", "vision": False, "timeout": 90},
]
LLM_ENDPOINTS = {"openrouter": "https://openrouter.ai/api/v1/chat/completions",
                 "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions"}


def llm_key(provider):
    try:
        return open(os.path.join(HERE, "keys", f"{provider}.txt"), encoding="utf-8").read().strip()
    except OSError:
        return None


async def call_cloud_llm(m, system, user_text, image_path=None):
    key = llm_key(m["provider"])
    if not key:
        raise RuntimeError("no key")
    content = user_text
    if image_path and m["vision"]:
        import base64, mimetypes
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        b64 = base64.b64encode(open(image_path, "rb").read()).decode()
        content = [{"type": "text", "text": user_text}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]
    body = {"model": m["model"], "max_tokens": 2000, "temperature": 0.8,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    if m["provider"] == "openrouter":
        headers["X-Title"] = "Wan Studio"
    async with http.post(LLM_ENDPOINTS[m["provider"]], json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=m["timeout"])) as r:
        txt = await r.text()
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}: {txt[:160]}")
    j = json.loads(txt)
    if j.get("error"):
        raise RuntimeError(str(j["error"])[:160])
    return (j["choices"][0]["message"].get("content") or "").strip()


async def api_improve(req):
    d = await req.json()
    idea = (d.get("prompt") or "").strip()
    if not idea:
        return web.json_response({"error": "Write an idea first"}, status=400)
    i2v = d.get("mode") == "i2v"
    system = IMPROVE_SYSTEM_I2V if i2v else IMPROVE_SYSTEM
    shape = {"9:16": "vertical 9:16 video for Reels/TikTok", "1:1": "square video"}.get(d.get("aspect"), "landscape video")
    user_text = f"Idea ({shape}): {idea}" + (" The attached photo is the first frame." if i2v else "")
    img = os.path.join(UPLOADS, os.path.basename(d["image"])) if i2v and d.get("image") else None
    if img and not os.path.exists(img):
        img = None
    tried = []
    for m in LLM_CHAIN:
        if not llm_key(m["provider"]):
            continue
        t0 = time.time()
        try:
            opts = parse_options(await call_cloud_llm(m, system, user_text, img))
            if opts:
                log(f"improve: {m['name']} answered in {time.time() - t0:.0f}s")
                return web.json_response({"options": opts, "text": opts[0], "model": m["name"], "saw_photo": bool(img and m["vision"])})
            tried.append(f"{m['name']}: empty answer")
        except Exception as e:
            tried.append(f"{m['name']}: {str(e)[:80]}")
            log("improve fallback:", tried[-1])
    # last resort: the small model on the Kaggle server
    if state["power"] == "ready" and live.get("llm"):
        try:
            r = await gw_json("POST", "/llm", json={"prompt": user_text, "system": system, "max_tokens": 650, "temperature": 0.8})
            t0 = time.time()
            while time.time() - t0 < 170:
                await asyncio.sleep(1.5)
                s_ = await gw_json("GET", f"/llm/{r['id']}")
                if s_.get("done"):
                    opts = parse_options(s_.get("text", ""))
                    if opts:
                        return web.json_response({"options": opts, "text": opts[0], "model": "Qwen2.5 3B (Kaggle)"})
                    break
        except Exception as e:
            tried.append(f"Kaggle: {str(e)[:80]}")
    return web.json_response({"offline": True, "error": "; ".join(tried)[:400]})


''' + s[a1:]
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)

a = open("web/app.js", encoding="utf-8").read()
R = [
 ('''    const r = await api("/api/improve", { json: { prompt: idea, mode: form.mode, aspect: form.aspect } });
    if (r.options && r.options.length) showOptions(r.options, r.model && r.model.includes("7b") ? "written by the larger AI on the GPU" : "written by the AI");''',
  '''    const r = await api("/api/improve", { json: { prompt: idea, mode: form.mode, aspect: form.aspect, image: form.mode === "i2v" ? form.image : null } });
    if (r.options && r.options.length) showOptions(r.options, `written by ${r.model}${r.saw_photo ? ", which looked at your photo" : ""}`);'''),
 ('''    else showOptions([offlineImprove(idea)], S && S.power === "ready" ? "the AI didn't answer, so this uses built-in ideas" : "server is off, so this uses built-in ideas. Turn it on for 3 AI versions");''',
  '''    else showOptions([offlineImprove(idea)], "the AI models are busy right now, so this uses built-in ideas. Try again in a minute");'''),
 ('''btn.disabled = true; label.textContent = S && S.power === "ready" ? "Writing 3 versions…" : "Improving…";''',
  '''btn.disabled = true; label.textContent = "Writing 3 versions…";'''),
]
for o, n in R:
    assert o in a, o[:60]
    a = a.replace(o, n, 1)
open("web/app.js", "w", encoding="utf-8").write(a)
print("ok")
