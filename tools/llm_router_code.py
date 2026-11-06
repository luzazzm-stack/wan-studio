# Free-model router for "Improve my prompt".
# Asks a few models at a time (waves), healthiest first; learns from each answer; rests busy models;
# spends the OpenRouter free allowance (50 requests/day) carefully; never waits more than ~90 s.
LLM_MODELS = [
    # name, provider, model id, can see photos
    ("Qwen3.8 27B", "openrouter", "qwen/qwen3.8-27b:free", True),
    ("Gemma 4 26B", "openrouter", "google/gemma-4-26b-a4b-it:free", True),
    ("Llama 3.2 90B Vision", "nvidia", "meta/llama-3.2-90b-vision-instruct", True),
    ("Nemotron 3 Ultra", "nvidia", "nvidia/nemotron-3-ultra-550b-a55b", False),
    ("GLM-5.3", "nvidia", "z-ai/glm-5.3", False),
    ("GLM-5.3 Flash", "nvidia", "z-ai/glm-5.3-flash", False),
    ("Llama 3.2 11B Vision", "nvidia", "meta/llama-3.2-11b-vision-instruct", True),
    ("Nemotron 3 Super", "nvidia", "nvidia/nemotron-3-super-120b-a12b", False),
    ("Gemma 4 31B", "nvidia", "google/gemma-4-31b-it", True),
    ("DeepSeek v4.1 Flash", "nvidia", "deepseek-ai/deepseek-v4.1-flash", False),
    ("Nemotron 3 Ultra (OR)", "openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", False),
    ("Ling 3.0 Flash", "openrouter", "inclusionai/ling-3.0-flash-sante:free", False),
]
LLM_ENDPOINTS = {"openrouter": "https://openrouter.ai/api/v1/chat/completions",
                 "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions"}
LLM_PREFERRED = ("Qwen3.8 27B", "Gemma 4 26B", "GLM-5.3")    # the user's picks get a small head start
OPENROUTER_DAILY_LIMIT, OPENROUTER_RESERVE = 50, 5
WAVE_SIZE, WAVE_EVERY, IMPROVE_DEADLINE, PER_CALL_TIMEOUT = 2, 15, 90, 75
llm_health = load("llm_health.json", {})     # model id -> {ok, fail, lat, rest_until}
llm_budget = load("llm_budget.json", {})     # {"day": "YYYY-MM-DD", "openrouter": n}


def llm_key(provider):
    try:
        return open(os.path.join(HERE, "keys", f"{provider}.txt"), encoding="utf-8").read().strip()
    except OSError:
        return None


def openrouter_left():
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if llm_budget.get("day") != day:
        llm_budget.clear()
        llm_budget.update(day=day, openrouter=0)
    return OPENROUTER_DAILY_LIMIT - OPENROUTER_RESERVE - llm_budget.get("openrouter", 0)


def health_score(name, model_id):
    h = llm_health.get(model_id, {})
    ok, fail = h.get("ok", 0), h.get("fail", 0)
    rate = (ok + 1) / (ok + fail + 2)                 # unknown models start at 50 %
    lat = h.get("lat", 30.0)
    return rate * 100 - lat + (15 if name in LLM_PREFERRED else 0)


def health_record(model_id, ok, latency=None, rest=0):
    h = llm_health.setdefault(model_id, {"ok": 0, "fail": 0, "lat": 30.0})
    # recent results count more: decay old counts a little each time
    h["ok"], h["fail"] = h["ok"] * 0.9 + (1 if ok else 0), h["fail"] * 0.9 + (0 if ok else 1)
    if latency is not None:
        h["lat"] = round(h["lat"] * 0.6 + latency * 0.4, 1)
    if rest:
        h["rest_until"] = time.time() + rest
    save("llm_health.json", llm_health)


async def call_cloud_llm(provider, model_id, vision, system, user_text, image_path=None, timeout=PER_CALL_TIMEOUT):
    key = llm_key(provider)
    content = user_text
    if image_path and vision:
        import base64, mimetypes
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        b64 = base64.b64encode(open(image_path, "rb").read()).decode()
        content = [{"type": "text", "text": user_text}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]
    body = {"model": model_id, "max_tokens": 2000, "temperature": 0.8,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    if provider == "openrouter":
        headers["X-Title"] = "Wan Studio"
        llm_budget["openrouter"] = llm_budget.get("openrouter", 0) + 1
        save("llm_budget.json", llm_budget)
    async with http.post(LLM_ENDPOINTS[provider], json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
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

    now = time.time()
    or_left = openrouter_left()
    cands = [(n, p, m, v) for n, p, m, v in LLM_MODELS
             if llm_key(p) and llm_health.get(m, {}).get("rest_until", 0) < now and (p != "openrouter" or or_left > 0)]
    # with a photo, models that can see it go first
    cands.sort(key=lambda c: (-(1 if (img and c[3]) else 0), -health_score(c[0], c[2])))
    if or_left <= 10:   # running low on the free OpenRouter allowance: keep it for when NVIDIA fails
        cands.sort(key=lambda c: c[1] == "openrouter")
    tried, results, tasks = [], [], {}
    start = time.time()

    async def ask(c):
        n, p, m, v = c
        t0 = time.time()
        try:
            opts = parse_options(await call_cloud_llm(p, m, v, system, user_text, img))
            if not opts:
                raise RuntimeError("empty answer")
            health_record(m, True, time.time() - t0)
            log(f"improve: {n} answered in {time.time() - t0:.0f}s ({len(opts)} versions)")
            return c, opts
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err = str(e)
            busy = any(x in err for x in ("429", "503", "rate", "overloaded", "Timeout", "timed out")) or not err
            health_record(m, False, rest=300 if busy else 60)
            tried.append(f"{n}: {(err or 'timed out')[:70]}")
            return c, None

    queue = list(cands)
    best = None
    while time.time() - start < IMPROVE_DEADLINE:
        if queue and (not tasks or time.time() - start >= WAVE_EVERY * len(tried + list(tasks)) / WAVE_SIZE):
            for c in queue[:WAVE_SIZE]:
                tasks[asyncio.create_task(ask(c))] = c
            queue = queue[WAVE_SIZE:]
        if not tasks:
            break
        done, _ = await asyncio.wait(list(tasks), timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            c = tasks.pop(t)
            _, opts = t.result()
            if opts and (best is None or len(opts) > len(best[1])):
                best = (c, opts)
        if best and (len(best[1]) >= 3 or not tasks):
            break
    for t in tasks:
        t.cancel()
    if best:
        c, opts = best
        return web.json_response({"options": opts, "text": opts[0], "model": c[0], "saw_photo": bool(img and c[3]),
                                  "seconds": round(time.time() - start)})
    return web.json_response({"offline": True, "error": "; ".join(tried)[:400]})
