"""Wan Studio: local app that drives Wan 2.2 running on Kaggle (2x T4).

Serves the web UI on port 8765 (laptop + phone on the same Wi-Fi), holds the Kaggle key,
turns the Kaggle server on/off, queues video jobs across both GPUs, downloads finished videos.
"""
import asyncio, json, os, random, re, secrets, socket, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor

HERE = os.environ.get("WAN_STUDIO_HOME") or os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WEB = os.path.join(HERE, "web")
DEMOS = os.path.join(HERE, "demos")
UPLOADS = os.path.join(DATA, "uploads")
THUMBS = os.path.join(DATA, "thumbs")
ENHANCE = os.path.join(DATA, "enhance")
for d in (DATA, DEMOS, UPLOADS, THUMBS, ENHANCE):
    os.makedirs(d, exist_ok=True)

if sys.executable.lower().endswith("pythonw.exe") or not sys.stdout:
    sys.stdout = sys.stderr = open(os.path.join(DATA, "server.log"), "a", buffering=1, encoding="utf-8")

import aiohttp  # noqa: E402
from aiohttp import web  # noqa: E402
import kaggle_ctl  # noqa: E402

PORT = 8765
POOL = ThreadPoolExecutor(4)
SIZES = {"16:9": (1280, 704), "9:16": (704, 1280), "1:1": (960, 960)}
# FastWan distillation LoRA for Wan 2.2 5B: few steps, no CFG.
TURBO = {"lora": "Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors", "steps": 6, "strength": 1.0, "sampler": "euler"}
QUALITY_STEPS = {"turbo": TURBO["steps"], "standard": 20, "high": 30}
UPSCALED = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ persistence
def load(name, default):
    p = os.path.join(DATA, name)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(name, obj):
    p = os.path.join(DATA, name)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


DEFAULT_SETTINGS = {
    "idle_min": 20, "max_hours": 6, "steps": 20, "cfg": 5.0, "aspect": "16:9", "seconds": 5,
    "pin": f"{random.randint(0, 9999):04d}", "theme": "dark",
    "output_dir": os.path.join(os.path.expanduser("~"), "Videos", "Wan Studio"),
}
settings = {**DEFAULT_SETTINGS, **load("settings.json", {})}
save("settings.json", settings)
os.makedirs(settings["output_dir"], exist_ok=True)

state = load("state.json", {})
state.setdefault("topic", "wanstudio-" + secrets.token_hex(8))
state.setdefault("power", "off")  # off | starting | ready | stopping | error
save("state.json", state)

jobs = load("jobs.json", [])
library = load("library.json", [])
stats = load("stats.json", {"rate": None, "n": 0})  # seconds per (frame*step), measured

live = {"stage": "", "pct": 0, "detail": "", "error": None, "gpus": [{}, {}], "llm": False,
        "uptime": 0, "idle_s": 0, "timings": {}, "health_fail": 0}
quota_cache = {"t": 0, "v": None}
last_user = time.time()


def idle_since():
    # Idle time counts from the latest of: user action, server ready, last job finishing.
    return max(last_user, state.get("ready_at", 0), live.get("last_busy", 0))


def save_jobs():
    save("jobs.json", jobs[-300:])


def save_state():
    save("state.json", state)


def job_by_id(jid):
    return next((j for j in jobs if j["id"] == jid), None)


def lib_by_id(lid):
    return next((x for x in library if x["id"] == lid), None)


# ------------------------------------------------------------------ poster images
# A still frame per video, so pages show pictures without loading (and decoding) dozens of videos.
import shutil, subprocess  # noqa: E402
FFMPEG = shutil.which("ffmpeg") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links", "ffmpeg.exe")


def make_thumb(src, dst):
    if os.path.exists(dst) or not os.path.exists(src) or not os.path.exists(FFMPEG):
        return
    try:
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", "0.5", "-i", src, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", dst],
                       timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        log("thumb failed", os.path.basename(src), e)


def make_all_thumbs():
    for f in os.listdir(DEMOS):
        if f.endswith(".mp4"):
            make_thumb(os.path.join(DEMOS, f), os.path.join(DEMOS, f[:-4] + ".jpg"))
    for x in library:
        make_thumb(os.path.join(settings["output_dir"], x["file"]), os.path.join(THUMBS, x["id"] + ".jpg"))


# ------------------------------------------------------------------ workflows
def wf_generate(p, prefix, image_name=None):
    w, h = SIZES[p["aspect"]]
    frames = int(p["seconds"]) * 24 + 1
    turbo = p.get("quality") == "turbo"
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["14", 0] if turbo else ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": p["prompt"]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": p.get("negative", "")}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": w, "height": h, "length": frames, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
                                                    "seed": int(p["seed"]), "steps": int(p["steps"]), "cfg": float(p["cfg"]),
                                                    "sampler_name": TURBO["sampler"] if turbo else "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": 24.0}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }
    if turbo:
        wf["14"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": TURBO["lora"], "strength_model": TURBO["strength"]}}
        wf["8"]["inputs"].update(steps=TURBO["steps"], cfg=1.0)
    if image_name:
        wf["12"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
        wf["13"] = {"class_type": "ImageScale", "inputs": {"image": ["12", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}}
        wf["7"]["inputs"]["start_image"] = ["13", 0]
    return wf


ANIM_SIZES = {"9:16": (480, 832), "16:9": (832, 480), "1:1": (640, 640)}
ANIM_FPS = 16
ANIM_STEPS = 6


def anim_frames(seconds):
    return int(seconds) * ANIM_FPS + 1           # 4k+1 frames, as Wan needs (3 s = 49, 5 s = 81)


def wf_animate(p, image_name, video_name, prefix):
    w, h = ANIM_SIZES[p["aspect"]]
    n = anim_frames(p["seconds"])
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "Wan2.2-Animate-14B-Q4_K_M.gguf"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "strength_model": 1.0,
                                                              "lora_name": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"}},
        "3": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 8.0}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": p["prompt"]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 0], "text": p.get("negative", "")}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "8": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "9": {"class_type": "ImageScale", "inputs": {"image": ["8", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}},
        "10": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
        "11": {"class_type": "GetVideoComponents", "inputs": {"video": ["10", 0]}},
        "12": {"class_type": "OnnxDetectionModelLoader", "inputs": {"vitpose_model": "vitpose-l-wholebody.onnx", "yolo_model": "yolov10m.onnx",
                                                                    "onnx_device": "CUDAExecutionProvider"}},
        "13": {"class_type": "PoseAndFaceDetection", "inputs": {"model": ["12", 0], "images": ["11", 0], "width": w, "height": h,
                                                                "retarget_image": ["9", 0], "face_padding": 0}},
        "14": {"class_type": "DrawViTPose", "inputs": {"pose_data": ["13", 0], "width": w, "height": h, "retarget_padding": 16,
                                                       "body_stick_width": -1, "hand_stick_width": -1, "draw_head": True}},
        "15": {"class_type": "WanAnimateToVideo", "inputs": {"positive": ["5", 0], "negative": ["6", 0], "vae": ["7", 0], "width": w, "height": h,
                                                             "length": n, "batch_size": 1, "reference_image": ["9", 0], "face_video": ["13", 1],
                                                             "pose_video": ["14", 0], "continue_motion_max_frames": 5, "video_frame_offset": 0}},
        "16": {"class_type": "KSampler", "inputs": {"model": ["3", 0], "positive": ["15", 0], "negative": ["15", 1], "latent_image": ["15", 2],
                                                    "seed": int(p["seed"]), "steps": ANIM_STEPS, "cfg": 1.0, "sampler_name": "euler",
                                                    "scheduler": "simple", "denoise": 1.0}},
        "17": {"class_type": "TrimVideoLatent", "inputs": {"samples": ["16", 0], "trim_amount": ["15", 3]}},
        "18": {"class_type": "VAEDecode", "inputs": {"samples": ["17", 0], "vae": ["7", 0]}},
        "19": {"class_type": "CreateVideo", "inputs": {"images": ["18", 0], "fps": float(ANIM_FPS), "audio": ["11", 1]}},
        "20": {"class_type": "SaveVideo", "inputs": {"video": ["19", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }


def prep_motion_video(src, dst, aspect, seconds):
    """Make the driving video match what Animate expects: 16 fps, exact size (cropped to fill), exact length, AAC audio."""
    w, h = ANIM_SIZES[aspect]
    n = anim_frames(seconds)
    has_audio = bool(subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", src],
                                    capture_output=True, text=True, creationflags=NOWIN).stdout.strip())
    audio_in = [] if has_audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]   # silent track so the workflow always has audio
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, *audio_in, "-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                    "-vf", f"fps={ANIM_FPS},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
                    "-frames:v", str(n), "-t", f"{n / ANIM_FPS:.3f}", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", dst], check=True, timeout=300, creationflags=NOWIN)


def prep_ref_image(src, dst, aspect):
    """Fit the whole character inside the frame (no cropping) on a blurred copy of the photo, so full-body stays full-body."""
    w, h = ANIM_SIZES[aspect]
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-filter_complex",
                    f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:3[bg];"
                    f"[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2",
                    "-frames:v", "1", dst], check=True, timeout=120, creationflags=NOWIN)


