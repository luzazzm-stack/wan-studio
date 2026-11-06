# Adds the "Animate" page (photo + motion video -> character performs the motion) to the Wan Studio UI.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def patch(path, pairs, append=None):
    s = open(path, encoding="utf-8").read()
    for o, n in pairs:
        assert o in s, (path, o[:70])
        s = s.replace(o, n, 1)
    if append:
        s += append
    open(path, "w", encoding="utf-8").write(s)


# ---------------- HTML
patch("web/index.html", [
    ('''  <a href="#enhance" data-page="enhance" title="Enhance a video">''',
     '''  <a href="#animate" data-page="animate" title="Animate a character"><iconify-icon icon="solar:running-round-linear" aria-hidden="true"></iconify-icon><b>Animate</b></a>
  <a href="#enhance" data-page="enhance" title="Enhance a video">'''),
    ('''<section class="page" id="page-enhance">''', '''<section class="page" id="page-animate">
  <div class="page-head"><div><h1>Animate a character</h1><p>Your character copies the moves of any video. Runs on its own GPU.</p></div></div>
  <div class="enhance-grid">
    <div class="glass panel">
      <div class="anim-drops">
        <div class="drop" id="aImgDrop" role="button" tabindex="0" aria-label="Choose the character photo">
          <input type="file" id="aImgFile" accept="image/png,image/jpeg,image/webp" hidden>
          <div class="drop-empty" id="aImgEmpty"><iconify-icon icon="solar:user-rounded-linear" class="drop-icon" aria-hidden="true"></iconify-icon><b>1. Character photo</b><span>A clear, full-body photo works best</span></div>
          <div class="drop-full hidden" id="aImgFull"><img id="aImgPrev" alt="Character photo"></div>
        </div>
        <div class="drop" id="aVidDrop" role="button" tabindex="0" aria-label="Choose the motion video">
          <input type="file" id="aVidFile" accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm,.mkv" hidden>
          <div class="drop-empty" id="aVidEmpty"><iconify-icon icon="solar:videocamera-record-linear" class="drop-icon" aria-hidden="true"></iconify-icon><b>2. Motion video</b><span>Someone dancing, walking, talking… (first 5 s are used)</span></div>
          <div class="drop-full hidden" id="aVidFull"><video id="aVidPrev" muted loop playsinline autoplay></video></div>
        </div>
      </div>
      <label class="lbl" for="aPrompt">Describe the scene <span class="hint">optional</span></label>
      <textarea id="aPrompt" rows="3" placeholder="Example: a smiling trekking guide with a big mustache dancing on a mountain ridge, sunny day"></textarea>
    </div>
    <div class="glass panel">
      <h2>Settings</h2>
      <div class="lbl">Shape</div>
      <div class="seg small" id="aShape" role="radiogroup" aria-label="Shape">
        <button data-a="9:16" class="on" role="radio">Portrait<small>Reels · 480×832</small></button>
        <button data-a="16:9" role="radio">Landscape<small>832×480</small></button>
        <button data-a="1:1" role="radio">Square<small>640×640</small></button>
      </div>
      <div class="lbl">Length</div>
      <div class="seg small" id="aLen" role="radiogroup" aria-label="Length">
        <button data-s="3" role="radio">3 seconds<small>faster</small></button>
        <button data-s="5" class="on" role="radio">5 seconds<small>uses more GPU time</small></button>
      </div>
      <div class="go">
        <div class="estimate" id="aEstimate" aria-live="polite">Choose a photo and a video.</div>
        <button class="btn primary big" id="aBtn" disabled>Animate<iconify-icon icon="solar:arrow-right-linear" aria-hidden="true"></iconify-icon></button>
      </div>
      <p class="hint">Runs on GPU 2 (GPU 1 keeps making normal videos). The motion video's sound is kept. Results appear in My videos.</p>
    </div>
  </div>
</section>

<section class="page" id="page-enhance">'''),
])

# ---------------- JS
patch("web/app.js", [
    ('''const KIND = { enhance: ["Enhance", "Enhance"],''', '''const KIND = { animate: ["Animate", "Animate"], enhance: ["Enhance", "Enhance"],'''),
], append='''
// ------------------------------------------------------------------ Animate (Wan 2.2 Animate on GPU 2)
const anim = { image: null, video: null, aspect: "9:16", seconds: 5, dur: 0 };
function animReady() {
  const ok = anim.image && anim.video;
  $("#aBtn").disabled = !ok;
  if (!ok) { $("#aEstimate").textContent = !anim.image ? "Choose a character photo." : "Choose a motion video."; return; }
  const secs = anim.seconds === 5 && anim.dur >= 4.9 ? 5 : 3;
  const mins = Math.round((300 + 9 * (secs * 16 + 1)) / 60);
  $("#aEstimate").textContent = `About ${mins} min on GPU 2 · ${secs} s at 480p` + (anim.seconds === 5 && secs === 3 ? " (your video is shorter than 5 s)" : "");
}
function animPick(dropId, fileId, onFile) {
  const d = $(dropId), f = $(fileId);
  d.onclick = () => f.click();
  d.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); f.click(); } };
  d.ondragover = e => { e.preventDefault(); d.classList.add("over"); };
  d.ondragleave = () => d.classList.remove("over");
  d.ondrop = e => { e.preventDefault(); d.classList.remove("over"); if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]); };
  f.onchange = () => { if (f.files[0]) onFile(f.files[0]); f.value = ""; };
}
animPick("#aImgDrop", "#aImgFile", async file => {
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd }).then(r => r.json());
    if (r.error) throw new Error(r.error);
    anim.image = r.name; $("#aImgPrev").src = "/uploads/" + r.name;
    $("#aImgEmpty").classList.add("hidden"); $("#aImgFull").classList.remove("hidden");
  } catch (e) { toast("Upload failed: " + esc(e.message), "bad"); }
  animReady();
});
animPick("#aVidDrop", "#aVidFile", async file => {
  $("#aEstimate").textContent = "Uploading the video…";
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await fetch("/api/upload-video", { method: "POST", body: fd }).then(r => r.json());
    if (r.error) throw new Error(r.error);
    anim.video = r.name; anim.dur = r.duration || 0; $("#aVidPrev").src = "/uploads/" + r.name;
    $("#aVidEmpty").classList.add("hidden"); $("#aVidFull").classList.remove("hidden");
  } catch (e) { toast("Upload failed: " + esc(e.message), "bad"); }
  animReady();
});
$$("#aShape button").forEach(b => b.onclick = () => { anim.aspect = b.dataset.a; $$("#aShape button").forEach(x => x.classList.toggle("on", x === b)); animReady(); });
$$("#aLen button").forEach(b => b.onclick = () => { anim.seconds = +b.dataset.s; $$("#aLen button").forEach(x => x.classList.toggle("on", x === b)); animReady(); });
$("#aBtn").onclick = async () => {
  try {
    await api("/api/animate", { json: { image: anim.image, video: anim.video, aspect: anim.aspect, seconds: anim.seconds, prompt: $("#aPrompt").value } });
    toast("Added to the queue (GPU 2)", "good"); go("queue");
  } catch (e) { toast(esc(e.message), "bad"); }
};
''')

# ---------------- CSS
patch("web/style.css", [], append='''
/* Animate page */
.anim-drops { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 18px; }
.anim-drops .drop { min-height: 300px; }
.anim-drops .drop-full img, .anim-drops .drop-full video { width: 100%; height: 300px; object-fit: contain; border-radius: 18px; background: #000; display: block; }
@media (max-width: 760px) { .anim-drops { grid-template-columns: 1fr; } }
''')
print("ui ok")
