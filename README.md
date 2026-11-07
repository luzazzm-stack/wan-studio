# Wan Studio

Make AI videos with **Wan 2.2 (TI2V-5B)** running on **your own free Kaggle GPUs** (2× T4). Windows app.

## Download

| | |
|---|---|
| **Windows** (10 / 11, 64-bit) | [**WanStudio-Setup.exe**](https://github.com/luzazzm-stack/wan-studio/releases/latest/download/WanStudio-Setup.exe) (installer, recommended) |
| Windows, no install | [WanStudio-Windows.zip](https://github.com/luzazzm-stack/wan-studio/releases/latest/download/WanStudio-Windows.zip) (unzip and run **WanStudio.exe**) |

All versions: [github.com/luzazzm-stack/wan-studio/releases/latest](https://github.com/luzazzm-stack/wan-studio/releases/latest)

**Setup in 3 steps**
1. Make a free [Kaggle account](https://www.kaggle.com/account/login?phase=startRegisterTab) and **verify your phone number**
   at [kaggle.com/settings](https://www.kaggle.com/settings). Kaggle only gives GPUs to phone-verified accounts.
2. On [kaggle.com/settings](https://www.kaggle.com/settings), in the **API** section, press **Create New Token** and copy it.
3. Install and open Wan Studio, then sign in with your Kaggle username and that token. Flip the power switch: your
   server is ready in about 5 minutes.

- If Windows says "Windows protected your PC", press **More info → Run anyway** (the app is not signed by a company).
- No administrator rights needed. The app installs to `%LOCALAPPDATA%\Programs\Wan Studio`. Your sign-in, settings and
  API keys are kept in `%LOCALAPPDATA%\Wan Studio`, your videos in `Videos\Wan Studio`.
- **Animate** and **Enhance** also need the free FFmpeg: open PowerShell, run `winget install Gyan.FFmpeg`, then reopen Wan Studio.
- Optional: free API keys (Gemini, NVIDIA) in **Settings → API keys** turn on **Improve my prompt**, **Make a picture first**
  and **Suggest motion**. They stay on your computer.

Everything runs in your own Kaggle account with your free GPU hours (about 30 h a week). Your token stays on your
computer and is used only to start and stop your own server.

**Licence:** the Wan 2.2 model is released by the Wan team under the Apache 2.0 licence.

## Start
Open **Wan Studio** from the Start menu or the desktop. The first time, sign in to Kaggle (see above). Flip the switch at
the top to turn the Kaggle server on (about 4–5 minutes).

Phone: same Wi-Fi, open the address shown in **Settings → Open on your phone** and enter the PIN.

## How it works
- `server.py`: the local app (port 8765). Holds your Kaggle sign-in, runs the queue, saves videos to `Videos\Wan Studio`.
- `kaggle_ctl.py`: everything that talks to Kaggle (sign-in check, start, stop, status, GPU hours).
- `kaggle/wan_server.py`: pushed to Kaggle as the private kernel `<your username>/wan-studio-server` each time you turn on.
  It runs two ComfyUI copies (one per T4) plus a small CPU LLM for "Improve my prompt", behind a key-protected gateway and a
  Cloudflare quick tunnel. The tunnel address is announced on a private ntfy.sh topic.
- Turning off calls the server's `/shutdown`, then deletes the kernel so the GPU session is surely gone.
- The Kaggle server also stops itself when idle (auto-off minutes + 5) or after the max session hours, even if the laptop is off.

## Build it yourself
- `build_client.sh` (Git Bash): builds the Windows app with PyInstaller, the portable zip and the installer
  (`installer/WanStudio.iss`, Inno Setup 6) into `build/`. Needs Python 3.12 with `requirements.txt`; set `PY=` to it.
- `tests/test_signin.py`: checks sign-in, power gating and where data is kept, without starting any Kaggle GPU.
  `python -B tests/test_signin.py <scratch dir>` (source) or add `--exe build\dist_client\WanStudio\WanStudio.exe` (built app).
- `tools/`: developer helpers (screenshots, probes, old patch scripts).

## Speed (measured on 2× T4)
- Standard 720p, 5 s: about 23 min. 3 s: about 10 min. Two videos run at once.
- Turbo (FastWan LoRA, 6 steps, no CFG): a few minutes.
- Quality (FastWan LoRA, 10 steps, no CFG): about 10-12 min for a 5 s 720p clip on a T4; 1080p upscale adds about 17 min.
- Upscale to 1080p (Real-ESRGAN x2), Smooth (RIFE 2×).
