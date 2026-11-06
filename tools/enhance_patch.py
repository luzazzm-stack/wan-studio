# 1) Simpler Create page: Prompt panel + Settings panel. Server card and "Latest video" move to the Queue page.
# 2) New Enhance page: upload your own video (up to 60 s) to upscale to 1080p and/or smooth to double frame rate.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# ------------------------------------------------------------------ index.html
h = open("web/index.html", encoding="utf-8").read()

# move the side column (server card + latest video) to the Queue page
s = h.index('    <div class="side-col">')
e = h.index("</aside>", s) + len("</aside>")
e = h.index("</div>", e) + len("</div>")          # closes .side-col
side = h[s:e]
h = h[:s].rstrip() + "\n" + h[e:]

# split the compose panel: prompt (left) and settings (right)
a0 = h.index('      <div class="lbl">Shape</div>')
a1 = h.index('      <div class="go">')
settings_block = h[a0:a1]
h = h[:a0] + h[a1:]
go_end = h.index("</div>", h.index('<button class="btn primary big" id="generateBtn"')) + len("</div>")   # closes .go
panel_end = h.index("</div>", go_end) + len("</div>")                                                   # closes .compose
h = h[:panel_end] + '''

    <div class="glass panel settings-panel">
      <h2>Settings</h2>
''' + settings_block.replace('      <div class="lbl">Shape</div>', '      <div class="lbl first">Shape</div>', 1) + "    </div>" + h[panel_end:]

# queue page: list on the left, server + latest on the right
old = '  <div id="jobList" class="job-list"></div>'
assert old in h
h = h.replace(old, '  <div class="queue-grid">\n    <div id="jobList" class="job-list"></div>\n' + side + "\n  </div>")

# enhance page + dock entry
old = '''<!-- ============================== GALLERY -->'''
assert old in h
h = h.replace(old, '''<!-- ============================== ENHANCE -->
<section class="page" id="page-enhance">
  <div class="page-head"><div><h1>Enhance a video</h1></div></div>
  <div class="enhance-grid">
    <div class="glass panel">
      <div class="drop vdrop" id="vdrop" role="button" tabindex="0" aria-label="Choose a video to enhance">
        <input type="file" id="vfile" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv" hidden>
        <div class="drop-empty" id="vdropEmpty"><iconify-icon icon="solar:upload-minimalistic-linear" class="drop-icon" aria-hidden="true"></iconify-icon><b>Drop your video here</b><span>or click to choose one. MP4, MOV or WEBM, up to 60 seconds.</span></div>
        <div class="drop-full hidden" id="vdropFull"><video id="vPreview" controls muted playsinline></video></div>
      </div>
      <div class="vinfo hidden" id="vinfo"></div>
    </div>
    <div class="glass panel">
      <h2>What to do</h2>
      <div class="toggles one">
        <label class="toggle"><input type="checkbox" id="enhUp" checked><span class="track"><i></i></span><span class="toggle-text">Upscale to 1080p<em id="enhUpHint">sharper and bigger, keeps the same look</em></span></label>
        <label class="toggle"><input type="checkbox" id="enhSmooth"><span class="track"><i></i></span><span class="toggle-text">Smooth motion<em>doubles the frames (for example 24 to 48 per second)</em></span></label>
      </div>
      <div class="go">
        <div class="estimate" id="enhEstimate" aria-live="polite">Choose a video first.</div>
        <button class="btn primary big" id="enhBtn" disabled>Enhance video<iconify-icon icon="solar:arrow-right-linear" aria-hidden="true"></iconify-icon></button>
      </div>
      <p class="hint">Sound is kept. The result appears in My videos. Long videos are split into short pieces, enhanced on both GPUs and joined again.</p>
    </div>
  </div>
</section>

<!-- ============================== GALLERY -->''', 1)
old = '''<a href="#gallery" data-page="gallery" title="My videos">'''
assert old in h
h = h.replace(old, '''<a href="#enhance" data-page="enhance" title="Enhance a video"><iconify-icon icon="solar:maximize-square-linear" aria-hidden="true"></iconify-icon><b>Enhance</b></a>
  ''' + old, 1)
