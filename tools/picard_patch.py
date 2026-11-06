# Moves "Make a picture first" into its own Pictures card at the bottom right of the home page.
import os, re
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def rep(s, old, new, label):
    assert old in s, label
    return s.replace(old, new, 1)


h = open("web/index.html", encoding="utf-8").read()
h = rep(h, '''      <div class="improve-opts hidden" id="picOpts" aria-live="polite"></div>\n''', "", "picOpts")
h = rep(h, '''        <button class="btn glass-btn" id="makePicBtn"><iconify-icon icon="solar:gallery-add-linear" aria-hidden="true"></iconify-icon><span>Make a picture first</span></button>\n''', "", "makePicBtn")
h = rep(h, '''    <div class="glass panel settings-panel">''', '''    <div class="right-col">
    <div class="glass panel settings-panel">''', "right-col open")
h = rep(h, '''      </details>

    </div>

  </div>
</section>''', '''      </details>

    </div>

    <section class="glass panel pictures" id="picCard" aria-label="Pictures">
      <div class="pics-head">
        <h2><iconify-icon icon="solar:gallery-add-linear" aria-hidden="true"></iconify-icon>Pictures</h2>
        <span class="hint">Free, made with NVIDIA FLUX</span>
      </div>
      <p class="hint">Make a picture, then press <b>Animate</b> to turn it into a video. Starting from a picture gives you more control over how the video looks.</p>
      <textarea id="picPrompt" rows="3" autocomplete="off" placeholder="Describe the picture: e.g. a cozy coffee shop counter with a latte, morning sunlight through the window" aria-label="Describe the picture"></textarea>
      <div class="row pics-actions">
        <button class="btn small ghost" id="picFromPrompt">Use my video prompt</button>
        <span class="hint" id="picShape"></span>
        <button class="btn primary" id="picMake"><iconify-icon icon="solar:magic-stick-3-linear" aria-hidden="true"></iconify-icon><span>Make 2 pictures</span></button>
      </div>
      <div class="pic-grid" id="picGrid" aria-live="polite"></div>
    </section>
    </div>

  </div>
</section>''', "right-col close")
open("web/index.html", "w", encoding="utf-8").write(h)

a = open("web/app.js", encoding="utf-8").read()
a0 = a.index("// 1) picture first, then video")
a1 = a.index("// 5) suggest motion from the photo")
a = a[:a0] + '''// 1) Pictures card: make a picture, then animate it
const SHAPE_NAME = { "16:9": "wide 16:9", "9:16": "tall 9:16", "1:1": "square 1:1" };
function renderPicShape() { $("#picShape").textContent = "Shape: " + SHAPE_NAME[form.aspect]; }
$$("#aspects button").forEach(b => b.addEventListener("click", renderPicShape));
renderPicShape();
$("#picFromPrompt").onclick = () => {
  if (!promptEl.value.trim()) { toast("Your video prompt is empty"); return; }
  $("#picPrompt").value = promptEl.value.trim();
};
$("#picMake").onclick = async () => {
  const idea = $("#picPrompt").value.trim();
  if (!idea) { toast("Describe the picture first"); $("#picPrompt").focus(); return; }
  const btn = $("#picMake"), grid = $("#picGrid");
  btn.disabled = true; btn.querySelector("span").textContent = "Making…";
  grid.innerHTML = `<div class="pic skeleton ar-${form.aspect.replace(":", "x")}"></div>`.repeat(2);
  try {
    const r = await api("/api/make-image", { json: { prompt: idea, aspect: form.aspect, count: 2 } });
    grid.innerHTML = r.images.map(n => `<figure class="pic">
        <img src="/uploads/${esc(n)}" alt="Generated picture" width="${r.width}" height="${r.height}">
        <figcaption><button class="btn small primary" data-animate="${esc(n)}">Animate</button>
        <a class="btn small glass-btn" href="/uploads/${esc(n)}" download="${esc(n)}">Download</a></figcaption></figure>`).join("");
  } catch (e) { grid.innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  finally { btn.disabled = false; btn.querySelector("span").textContent = "Make 2 pictures"; }
};
$("#picGrid").onclick = e => {
  const b = e.target.closest("[data-animate]"); if (!b) return;
  $('#modeSeg button[data-mode="i2v"]').click();
  showPhoto(b.dataset.animate);
  if (!promptEl.value.trim() || promptEl.value.trim() === $("#picPrompt").value.trim()) promptEl.value = "";
  analyze(); window.scrollTo({ top: 0, behavior: "smooth" }); promptEl.focus();
  toast("Picture added. Describe how it should move, or press Suggest motion.", "good");
};

''' + a[a1:]
assert "makePicBtn" not in a and "picOpts" not in a
open("web/app.js", "w", encoding="utf-8").write(a)

c = open("web/style.css", encoding="utf-8").read()
c += '''
/* Pictures card (home, bottom right) */
.right-col { display: flex; flex-direction: column; gap: 24px; min-width: 0; }
.pictures { padding: 26px; display: grid; gap: 12px; }
.pics-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.pics-head h2 { margin: 0; display: flex; align-items: center; gap: 8px; }
.pics-head h2 iconify-icon { color: var(--accent); }
.pictures p { margin: 0; }
.pics-actions { justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.pictures .pic { margin: 0; cursor: default; display: flex; flex-direction: column; }
.pictures .pic figcaption { display: flex; gap: 6px; padding: 8px; justify-content: center; }
.pic.ar-16x9 { aspect-ratio: 16 / 9; } .pic.ar-9x16 { aspect-ratio: 9 / 16; } .pic.ar-1x1 { aspect-ratio: 1; }
'''
open("web/style.css", "w", encoding="utf-8").write(c)
print("ok")
