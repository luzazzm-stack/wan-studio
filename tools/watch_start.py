# Waits for the Kaggle server to announce its URL on ntfy, then follows /health until ready or error.
import json, sys, time, urllib.request
key, topic, since = sys.argv[1], sys.argv[2], sys.argv[3]
url, last = None, None
t0 = time.time()
while time.time() - t0 < 3600:
    try:
        if not url:
            raw = urllib.request.urlopen(f"https://ntfy.sh/{topic}/json?poll=1&since={since}", timeout=30).read().decode()
            for line in raw.splitlines():
                m = json.loads(json.loads(line).get("message", "{}") or "{}")
                if m.get("url"): url = m["url"]; print("URL", url, flush=True)
                if m.get("type") == "error": print("ERROR", m, flush=True); sys.exit(1)
        else:
            h = json.loads(urllib.request.urlopen(urllib.request.Request(url + "/health", headers={"X-Key": key}), timeout=30).read())
            s = (h["stage"], h["pct"], h["detail"][:40])
            if s != last: print(time.strftime("%T"), *s, flush=True); last = s
            if h["ready"] or h["error"]:
                print(json.dumps({k: h[k] for k in ("ready", "error", "timings", "llm")}), flush=True); break
    except Exception as e:
        print("..", type(e).__name__, str(e)[:80], flush=True)
    time.sleep(15)