open("web/index.html", "w", encoding="utf-8").write(h)

# ------------------------------------------------------------------ app.js
a = open("web/app.js", encoding="utf-8").read()
R = [
 ('const KIND = { t2v: ["From words", "From words"],', 'const KIND = { enhance: ["Enhance", "Enhance"], t2v: ["From words", "From words"],'),
 ('''  if (j.kind === "upscale" || j.kind === "interp") return KIND[j.kind][1] + ": " + (p.prompt || "video");''',
  '''  if (j.kind === "enhance") return `Enhance: ${p.title || "video"} (part ${p.index + 1} of ${p.total})`;
  if (j.kind === "upscale" || j.kind === "interp") return KIND[j.kind][1] + ": " + (p.prompt || "video");'''),
 ('''  if (page === "settings") renderSettings();''', '''  if (page === "settings") renderSettings();
  if (page === "queue") loadLibrary();'''),
 ('''    toast(`${r.jobs.length === 2 ? "2 videos" : "Video"} added to the queue`, "good");''',
  '''    toast(`${r.jobs.length === 2 ? "2 videos" : "Video"} added. <a class="link" data-goto="queue">See progress</a>`, "good");'''),
]
for o, n in R:
    assert o in a, o[:70]
    a = a.replace(o, n)
enh = r'''// ------------------------------------------------------------------ enhance (upload your own video)
let enhVideo = null;
const vdrop = $("#vdrop");
vdrop.onclick = () => $("#vfile").click();
vdrop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#vfile").click(); } };
vdrop.ondragover = e => { e.preventDefault(); vdrop.classList.add("over"); };
vdrop.ondragleave = () => vdrop.classList.remove("over");
vdrop.ondrop = e => { e.preventDefault(); vdrop.classList.remove("over"); if (e.dataTransfer.files[0]) uploadVideo(e.dataTransfer.files[0]); };
$("#vfile").onchange = () => { if ($("#vfile").files[0]) uploadVideo($("#vfile").files[0]); };
async function uploadVideo(file) {
  $("#enhEstimate").textContent = "Uploading and checking the video…";
  $("#enhBtn").disabled = true;
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await fetch("/api/upload-video", { method: "POST", body: fd }).then(r => r.json());
    if (r.error) throw new Error(r.error);
    enhVideo = r;
    $("#vPreview").src = "/uploads/" + r.name;
    $("#vdropEmpty").classList.add("hidden"); $("#vdropFull").classList.remove("hidden");
    $("#vinfo").classList.remove("hidden");
    $("#vinfo").innerHTML = `<span>${esc(r.title)}</span><span>${r.width}×${r.height}</span><span>${r.duration.toFixed(1)} s</span><span>${Math.round(r.fps)} fps</span><span>${r.audio ? "with sound" : "no sound"}</span><button class="btn small ghost" id="vChange">Choose another</button>`;
    $("#vChange").onclick = e => { e.stopPropagation(); $("#vfile").click(); };
    $("#enhUp").disabled = !r.can_upscale; if (!r.can_upscale) $("#enhUp").checked = false;
    $("#enhUpHint").textContent = r.can_upscale ? `sharper and bigger: ${r.width}×${r.height} becomes ${r.target_w}×${r.target_h}` : "this video is already 1080p or larger";
    renderEnhance();
  } catch (e) { enhVideo = null; $("#enhEstimate").textContent = e.message; toast("Could not use that video: " + esc(e.message), "bad"); }
}
function renderEnhance() {
  if (!enhVideo) return;
  const up = $("#enhUp").checked, sm = $("#enhSmooth").checked;
  $("#enhBtn").disabled = !(up || sm) || enhVideo.too_long;
  if (enhVideo.too_long) { $("#enhEstimate").innerHTML = `This video is ${enhVideo.duration.toFixed(0)} s. <b>Trim it to 60 seconds or less</b> (for example in CapCut) and try again.`; return; }
  if (!up && !sm) { $("#enhEstimate").textContent = "Switch on at least one option."; return; }
  const frames = enhVideo.duration * Math.min(enhVideo.fps, 30);
  const secs = frames * ((up ? 2.8 : 0) + (sm ? 0.35 : 0)) / 2 + 60;
  $("#enhEstimate").innerHTML = `About <b>${fmtMin(secs)}</b> using both GPUs` + (S && S.power !== "ready" ? "<br>The server is off: it will start once it's on." : "");
}
$("#enhUp").onchange = renderEnhance; $("#enhSmooth").onchange = renderEnhance;
$("#enhBtn").onclick = async () => {
  if (!enhVideo) return;
  const btn = $("#enhBtn"); btn.disabled = true;
  $("#enhEstimate").textContent = "Preparing the video…";
  try {
    const r = await api("/api/enhance", { json: { name: enhVideo.name, upscale: $("#enhUp").checked, smooth: $("#enhSmooth").checked } });
    toast(`Enhancing in ${r.parts} part${r.parts === 1 ? "" : "s"}. <a class="link" data-goto="queue">See progress</a>`, "good");
    if (S.power === "off" || S.power === "error") {
      if (await confirmBox("Turn on the server?", "The Kaggle GPU server is off. Turn it on now? It takes about 5 minutes, then the enhancing starts by itself.", "Turn on"))
        await api("/api/power", { json: { on: true } });
    }
    poll();
  } catch (e) { toast("Could not start: " + esc(e.message), "bad"); }
  renderEnhance();
};

'''
a = a.replace("// ------------------------------------------------------------------ prompt lab (interactive guide)", enh + "// ------------------------------------------------------------------ prompt lab (interactive guide)", 1)
assert "uploadVideo" in a
open("web/app.js", "w", encoding="utf-8").write(a)

