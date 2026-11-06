# 1) Home: "Activity" panel under the prompt (server status, live progress, recent videos).
# 2) Enhance: output size (1080p / 2K / 4K), several videos at once, Original/Enhanced compare in the viewer.
import os, re
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ================================================================== server.py
s = open("server.py", encoding="utf-8").read()
a0 = s.index("def enhance_plan(info, upscale):")
a1 = s.index("async def api_upload_video(req):")
s = s[:a0] + '''ENH_SIZES = {"1080p": (1920, 1080), "2k": (2560, 1440), "4k": (3840, 2160)}
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


''' + s[a1:]

R = [
 ('''    ww, wh, tw, th = enhance_plan(info, True)
    can_up = max(info["width"], info["height"]) < 1900 and min(info["width"], info["height"]) < 1060
    return web.json_response({**info, "name": name, "title": os.path.splitext(os.path.basename(part.filename or "video"))[0][:60],
                              "can_upscale": can_up, "target_w": tw, "target_h": th, "too_long": info["duration"] > MAX_ENHANCE_SECONDS + 0.5})''',
  '''    return web.json_response({**info, "name": name, "title": os.path.splitext(os.path.basename(part.filename or "video"))[0][:60],
                              "targets": enhance_targets(info), "too_long": info["duration"] > MAX_ENHANCE_SECONDS + 0.5})'''),
 ('''    ww, wh, tw, th = enhance_plan(info, up)
    fps = min(info["fps"], 30.0)
    seg = max(1.5, 84 / fps)                     # about 84 frames per piece keeps GPU memory and RAM safe''',
  '''    size = (d.get("size") if d.get("size") in ENH_SIZES else "1080p") if up else None
    if up and not next(t for t in enhance_targets(info) if t["key"] == size)["ok"]:
        if not sm:
            return web.json_response({"error": f"This video is already {ENH_LABEL[size]} or larger"}, status=400)
        up, size = False, None
    ww, wh, tw, th = enhance_plan(info, size)
    fps = min(info["fps"], 30.0)
    n_frames = max(12, min(84, int(84 * (1920 * 1080) / (tw * th))))   # fewer frames per piece for bigger output (RAM)
    seg = max(0.4, n_frames / fps)'''),
 ('''    meta = {"src": src, "title": title, "upscale": up, "smooth": sm, "w": tw, "h": th, "fps": fps * (2 if sm else 1),''',
  '''    meta = {"src": src, "orig": name, "size": size, "title": title, "upscale": up, "smooth": sm, "w": tw, "h": th, "fps": fps * (2 if sm else 1),'''),
 ('''"upscale": up, "smooth": sm, "title": title, "frames": int(seg * fps)})''',
  '''"upscale": up, "smooth": sm, "title": title, "frames": int(seg * fps), "mp": round(ww * wh / 1e6, 2)})'''),
 ('''        return int(p.get("frames", 96) * ((2.8 if p.get("upscale") else 0) + (0.35 if p.get("smooth") else 0)) + 40)''',
  '''        return int(p.get("frames", 84) * ((3.1 * p.get("mp", 0.9) if p.get("upscale") else 0) + (0.35 if p.get("smooth") else 0)) + 40)'''),
 ('''"res": "1080p" if meta["upscale"] else f"{min(w, h)}p"}''',
  '''"res": ENH_LABEL.get(meta.get("size"), "1080p") if meta["upscale"] else f"{min(w, h)}p", "original": meta.get("orig")}'''),
 ('''        tag = "_".join(x for x in ("1080p" if meta["upscale"] else "", "smooth" if meta["smooth"] else "") if x)''',
  '''        tag = "_".join(x for x in (ENH_LABEL.get(meta.get("size"), "1080p") if meta["upscale"] else "", "smooth" if meta["smooth"] else "") if x)'''),
]
for o, n in R:
    assert o in s, o[:70]
    s = s.replace(o, n, 1)
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)

