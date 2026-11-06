# Adds Wan 2.2 Animate to the Kaggle kernel template: GPU 0 keeps Wan 2.2 TI2V-5B, GPU 1 runs Animate-14B (GGUF).
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
p = "kaggle/wan_server.py"
s = open(p, encoding="utf-8").read()
assert "Animate" not in s, "already patched"


def rep(o, n):
    global s
    assert o in s, o[:80]
    s = s.replace(o, n, 1)


rep('''    ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
     "upscale_models/RealESRGAN_x2plus.pth"),''', '''    ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
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
     "detection/vitpose-l-wholebody.onnx"),''')

rep('''        sh(f"git clone -q --depth 1 https://github.com/Fannovel16/ComfyUI-Frame-Interpolation {C}/custom_nodes/ComfyUI-Frame-Interpolation")''',
    '''        sh(f"git clone -q --depth 1 https://github.com/Fannovel16/ComfyUI-Frame-Interpolation {C}/custom_nodes/ComfyUI-Frame-Interpolation")
        sh(f"git clone -q --depth 1 https://github.com/city96/ComfyUI-GGUF {C}/custom_nodes/ComfyUI-GGUF")
        sh(f"git clone -q --depth 1 https://github.com/kijai/ComfyUI-WanAnimatePreprocess {C}/custom_nodes/ComfyUI-WanAnimatePreprocess")''')
rep('''        sh(f"pip install -q -r {C}/requirements.txt einops kornia 2>&1 | tail -3")''',
    '''        sh(f"pip install -q -r {C}/requirements.txt einops kornia gguf onnxruntime-gpu opencv-python-headless 2>&1 | tail -3")''')

# warm only GPU 0 with the 5B model; GPU 1 is reserved for Animate (its model loads on the first Animate job)
rep('''        ts = [threading.Thread(target=warm, args=(g, p)) for g, p in enumerate(PORTS)]''',
    '''        ts = [threading.Thread(target=warm, args=(g, p)) for g, p in enumerate(PORTS) if g == 0]''')
open(p, "w", encoding="utf-8").write(s)
import ast
ast.parse(s.replace("__IDLE_MIN__", "20").replace("__MAX_HOURS__", "9"))
print("kernel ok")