# ------------------------------------------------------------------ style.css
c = open("web/style.css", encoding="utf-8").read()
c += '''
/* ===================== simpler Create page + Enhance page + Queue layout ===================== */
.create-grid { grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 24px; }
.settings-panel { padding: 26px; }
.settings-panel h2 { margin-bottom: 4px; }
.lbl.first { margin-top: 14px; }
.compose #prompt { min-height: 220px; font-size: 17px; }
.compose .go { border-top: 0; padding-top: 4px; }
.settings-panel .two-col { grid-template-columns: 1fr; gap: 0; }
.settings-panel .toggles { grid-template-columns: 1fr; }
.toggles.one { grid-template-columns: 1fr; margin-top: 12px; }
.queue-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(320px, 1fr); gap: 24px; align-items: start; }
#page-queue .mini-queue { display: none; }
.enhance-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 24px; align-items: start; }
.vdrop { margin-top: 0; }
.vdrop .drop-empty { padding: 64px 24px; }
.vdrop video { width: 100%; max-height: 52vh; display: block; background: #000; }
.vinfo { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 14px; font-size: 13px; }
.vinfo span { border: 1px solid var(--line); padding: 3px 10px; border-radius: 999px; color: var(--text-2); font-variant-numeric: tabular-nums; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.toggle input:disabled + .track { opacity: .4; }
@media (max-width: 1020px) { .queue-grid, .enhance-grid { grid-template-columns: minmax(0, 1fr); } .queue-grid .side-col { order: -1; position: static; display: flex; } }
@media (max-width: 760px) {
  .island a b { display: none; }
  .island a.active b { display: block; }
  .island a { padding: 9px 4px; }
  .queue-grid .side-col { display: flex; }
  .queue-grid .window { display: none; }
}
'''
open("web/style.css", "w", encoding="utf-8").write(c)
print("html/js/css ok")
