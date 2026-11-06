# One tiny chat request to every free OpenRouter model; reports which ones answer and how fast.
import json, os, time, urllib.request
key = open(os.path.join(os.path.dirname(__file__), "..", "keys", "openrouter.txt")).read().strip()
data = json.load(urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=30))["data"]
free = sorted(m["id"] for m in data if m["id"].endswith(":free") or m["id"] == "openrouter/free")
ok = 0
for m in free:
    if "content-safety" in m:
        continue
    body = {"model": m, "messages": [{"role": "user", "content": "Reply with the single word: ready"}], "max_tokens": 40}
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "X-Title": "Wan Studio"})
    t = time.time()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=90))
        if "error" in r:
            raise RuntimeError(str(r["error"])[:120])
        msg = (r["choices"][0]["message"].get("content") or "").strip().replace("\n", " ")
        ok += 1
        print(f"OK   {m:48s} {time.time()-t:5.1f}s  {msg[:30]!r}", flush=True)
    except urllib.error.HTTPError as e:
        print(f"FAIL {m:48s} HTTP {e.code} {e.read()[:110]!r}", flush=True)
    except Exception as e:
        print(f"FAIL {m:48s} {str(e)[:110]}", flush=True)
    time.sleep(2)
print(f"\n{ok} working of {len(free)} free")
