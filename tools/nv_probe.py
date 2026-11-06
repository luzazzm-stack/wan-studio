# Sends one tiny chat request to every NVIDIA catalogue model and reports which ones answer.
import json, os, sys, time, urllib.request
key = open(os.path.join(os.path.dirname(__file__), "..", "keys", "nvidia.txt")).read().strip()
models = sorted(m["id"] for m in json.load(urllib.request.urlopen("https://integrate.api.nvidia.com/v1/models", timeout=30))["data"])
skip = ("embed", "retriever", "reward", "nvclip", "parse", "detector", "safety", "guard", "deplot", "kosmos", "calibration", "translate", "topic-control")
ok, bad = [], []
for m in models:
    if any(s in m for s in skip):
        continue
    body = {"model": m, "messages": [{"role": "user", "content": "Reply with the single word: ready"}], "max_tokens": 16, "temperature": 0}
    req = urllib.request.Request("https://integrate.api.nvidia.com/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json"})
    t = time.time()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=60))
        msg = (r["choices"][0]["message"].get("content") or r["choices"][0]["message"].get("reasoning_content") or "").strip().replace("\n", " ")
        ok.append((m, round(time.time() - t, 1), msg[:30]))
        print(f"OK   {m:55s} {time.time()-t:5.1f}s  {msg[:30]!r}", flush=True)
    except urllib.error.HTTPError as e:
        bad.append((m, e.code)); print(f"FAIL {m:55s} HTTP {e.code} {e.read()[:90]!r}", flush=True)
    except Exception as e:
        bad.append((m, str(e)[:40])); print(f"FAIL {m:55s} {str(e)[:60]}", flush=True)
    time.sleep(1.5)
print(f"\n{len(ok)} working, {len(bad)} failed")
