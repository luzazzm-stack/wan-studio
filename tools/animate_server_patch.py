# Adds Wan 2.2 Animate jobs to the local app: GPU 0 = normal Wan videos, GPU 1 = Animate.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
s = open("server.py", encoding="utf-8").read()
assert "wf_animate" not in s, "already patched"


def rep(o, n):
    global s
    assert o in s, o[:80]
    s = s.replace(o, n, 1)


# ---------------- workflow
rep("def wf_upscale(video_name, aspect, fps, prefix):", '''ANIM_SIZES = {"9:16": (480, 832), "16:9": (832, 480), "1:1": (640, 640)}
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
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", src, "-vf", f"fps={ANIM_FPS},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
                    "-frames:v", str(n), "-t", f"{n / ANIM_FPS:.3f}", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", dst], check=True, timeout=300, creationflags=NOWIN)


def wf_upscale(video_name, aspect, fps, prefix):''')

# ---------------- time estimate
rep('''    if k in ("upscale", "interp"):
        return 340 if k == "upscale" else 60''', '''    if k in ("upscale", "interp"):
        return 340 if k == "upscale" else 60
    if k == "animate":
        return 300 + 9 * anim_frames(p["seconds"])          # first rough T4 guess; refined after real runs''')

# ---------------- scheduler: don't stop looking when GPU 0 has nothing for itself
rep('''        nxt = next((j for j in jobs if j["status"] == "queued" and j.get("want_gpu") in (None, g)), None)
        if not nxt:
            break''', '''        nxt = next((j for j in jobs if j["status"] == "queued" and j.get("want_gpu") in (None, g)), None)
        if not nxt:
            continue''')

# ---------------- GPU routing: Wan 2.2 videos on GPU 0, Animate on GPU 1
rep('''def new_job(kind, params, group=None, want_gpu=None):
    j = {''', '''def new_job(kind, params, group=None, want_gpu=None):
    if want_gpu is None:
        want_gpu = {"t2v": 0, "i2v": 0, "animate": 1}.get(kind)
    j = {''')

# ---------------- submit
rep('''        elif j["kind"] == "enhance":
            name = await upload_to_gpu(g, p["file"], f"enh_{j['id']}.mp4")''', '''        elif j["kind"] == "animate":
            img = await upload_to_gpu(g, os.path.join(UPLOADS, p["image"]), p["image"])
            prepped = os.path.join(UPLOADS, f"anim_{j['id']}.mp4")
            await blocking(prep_motion_video, os.path.join(UPLOADS, p["video"]), prepped, p["aspect"], p["seconds"])
            vid = await upload_to_gpu(g, prepped, f"anim_{j['id']}.mp4")
            wf = wf_animate(p, img, vid, prefix)
        elif j["kind"] == "enhance":
            name = await upload_to_gpu(g, p["file"], f"enh_{j['id']}.mp4")''')

# ---------------- library item
rep('''            tag = {"upscale": "1080p", "interp": "smooth"}.get(j["kind"], f"s{p.get('seed')}")''',
    '''            tag = {"upscale": "1080p", "interp": "smooth", "animate": "animate"}.get(j["kind"], f"s{p.get('seed')}")''')
rep('''                item.update({k: p.get(k) for k in ("prompt", "negative", "aspect", "seconds", "steps", "seed", "cfg", "template", "image", "quality")})
                item.update(fps=24, res="720p")''', '''                item.update({k: p.get(k) for k in ("prompt", "negative", "aspect", "seconds", "steps", "seed", "cfg", "template", "image", "quality")})
                item.update(fps=24, res="720p")
                if j["kind"] == "animate":
                    item.update(fps=ANIM_FPS, res="480p", steps=ANIM_STEPS, motion=p.get("video"))''')

# ---------------- API
rep("async def api_process(req):", '''async def api_animate(req):
    d = await req.json()
    img, vid = os.path.basename(d.get("image") or ""), os.path.basename(d.get("video") or "")
    if not img or not os.path.exists(os.path.join(UPLOADS, img)):
        return web.json_response({"error": "Choose a character photo first"}, status=400)
    if not vid or not os.path.exists(os.path.join(UPLOADS, vid)):
        return web.json_response({"error": "Choose a motion video first"}, status=400)
    aspect = d.get("aspect") if d.get("aspect") in ANIM_SIZES else "9:16"
    seed = int(d.get("seed", -1))
    p = {"prompt": (d.get("prompt") or "").strip() or "the character moves naturally, smooth motion, detailed face, high quality",
         "negative": d.get("negative", ""), "aspect": aspect, "seconds": 5 if int(d.get("seconds", 5)) >= 5 else 3,
         "image": img, "video": vid, "seed": seed if seed >= 0 else random.randint(0, 2 ** 31)}
    j = new_job("animate", p)
    save_jobs()
    return web.json_response({"jobs": [j["id"]]})


async def api_process(req):''')
rep('''        web.post("/api/upload", api_upload),''', '''        web.post("/api/upload", api_upload), web.post("/api/animate", api_animate),''')
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("server ok")