def wf_upscale(video_name, aspect, fps, prefix):
    w, h = UPSCALED.get(aspect, (1920, 1080))
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x2plus.pth"}},
        "4": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["3", 0], "image": ["2", 0]}},
        "5": {"class_type": "ImageScale", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "center"}},
        "6": {"class_type": "CreateVideo", "inputs": {"images": ["5", 0], "fps": float(fps)}},
        "7": {"class_type": "SaveVideo", "inputs": {"video": ["6", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }


def wf_enhance(video_name, w, h, fps, upscale, smooth, prefix):
    wf = {"1": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
          "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}}}
    frames = ["2", 0]
    if upscale:
        wf["3"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "RealESRGAN_x2plus.pth"}}
        wf["4"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["3", 0], "image": frames}}
        wf["5"] = {"class_type": "ImageScale", "inputs": {"image": ["4", 0], "upscale_method": "lanczos", "width": w, "height": h, "crop": "disabled"}}
        frames = ["5", 0]
    if smooth:
        wf["6"] = {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": frames, "clear_cache_after_n_frames": 10,
                                                        "multiplier": 2, "fast_mode": True, "ensemble": True, "scale_factor": 1.0,
                                                        "dtype": "float16", "torch_compile": False, "batch_size": 2}}
        frames = ["6", 0]
    wf["7"] = {"class_type": "CreateVideo", "inputs": {"images": frames, "fps": float(fps) * (2 if smooth else 1)}}
    wf["8"] = {"class_type": "SaveVideo", "inputs": {"video": ["7", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}}
    return wf


def wf_interp(video_name, fps, prefix):
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": video_name}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "3": {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": ["2", 0], "clear_cache_after_n_frames": 10,
                                                   "multiplier": 2, "fast_mode": True, "ensemble": True, "scale_factor": 1.0,
                                                   "dtype": "float16", "torch_compile": False, "batch_size": 4}},
        "4": {"class_type": "CreateVideo", "inputs": {"images": ["3", 0], "fps": float(fps) * 2}},
        "5": {"class_type": "SaveVideo", "inputs": {"video": ["4", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }


# ------------------------------------------------------------------ remote (Kaggle gateway) helpers
http: aiohttp.ClientSession = None


def gw(path):
    return state["url"].rstrip("/") + path


def gw_headers():
    return {"X-Key": state.get("key", "")}


async def gw_json(method, path, timeout=30, **kw):
    async with http.request(method, gw(path), headers=gw_headers(), timeout=aiohttp.ClientTimeout(total=timeout), **kw) as r:
        txt = await r.text()
        if r.status >= 400:
            raise RuntimeError(f"{r.status}: {txt[:500]}")
        return json.loads(txt) if txt else None


async def blocking(fn, *a):
    return await asyncio.get_running_loop().run_in_executor(POOL, fn, *a)


# ------------------------------------------------------------------ power
async def power_on():
    if state["power"] in ("starting", "ready"):
        return
    if state["power"] == "error" and state.get("url") and state.get("key"):
        try:
            await gw_json("GET", "/health", timeout=20)
            state.update(power="ready", error=None)
            live.update(health_fail=0)
            save_state()
            log("power on: reconnected to the running server")
            return
        except Exception:
            pass
    mark_session_ended("The server was restarted")
    state.update(power="starting", key=kaggle_ctl.new_key(), url=None, pushed_at=time.time(), error=None, started_by_app=time.time())
    live.update(stage="queued", pct=1, detail="Sending the server to Kaggle", error=None, health_fail=0, gpus=[{}, {}], llm=False)
    save_state()
    try:
        st = await blocking(kaggle_ctl.status)
        if st in ("running", "queued"):
            await blocking(kaggle_ctl.delete)  # an old session with an unknown key: replace it
            await asyncio.sleep(5)
        await blocking(kaggle_ctl.push, state["key"], state["topic"], settings["idle_min"] + 5, settings["max_hours"])
        live.update(stage="queued", pct=2, detail="Waiting for Kaggle to give us 2 GPUs")
        quota_cache["t"] = 0
    except Exception as e:
        state.update(power="error", error=f"Could not start on Kaggle: {e}")
        save_state()
        log("power_on failed", e)


async def power_off(reason="Turned off"):
    if state["power"] == "off":
        return
    prev = state["power"]
    state["power"] = "stopping"
    live.update(stage="stopping", detail=reason)
    save_state()
    if state.get("url") and prev in ("ready", "starting"):
        try:
            await gw_json("POST", "/shutdown", timeout=15)
        except Exception:
            pass
    await asyncio.sleep(3)
    try:
        await blocking(kaggle_ctl.delete)  # guarantees the GPU session is gone
    except Exception as e:
        log("delete failed", e)
    mark_session_ended("Server was turned off before this finished")
    state.update(power="off", url=None, last_stop_reason=reason)
    live.update(stage="", pct=0, detail="", gpus=[{}, {}], llm=False)
    quota_cache["t"] = 0
    save_state()
    log("power off:", reason)


async def laptop_online():
    try:
        await asyncio.get_running_loop().getaddrinfo("www.kaggle.com", 443)
        return True
    except Exception:
        return False


def mark_session_ended(msg):
    for j in jobs:
        if j["status"] in ("uploading", "running", "downloading"):
            j.update(status="queued", gpu=None, prompt_id=None, progress=0, note=msg + " - it will run again next time.")
    save_jobs()


async def poll_ntfy():
    since = int(state.get("pushed_at", time.time()) - 5)
    async with http.get(f"https://ntfy.sh/{state['topic']}/json?poll=1&since={since}", timeout=aiohttp.ClientTimeout(total=20)) as r:
        txt = await r.text()
    msgs = []
    for line in txt.splitlines():
        try:
            m = json.loads(json.loads(line).get("message") or "{}")
            if m.get("t", 0) >= since:
                msgs.append(m)
        except Exception:
            pass
    return msgs


async def power_loop():
    while True:
        try:
            await power_tick()
        except Exception as e:
            log("power_tick error", repr(e))
        await asyncio.sleep(4)


async def power_tick():
    p = state["power"]
    if p not in ("starting", "ready"):
        return
    msgs = []
    if not state.get("url") or live["health_fail"] >= 3:
        try:
            msgs = await poll_ntfy()
        except Exception:
            pass
        for m in msgs:
            if m.get("type") == "url" and not state.get("url"):
                state["url"] = m["url"]
                save_state()
            if m.get("type") == "error":
                state.update(power="error", error="The Kaggle server failed to start: " + m.get("error", ""))
                save_state()
                await blocking(kaggle_ctl.delete)
                return
            if m.get("type") == "stopped":
                mark_session_ended("The server stopped (" + m.get("reason", "") + ")")
                state.update(power="off", url=None, last_stop_reason="Kaggle server stopped: " + m.get("reason", ""))
                save_state()
                return
    if not state.get("url"):
        waited = time.time() - state.get("pushed_at", time.time())
        live.update(stage="queued", pct=2, detail=f"Waiting for Kaggle to give us 2 GPUs ({int(waited)} s)")
        if waited > 900:
            st = await blocking(kaggle_ctl.status)
            if st not in ("running", "queued"):
                state.update(power="error", error=f"Kaggle session did not start (status: {st}).")
                save_state()
        return
    try:
        h = await gw_json("GET", "/health", timeout=20)
        live.update(stage=h["stage"], pct=h["pct"], detail=h["detail"], error=h["error"], gpus=h["gpus"], llm=h["llm"], llm_gpu=h.get("llm_gpu", False),
                    uptime=h["uptime"], idle_s=h["idle_s"], timings=h.get("timings", {}), health_fail=0)
        if h["error"]:
            state.update(power="error", error="The Kaggle server failed to start: " + h["error"][:600])
            save_state()
            await blocking(kaggle_ctl.delete)
            return
        if h["ready"] and p == "starting":
            state["power"] = "ready"
            state["ready_at"] = time.time()
            save_state()
            log("server ready", h.get("timings"))
    except Exception as e:
        if not await laptop_online():
            live.update(detail="This laptop is offline. The server keeps working; waiting for the internet to come back.")
            return
        live["health_fail"] += 1
        if live["health_fail"] in (3, 10) or live["health_fail"] % 15 == 0:
            st = await blocking(kaggle_ctl.status)
            if st not in ("running", "queued"):
                mark_session_ended("The Kaggle session ended")
                state.update(power="off", url=None, last_stop_reason=f"Kaggle session ended ({st})")
                save_state()
                return
        if live["health_fail"] > 40:
            state.update(power="error", error=f"Lost contact with the Kaggle server: {e}")
            save_state()
        return
    # auto-off: nothing running or waiting, and nobody used the app for idle_min
    if state["power"] == "ready":
        active = any(j["status"] in ("queued", "uploading", "running", "downloading") for j in jobs)
        if active:
            live["last_busy"] = time.time()
        if not active and time.time() - idle_since() > settings["idle_min"] * 60:
            await power_off(f"Auto-off after {settings['idle_min']} min without use")


# ------------------------------------------------------------------ job scheduler
def eff_steps(p):
    # CFG 1 (turbo) skips the negative pass, so each step costs about half.
    return int(p["steps"]) * (0.9 if p.get("quality") == "turbo" else 1)


def overhead(frames):
    # Model loading + VAE decode + saving, measured on T4 (~170 s for 121 frames).
    return 30 + 1.2 * frames


def estimate_seconds(j):
    k = j["kind"]
    p = j["params"]
    if k == "enhance":
        return int(p.get("frames", 84) * ((3.1 * p.get("mp", 0.9) if p.get("upscale") else 0) + (0.35 if p.get("smooth") else 0)) + 40)
    if k in ("upscale", "interp"):
        return 340 if k == "upscale" else 60
    if k == "animate":
        return 240 + 15.6 * anim_frames(p["seconds"])       # measured on T4: 5 s (81 frames) took 1511 s
    rate = stats.get("rate") or 0.55
    frames = int(p["seconds"]) * 24 + 1
    return int(rate * frames * eff_steps(p) + overhead(frames))


async def scheduler_loop():
    while True:
        try:
            if state["power"] == "ready":
                await schedule_tick()
        except Exception as e:
            log("scheduler error", repr(e))
        await asyncio.sleep(3)


async def schedule_tick():
    busy = {j["gpu"] for j in jobs if j["status"] in ("uploading", "running", "downloading") and j.get("gpu") is not None}
    for j in [j for j in jobs if j["status"] == "running"]:
        try:
            await check_running(j)  # one GPU's trouble must not block the other GPU's jobs
        except Exception as e:
            j["check_fails"] = j.get("check_fails", 0) + 1
            if j["check_fails"] in (1, 20) or j["check_fails"] % 100 == 0:
                log("check failed", j["id"], "gpu", j["gpu"], repr(e)[:200])
            if j["check_fails"] > 200:  # ~10 min without an answer from that GPU
                lost_job(j, "The GPU stopped responding")
    for g in (0, 1):
        if g in busy:
            continue
        nxt = next((j for j in jobs if j["status"] == "queued" and j.get("want_gpu") in (None, g)), None)
        if not nxt:
            continue
        busy.add(g)
        nxt.update(status="uploading", gpu=g)  # claim it now so the other GPU can't take the same job
        asyncio.create_task(submit(nxt, g))


async def upload_to_gpu(g, path, as_name):
    data = aiohttp.FormData()
    data.add_field("image", open(path, "rb"), filename=as_name)
    data.add_field("overwrite", "true")
    r = await gw_json("POST", f"/g{g}/upload/image", timeout=300, data=data)
    return r["name"]


async def submit(j, g):
    j.update(status="uploading", gpu=g, progress=0, note=None, error=None)
    save_jobs()
    try:
        p = j["params"]
        prefix = f"ws_{j['id']}"
        if j["kind"] in ("t2v", "i2v"):
            img = None
            if j["kind"] == "i2v":
                img = await upload_to_gpu(g, os.path.join(UPLOADS, p["image"]), p["image"])
            wf = wf_generate(p, prefix, img)
        elif j["kind"] == "animate":
            fitted = os.path.join(UPLOADS, f"animref_{j['id']}.png")
            await blocking(prep_ref_image, os.path.join(UPLOADS, p["image"]), fitted, p["aspect"])
            img = await upload_to_gpu(g, fitted, f"animref_{j['id']}.png")
            prepped = os.path.join(UPLOADS, f"anim_{j['id']}.mp4")
            await blocking(prep_motion_video, os.path.join(UPLOADS, p["video"]), prepped, p["aspect"], p["seconds"])
            vid = await upload_to_gpu(g, prepped, f"anim_{j['id']}.mp4")
            wf = wf_animate(p, img, vid, prefix)
        elif j["kind"] == "enhance":
            name = await upload_to_gpu(g, p["file"], f"enh_{j['id']}.mp4")
            wf = wf_enhance(name, p["w"], p["h"], p["fps"], p["upscale"], p["smooth"], prefix)
        else:
            src = lib_by_id(p["source"])
            if not src:
                raise RuntimeError("The source video is no longer in your library")
            name = await upload_to_gpu(g, os.path.join(settings["output_dir"], src["file"]), f"src_{j['id']}.mp4")
            wf = wf_upscale(name, src["aspect"], src.get("fps", 24), prefix) if j["kind"] == "upscale" else wf_interp(name, src.get("fps", 24), prefix)
        r = await gw_json("POST", f"/g{g}/prompt", json={"prompt": wf, "client_id": "wanstudio"})
        if r.get("node_errors"):
            raise RuntimeError(json.dumps(r["node_errors"])[:800])
        j.update(status="running", prompt_id=r["prompt_id"], started=time.time(), check_fails=0,
                 restarts_at_submit=live["gpus"][g].get("restarts", 0))
        save_jobs()
        log("job", j["id"], j["kind"], "-> gpu", g)
    except Exception as e:
        j.update(status="failed", error=str(e)[:800], finished=time.time())
        save_jobs()
        log("submit failed", j["id"], e)


def lost_job(j, why):
    # The GPU crashed or hung: run the job again once, then give up.
    if j.get("retries", 0) < 1:
        j.update(status="queued", gpu=None, prompt_id=None, progress=0, phase=None, check_fails=0,
                 retries=j.get("retries", 0) + 1, note=f"{why}, so it is being made again.")
    else:
        j.update(status="failed", error=f"{why} twice. Try a shorter video, or turn the server off and on.", finished=time.time())
    save_jobs()
    log("job lost", j["id"], why)


async def check_running(j):
    g = j["gpu"]
    gp = live["gpus"][g] if g is not None and g < len(live["gpus"]) else {}
    if gp.get("restarts", 0) > j.get("restarts_at_submit", 0):
        return lost_job(j, "The GPU crashed while making this video")
    if j.get("started") and time.time() - j["started"] > 3 * estimate_seconds(j) + 600:
        try:
            await gw_json("POST", f"/g{g}/interrupt", json={"prompt_id": j["prompt_id"]})
        except Exception:
            pass
        return lost_job(j, "It was taking far longer than expected")
    if gp.get("prompt_id") == j["prompt_id"] and gp.get("max"):
        j["progress"] = round(gp["value"] / gp["max"], 3)
        j["phase"] = "sampling" if gp["value"] < gp["max"] else "finishing"
    elif j.get("progress", 0) >= 0.99:
        j["phase"] = "finishing"
    h = await gw_json("GET", f"/g{g}/history/{j['prompt_id']}")
    j["check_fails"] = 0
    if j["prompt_id"] not in (h or {}):
        return
    item = h[j["prompt_id"]]
    st = item.get("status", {})
    if st.get("status_str") == "error" or not st.get("completed", True):
        if j.get("cancel"):
            j.update(status="cancelled", finished=time.time())
        else:
            msg = "; ".join(str(m[1].get("exception_message", "")) for m in st.get("messages", []) if m[0] == "execution_error")
            j.update(status="failed", error=(msg or "Generation failed")[:800], finished=time.time())
        save_jobs()
        return
    out = None
    for node_out in item.get("outputs", {}).values():
        for v in node_out.values():
            if isinstance(v, list):
                for f in v:
                    if isinstance(f, dict) and f.get("filename", "").lower().endswith((".mp4", ".webm", ".mov")):
                        out = f
    if not out:
        j.update(status="failed", error="Finished but no video was produced", finished=time.time())
        save_jobs()
        return
    j.update(status="downloading", progress=1)
    save_jobs()
    asyncio.create_task(download_result(j, out))


def slug(text, n=5):
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())[:n]
    return "-".join(words) or "video"


async def download_result(j, f):
    g = j["gpu"]
    try:
        q = {"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")}
        async with http.get(gw(f"/g{g}/view"), params=q, headers=gw_headers(), timeout=aiohttp.ClientTimeout(total=900)) as r:
            if r.status != 200:
                raise RuntimeError(f"download {r.status}")
            data = await r.read()
        p = j["params"]
        took = time.time() - j["started"]
        if j["kind"] == "enhance":
            gdir = os.path.join(ENHANCE, p["group"])
            with open(os.path.join(gdir, f"out_{p['index']:03d}.mp4"), "wb") as fh:
                fh.write(data)
            j.update(status="done", finished=time.time(), took=round(took))
            save_jobs()
            await finish_enhance(p["group"])
            log("job done", j["id"], f"{took:.0f}s")
            return
        if p.get("demo"):
            dpath = os.path.join(DEMOS, p["demo"] + ".mp4")
            with open(dpath, "wb") as fh:
                fh.write(data)
            if os.path.exists(dpath[:-4] + ".jpg"):
                os.remove(dpath[:-4] + ".jpg")
            await blocking(make_thumb, dpath, dpath[:-4] + ".jpg")
            j.update(status="done", finished=time.time(), took=round(took))
        else:
            src = lib_by_id(p.get("source")) if p.get("source") else None
            base = src or p
            tag = {"upscale": "1080p", "interp": "smooth", "animate": "animate"}.get(j["kind"], f"s{p.get('seed')}")
            name = f"{time.strftime('%Y-%m-%d_%H%M')}_{slug(base.get('prompt', 'video'))}_{tag}.mp4"
            with open(os.path.join(settings["output_dir"], name), "wb") as fh:
                fh.write(data)
            item = {"id": uuid.uuid4().hex[:10], "file": name, "kind": j["kind"], "created": time.time(), "favorite": False,
                    "took": round(took), "size": len(data)}
            if src:
                item.update({k: src.get(k) for k in ("prompt", "negative", "aspect", "seconds", "steps", "seed", "cfg", "template", "image", "quality")})
                item["parent"] = src["id"]
                item["fps"] = src.get("fps", 24) * (2 if j["kind"] == "interp" else 1)
                item["res"] = "1080p" if j["kind"] == "upscale" else src.get("res", "720p")
                if j["kind"] == "interp" and src.get("res") == "1080p":
                    item["res"] = "1080p"
            else:
                item.update({k: p.get(k) for k in ("prompt", "negative", "aspect", "seconds", "steps", "seed", "cfg", "template", "image", "quality")})
                item.update(fps=24, res="720p")
                if j["kind"] == "animate":
                    item.update(fps=ANIM_FPS, res="480p", steps=ANIM_STEPS, motion=p.get("video"))
            library.append(item)
            save("library.json", library)
            await blocking(make_thumb, os.path.join(settings["output_dir"], name), os.path.join(THUMBS, item["id"] + ".jpg"))
            # "1080p" / "1080p + smooth" chosen on Create: chain the follow-up step automatically.
            if j["kind"] in ("t2v", "i2v") and p.get("upscale"):
                new_job("upscale", {"source": item["id"], "prompt": p.get("prompt", ""), "then_smooth": bool(p.get("smooth"))})
            elif j["kind"] == "upscale" and p.get("then_smooth"):
                new_job("interp", {"source": item["id"], "prompt": p.get("prompt", "")})
            j.update(status="done", finished=time.time(), took=round(took), result=item["id"])
        if j["kind"] in ("t2v", "i2v"):
            frames = int(p["seconds"]) * 24 + 1
            r_ = max(0.05, (took - overhead(frames)) / (frames * eff_steps(p)))
            n = min(stats.get("n", 0), 9)
            stats["rate"] = r_ if not stats.get("rate") else (stats["rate"] * n + r_) / (n + 1)
            stats["n"] = n + 1
            save("stats.json", stats)
        log("job done", j["id"], f"{took:.0f}s")
    except Exception as e:
        j.update(status="failed", error=f"Could not download the result: {e}", finished=time.time())
        log("download failed", j["id"], e)
    save_jobs()


