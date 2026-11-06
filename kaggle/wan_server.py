# Wan Studio server for Kaggle (2x T4). This file is a TEMPLATE: the Wan Studio app fills in the
# __PLACEHOLDERS__ and pushes it as the kernel. It runs Wan 2.2 TI2V-5B in two ComfyUI instances
# (one per GPU) behind a small key-protected gateway, exposed through a Cloudflare quick tunnel.
# The tunnel URL is announced on ntfy.sh/<TOPIC>. The script exits (ending the Kaggle session)
# when idle too long, when MAX_HOURS is reached, or when /shutdown is called.
import asyncio, json, os, subprocess, sys, threading, time, urllib.request, uuid, re

KEY, TOPIC = "__KEY__", "__TOPIC__"
IDLE_MIN, MAX_HOURS = __IDLE_MIN__, __MAX_HOURS__
LLM_MODEL = "qwen2.5:3b"          # CPU fallback while both GPUs are making video
W = "/tmp/wan"
C = f"{W}/ComfyUI"
PORTS = [8188, 8189]
T0 = time.time()

S = {"stage": "booting", "pct": 0, "detail": "", "ready": False, "error": None, "llm": False,
     "timings": {}, "gpus": [{} for _ in PORTS]}
last_active = time.time()
shutdown = threading.Event()
procs = []
llm_jobs = {}
comfy, comfy_args = {}, {}

HF = "https://huggingface.co/Comfy-Org"
MODELS = [
    (f"{HF}/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
     "diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"),
    (f"{HF}/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
     "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    (f"{HF}/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors",
     "vae/wan2.2_vae.safetensors"),
    ("https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/FastWan/Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors",
     "loras/Wan2_2_5B_FastWanFullAttn_lora_rank_128_bf16.safetensors"),
    ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
     "upscale_models/RealESRGAN_x2plus.pth"),
    # ---- Wan 2.2 Animate (runs on GPU 1)
    ("https://huggingface.co/QuantStack/Wan2.2-Animate-14B-GGUF/resolve/main/Wan2.2-Animate-14B-Q4_K_M.gguf",
     "diffusion_models/Wan2.2-Animate-14B-Q4_K_M.gguf"),
    (f"{HF}/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
     "vae/wan_2.1_vae.safetensors"),
    ("https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
     "loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
    ("https://huggingface.co/Wan-AI/Wan2.2-Animate-14B/resolve/main/process_checkpoint/det/yolov10m.onnx",
     "detection/yolov10m.onnx"),
    ("https://huggingface.co/JunkyByte/easy_ViTPose/resolve/main/onnx/wholebody/vitpose-l-wholebody.onnx",
     "detection/vitpose-l-wholebody.onnx"),
]


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def ntfy(d):
    d = {**d, "t": time.time()}
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=json.dumps(d).encode()), timeout=20)
    except Exception as e:
        log("ntfy failed", e)


def stage(name, pct, detail=""):
    S.update(stage=name, pct=pct, detail=detail)
    log("STAGE", name, pct, detail)


def sh(cmd):
    log("+", cmd)
    r = subprocess.run(cmd, shell=True)
    if r.returncode:
        raise RuntimeError(f"command failed ({r.returncode}): {cmd}")


# ---------------------------------------------------------------- setup (runs in a thread)
dl = {"done": 0, "total": 1}


def download_all():
    sizes = []
    for url, _ in MODELS:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            sizes.append(int(r.headers.get("Content-Length") or 0))
    dl["total"] = sum(sizes) or 1
    errs = []

    def one(url, rel):
        dest = f"{C}/models/{rel}"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=120) as r, open(dest + ".part", "wb") as f:
                    while True:
                        b = r.read(8 << 20)
                        if not b:
                            break
                        f.write(b)
                        dl["done"] += len(b)
                os.rename(dest + ".part", dest)
                return
            except Exception as e:
                log("download retry", rel, e)
                time.sleep(5)
        errs.append(rel)

    ts = [threading.Thread(target=one, args=m) for m in MODELS]
    [t.start() for t in ts]
    while any(t.is_alive() for t in ts):
        time.sleep(3)
        if S["stage"] == "downloading":
            stage("downloading", 15 + int(55 * dl["done"] / dl["total"]),
                  f"{dl['done'] >> 20} / {dl['total'] >> 20} MB")
    if errs:
        raise RuntimeError(f"download failed: {errs}")


