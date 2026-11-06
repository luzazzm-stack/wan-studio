"""Wan Studio for Windows: the app window (WebView2) plus the local server in one program.

Developer build (build_app.sh): app\\WanStudio\\WanStudio.exe; data, keys and the UI files stay in the project folder,
so the app can be updated without rebuilding.
Public build (build_client.sh + installer/WanStudio.iss): one folder with web/ and kaggle/ next to the exe. Its data
(Kaggle sign-in, settings, queue, API keys) lives in %LOCALAPPDATA%\\Wan Studio\\data, never next to the exe.
"""
import ctypes, json, os, sys, threading, time, urllib.request

if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(sys.executable)
    if os.path.isdir(os.path.join(EXE_DIR, "web")):          # public build (installed or portable)
        HOME = EXE_DIR
        os.environ.setdefault("WAN_STUDIO_DATA", os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Wan Studio", "data"))
    else:
        HOME = os.path.abspath(os.path.join(EXE_DIR, "..", ".."))
else:
    HOME = os.path.dirname(os.path.abspath(__file__))
os.environ["WAN_STUDIO_HOME"] = HOME
DATA = os.environ.get("WAN_STUDIO_DATA") or os.path.join(HOME, "data")
os.makedirs(DATA, exist_ok=True)
sys.stdout = sys.stderr = open(os.path.join(DATA, "app.log"), "a", buffering=1, encoding="utf-8")
sys.path.insert(0, HOME)

URL = "http://127.0.0.1:" + os.environ.get("WAN_STUDIO_PORT", "8765")


def server_up():
    try:
        urllib.request.urlopen(URL + "/api/state", timeout=1.5).read()
        return True
    except Exception:
        return False


def main():
    own_server = False
    loop_box = {}
    if server_up():
        # Another copy is already running: if it has a window, bring it to the front and leave.
        try:
            r = json.loads(urllib.request.urlopen(urllib.request.Request(URL + "/api/show", method="POST"), timeout=3).read())
            if r.get("shown"):
                return
        except Exception:
            pass
    else:
        import asyncio
        import server
        from aiohttp import web

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_box["loop"] = loop
            web.run_app(server.make_app(), host="0.0.0.0", port=server.PORT, print=None, access_log=None, handle_signals=False, loop=loop)

        threading.Thread(target=run, daemon=True).start()
        own_server = True
        for _ in range(60):
            if server_up():
                break
            time.sleep(0.25)

    import webview
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TheEverestHoliday.WanStudio")
    except Exception:
        pass
    webview.settings["ALLOW_DOWNLOADS"] = True
    win = webview.create_window("Wan Studio", URL, width=1380, height=900, min_size=(420, 640), background_color="#000000")

    if own_server:
        import server

        def show():
            win.show()
            win.restore()
        server.show_window = show

        def on_closing():
            busy = server.state.get("power") in ("starting", "ready") or any(
                j["status"] in ("queued", "uploading", "running", "downloading") for j in server.jobs)
            if busy and win.create_confirmation_dialog(
                    "Wan Studio", "The Kaggle server is on or videos are still being made.\n\n"
                    "OK: keep Wan Studio working in the background (open it again from the Start menu).\n"
                    "Cancel: quit and turn the Kaggle server off."):
                win.hide()
                return False
            return True
        win.events.closing += on_closing

    webview.start()

    if own_server and loop_box.get("loop"):
        import asyncio
        import server
        if server.state.get("power") in ("starting", "ready"):
            try:
                asyncio.run_coroutine_threadsafe(server.power_off("Wan Studio was closed"), loop_box["loop"]).result(timeout=40)
            except Exception as e:
                print("power off on exit failed", e)


if __name__ == "__main__":
    main()
