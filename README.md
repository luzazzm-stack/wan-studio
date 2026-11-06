# Wan Studio

Make AI videos with **Wan 2.2 (TI2V-5B)** running on your free Kaggle GPUs (2× T4, account `luzamhjo`).

## Start
Double-click **Wan Studio** on the desktop. The app window opens; flip the switch at the top to turn the Kaggle server on (about 4–5 minutes).

Phone: same Wi-Fi, open the address shown in **Settings → Open on your phone** and enter the PIN.

## How it works
- `server.py`: the local app (port 8765). Holds the Kaggle key, runs the queue, saves videos to `Videos\Wan Studio`.
- `kaggle/wan_server.py`: pushed to Kaggle as the kernel `luzamhjo/wan-studio-server` each time you turn on. It runs two ComfyUI copies (one per T4) plus a small CPU LLM for "Improve my prompt", behind a key-protected gateway and a Cloudflare quick tunnel. The tunnel address is announced on a private ntfy.sh topic.
- Turning off calls the server's `/shutdown`, then deletes the kernel so the GPU session is surely gone.
- The Kaggle server also stops itself when idle (auto-off minutes + 5) or after the max session hours, even if the laptop is off.

## Files
- `data/`: settings, jobs, library, logs (`server.log`). `keys/`: Kaggle token.
- `demos/`: template demo videos. `web/`: the UI. `.venv/`: Python for the app.
- `tools/`: test helpers (screenshots, probes).

## Speed (measured on 2× T4)
- Standard 720p, 5 s: about 23 min. 3 s: about 10 min. Two videos run at once.
- Turbo (FastWan LoRA, 6 steps, no CFG): a few minutes.
- Upscale to 1080p (Real-ESRGAN x2), Smooth (RIFE 2×).