# ================================================================== index.html
h = open("web/index.html", encoding="utf-8").read()
# wrap the compose panel in a left column and add the Activity panel under it
c0 = h.index('    <div class="glass panel compose">')
c1 = h.index('    <div class="glass panel settings-panel">')
compose = h[c0:c1].rstrip()
h = h[:c0] + '    <div class="left-col">\n' + compose + '''

    <section class="glass panel activity" id="activity" aria-label="Activity">
      <div class="act-head">
        <div class="power-title"><span class="ping" aria-hidden="true"><i></i><i></i></span><span id="homeStatus">Server off</span></div>
        <span class="hint" id="homeSub"></span>
        <button class="btn small glass-btn" id="homePower">Turn on</button>
      </div>
      <div class="mini-queue" id="miniQueue"></div>
      <div class="recent-head"><b>Recent videos</b><a class="link" href="#gallery" data-goto="gallery">All videos</a></div>
      <div class="recent" id="homeRecent"></div>
    </section>
    </div>

''' + h[c1:]
# the old mini queue lived in the "Latest video" window
old = '        <div class="mini-queue" id="miniQueue"></div>\n      </div>\n    </aside>'
assert old in h
h = h.replace(old, '      </div>\n    </aside>', 1)

# enhance page: several files, size choice, list
e0 = h.index('<section class="page" id="page-enhance">')
e1 = h.index("</section>", e0) + len("</section>")
h = h[:e0] + '''<section class="page" id="page-enhance">
  <div class="page-head"><div><h1>Enhance your videos</h1></div></div>
  <div class="enhance-grid">
    <div class="glass panel">
      <div class="drop vdrop" id="vdrop" role="button" tabindex="0" aria-label="Choose videos to enhance">
        <input type="file" id="vfile" multiple accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv" hidden>
        <div class="drop-empty" id="vdropEmpty"><iconify-icon icon="solar:upload-minimalistic-linear" class="drop-icon" aria-hidden="true"></iconify-icon><b>Drop your videos here</b><span>or click to choose. MP4, MOV or WEBM, up to 60 seconds each. You can add several.</span></div>
        <div class="drop-full hidden" id="vdropFull"><video id="vPreview" controls muted playsinline></video></div>
      </div>
      <div class="vlist" id="vlist"></div>
      <button class="btn small glass-btn hidden" id="vAddMore"><iconify-icon icon="solar:add-circle-linear" aria-hidden="true"></iconify-icon>Add more videos</button>
    </div>
    <div class="glass panel">
      <h2>What to do</h2>
      <div class="toggles one">
        <label class="toggle"><input type="checkbox" id="enhUp" checked><span class="track"><i></i></span><span class="toggle-text">Upscale<em id="enhUpHint">sharper and bigger, keeps the same look</em></span></label>
      </div>
      <div class="seg small enh-size" id="enhSize" role="radiogroup" aria-label="Output size">
        <button data-s="1080p" class="on" role="radio">1080p<small>Full HD</small></button>
        <button data-s="2k" role="radio">2K<small>1440p</small></button>
        <button data-s="4k" role="radio">4K<small>slowest</small></button>
      </div>
      <div class="toggles one">
        <label class="toggle"><input type="checkbox" id="enhSmooth"><span class="track"><i></i></span><span class="toggle-text">Smooth motion<em>doubles the frames (for example 24 to 48 per second)</em></span></label>
      </div>
      <div class="go">
        <div class="estimate" id="enhEstimate" aria-live="polite">Choose a video first.</div>
        <button class="btn primary big" id="enhBtn" disabled><span id="enhBtnText">Enhance video</span><iconify-icon icon="solar:arrow-right-linear" aria-hidden="true"></iconify-icon></button>
      </div>
      <p class="hint">Sound is kept. Results appear in My videos, where you can compare them with the original.</p>
    </div>
  </div>
</section>''' + h[e1:]
old = '<button class="btn glass-btn" id="vCopy">Copy prompt</button>'
assert old in h
h = h.replace(old, '<button class="btn glass-btn hidden" id="vCompare">Show original</button>\n          ' + old, 1)
open("web/index.html", "w", encoding="utf-8").write(h)

