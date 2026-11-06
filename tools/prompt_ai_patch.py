# Better "Improve my prompt": Wan's official prompt-extension rules, a 7B model on the GPU when it is free
# (3B on CPU otherwise), and three versions to choose from.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ------------------------------------------------------------------ Kaggle server
k = open("kaggle/wan_server.py", encoding="utf-8").read()
R = [
 ('''LLM_MODEL = "qwen2.5:3b"''', '''LLM_MODEL = "qwen2.5:3b"          # CPU fallback while both GPUs are making video
LLM_GPU_MODEL = "qwen2.5:7b"      # better rewrites; runs on GPU 2 only when it is idle, then unloads'''),
 ('''    # Small CPU-only LLM used by the "Improve my prompt" button (GPUs stay free for video).''',
  '''    # LLM for "Improve my prompt". Ollama only sees GPU 2; each request picks GPU (when idle) or CPU.'''),
 ('''        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "OLLAMA_HOST": "127.0.0.1:11434"}''',
  '''        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "1", "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_MAX_LOADED_MODELS": "1"}'''),
 ('''        sh(f"OLLAMA_HOST=127.0.0.1:11434 ollama pull {LLM_MODEL} >/dev/null 2>&1")
        S["llm"] = True''', '''        sh(f"OLLAMA_HOST=127.0.0.1:11434 ollama pull {LLM_MODEL} >/dev/null 2>&1")
        S["llm"] = True
        sh(f"OLLAMA_HOST=127.0.0.1:11434 ollama pull {LLM_GPU_MODEL} >/dev/null 2>&1")
        S["llm_gpu"] = True'''),
 ('''        async def run():
            try:
                async with session.post("http://127.0.0.1:11434/api/chat", json={
                        "model": LLM_MODEL, "stream": False, "options": {"num_predict": d.get("max_tokens", 220), "temperature": 0.7, "num_thread": 2},
                        "messages": [{"role": "system", "content": d.get("system", "")}, {"role": "user", "content": d["prompt"]}]}) as r:
                    j = await r.json()
                llm_jobs[jid] = {"done": True, "text": j.get("message", {}).get("content", "")}''',
  '''        async def run():
            try:
                g2 = S["gpus"][1] if len(S["gpus"]) > 1 else {}
                gpu_free = S.get("llm_gpu") and not g2.get("prompt_id") and not g2.get("queue")
                body = {"model": LLM_GPU_MODEL if gpu_free else LLM_MODEL, "stream": False,
                        "keep_alive": 0 if gpu_free else "10m",   # free the GPU memory right after answering
                        "options": {"num_predict": d.get("max_tokens", 220), "temperature": d.get("temperature", 0.7),
                                    **({} if gpu_free else {"num_gpu": 0, "num_thread": 2})},
                        "messages": [{"role": "system", "content": d.get("system", "")}, {"role": "user", "content": d["prompt"]}]}
                async with session.post("http://127.0.0.1:11434/api/chat", json=body) as r:
                    j = await r.json()
                llm_jobs[jid] = {"done": True, "text": j.get("message", {}).get("content", ""), "model": body["model"]}'''),
]
for o, n in R:
    assert o in k, o[:60]
    k = k.replace(o, n, 1)
open("kaggle/wan_server.py", "w", encoding="utf-8").write(k)

