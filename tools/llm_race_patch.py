# Ask the fast cloud models at the same time and take the first good answer (in preference order once two finish);
# models that were just rate-limited are skipped for 10 minutes; GLM-5.3 is tried after them, then the Kaggle model.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
s = open("server.py", encoding="utf-8").read()
old_start = s.index('    tried = []\n    for m in LLM_CHAIN:')
old_end = s.index('    # last resort: the small model on the Kaggle server')
s = s[:old_start] + '''    tried = []
    usable = [m for m in LLM_CHAIN if llm_key(m["provider"]) and time.time() > LLM_COOLDOWN.get(m["model"], 0)]
    fast = [m for m in usable if m["timeout"] <= 60]
    slow = [m for m in usable if m["timeout"] > 60]

    async def ask(m):
        t0 = time.time()
        try:
            opts = parse_options(await call_cloud_llm(m, system, user_text, img))
            if not opts:
                raise RuntimeError("empty answer")
            log(f"improve: {m['name']} answered in {time.time() - t0:.0f}s")
            return m, opts
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                LLM_COOLDOWN[m["model"]] = time.time() + 600
            tried.append(f"{m['name']}: {str(e)[:80]}")
            return m, None

    for group in (fast, slow):
        if not group:
            continue
        tasks = [asyncio.create_task(ask(m)) for m in group]
        try:
            for fut in asyncio.as_completed(tasks):
                m, opts = await fut
                if opts:
                    return web.json_response({"options": opts, "text": opts[0], "model": m["name"], "saw_photo": bool(img and m["vision"])})
        finally:
            for t in tasks:
                t.cancel()
''' + s[old_end:]
s = s.replace('''LLM_ENDPOINTS = {''', '''LLM_COOLDOWN = {}   # model -> time until which it is skipped (after a rate-limit answer)
LLM_ENDPOINTS = {''', 1)
s = s.replace('''    {"name": "GLM-5.3", "provider": "nvidia", "model": "z-ai/glm-5.3", "vision": False, "timeout": 150},''',
              '''    {"name": "GLM-5.3", "provider": "nvidia", "model": "z-ai/glm-5.3", "vision": False, "timeout": 120},''', 1)
s = s.replace('''    {"name": "Nemotron 3 Ultra", "provider": "nvidia", "model": "nvidia/nemotron-3-ultra-550b-a55b", "vision": False, "timeout": 90},''',
              '''    {"name": "Nemotron 3 Ultra", "provider": "nvidia", "model": "nvidia/nemotron-3-ultra-550b-a55b", "vision": False, "timeout": 60},''', 1)
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("ok")