# ------------------------------------------------------------------ HTTP API
def is_local(req):
    return req.remote in ("127.0.0.1", "::1")


@web.middleware
async def auth_mw(req, handler):
    global last_user
    if not is_local(req) and req.path not in ("/login", "/style.css", "/favicon.svg"):
        if req.cookies.get("ws_pin") != settings["pin"]:
            if req.path.startswith("/api/"):
                return web.json_response({"error": "login"}, status=401)
            raise web.HTTPFound("/login")
    if req.path.startswith("/api/") and req.path != "/api/state":
        last_user = time.time()
    return await handler(req)


LOGIN_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Wan Studio</title><link rel=stylesheet href=/style.css></head><body class=login-body><form method=post class=login-card>
<div class=logo>🎬 Wan Studio</div><p>Enter the PIN shown in Settings on your laptop.</p>{err}
<input name=pin inputmode=numeric autocomplete=off autofocus placeholder=PIN><button class="btn primary">Open</button></form></body></html>"""


async def login_get(req):
    return web.Response(text=LOGIN_HTML.format(err=""), content_type="text/html")


async def login_post(req):
    f = await req.post()
    if f.get("pin", "").strip() == settings["pin"]:
        r = web.HTTPFound("/")
        r.set_cookie("ws_pin", settings["pin"], max_age=3600 * 24 * 365)
        raise r
    return web.Response(text=LOGIN_HTML.format(err="<p class=err>Wrong PIN</p>"), content_type="text/html")


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


async def get_quota():
    if time.time() - quota_cache["t"] > 300:
        try:
            quota_cache["v"] = await blocking(kaggle_ctl.quota)
        except Exception as e:
            log("quota failed", e)
        quota_cache["t"] = time.time()
    return quota_cache["v"]


def public_job(j):
    d = {k: j.get(k) for k in ("id", "kind", "status", "gpu", "progress", "phase", "created", "started", "finished",
                               "error", "note", "took", "result", "group")}
    d["params"] = {k: v for k, v in j["params"].items()}
    if j["status"] in ("queued", "uploading", "running"):
        est = estimate_seconds(j)
        d["estimate"] = est
        if j["status"] == "running" and j.get("started"):
            d["eta"] = max(5, int(est - (time.time() - j["started"])))
    return d


async def api_state(req):
    ip = lan_ip()
    return web.json_response({
        "power": state["power"], "error": state.get("error"), "last_stop_reason": state.get("last_stop_reason"),
        "live": {**{k: live[k] for k in ("stage", "pct", "detail", "gpus", "llm", "uptime", "idle_s", "timings")}, "llm_gpu": live.get("llm_gpu", False)},
        "ready_at": state.get("ready_at"), "pushed_at": state.get("pushed_at"),
        "jobs": [public_job(j) for j in jobs[-80:]],
        "quota": await get_quota(),
        "idle_left": (max(0, int(settings["idle_min"] * 60 - (time.time() - idle_since())))
                      if state["power"] == "ready" else None),
        "settings": {k: v for k, v in settings.items() if k != "pin" or is_local(req)},
        "lan_url": f"http://{ip}:{PORT}" if ip else None, "local": is_local(req),
        "rate": stats.get("rate"),
    })


async def api_power(req):
    d = await req.json()
    if d.get("on"):
        asyncio.create_task(power_on())
    else:
        asyncio.create_task(power_off("Turned off from the app"))
    return web.json_response({"ok": True})


def new_job(kind, params, group=None, want_gpu=None):
    if want_gpu is None:
        want_gpu = {"t2v": 0, "i2v": 0, "animate": 1}.get(kind)
    j = {"id": uuid.uuid4().hex[:10], "kind": kind, "status": "queued", "params": params, "created": time.time(),
         "gpu": None, "progress": 0, "group": group, "want_gpu": want_gpu}
    jobs.append(j)
    return j


async def api_generate(req):
    d = await req.json()
    prompt = (d.get("prompt") or "").strip()
    if not prompt:
        return web.json_response({"error": "Write a prompt first"}, status=400)
    kind = "i2v" if d.get("image") else "t2v"
    base = {"prompt": prompt, "negative": d.get("negative", ""), "aspect": d.get("aspect", "16:9") if d.get("aspect") in SIZES else "16:9",
            "seconds": max(2, min(5, int(d.get("seconds", 5)))), "quality": d.get("quality") if d.get("quality") in QUALITY_STEPS else "standard",
            "cfg": float(d.get("cfg", settings["cfg"])), "template": d.get("template"), "image": d.get("image"), "demo": d.get("demo"),
            "upscale": bool(d.get("upscale")), "smooth": bool(d.get("smooth"))}
    base["steps"] = QUALITY_STEPS[base["quality"]]
    if base["quality"] == "turbo":
        base["cfg"] = 1.0
    count = 2 if d.get("two") else 1
    seed = int(d.get("seed", -1))
    group = uuid.uuid4().hex[:6] if count > 1 else None
    made = []
    for i in range(count):
        s = seed + i if seed >= 0 else random.randint(0, 2 ** 31)
        made.append(new_job(kind, {**base, "seed": s}, group))
    save_jobs()
    return web.json_response({"jobs": [m["id"] for m in made]})


async def api_animate(req):
    d = await req.json()
    img, vid = os.path.basename(d.get("image") or ""), os.path.basename(d.get("video") or "")
    if not img or not os.path.exists(os.path.join(UPLOADS, img)):
        return web.json_response({"error": "Choose a character photo first"}, status=400)
    if not vid or not os.path.exists(os.path.join(UPLOADS, vid)):
        return web.json_response({"error": "Choose a motion video first"}, status=400)
    aspect = d.get("aspect") if d.get("aspect") in ANIM_SIZES else "9:16"
    seed = int(d.get("seed", -1))
    try:
        dur = (await blocking(probe_video, os.path.join(UPLOADS, vid)))["duration"]
    except Exception:
        dur = 5
    secs = 5 if int(d.get("seconds", 5)) >= 5 and dur >= 4.9 else 3     # never ask for more motion than the video has
    p = {"prompt": (d.get("prompt") or "").strip() or "the character moves naturally, smooth motion, detailed face, high quality",
         "negative": d.get("negative", ""), "aspect": aspect, "seconds": secs,
         "image": img, "video": vid, "seed": seed if seed >= 0 else random.randint(0, 2 ** 31)}
    j = new_job("animate", p)
    save_jobs()
    return web.json_response({"jobs": [j["id"]]})


async def api_process(req):
    d = await req.json()
    src = lib_by_id(d.get("source"))
    if not src or d.get("kind") not in ("upscale", "interp"):
        return web.json_response({"error": "Unknown video"}, status=400)
    j = new_job(d["kind"], {"source": src["id"], "prompt": src.get("prompt", "")})
    save_jobs()
    return web.json_response({"jobs": [j["id"]]})


async def api_cancel(req):
    j = job_by_id(req.match_info["id"])
    if not j:
        return web.json_response({"error": "unknown job"}, status=404)
    if j["status"] == "queued":
        j["status"] = "cancelled"
    elif j["status"] in ("running", "uploading"):
        j["cancel"] = True
        try:
            if j.get("prompt_id"):
                await gw_json("POST", f"/g{j['gpu']}/interrupt", json={"prompt_id": j["prompt_id"]})
        except Exception as e:
            log("interrupt failed", e)
    save_jobs()
    return web.json_response({"ok": True})


async def api_clear_jobs(req):
    global jobs
    jobs[:] = [j for j in jobs if j["status"] in ("queued", "uploading", "running", "downloading")]
    save_jobs()
    return web.json_response({"ok": True})


async def api_retry(req):
    j = job_by_id(req.match_info["id"])
    if not j:
        return web.json_response({"error": "unknown job"}, status=404)
    n = new_job(j["kind"], dict(j["params"]))
    save_jobs()
    return web.json_response({"jobs": [n["id"]]})


async def api_library(req):
    items = [x for x in library if os.path.exists(os.path.join(settings["output_dir"], x["file"]))]
    return web.json_response(sorted(items, key=lambda x: -x["created"]))


async def api_lib_update(req):
    x = lib_by_id(req.match_info["id"])
    if not x:
        return web.json_response({"error": "unknown"}, status=404)
    d = await req.json()
    if "favorite" in d:
        x["favorite"] = bool(d["favorite"])
    if "title" in d:
        x["title"] = str(d["title"])[:120]
    save("library.json", library)
    return web.json_response(x)


async def api_lib_delete(req):
    x = lib_by_id(req.match_info["id"])
    if x:
        try:
            os.remove(os.path.join(settings["output_dir"], x["file"]))
        except FileNotFoundError:
            pass
        library.remove(x)
        save("library.json", library)
    return web.json_response({"ok": True})


async def api_upload(req):
    reader = await req.multipart()
    part = await reader.next()
    ext = os.path.splitext(part.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return web.json_response({"error": "Use a PNG, JPG or WEBP photo"}, status=400)
    name = f"img_{uuid.uuid4().hex[:10]}{ext}"
    with open(os.path.join(UPLOADS, name), "wb") as f:
        while True:
            chunk = await part.read_chunk()
            if not chunk:
                break
            f.write(chunk)
    return web.json_response({"name": name})


# ------------------------------------------------------------------ enhance your own video
FFPROBE = shutil.which("ffprobe") or os.path.join(os.path.dirname(FFMPEG), "ffprobe.exe")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_ENHANCE_SECONDS = 60


def even(x):
    return max(2, int(round(x / 2)) * 2)


def probe_video(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                         capture_output=True, text=True, timeout=60, creationflags=NOWIN).stdout
    d = json.loads(out or "{}")
    v = next((x for x in d.get("streams", []) if x.get("codec_type") == "video"), None)
    if not v:
        raise RuntimeError("That file has no video in it")
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0
    if not fps:
        num, den = (v.get("r_frame_rate") or "24/1").split("/")
        fps = float(num) / float(den)
    w, h = int(v["width"]), int(v["height"])
    rot = str((v.get("tags") or {}).get("rotate", "0"))
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = str(abs(int(sd["rotation"])))
    if rot in ("90", "270"):
        w, h = h, w
    dur = float(v.get("duration") or d.get("format", {}).get("duration") or 0)
    return {"width": w, "height": h, "fps": fps, "duration": dur, "audio": any(x.get("codec_type") == "audio" for x in d.get("streams", []))}


ENH_SIZES = {"1080p": (1920, 1080), "2k": (2560, 1440), "4k": (3840, 2160)}
ENH_LABEL = {"1080p": "1080p", "2k": "1440p", "4k": "4K"}


def enhance_plan(info, size):
    """Working size (what is sent to the GPU) and target size (what comes back). size=None means keep the size."""
    w, h = info["width"], info["height"]
    if size:
        long_t, short_t = ENH_SIZES[size]
        t = min(long_t / max(w, h), short_t / min(w, h))      # fit inside the target box, keep the shape
        tw, th = even(w * t), even(h * t)
        k = min(1.0, (tw / 2) / w)                            # the model doubles; never enlarge before the model
        return even(w * k), even(h * k), tw, th
    k = min(1.0, 1920 / max(w, h))
    return even(w * k), even(h * k), even(w * k), even(h * k)


def enhance_targets(info):
    out = []
    for key in ("1080p", "2k", "4k"):
        long_t, short_t = ENH_SIZES[key]
        t = min(long_t / max(info["width"], info["height"]), short_t / min(info["width"], info["height"]))
        _, _, tw, th = enhance_plan(info, key)
        out.append({"key": key, "w": tw, "h": th, "ok": t > 1.05})
    return out


async def api_upload_video(req):
    reader = await req.multipart()
    part = await reader.next()
    ext = os.path.splitext(part.filename or "")[1].lower()
    if ext not in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        return web.json_response({"error": "Use an MP4, MOV or WEBM video"}, status=400)
    name = f"vid_{uuid.uuid4().hex[:10]}{ext}"
    path = os.path.join(UPLOADS, name)
    size = 0
    with open(path, "wb") as f:
        while True:
            chunk = await part.read_chunk(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > 1024 ** 3:
                f.close()
                os.remove(path)
                return web.json_response({"error": "That video is larger than 1 GB"}, status=400)
            f.write(chunk)
    try:
        info = await blocking(probe_video, path)
    except Exception as e:
        os.remove(path)
        return web.json_response({"error": str(e) or "Could not read that video"}, status=400)
    return web.json_response({**info, "name": name, "title": os.path.splitext(os.path.basename(part.filename or "video"))[0][:60],
                              "targets": enhance_targets(info), "too_long": info["duration"] > MAX_ENHANCE_SECONDS + 0.5})


def split_video(src, gdir, ww, wh, fps, seg_seconds):
    os.makedirs(gdir, exist_ok=True)
    cmd = [FFMPEG, "-v", "error", "-y", "-i", src, "-an", "-vf", f"scale={ww}:{wh}:flags=lanczos,fps={fps:.3f},format=yuv420p",
           "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-bf", "0", "-force_key_frames", f"expr:gte(t,n_forced*{seg_seconds:.3f})",
           "-f", "segment", "-segment_time", f"{seg_seconds:.3f}", "-reset_timestamps", "1", os.path.join(gdir, "in_%03d.mp4")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError("Could not prepare the video: " + r.stderr[-300:])
    return sorted(f for f in os.listdir(gdir) if f.startswith("in_") and f.endswith(".mp4"))


async def api_enhance(req):
    d = await req.json()
    name = os.path.basename(d.get("name") or "")
    src = os.path.join(UPLOADS, name)
    up, sm = bool(d.get("upscale")), bool(d.get("smooth"))
    if not name or not os.path.exists(src) or not (up or sm):
        return web.json_response({"error": "Choose a video and at least one option"}, status=400)
    info = await blocking(probe_video, src)
    if info["duration"] > MAX_ENHANCE_SECONDS + 0.5:
        return web.json_response({"error": f"Videos up to {MAX_ENHANCE_SECONDS} seconds. Trim it first."}, status=400)
    size = (d.get("size") if d.get("size") in ENH_SIZES else "1080p") if up else None
    if up and not next(t for t in enhance_targets(info) if t["key"] == size)["ok"]:
        if not sm:
            return web.json_response({"error": f"This video is already {ENH_LABEL[size]} or larger"}, status=400)
        up, size = False, None
    ww, wh, tw, th = enhance_plan(info, size)
    fps = min(info["fps"], 30.0)
    n_frames = max(12, min(84, int(84 * (1920 * 1080) / (tw * th))))   # fewer frames per piece for bigger output (RAM)
    seg = max(0.4, n_frames / fps)
    gid = uuid.uuid4().hex[:8]
    gdir = os.path.join(ENHANCE, gid)
    try:
        parts = await blocking(split_video, src, gdir, ww, wh, fps, seg)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)
    title = str(d.get("title") or os.path.splitext(name)[0])[:60]
    meta = {"src": src, "orig": name, "size": size, "title": title, "upscale": up, "smooth": sm, "w": tw, "h": th, "fps": fps * (2 if sm else 1),
            "duration": info["duration"], "audio": info["audio"], "parts": len(parts)}
    with open(os.path.join(gdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    for i, fn in enumerate(parts):
        new_job("enhance", {"group": gid, "index": i, "total": len(parts), "file": os.path.join(gdir, fn), "w": tw, "h": th, "fps": fps,
                            "upscale": up, "smooth": sm, "title": title, "frames": int(seg * fps), "mp": round(ww * wh / 1e6, 2)})
    save_jobs()
    return web.json_response({"parts": len(parts), "group": gid})


def join_video(gdir, meta, out_path):
    outs = sorted(f for f in os.listdir(gdir) if f.startswith("out_") and f.endswith(".mp4"))
    with open(os.path.join(gdir, "list.txt"), "w", encoding="utf-8") as f:
        for o in outs:
            f.write("file '" + os.path.join(gdir, o).replace("\\", "/").replace("'", "'\\''") + "'\n")
    cmd = [FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", os.path.join(gdir, "list.txt")]
    if meta.get("audio"):
        cmd += ["-i", meta["src"], "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, creationflags=NOWIN)
    if r.returncode:
        raise RuntimeError(r.stderr[-400:])


async def finish_enhance(gid):
    group = [j for j in jobs if j["kind"] == "enhance" and j["params"].get("group") == gid]
    if not group or any(j["status"] != "done" for j in group):
        return
    gdir = os.path.join(ENHANCE, gid)
    try:
        meta = json.load(open(os.path.join(gdir, "meta.json"), encoding="utf-8"))
        tag = "_".join(x for x in (ENH_LABEL.get(meta.get("size"), "1080p") if meta["upscale"] else "", "smooth" if meta["smooth"] else "") if x)
        name = f"{time.strftime('%Y-%m-%d_%H%M')}_{slug(meta['title'])}_{tag}.mp4"
        out_path = os.path.join(settings["output_dir"], name)
        await blocking(join_video, gdir, meta, out_path)
        w, h = meta["w"], meta["h"]
        aspect = "16:9" if w / h > 1.25 else "9:16" if w / h < 0.8 else "1:1"
        item = {"id": uuid.uuid4().hex[:10], "file": name, "kind": "enhance", "created": time.time(), "favorite": False,
                "took": sum(j.get("took") or 0 for j in group), "size": os.path.getsize(out_path), "prompt": meta["title"] + " (your video, enhanced)",
                "aspect": aspect, "seconds": round(meta["duration"]), "fps": round(meta["fps"]), "res": ENH_LABEL.get(meta.get("size"), "1080p") if meta["upscale"] else f"{min(w, h)}p", "original": meta.get("orig")}
        library.append(item)
        save("library.json", library)
        await blocking(make_thumb, out_path, os.path.join(THUMBS, item["id"] + ".jpg"))
        group[-1]["result"] = item["id"]
        save_jobs()
        shutil.rmtree(gdir, ignore_errors=True)
        log("enhance finished", gid, name)
    except Exception as e:
        group[-1].update(status="failed", error=f"Could not join the pieces: {e}")
        save_jobs()
        log("enhance join failed", gid, e)


# Based on Wan 2.2's own prompt-extension instructions (wan/utils/system_prompt.py, T2V/I2V English), plus business context.
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


# Free-model router for "Improve my prompt".
# Asks a few models at a time (waves), healthiest first; learns from each answer; rests busy models;
# spends the OpenRouter free allowance (50 requests/day) carefully; never waits more than ~90 s.
LLM_MODELS = [
    # name, provider, model id, can see photos. "gemini2" = FREE key (used first); "gemini" = PAID key (backup, capped per day)
    ("Gemini 3.8 Flash", "gemini2", "gemini-3.8-flash", True),
    ("Gemini 3.5 Flash", "gemini2", "gemini-3.5-flash", True),
    ("Gemini Flash (latest)", "gemini2", "gemini-flash-latest", True),
    ("Gemini 3.1 Flash Lite", "gemini2", "gemini-3.1-flash-lite", True),
    ("Gemini 3.8 Flash (paid key)", "gemini", "gemini-3.8-flash", True),
    ("Gemini 3.5 Flash (paid key)", "gemini", "gemini-3.5-flash", True),
]
LLM_ENDPOINTS = {"gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                 "gemini2": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}
LLM_PREFERRED = ("Gemini 3.8 Flash", "Gemini 3.5 Flash")
PAID_PROVIDERS, PAID_DAILY_CAP = ("gemini",), 30   # the paid key is only a backup, at most 30 calls a day    # the user's picks get a small head start
LLM_SMALL = ("Llama 3.2 11B Vision", "Ling 3.0 Flash", "Gemini 3.1 Flash Lite")         # fast but weaker: used only when bigger ones are busy
SMALL_GRACE = 12   # seconds to keep waiting for a bigger model after a small one answers
OPENROUTER_DAILY_LIMIT, OPENROUTER_RESERVE = 50, 5
WAVE_SIZE, WAVE_EVERY, IMPROVE_DEADLINE, PER_CALL_TIMEOUT = 2, 15, 90, 75
llm_health = load("llm_health.json", {})     # model id -> {ok, fail, lat, rest_until}
llm_budget = load("llm_budget.json", {})     # {"day": "YYYY-MM-DD", "openrouter": n}


def llm_key(provider):
    try:
        return open(os.path.join(HERE, "keys", f"{provider}.txt"), encoding="utf-8").read().strip()
    except OSError:
        return None


def openrouter_left():
    day = time.strftime("%Y-%m-%d", time.gmtime())
    if llm_budget.get("day") != day:
        llm_budget.clear()
        llm_budget.update(day=day, openrouter=0)
    return OPENROUTER_DAILY_LIMIT - OPENROUTER_RESERVE - llm_budget.get("openrouter", 0)


def paid_left():
    openrouter_left()   # also rolls the counters over to a new day
    return PAID_DAILY_CAP - llm_budget.get("paid", 0)


def health_score(name, model_id):
    h = llm_health.get(model_id, {})
    ok, fail = h.get("ok", 0), h.get("fail", 0)
    rate = (ok + 1) / (ok + fail + 2)                 # unknown models start at 50 %
    lat = h.get("lat", 15.0)
    return rate * 100 - lat + (15 if name in LLM_PREFERRED else 0) - (80 if name in LLM_SMALL else 0)


def health_record(model_id, ok, latency=None, rest=0):
    h = llm_health.setdefault(model_id, {"ok": 0, "fail": 0, "lat": 30.0})
    # recent results count more: decay old counts a little each time
    h["ok"], h["fail"] = h["ok"] * 0.9 + (1 if ok else 0), h["fail"] * 0.9 + (0 if ok else 1)
    if latency is not None:
        h["lat"] = round(h["lat"] * 0.6 + latency * 0.4, 1)
    if rest:
        h["rest_until"] = time.time() + rest
    save("llm_health.json", llm_health)


async def call_cloud_llm(provider, model_id, vision, system, user_text, image_path=None, timeout=PER_CALL_TIMEOUT):
    key = llm_key(provider)
    content = user_text
    if image_path and vision:
        import base64, mimetypes
        mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        b64 = base64.b64encode(open(image_path, "rb").read()).decode()
        content = [{"type": "text", "text": user_text}, {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]
    body = {"model": model_id, "max_tokens": 2000, "temperature": 0.8,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
    if provider in PAID_PROVIDERS:
        llm_budget["paid"] = llm_budget.get("paid", 0) + 1
        save("llm_budget.json", llm_budget)
    if provider in ("gemini", "gemini2"):
        body["reasoning_effort"] = "low"     # keep Gemini's thinking short so the answer comes fast
    if provider == "openrouter":
        headers["X-Title"] = "Wan Studio"
        llm_budget["openrouter"] = llm_budget.get("openrouter", 0) + 1
        save("llm_budget.json", llm_budget)
    async with http.post(LLM_ENDPOINTS[provider], json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        txt = await r.text()
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}: {txt[:160]}")
    j = json.loads(txt)
    if j.get("error"):
        raise RuntimeError(str(j["error"])[:160])
    return (j["choices"][0]["message"].get("content") or "").strip()


async def api_improve(req):
    d = await req.json()
    idea = (d.get("prompt") or "").strip()
    if not idea:
        return web.json_response({"error": "Write an idea first"}, status=400)
    i2v = d.get("mode") == "i2v"
    system = IMPROVE_SYSTEM_I2V if i2v else IMPROVE_SYSTEM
    shape = {"9:16": "vertical 9:16 video for Reels/TikTok", "1:1": "square video"}.get(d.get("aspect"), "landscape video")
    user_text = f"Idea ({shape}): {idea}" + (" The attached photo is the first frame." if i2v else "")
    img = os.path.join(UPLOADS, os.path.basename(d["image"])) if i2v and d.get("image") else None
    if img and not os.path.exists(img):
        img = None

    now = time.time()
    cands = [(n, p, m, v) for n, p, m, v in LLM_MODELS
             if llm_key(p) and llm_health.get(f"{p}|{m}", {}).get("rest_until", 0) < now]
    cands.sort(key=lambda c: (-(1 if (img and c[3]) else 0), -health_score(c[0], f"{c[1]}|{c[2]}")))
    free = [c for c in cands if c[1] not in PAID_PROVIDERS]
    paid = [c for c in cands if c[1] in PAID_PROVIDERS] if paid_left() > 0 else []
    tried = []
    start = time.time()

    async def ask(c):
        n, p, m, v = c
        t0 = time.time()
        try:
            opts = parse_options(await call_cloud_llm(p, m, v, system, user_text, img))
            if not opts:
                raise RuntimeError("empty answer")
            health_record(f"{p}|{m}", True, time.time() - t0)
            log(f"improve: {n} answered in {time.time() - t0:.0f}s ({len(opts)} versions)")
            return c, opts
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err = str(e)
            busy = any(x in err for x in ("429", "503", "rate", "overloaded", "Timeout", "timed out")) or not err
            health_record(f"{p}|{m}", False, rest=300 if busy else 60)
            tried.append(f"{n}: {(err or 'timed out')[:70]}")
            return c, None

    async def run_pool(pool, deadline):
        """Ask `pool` in waves; prefer a big model's answer over a small one (wait up to SMALL_GRACE for it)."""
        queue, tasks, best, best_at = list(pool), {}, None, 0
        while time.time() < deadline:
            launched = len(pool) - len(queue)
            if queue and (not tasks or time.time() - start >= WAVE_EVERY * launched / WAVE_SIZE):
                for c in queue[:WAVE_SIZE]:
                    tasks[asyncio.create_task(ask(c))] = c
                queue = queue[WAVE_SIZE:]
            if best and best[0][0] in LLM_SMALL and not any(c[0] not in LLM_SMALL for c in tasks.values()):
                for c in [c for c in queue if c[0] not in LLM_SMALL][:WAVE_SIZE]:
                    tasks[asyncio.create_task(ask(c))] = c
                    queue.remove(c)
            if not tasks:
                break
            done, _ = await asyncio.wait(list(tasks), timeout=1.0, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                c = tasks.pop(t)
                _, opts = t.result()
                if opts and (best is None or (best[0][0] in LLM_SMALL and c[0] not in LLM_SMALL)
                             or ((best[0][0] in LLM_SMALL) == (c[0] in LLM_SMALL) and len(opts) > len(best[1]))):
                    best, best_at = (c, opts), time.time()
            if best and len(best[1]) >= 3 and (best[0][0] not in LLM_SMALL or time.time() - best_at > SMALL_GRACE
                                               or all(c[0] in LLM_SMALL for c in tasks.values())):
                break
        for t in tasks:
            t.cancel()
        return best

    # 1) the free key; 2) only if it gave nothing at all, the paid key (capped per day)
    best = await run_pool(free, start + IMPROVE_DEADLINE) if free else None
    if not best and paid:
        log("improve: free key gave no answer, using the paid key")
        best = await run_pool(paid, time.time() + 45)
    if best:
        c, opts = best
        return web.json_response({"options": opts, "text": opts[0], "model": c[0], "saw_photo": bool(img and c[3]),
                                  "paid": c[1] in PAID_PROVIDERS, "seconds": round(time.time() - start)})
    return web.json_response({"offline": True, "error": "; ".join(tried)[:400]})


# ------------------------------------------------------------------ API keys (Settings): list / add / edit / remove / test
KEY_PROVIDERS = {
    "gemini2": {"label": "Gemini (free key)", "used": "Improve my prompt (used first)"},
    "gemini": {"label": "Gemini (paid key)", "used": "Improve my prompt (backup, max 30 a day)"},
    "nvidia": {"label": "NVIDIA", "used": "Make a picture first, Suggest motion, Caption & hashtags"},
    "openrouter": {"label": "OpenRouter", "used": "Not used right now"},
    "kaggle_luzamhjo_access_token": {"label": "Kaggle (luzamhjo)", "used": "Runs the video server. Restart the app after changing it"},
}


def key_path(provider):
    return os.path.join(HERE, "keys", f"{provider}.txt")


def mask(k):
    return (k[:4] + "…" + k[-4:]) if len(k) > 10 else "…"


async def api_keys_list(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    out = []
    for p, info in KEY_PROVIDERS.items():
        k = llm_key(p) or ""
        out.append({"provider": p, **info, "set": bool(k), "masked": mask(k) if k else ""})
    return web.json_response(out)


async def api_keys_save(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    d = await req.json()
    p, k = d.get("provider"), (d.get("key") or "").strip()
    if p not in KEY_PROVIDERS or len(k) < 10 or any(c.isspace() for c in k):
        return web.json_response({"error": "Choose a service and paste a valid key"}, status=400)
    os.makedirs(os.path.dirname(key_path(p)), exist_ok=True)
    with open(key_path(p), "w", encoding="utf-8") as f:
        f.write(k)
    log("api key saved for", p)
    return web.json_response({"ok": True, "masked": mask(k)})


async def api_keys_delete(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    p = req.match_info["provider"]
    if p in KEY_PROVIDERS and os.path.exists(key_path(p)):
        os.remove(key_path(p))
        log("api key removed for", p)
    return web.json_response({"ok": True})


async def api_keys_test(req):
    if not is_local(req):
        return web.json_response({"error": "API keys can only be managed on the laptop"}, status=403)
    p = req.match_info["provider"]
    k = llm_key(p)
    if not k:
        return web.json_response({"ok": False, "message": "No key saved"})
    t0 = time.time()
    try:
        if p in ("gemini", "gemini2"):
            async with http.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": k},
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
                j = await r.json()
                if r.status != 200:
                    raise RuntimeError(j.get("error", {}).get("message", f"HTTP {r.status}"))
                msg = f"Works: {len(j.get('models', []))} models available"
        elif p == "openrouter":
            async with http.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {k}"},
                                timeout=aiohttp.ClientTimeout(total=30)) as r:
                j = await r.json()
                if r.status != 200:
                    raise RuntimeError(str(j.get("error", f"HTTP {r.status}"))[:120])
                fd = j.get("data", {}).get("free_model_daily_requests") or {}
                msg = "Works" + (f": {fd.get('remaining')} of {fd.get('limit')} free requests left today" if fd else "")
        elif p == "nvidia":
            body = {"model": "meta/llama-3.2-11b-vision-instruct", "messages": [{"role": "user", "content": "Reply: ok"}], "max_tokens": 5}
            async with http.post(LLM_ENDPOINTS_ALL["nvidia"], json=body, headers={"Authorization": f"Bearer {k}", "Accept": "application/json"},
                                 timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}: {(await r.text())[:120]}")
                msg = "Works"
        else:
            q = await blocking(kaggle_ctl.quota)
            msg = f"Works: {q['total_h'] - q['used_h']:.1f} of {q['total_h']:.0f} GPU hours left this week"
        return web.json_response({"ok": True, "message": f"{msg} ({time.time() - t0:.1f} s)"})
    except Exception as e:
        return web.json_response({"ok": False, "message": str(e)[:200]})


LLM_ENDPOINTS_ALL = {"nvidia": "https://integrate.api.nvidia.com/v1/chat/completions"}


# ------------------------------------------------------------------ extra AI features (NVIDIA free models only; never Gemini)
NV_CHAT = "https://integrate.api.nvidia.com/v1/chat/completions"
NV_FLUX = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
FLUX_SIZES = {"16:9": (1344, 768), "9:16": (768, 1344), "1:1": (1024, 1024)}
NV_TEXT_MODELS = ["meta/llama-3.2-90b-vision-instruct", "nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3-super-120b-a12b",
                  "meta/llama-3.2-11b-vision-instruct"]
NV_VISION_MODELS = ["meta/llama-3.2-90b-vision-instruct", "meta/llama-3.2-11b-vision-instruct"]


def nv_headers():
    k = llm_key("nvidia")
    if not k:
        raise RuntimeError("Add an NVIDIA key in Settings → API keys to use this")
    return {"Authorization": f"Bearer {k}", "Content-Type": "application/json", "Accept": "application/json"}


async def nv_chat(models, messages, max_tokens=900, timeout=60):
    errors = []
    for m in models:
        try:
            async with http.post(NV_CHAT, json={"model": m, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
                                 headers=nv_headers(), timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                txt = await r.text()
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
            out = (json.loads(txt)["choices"][0]["message"].get("content") or "").strip()
            if out:
                return out, m
            errors.append(f"{m}: empty")
        except Exception as e:
            errors.append(f"{m.split('/')[-1]}: {str(e)[:60]}")
            if "Add an NVIDIA key" in str(e):
                raise
    raise RuntimeError("NVIDIA models are busy right now (" + "; ".join(errors)[:200] + ")")


def small_jpeg_b64(path, width=448):
    """NVIDIA's vision models need small images: shrink to ~25 KB."""
    out = os.path.join(UPLOADS, "_vision_tmp.jpg")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path, "-vf", f"scale={width}:-2", "-q:v", "6", out],
                   timeout=60, creationflags=NOWIN)
    import base64
    return base64.b64encode(open(out, "rb").read()).decode()


async def api_make_image(req):
    """1) Picture first: FLUX.1-dev makes starting images from the prompt."""
    d = await req.json()
    prompt = (d.get("prompt") or "").strip()
    if not prompt:
        return web.json_response({"error": "Describe the picture first"}, status=400)
    w, h = FLUX_SIZES.get(d.get("aspect"), FLUX_SIZES["16:9"])
    count = max(1, min(4, int(d.get("count", 2))))
    import base64
    names, errors = [], []
    for i in range(count):
        seed = random.randint(1, 2 ** 31 - 1)
        try:
            async with http.post(NV_FLUX, json={"prompt": prompt[:1800], "width": w, "height": h, "steps": 28, "seed": seed},
                                 headers=nv_headers(), timeout=aiohttp.ClientTimeout(total=120)) as r:
                txt = await r.text()
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}: {txt[:100]}")
            art = json.loads(txt)["artifacts"][0]
            if art.get("finishReason") not in (None, "SUCCESS"):
                raise RuntimeError(f"image blocked ({art.get('finishReason')})")
            name = f"img_{uuid.uuid4().hex[:10]}.jpg"
            with open(os.path.join(UPLOADS, name), "wb") as f:
                f.write(base64.b64decode(art["base64"]))
            names.append(name)
        except Exception as e:
            errors.append(str(e)[:120])
            if "Add an NVIDIA key" in str(e):
                break
    if not names:
        return web.json_response({"error": errors[0] if errors else "No image was made"}, status=502)
    return web.json_response({"images": names, "width": w, "height": h})


async def api_suggest_motion(req):
    """5) Look at the photo and suggest what could move (3 versions)."""
    d = await req.json()
    path = os.path.join(UPLOADS, os.path.basename(d.get("image") or ""))
    if not d.get("image") or not os.path.exists(path):
        return web.json_response({"error": "Choose a photo first"}, status=400)
    b64 = await blocking(small_jpeg_b64, path)
    idea = (d.get("prompt") or "").strip()
    ask = ("This photo is the first frame of a short video clip. Describe 3 different ways the scene could move in the next 5 seconds "
           "(subject movement and camera movement). Keep what is in the photo. "
           + (f"Build on this idea: {idea}. " if idea else "")
           + 'Write 3 numbered lines, "1." "2." "3.", 30-60 words each, nothing else.')
    msgs = [{"role": "user", "content": [{"type": "text", "text": ask},
                                         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]

    async def one(m):
        text, _ = await nv_chat([m], msgs, max_tokens=700, timeout=75)
        opts = [o for o in parse_options(text) if not re.search(r"(I'm not|I can't|I cannot|not going to)", o)]
        if len(opts) < 3:
            raise RuntimeError("unusable answer")
        return opts, m

    # ask the fast 11B and the stronger 90B at the same time; first good answer wins
    tasks = [asyncio.create_task(one(m)) for m in NV_VISION_MODELS]
    opts = model = None
    for fut in asyncio.as_completed(tasks):
        try:
            opts, model = await fut
            break
        except Exception:
            continue
    for t in tasks:
        t.cancel()
    if not opts:
        return web.json_response({"error": "NVIDIA's photo models are busy right now. Try again in a minute."}, status=502)
    return web.json_response({"options": opts, "model": model.split("/")[-1]})


async def api_social_kit(req):
    """4) Title, caption and hashtags for a finished video."""
    d = await req.json()
    x = lib_by_id(d.get("id"))
    if not x:
        return web.json_response({"error": "Unknown video"}, status=404)
    platform = d.get("platform") or {"9:16": "Instagram Reels / TikTok", "1:1": "Instagram post"}.get(x.get("aspect"), "YouTube / Facebook")
    ask = (f"Write social media text for a short video made from this description: \"{x.get('prompt', '')}\". Platform: {platform}. "
           "Return JSON only, with keys: title (max 60 characters), caption (2 to 3 short sentences, friendly, no hashtags), "
           "hashtags (list of 10 relevant hashtags without the # sign), hook (one punchy first line for the first second of the video).")
    try:
        text, model = await nv_chat(NV_TEXT_MODELS, [{"role": "user", "content": ask}], max_tokens=600)
        m = re.search(r"\{.*\}", text, re.S)
        kit = json.loads(m.group(0)) if m else None
        if not kit or not kit.get("caption"):
            raise RuntimeError("The AI gave an unusable answer. Try again.")
        tags = [("#" + str(t).lstrip("#").replace(" ", "")) for t in (kit.get("hashtags") or [])][:15]
        return web.json_response({"title": kit.get("title", ""), "caption": kit.get("caption", ""), "hook": kit.get("hook", ""),
                                  "hashtags": tags, "platform": platform, "model": model.split("/")[-1]})
    except Exception as e:
        return web.json_response({"error": str(e)[:200]}, status=502)


async def api_settings(req):
    d = await req.json()
    for k in ("idle_min", "max_hours", "steps"):
        if k in d:
            settings[k] = max(1, int(d[k]))
    if "cfg" in d:
        settings["cfg"] = float(d["cfg"])
    for k in ("aspect", "theme"):
        if k in d:
            settings[k] = d[k]
    if d.get("nav") in ("a", "b", "c", "d"):
        settings["nav"] = d["nav"]
    if "seconds" in d:
        settings["seconds"] = max(2, min(5, int(d["seconds"])))
    if "pin" in d and is_local(req) and re.fullmatch(r"\d{4,8}", str(d["pin"])):
        settings["pin"] = str(d["pin"])
    save("settings.json", settings)
    return web.json_response({"ok": True})


async def api_demos(req):
    return web.json_response(sorted(f[:-4] for f in os.listdir(DEMOS) if f.endswith(".mp4")))


show_window = None  # set by app_main.py when running as the Windows app


async def api_show(req):
    if show_window:
        show_window()
    return web.json_response({"shown": bool(show_window)})


async def api_open_folder(req):
    if is_local(req):
        os.startfile(settings["output_dir"])
    return web.json_response({"ok": True})


async def media(req):
    name = os.path.basename(req.match_info["name"])
    p = os.path.join(settings["output_dir"], name)
    if not os.path.exists(p):
        raise web.HTTPNotFound()
    headers = {"Content-Disposition": f'attachment; filename="{name}"'} if req.query.get("dl") else {}
    return web.FileResponse(p, headers=headers)


async def upload_file(req):
    p = os.path.join(UPLOADS, os.path.basename(req.match_info["name"]))
    if not os.path.exists(p):
        raise web.HTTPNotFound()
    return web.FileResponse(p)


async def index(req):
    return web.FileResponse(os.path.join(WEB, "index.html"), headers={"Cache-Control": "no-cache"})


async def on_start(app):
    global http
    http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
    if state["power"] in ("stopping", "error"):
        # The app was closed while turning off (or after an error): finish the stop so the power button works again.
        state.update(power="off", url=None, error=None, last_stop_reason=state.get("last_stop_reason") or "Turned off")
        save_state()
        asyncio.get_running_loop().run_in_executor(POOL, kaggle_ctl.delete)
    for j in jobs:  # jobs that were mid-flight when the app closed
        if j["status"] in ("uploading", "downloading"):
            j.update(status="queued", gpu=None, prompt_id=None)
    save_jobs()
    asyncio.get_running_loop().run_in_executor(POOL, make_all_thumbs)
    asyncio.create_task(power_loop())
    asyncio.create_task(scheduler_loop())
    log(f"Wan Studio on http://localhost:{PORT}  (LAN: {lan_ip()}:{PORT})  power={state['power']}")


def make_app():
    app = web.Application(middlewares=[auth_mw], client_max_size=50 * 1024 ** 2)
    app.add_routes([
        web.get("/", index), web.get("/login", login_get), web.post("/login", login_post),
        web.get("/api/state", api_state), web.post("/api/power", api_power),
        web.post("/api/generate", api_generate), web.post("/api/process", api_process),
        web.post("/api/jobs/{id}/cancel", api_cancel), web.post("/api/jobs/{id}/retry", api_retry),
        web.post("/api/jobs/clear", api_clear_jobs),
        web.get("/api/library", api_library), web.post("/api/library/{id}", api_lib_update),
        web.delete("/api/library/{id}", api_lib_delete),
        web.post("/api/upload", api_upload), web.post("/api/animate", api_animate), web.post("/api/improve", api_improve),
        web.post("/api/make-image", api_make_image), web.post("/api/suggest-motion", api_suggest_motion),
        web.post("/api/social-kit", api_social_kit),
        web.post("/api/upload-video", api_upload_video), web.post("/api/enhance", api_enhance),
        web.post("/api/settings", api_settings),
        web.get("/api/keys", api_keys_list), web.post("/api/keys", api_keys_save),
        web.delete("/api/keys/{provider}", api_keys_delete), web.post("/api/keys/{provider}/test", api_keys_test), web.get("/api/demos", api_demos),
        web.post("/api/open-folder", api_open_folder), web.post("/api/show", api_show),
        web.get("/media/{name}", media), web.get("/uploads/{name}", upload_file),
        web.static("/demos", DEMOS), web.static("/thumbs", THUMBS), web.static("/", WEB),
    ])
    app.on_startup.append(on_start)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None, access_log=None)