def wan_workflow(prompt, neg, w, h, frames, steps, seed, prefix, cfg=5.0):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": neg}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": w, "height": h, "length": frames, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["7", 0],
                                                    "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": 24.0}},
        "11": {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }


def http_json(url, data=None, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


def run_and_wait(port, wf, timeout=1800):
    pid = http_json(f"http://127.0.0.1:{port}/prompt", {"prompt": wf, "client_id": "warmup"})["prompt_id"]
    t = time.time()
    while time.time() - t < timeout:
        h = http_json(f"http://127.0.0.1:{port}/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise RuntimeError(f"warmup error on port {port}: {json.dumps(st)[:1500]}")
            return time.time() - t
        time.sleep(2)
    raise RuntimeError("warmup timeout")


def setup():
    try:
        stage("installing", 3, "ComfyUI")
        os.makedirs(W, exist_ok=True)
        sh(f"git clone -q --depth 1 https://github.com/comfyanonymous/ComfyUI {C}")
        sh(f"git clone -q --depth 1 https://github.com/Fannovel16/ComfyUI-Frame-Interpolation {C}/custom_nodes/ComfyUI-Frame-Interpolation")
        sh(f"git clone -q --depth 1 https://github.com/city96/ComfyUI-GGUF {C}/custom_nodes/ComfyUI-GGUF")
        sh(f"git clone -q --depth 1 https://github.com/kijai/ComfyUI-WanAnimatePreprocess {C}/custom_nodes/ComfyUI-WanAnimatePreprocess")
        stage("downloading", 15, "models")
        dt = threading.Thread(target=download_all_safe)
        dt.start()
        sh(f"pip install -q -r {C}/requirements.txt einops kornia gguf onnxruntime-gpu opencv-python-headless 2>&1 | tail -3")
        dt.join()
        if dl.get("error"):
            raise RuntimeError(dl["error"])
        S["timings"]["setup_s"] = round(time.time() - T0)

        stage("starting", 72, "launching ComfyUI on both GPUs")
        cli = open(f"{C}/comfy/cli_args.py").read()
        for g, port in enumerate(PORTS):
            args = [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", str(port), "--cuda-device", str(g),
                    "--output-directory", f"{W}/out{g}", "--input-directory", f"{W}/in{g}",
                    "--disable-auto-launch", "--preview-method", "none"]
            if "--user-directory" in cli:
                args += ["--user-directory", f"{W}/user{g}"]
            if "--database-url" in cli:
                args += ["--database-url", f"sqlite:///{W}/db{g}.sqlite"]
            # Keep ComfyUI's default dynamic VRAM: it shares the model files between both instances via mmap.
            # --disable-dynamic-vram made each instance hold its own ~17 GB copy in RAM and one got OOM-killed.
            for d in ("out", "in", "user"):
                os.makedirs(f"{W}/{d}{g}", exist_ok=True)
            comfy_args[g] = args
            comfy[g] = subprocess.Popen(args, cwd=C, stdout=open(f"{W}/comfy{g}.log", "w"), stderr=subprocess.STDOUT)
            procs.append(comfy[g])
        for port in PORTS:
            for _ in range(300):
                try:
                    http_json(f"http://127.0.0.1:{port}/system_stats", timeout=5)
                    break
                except Exception:
                    time.sleep(2)
            else:
                raise RuntimeError(f"ComfyUI on {port} did not start: " + open(f"{W}/comfy{PORTS.index(port)}.log").read()[-1500:])

        stage("warming", 85, "loading the model into both GPUs")
        res = {}

        def warm(g, port):
            try:
                res[g] = run_and_wait(port, wan_workflow("a calm lake at sunrise", "", 256, 256, 9, 2, 1, "warmup"))
            except Exception as e:
                res[g] = e
        ts = [threading.Thread(target=warm, args=(g, p)) for g, p in enumerate(PORTS) if g == 0]
        [t.start() for t in ts]
        [t.join() for t in ts]
        for g, r in res.items():
            if isinstance(r, Exception):
                raise r
            S["timings"][f"warm{g}_s"] = round(r)
        S["timings"]["ready_s"] = round(time.time() - T0)
        global last_active
        last_active = time.time()
        S["ready"] = True
        stage("ready", 100, "")
        ntfy({"type": "ready", "url": S.get("url")})
        threading.Thread(target=setup_llm, daemon=True).start()
    except Exception as e:
        S["error"] = str(e)[:3000]
        stage("error", S["pct"], str(e)[:300])
        ntfy({"type": "error", "error": str(e)[:1000]})
        for g in range(len(PORTS)):
            p = f"{W}/comfy{g}.log"
            if os.path.exists(p):
                log(f"--- comfy{g}.log tail ---\n" + open(p).read()[-3000:])


def download_all_safe():
    try:
        download_all()
    except Exception as e:
        dl["error"] = str(e)


def setup_llm():
    # LLM for "Improve my prompt". Ollama only sees GPU 2; each request picks GPU (when idle) or CPU.
    try:
        sh("(apt-get install -y -qq zstd >/dev/null 2>&1 || true) && curl -fsSL https://ollama.com/install.sh | sh >/dev/null 2>&1")
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_MAX_LOADED_MODELS": "1"}
        procs.append(subprocess.Popen(["ollama", "serve"], env=env, stdout=open(f"{W}/ollama.log", "w"), stderr=subprocess.STDOUT))
        time.sleep(6)
        sh(f"OLLAMA_HOST=127.0.0.1:11434 ollama pull {LLM_MODEL} >/dev/null 2>&1")
        S["llm"] = True

        log("LLM ready")
    except Exception as e:
        log("LLM setup failed", e)


# ---------------------------------------------------------------- gateway
async def gateway():
    import aiohttp
    from aiohttp import web

    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600))

    @web.middleware
    async def auth(req, handler):
        global last_active
        if (req.headers.get("X-Key") or req.query.get("key")) != KEY:
            return web.json_response({"error": "bad key"}, status=401)
        if req.path != "/health":
            last_active = time.time()
        return await handler(req)

    async def health(req):
        return web.json_response({**S, "uptime": round(time.time() - T0), "idle_s": round(time.time() - last_active),
                                  "idle_limit_s": IDLE_MIN * 60, "max_s": MAX_HOURS * 3600})

    async def proxy(req):
        g = int(req.match_info["g"])
        q = {k: v for k, v in req.query.items() if k != "key"}
        hdr = {"Content-Type": req.headers["Content-Type"]} if "Content-Type" in req.headers else {}
        async with session.request(req.method, f"http://127.0.0.1:{PORTS[g]}/{req.match_info['path']}",
                                   params=q, data=await req.read(), headers=hdr) as r:
            body = await r.read()
            return web.Response(body=body, status=r.status,
                                headers={"Content-Type": r.headers.get("Content-Type", "application/octet-stream")})

    async def llm_start(req):
        d = await req.json()
        jid = uuid.uuid4().hex[:10]
        llm_jobs[jid] = {"done": False}

        async def run():
            try:
                g2 = S["gpus"][1] if len(S["gpus"]) > 1 else {}
                gpu_free = False  # GPU model removed at the user's request; the small model runs on the CPU
                body = {"model": LLM_MODEL, "stream": False,
                        "keep_alive": 0 if gpu_free else "10m",   # free the GPU memory right after answering
                        "options": {"num_predict": d.get("max_tokens", 220), "temperature": d.get("temperature", 0.7),
                                    **({} if gpu_free else {"num_gpu": 0, "num_thread": 2})},
                        "messages": [{"role": "system", "content": d.get("system", "")}, {"role": "user", "content": d["prompt"]}]}
                if gpu_free:
                    # Wan stays loaded in GPU 2's memory between videos; unload it so the 7B model fits fully (fast).
                    try:
                        async with session.post(f"http://127.0.0.1:{PORTS[1]}/free", json={"unload_models": True, "free_memory": True}) as fr:
                            await fr.read()
                    except Exception:
                        pass
                async with session.post("http://127.0.0.1:11434/api/chat", json=body) as r:
                    j = await r.json()
                llm_jobs[jid] = {"done": True, "text": j.get("message", {}).get("content", ""), "model": body["model"]}
            except Exception as e:
                llm_jobs[jid] = {"done": True, "error": str(e)}
        asyncio.create_task(run())
        return web.json_response({"id": jid})

    async def llm_get(req):
        return web.json_response(llm_jobs.get(req.match_info["id"], {"done": True, "error": "unknown id"}))

    async def do_shutdown(req):
        shutdown.set()
        return web.json_response({"ok": True})

    async def ws_watch(g):
        # Track live sampling progress of prompts queued with client_id "wanstudio".
        while True:
            try:
                async with session.ws_connect(f"http://127.0.0.1:{PORTS[g]}/ws?clientId=wanstudio") as ws:
                    async for m in ws:
                        if m.type != aiohttp.WSMsgType.TEXT:
                            continue
                        j = json.loads(m.data)
                        t, d = j.get("type"), j.get("data", {})
                        st = S["gpus"][g]
                        if t == "status":
                            st["queue"] = d.get("status", {}).get("exec_info", {}).get("queue_remaining", 0)
                        elif t == "execution_start":
                            st.update(prompt_id=d.get("prompt_id"), value=0, max=0, node=None, started=time.time())
                        elif t == "executing":
                            st["node"] = d.get("node")
                            if d.get("node") is None:
                                st.update(prompt_id=None, value=0, max=0)
                        elif t == "progress":
                            st.update(value=d.get("value"), max=d.get("max"), node=d.get("node"), prompt_id=d.get("prompt_id"))
            except Exception:
                pass
            await asyncio.sleep(3)

    app = web.Application(client_max_size=1024 ** 3, middlewares=[auth])
    app.add_routes([web.get("/health", health), web.post("/shutdown", do_shutdown),
                    web.post("/llm", llm_start), web.get("/llm/{id}", llm_get),
                    web.route("*", "/g{g:[01]}/{path:.*}", proxy)])
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 8000).start()
    log("gateway on :8000")

    async def start_watchers():
        while not S["ready"]:
            await asyncio.sleep(5)
        for g in range(len(PORTS)):
            asyncio.create_task(ws_watch(g))
    asyncio.create_task(start_watchers())


