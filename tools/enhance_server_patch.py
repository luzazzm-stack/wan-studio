# Server side of "Enhance a video": upload + probe, split into short pieces, run each on a GPU, join the pieces and keep the sound.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
s = open("server.py", encoding="utf-8").read()

R = [
 # workflow for one piece
 ('''def wf_interp(video_name, fps, prefix):''', '''def wf_enhance(video_name, w, h, fps, upscale, smooth, prefix):
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


def wf_interp(video_name, fps, prefix):'''),
 # submit
 ('''        else:
            src = lib_by_id(p["source"])
            if not src:
                raise RuntimeError("The source video is no longer in your library")''', '''        elif j["kind"] == "enhance":
            name = await upload_to_gpu(g, p["file"], f"enh_{j['id']}.mp4")
            wf = wf_enhance(name, p["w"], p["h"], p["fps"], p["upscale"], p["smooth"], prefix)
        else:
            src = lib_by_id(p["source"])
            if not src:
                raise RuntimeError("The source video is no longer in your library")'''),
 # estimate
 ('''    if k in ("upscale", "interp"):''', '''    if k == "enhance":
        return int(p.get("frames", 96) * ((2.8 if p.get("upscale") else 0) + (0.35 if p.get("smooth") else 0)) + 40)
    if k in ("upscale", "interp"):'''),
 # download
 ('''        if p.get("demo"):
            dpath = os.path.join(DEMOS, p["demo"] + ".mp4")''', '''        if j["kind"] == "enhance":
            gdir = os.path.join(ENHANCE, p["group"])
            with open(os.path.join(gdir, f"out_{p['index']:03d}.mp4"), "wb") as fh:
                fh.write(data)
            j.update(status="done", finished=time.time(), took=round(took))
            save_jobs()
            await finish_enhance(p["group"])
            log("job done", j["id"], f"{took:.0f}s")
            return
        if p.get("demo"):
            dpath = os.path.join(DEMOS, p["demo"] + ".mp4")'''),
 ('''THUMBS = os.path.join(DATA, "thumbs")
for d in (DATA, DEMOS, UPLOADS, THUMBS):''', '''THUMBS = os.path.join(DATA, "thumbs")
ENHANCE = os.path.join(DATA, "enhance")
for d in (DATA, DEMOS, UPLOADS, THUMBS, ENHANCE):'''),
 ('''        web.post("/api/upload", api_upload), web.post("/api/improve", api_improve),''',
  '''        web.post("/api/upload", api_upload), web.post("/api/improve", api_improve),
        web.post("/api/upload-video", api_upload_video), web.post("/api/enhance", api_enhance),'''),
 ('''IMPROVE_SYSTEM = (''', '''# ------------------------------------------------------------------ enhance your own video
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


def enhance_plan(info, upscale):
    """Working size (what is sent to the GPU) and target size (what comes back)."""
    w, h = info["width"], info["height"]
    long_side = max(w, h)
    if upscale:
        k = min(1.0, 1280 / long_side)                     # feed at most 720p-class frames to the 2x model
        ww, wh = even(w * k), even(h * k)
        t = min(1920 / max(ww, wh), 1080 / min(ww, wh))    # fit inside 1920x1080 (or 1080x1920)
        return ww, wh, even(ww * t), even(wh * t)
    k = min(1.0, 1920 / long_side)
    return even(w * k), even(h * k), even(w * k), even(h * k)


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
    ww, wh, tw, th = enhance_plan(info, True)
    can_up = max(info["width"], info["height"]) < 1900 and min(info["width"], info["height"]) < 1060
    return web.json_response({**info, "name": name, "title": os.path.splitext(os.path.basename(part.filename or "video"))[0][:60],
                              "can_upscale": can_up, "target_w": tw, "target_h": th, "too_long": info["duration"] > MAX_ENHANCE_SECONDS + 0.5})


def split_video(src, gdir, ww, wh, fps, seg_seconds):
    os.makedirs(gdir, exist_ok=True)
    cmd = [FFMPEG, "-v", "error", "-y", "-i", src, "-an", "-vf", f"scale={ww}:{wh}:flags=lanczos,fps={fps:.3f},format=yuv420p",
           "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-force_key_frames", f"expr:gte(t,n_forced*{seg_seconds:.3f})",
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
    ww, wh, tw, th = enhance_plan(info, up)
    fps = min(info["fps"], 30.0)
    seg = max(1.5, 84 / fps)                     # about 84 frames per piece keeps GPU memory and RAM safe
    gid = uuid.uuid4().hex[:8]
    gdir = os.path.join(ENHANCE, gid)
    try:
        parts = await blocking(split_video, src, gdir, ww, wh, fps, seg)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)
    title = str(d.get("title") or os.path.splitext(name)[0])[:60]
    meta = {"src": src, "title": title, "upscale": up, "smooth": sm, "w": tw, "h": th, "fps": fps * (2 if sm else 1),
            "duration": info["duration"], "audio": info["audio"], "parts": len(parts)}
    with open(os.path.join(gdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    for i, fn in enumerate(parts):
        new_job("enhance", {"group": gid, "index": i, "total": len(parts), "file": os.path.join(gdir, fn), "w": tw, "h": th, "fps": fps,
                            "upscale": up, "smooth": sm, "title": title, "frames": int(seg * fps)})
    save_jobs()
    return web.json_response({"parts": len(parts), "group": gid})


def join_video(gdir, meta, out_path):
    outs = sorted(f for f in os.listdir(gdir) if f.startswith("out_") and f.endswith(".mp4"))
    with open(os.path.join(gdir, "list.txt"), "w", encoding="utf-8") as f:
        for o in outs:
            f.write("file '" + os.path.join(gdir, o).replace("\\\\", "/").replace("'", "'\\\\''") + "'\\n")
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
        tag = "_".join(x for x in ("1080p" if meta["upscale"] else "", "smooth" if meta["smooth"] else "") if x)
        name = f"{time.strftime('%Y-%m-%d_%H%M')}_{slug(meta['title'])}_{tag}.mp4"
        out_path = os.path.join(settings["output_dir"], name)
        await blocking(join_video, gdir, meta, out_path)
        w, h = meta["w"], meta["h"]
        aspect = "16:9" if w / h > 1.25 else "9:16" if w / h < 0.8 else "1:1"
        item = {"id": uuid.uuid4().hex[:10], "file": name, "kind": "enhance", "created": time.time(), "favorite": False,
                "took": sum(j.get("took") or 0 for j in group), "size": os.path.getsize(out_path), "prompt": meta["title"] + " (your video, enhanced)",
                "aspect": aspect, "seconds": round(meta["duration"]), "fps": round(meta["fps"]), "res": "1080p" if meta["upscale"] else f"{min(w, h)}p"}
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


IMPROVE_SYSTEM = ('''),
]
for o, n in R:
    assert o in s, o[:70]
    s = s.replace(o, n, 1)
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)
print("server ok")
