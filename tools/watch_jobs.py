# Exits (with a reason) when all jobs finish, any job fails/gets requeued, power breaks, or nothing progresses for STALL minutes.
import json, sys, time, urllib.request
STALL = float(sys.argv[1]) if len(sys.argv) > 1 else 12
t0 = time.time(); last_sig, last_change = None, time.time()
while True:
    try:
        d = json.load(urllib.request.urlopen("http://localhost:8765/api/state", timeout=20))
    except Exception as e:
        print("APP DOWN", e); sys.exit(2)
    js = [j for j in d["jobs"] if j["status"] not in ("done", "failed", "cancelled") or (j.get("finished") or 0) > t0]
    sig = json.dumps([(j["id"], j["status"], round(j.get("progress") or 0, 2)) for j in js] + [d["power"], d["live"]["stage"], d["live"]["pct"]])
    if sig != last_sig:
        last_sig, last_change = sig, time.time()
        print(time.strftime("%T"), d["power"], d["live"]["stage"], [(j["kind"], j["status"], j.get("gpu"), j.get("progress"), j.get("took")) for j in js], flush=True)
    if d["power"] in ("error", "off"):
        print("POWER", d["power"], d.get("error"), d.get("last_stop_reason")); sys.exit(1)
    bad = [j for j in js if j["status"] == "failed" or (j.get("note") and "again" in j["note"] and j["status"] == "queued" and "turned off" not in j["note"])]
    if bad:
        print("PROBLEM", [(j["id"], j["status"], j.get("error"), j.get("note")) for j in bad]); sys.exit(1)
    if js and all(j["status"] in ("done", "cancelled") for j in js):
        print("ALL DONE", [(j["kind"], j.get("took")) for j in js]); sys.exit(0)
    if time.time() - last_change > STALL * 60:
        print(f"STALLED {STALL} min", sig[:500]); sys.exit(1)
    time.sleep(20)