def tunnel():
    sh("curl -fsSL -o /usr/local/bin/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /usr/local/bin/cloudflared")
    p = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    procs.append(p)
    for line in p.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m:
            S["url"] = m.group(0)
            log("URL", S["url"])
            ntfy({"type": "url", "url": S["url"]})
            break
    for _ in p.stdout:
        pass


def supervise():
    # Restart a ComfyUI instance that died (e.g. out of memory) so one crash doesn't take a GPU out for the session.
    for g, p in list(comfy.items()):
        if p.poll() is None:
            continue
        tail = open(f"{W}/comfy{g}.log", errors="replace").read()[-2500:]
        log(f"ComfyUI on GPU {g} exited with {p.returncode}; restarting. Log tail:\n{tail}")
        st = S["gpus"][g]
        st["restarts"] = st.get("restarts", 0) + 1
        st["last_crash"] = tail[-600:]
        st.update(prompt_id=None, value=0, max=0, queue=0)
        comfy[g] = subprocess.Popen(comfy_args[g], cwd=C, stdout=open(f"{W}/comfy{g}.log", "a"), stderr=subprocess.STDOUT)
        procs.append(comfy[g])


def busy():
    return any(g.get("prompt_id") or g.get("queue") for g in S["gpus"])


async def main():
    global last_active
    sh("pip install -q aiohttp 2>&1 | tail -1")
    await gateway()
    threading.Thread(target=tunnel, daemon=True).start()
    threading.Thread(target=setup, daemon=True).start()
    reason = None
    while not reason:
        await asyncio.sleep(15)
        if S["ready"]:
            supervise()
        if busy():
            last_active = time.time()
        if shutdown.is_set():
            reason = "stopped from app"
        elif time.time() - last_active > IDLE_MIN * 60 and (S["ready"] or S["error"]):
            reason = f"idle for {IDLE_MIN} min"
        elif time.time() - T0 > MAX_HOURS * 3600:
            reason = f"reached {MAX_HOURS} h limit"
    log("EXIT:", reason)
    ntfy({"type": "stopped", "reason": reason})
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass
    os._exit(0)


asyncio.run(main())
