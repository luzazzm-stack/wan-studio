# ------------------------------------------------------------------ API keys (Settings): list / add / edit / remove / test
KEY_PROVIDERS = {
    "gemini2": {"label": "Gemini (free key)", "used": "Improve my prompt (used first)"},
    "gemini": {"label": "Gemini (paid key)", "used": "Improve my prompt (backup, max 30 a day)"},
    "nvidia": {"label": "NVIDIA", "used": "Not used yet (for extra features)"},
    "openrouter": {"label": "OpenRouter", "used": "Not used yet (for extra features)"},
    "kaggle_luzamhjo_access_token": {"label": "Kaggle (luzamhjo)", "used": "Runs the video server. Restart the app after changing it"},
}


def key_path(provider):
    return os.path.join(HERE, "keys", f"{provider}.txt")


def mask(k):
    return (k[:4] + "…" + k[-4:]) if len(k) > 10 else "…"


async def api_keys_list(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    out = []
    for p, info in KEY_PROVIDERS.items():
        k = llm_key(p) or ""
        out.append({"provider": p, **info, "set": bool(k), "masked": mask(k) if k else ""})
    return web.json_response(out)


async def api_keys_save(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    d = await req.json()
    p, k = d.get("provider"), (d.get("key") or "").strip()
    if p not in KEY_PROVIDERS or len(k) < 10 or any(c.isspace() for c in k):
        return web.json_response({"error": "Choose a service and paste a valid key"}, status=400)
    os.makedirs(os.path.dirname(key_path(p)), exist_ok=True)
    with open(key_path(p), "w", encoding="utf-8") as f:
        f.write(k)
    log("api key saved for", p)
    return web.json_response({"ok": True, "masked": mask(k)})


async def api_keys_delete(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    p = req.match_info["provider"]
    if p in KEY_PROVIDERS and os.path.exists(key_path(p)):
        os.remove(key_path(p))
        log("api key removed for", p)
    return web.json_response({"ok": True})


async def api_keys_test(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    p = req.match_info["provider"]
    k = llm_key(p)
    if not k:
        return web.json_response({"ok": False, "message": "No key saved"})
    t0 = time.time()
    try:
        if p in ("gemini", "gemini2"):
            async with http.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": k},
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
                j = await r.json()
                if r.status != 200:
                    raise RuntimeError(j.get("error", {}).get("message", f"HTTP {r.status}"))
                msg = f"Works: {len(j.get('models', []))} models available"
        elif p == "openrouter":
            async with http.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {k}"},
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
                j = await r.json()
                if r.status != 200:
                    raise RuntimeError(str(j.get("error", f"HTTP {r.status}"))[:120])
                fd = j.get("data", {}).get("free_model_daily_requests") or {}
                msg = "Works" + (f": {fd.get('remaining')} of {fd.get('limit')} free requests left today" if fd else "")
        elif p == "nvidia":
            body = {"model": "meta/llama-3.2-11b-vision-instruct", "messages": [{"role": "user", "content": "Reply: ok"}], "max_tokens": 5}
            async with http.post(LLM_ENDPOINTS_ALL["nvidia"], json=body, headers={"Authorization": f"Bearer {k}", "Accept": "application/json"},
                                 timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:120]}")
                msg = "Works"
        else:
            q = await blocking(kaggle_ctl.quota)
            msg = f"Works: {q['total_h'] - q['used_h']:.1f} of {q['total_h']:.0f} GPU hours left this week"
        return web.json_response({"ok": True, "message": f"{msg} ({time.time() - t0:.1f} s)"})
    except Exception as e:
        return web.json_response({"ok": False, "message": str(e)[:200]})


LLM_ENDPOINTS_ALL = {"nvidia": "https://integrate.api.nvidia.com/v1/chat/completions"}
