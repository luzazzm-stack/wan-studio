"""Local test of the Kaggle sign-in (no kernel is ever pushed, no GPU is used).

Two modes:
  python -B tests/test_signin.py SCRATCH_DIR
      runs server.py from a scratch copy with an EMPTY user profile and its own data folder
  python -B tests/test_signin.py SCRATCH_DIR --exe PATH\\TO\\WanStudio.exe
      runs the BUILT app as a brand-new Windows user would (empty %LOCALAPPDATA%, empty profile)
Checks: starts signed out, no Kaggle calls while signed out, refuses to power on, refuses an empty and a bad token
(one read-only Kaggle call), keeps API keys in the user's data folder, sign out is harmless, data stays outside the
program folder.
Optional: WAN_TEST_TOKEN_FILE=<file with a real token> also checks a real sign-in (read-only: token check + GPU quota).
"""
import json, os, shutil, subprocess, sys, time, urllib.error, urllib.request

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.abspath(sys.argv[1])
EXE = sys.argv[sys.argv.index("--exe") + 1] if "--exe" in sys.argv else None
PORT = "8779"
UI = f"http://127.0.0.1:{PORT}"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
OK, FAIL = [], []


def check(name, cond, info=""):
    (OK if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  [{str(info)[:300]}]"), flush=True)


def req(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(UI + path, data=body, method=method or ("POST" if body is not None else "GET"),
                               headers={"Content-Type": "application/json"} if body is not None else {})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


try:
    urllib.request.urlopen(UI + "/api/state", timeout=1)
    sys.exit(f"Something already runs on port {PORT}; stop it first.")
except Exception:
    pass

shutil.rmtree(T, ignore_errors=True)
home, lad = os.path.join(T, "home"), os.path.join(T, "localappdata")
os.makedirs(home)
os.makedirs(lad)
env = {k: v for k, v in os.environ.items() if not k.startswith(("KAGGLE_", "WAN_STUDIO_"))}
env.update(WAN_STUDIO_PORT=PORT, USERPROFILE=home, HOME=home, LOCALAPPDATA=lad, PYTHONDONTWRITEBYTECODE="1")
if EXE:
    app = os.path.dirname(os.path.abspath(EXE))
    data = os.path.join(lad, "Wan Studio", "data")             # where the installed app keeps its data
    cmd = [os.path.abspath(EXE)]
else:
    app = os.path.join(T, "app")
    os.makedirs(app)
    for d in ("kaggle", "web"):
        shutil.copytree(os.path.join(SRC, d), os.path.join(app, d), ignore=shutil.ignore_patterns("__pycache__"))
    for f in ("server.py", "kaggle_ctl.py"):
        shutil.copy(os.path.join(SRC, f), app)
    data = os.path.join(T, "appdata")
    env.update(WAN_STUDIO_HOME=app, WAN_STUDIO_DATA=data)
    cmd = [sys.executable, "-B", os.path.join(app, "server.py")]
log = open(os.path.join(T, "run.log"), "w")
p = subprocess.Popen(cmd, cwd=app, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=NOWIN)
try:
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            if req("/api/state")[0] == 200:
                break
        except Exception:
            time.sleep(0.5)
    code, s = req("/api/state")
    check("app starts and answers", code == 200, code)
    check("starts signed out", s["kaggle"]["signed_in"] is False and s["kaggle"]["kernel"] is None and s["kaggle"]["user"] is None, s.get("kaggle"))
    check("no Kaggle quota call while signed out", s["quota"] is None, s["quota"])
    check("data folder is outside the program folder", os.path.exists(os.path.join(data, "state.json"))
          and not os.path.exists(os.path.join(app, "data")), data)
    check("no keys folder in the program folder", not os.path.exists(os.path.join(app, "keys")))
    html = urllib.request.urlopen(UI + "/", timeout=10).read().decode("utf-8")
    check("UI has the sign-in window", 'id="signin"' in html and "verified phone number" in html and "kaggle.com/settings" in html)
    js = urllib.request.urlopen(UI + "/app.js", timeout=10).read().decode("utf-8")
    check("UI opens sign-in on first run", "maybeSignIn()" in js and "needsSignIn" in js)
    code, r = req("/api/power", {"on": True})
    check("power on refused while signed out", code == 409 and r.get("signin"), (code, r))
    time.sleep(1.5)
    check("server still off", req("/api/state")[1]["power"] == "off")
    code, r = req("/api/signin", {"username": "nobody", "token": ""})
    check("empty token refused", code == 400, (code, r))
    code, r = req("/api/signin", {"username": "nobody", "token": "KGAT_" + "0" * 32})
    check("bad token refused by Kaggle", code == 400 and "did not accept" in (r or {}).get("error", ""), (code, r))
    check("no token file after a refused sign-in", not os.path.exists(os.path.join(data, "kaggle_token")))
    code, r = req("/api/keys")
    check("keys list has no Kaggle entry and nothing set", code == 200 and all(not k["set"] for k in r)
          and not any("kaggle" in k["provider"] for k in r), r)
    code, r = req("/api/keys", {"provider": "nvidia", "key": "nvapi-test-0000000000"})
    kp = os.path.join(data, "keys", "nvidia.txt")
    check("API key saved in the user's data folder", code == 200 and os.path.exists(kp) and not os.path.exists(os.path.join(app, "keys")), (code, r))
    req("/api/keys/nvidia", method="DELETE")
    check("API key removed", not os.path.exists(kp))
    code, r = req("/api/signout", {})
    check("sign out while signed out is harmless", code == 200, (code, r))

    tf = os.environ.get("WAN_TEST_TOKEN_FILE")
    if tf:
        token = open(os.path.expanduser(tf), encoding="utf-8").read().strip()
        code, r = req("/api/signin", {"username": "", "token": token})
        check("real token accepted, username found by Kaggle", code == 200 and r.get("user"), (code, r))
        s = req("/api/state")[1]
        check("signed in: kernel in the user's own account", s["kaggle"]["signed_in"] and s["kaggle"]["source"] == "app"
              and s["kaggle"]["kernel"] == f"{r.get('user')}/wan-studio-server", s["kaggle"])
        check("kaggle library works with it (GPU quota)", bool(s["quota"]) and s["quota"].get("total_h", 0) > 0, s["quota"])
        code, r = req("/api/signout", {})
        s = req("/api/state")[1]
        check("sign out removes the token", code == 200 and not s["kaggle"]["signed_in"]
              and not os.path.exists(os.path.join(data, "kaggle_token")), (code, s["kaggle"]))
finally:
    subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=NOWIN)
    log.close()
    time.sleep(1)
    shutil.rmtree(data, ignore_errors=True)    # never leave a token copy behind
print(f"\n{len(OK)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