# ================================================================== app.js
a = open("web/app.js", encoding="utf-8").read()
b0 = a.index("// ------------------------------------------------------------------ enhance (upload your own video)")
b1 = a.index("// ------------------------------------------------------------------ prompt lab (interactive guide)")
a = a[:b0] + open("tools/enhance2_code.js", encoding="utf-8").read() + "\n" + a[b1:]
R = [
 # home status mirrors the server card
 ('''  document.body.dataset.power = p;''', '''  document.body.dataset.power = p;
  const act = $("#activity"); if (act) act.className = "glass panel activity " + p;'''),
 ('''  $$(".gpu[data-g]").forEach(el => {''', '''  $("#homeStatus").textContent = $("#powerTitle").textContent;
  $("#homeSub").textContent = $("#powerSub").textContent;
  $("#homePower").textContent = p === "ready" || p === "starting" ? "Turn off" : p === "stopping" ? "Stopping…" : "Turn on";
  $("#homePower").disabled = p === "stopping";
  $$(".gpu[data-g]").forEach(el => {'''),
 ('''function renderPreview() {
  const x = library[0];''', '''function renderRecent() {
  const el = $("#homeRecent"); if (!el) return;
  el.innerHTML = library.slice(0, 4).map(x => `<button class="rthumb" data-open="${x.id}" aria-label="Open video" style="aspect-ratio:${x.aspect === "9:16" ? "9/16" : x.aspect === "1:1" ? "1/1" : "16/9"}">
    <img src="/thumbs/${x.id}.jpg" alt="" loading="lazy"><span class="tag">${x.res || "720p"}</span></button>`).join("")
    || `<div class="hint">Your finished videos will show up here.</div>`;
}
function renderPreview() {
  renderRecent();
  const x = library[0];'''),
 ('''  $("#vUpscale").disabled = cur.res === "1080p";''', '''  $("#vUpscale").disabled = cur.res !== "720p" && !!cur.res;
  const cmp = $("#vCompare"); cmp.classList.toggle("hidden", !cur.original); cmp.textContent = "Show original"; cmp.dataset.on = "";'''),
]
for o, n in R:
    assert o in a, o[:70]
    a = a.replace(o, n, 1)
# mini queue: friendly empty state
old = '''    + (active.length > 4 ?'''
assert old in a
a = a.replace(old, '''    + (!active.length ? `<div class="hint">Nothing is being made right now. Press Generate to start a video.</div>` : "")
    + (active.length > 4 ?''', 1)
a = a.replace('''$("#dockPower").onclick = () => $("#powerSwitch").click();''', '''$("#dockPower").onclick = () => $("#powerSwitch").click();
$("#homePower").onclick = () => $("#powerSwitch").click();
$("#vCompare").onclick = () => {
  const v = $("#vVideo"), t = v.currentTime, on = $("#vCompare").dataset.on === "1";
  v.src = on ? "/media/" + encodeURIComponent(cur.file) : "/uploads/" + encodeURIComponent(cur.original);
  v.currentTime = t; v.play().catch(() => {});
  $("#vCompare").dataset.on = on ? "" : "1"; $("#vCompare").textContent = on ? "Show original" : "Show enhanced";
};''', 1)
assert "homePower" in a and "vCompare" in a
open("web/app.js", "w", encoding="utf-8").write(a)

# ================================================================== style.css
c = open("web/style.css", encoding="utf-8").read()
c += "\n" + open("tools/activity_style.css", encoding="utf-8").read()
open("web/style.css", "w", encoding="utf-8").write(c)
print("ok")