# ------------------------------------------------------------------ local server
s = open("server.py", encoding="utf-8").read()
a0 = s.index("IMPROVE_SYSTEM = (")
a1 = s.index("async def api_settings(req):")
s = s[:a0] + r'''# Based on Wan 2.2's own prompt-extension instructions (wan/utils/system_prompt.py, T2V/I2V English), plus business context.
IMPROVE_SYSTEM = """You are a film director writing prompts for the Wan 2.2 text-to-video model. Rewrite the user's idea into high-quality English video prompts without changing its meaning (keep the same subject and action).
Rules:
1. Start with up to 4 short cinematic settings chosen from: time (Day time, Dawn time, Sunrise time, Sunset time, Night time), light (Daylight, Sunny lighting, Overcast lighting, Soft lighting, Hard lighting, Side lighting, Edge lighting, Practical lighting, Firelight, Moonlight), colour (Warm colors, Cool colors), shot (Close-up shot, Medium shot, Medium wide shot, Wide shot, Extreme wide shot), angle (Low angle shot, High angle shot, Aerial shot, Overhead shot), composition (Center composition, Balanced composition). Default to Day time and a Medium or Wide shot.
2. Describe the subject's look clearly (clothing, colours, number of people, posture). Never add people or objects that are not in the idea. Add concrete background details.
3. Describe the motion step by step with simple verbs. If there is no action, add a natural one, and add gentle background motion (clouds drifting, flags fluttering, water rippling, leaves moving).
4. Keep any camera movement the user gives. Otherwise add one simple move: slow push-in, slow pull-back, tracking shot, slow pan, or aerial view gliding forward. Never write the word "drone".
5. No mood or literary sentences (no "breathtaking", "magical atmosphere", "sense of wonder"). No text, logos or signs to read.
6. Skies are clear deep blue unless the idea says otherwise. Places in Nepal, Tibet or Bhutan should look accurate (prayer flags, stupas, stone trails, tea houses, snow peaks).
7. Each prompt is 60 to 110 words, one paragraph.
Write exactly 3 different versions (different camera, light or framing), each on its own line starting with "1.", "2." and "3.". Output nothing else.
Example of one version:
Sunrise time, aerial shot, wide shot, warm colors. A line of five trekkers in bright red and blue jackets walks along a narrow stone trail on a Himalayan ridge, prayer flags fluttering on ropes beside them. The camera glides slowly forward above them toward the snow-covered summit of Ama Dablam, which glows orange in the first light. Thin clouds drift across the valley below and the trekkers' poles click on the rocks as they climb."""

IMPROVE_SYSTEM_I2V = """You rewrite prompts for Wan 2.2 image-to-video. The user's photo is already the first frame, so describe only what MOVES and how the camera moves. Keep the user's actions and camera moves. If the idea is short, add natural motion for the main subject and the background (people walking, flags fluttering, clouds drifting, water rippling, steam rising). Do not describe the static scene in detail and never add new people or objects. Use simple verbs, one paragraph of 30 to 70 words, English.
Write exactly 3 different versions, each on its own line starting with "1.", "2." and "3.". Output nothing else."""


def parse_options(text):
    import re as _re
    opts = []
    for line in (text or "").splitlines():
        m = _re.match(r"^\s*(?:\*\*)?\s*(?:version\s*)?[1-3][.)]\s*(?:\*\*)?\s*(.+)$", line.strip(), _re.I)
        if m and len(m.group(1).split()) >= 8:
            opts.append(m.group(1).strip().strip('"').strip())
    if not opts and text and len(text.split()) >= 8:
        opts = [text.strip().strip('"')]
    return opts[:3]


async def api_improve(req):
    d = await req.json()
    idea = (d.get("prompt") or "").strip()
    if not idea:
        return web.json_response({"error": "Write an idea first"}, status=400)
    if state["power"] != "ready" or not live.get("llm"):
        return web.json_response({"offline": True})
    system = IMPROVE_SYSTEM_I2V if d.get("mode") == "i2v" else IMPROVE_SYSTEM
    shape = {"9:16": "vertical 9:16 video for Reels/TikTok", "1:1": "square video"}.get(d.get("aspect"), "landscape video")
    try:
        r = await gw_json("POST", "/llm", json={"prompt": f"Idea ({shape}): {idea}", "system": system, "max_tokens": 650, "temperature": 0.8})
        t0 = time.time()
        while time.time() - t0 < 170:
            await asyncio.sleep(1.5)
            s = await gw_json("GET", f"/llm/{r['id']}")
            if s.get("done"):
                if s.get("error"):
                    raise RuntimeError(s["error"])
                opts = parse_options(s.get("text", ""))
                if not opts:
                    raise RuntimeError("no usable answer")
                return web.json_response({"options": opts, "text": opts[0], "model": s.get("model")})
        raise RuntimeError("took too long")
    except Exception as e:
        log("improve failed", e)
        return web.json_response({"offline": True, "error": str(e)})


''' + s[a1:]
s = s.replace('''        "live": {k: live[k] for k in ("stage", "pct", "detail", "gpus", "llm", "uptime", "idle_s", "timings")},''',
              '''        "live": {**{k: live[k] for k in ("stage", "pct", "detail", "gpus", "llm", "uptime", "idle_s", "timings")}, "llm_gpu": live.get("llm_gpu", False)},''')
s = s.replace('''        live.update(stage=h["stage"], pct=h["pct"], detail=h["detail"], error=h["error"], gpus=h["gpus"], llm=h["llm"],''',
              '''        live.update(stage=h["stage"], pct=h["pct"], detail=h["detail"], error=h["error"], gpus=h["gpus"], llm=h["llm"], llm_gpu=h.get("llm_gpu", False),''')
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s); ast.parse(k)
print("ok", "llm_gpu=h.get" in s)
