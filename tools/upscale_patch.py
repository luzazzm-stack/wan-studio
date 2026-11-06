# Makes 1080p upscaling and Smooth visible: a Resolution choice on Create (auto-upscale), plus buttons on every video.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

h = open("web/index.html", encoding="utf-8").read()
old = '''          <div class="lbl">Quality <span class="hint">all 720p</span></div>'''
assert old in h
h = h.replace(old, '''          <div class="lbl">Quality</div>''')
old = '''      <div class="toggles">'''
assert old in h
h = h.replace(old, '''      <div class="lbl">Resolution <span class="hint" id="resHint">720p is what Wan makes</span></div>
      <div class="seg" id="resSeg" role="radiogroup" aria-label="Resolution">
        <button data-r="720" class="on" role="radio">720p</button>
        <button data-r="1080" role="radio"><iconify-icon icon="solar:maximize-square-linear" aria-hidden="true"></iconify-icon>1080p upscaled</button>
        <button data-r="1080s" role="radio"><iconify-icon icon="solar:stars-minimalistic-linear" aria-hidden="true"></iconify-icon>1080p + smooth 48 fps</button>
      </div>

      <div class="toggles">''', 1)
open("web/index.html", "w", encoding="utf-8").write(h)

a = open("web/app.js", encoding="utf-8").read()
R = [
 ('''  if (form.mode === "i2v") p.image = form.image;
  return p;''', '''  if (form.mode === "i2v") p.image = form.image;
  p.upscale = form.res !== "720"; p.smooth = form.res === "1080s";
  return p;'''),
 ('''  let txt = `About <b>${fmtMin(one)}</b> per video`;''', '''  const extra = (p.upscale ? 340 : 0) + (p.smooth ? 150 : 0);
  let txt = `About <b>${fmtMin(one + extra)}</b> per video` + (extra ? ` (${fmtMin(one)} to make it, ${fmtMin(extra)} to upscale${p.smooth ? " and smooth" : ""})` : "");'''),
 ('''<span class="hint num">${ago(x.created)}, ${x.seconds || "?"} s, seed ${x.seed ?? "–"}</span></div>''',
  '''<span class="hint num">${ago(x.created)}, ${x.seconds || "?"} s, seed ${x.seed ?? "–"}</span>
        <div class="row card-actions"><button class="btn small" data-up="${x.id}" ${x.res === "1080p" ? "disabled" : ""}>${x.res === "1080p" ? "Already 1080p" : "Upscale to 1080p"}</button><button class="btn small" data-smooth="${x.id}" ${(x.fps || 24) > 24 ? "disabled" : ""}>${(x.fps || 24) > 24 ? "Already smooth" : "Smooth 48 fps"}</button></div></div>'''),
 ('''<button class="btn small" data-open="${x.id}">Open</button>`;''',
  '''<div class="row"><button class="btn small" data-open="${x.id}">Open</button><button class="btn small" data-up="${x.id}" ${x.res === "1080p" ? "disabled" : ""}>Upscale to 1080p</button><button class="btn small" data-smooth="${x.id}" ${(x.fps || 24) > 24 ? "disabled" : ""}>Smooth 48 fps</button></div>`;'''),
 ('''const form = { mode: "t2v", aspect: "16:9", quality: "standard", image: null, imageUrl: null, template: null };''',
  '''const form = { mode: "t2v", aspect: "16:9", quality: "standard", res: "720", image: null, imageUrl: null, template: null };'''),
 ('''$("#cfg").oninput = () =>''', '''$$("#resSeg button").forEach(b => b.onclick = () => {
  form.res = b.dataset.r; $$("#resSeg button").forEach(x => x.classList.toggle("on", x === b));
  $("#resHint").textContent = { "720": "720p is what Wan makes", "1080": "made at 720p, then sharpened to 1080p (+6 min)", "1080s": "1080p, plus doubled frames for smoother motion (+8 min)" }[form.res];
  renderEstimate();
});
$("#cfg").oninput = () =>'''),
 ('''  if (c) { await api(`/api/jobs/${c.dataset.cancel}/cancel`''', '''  const up = e.target.closest("[data-up]"), sm = e.target.closest("[data-smooth]");
  if (up && !up.disabled) { await api("/api/process", { json: { kind: "upscale", source: up.dataset.up } }); toast("1080p upscale added to the queue (about 6 min)", "good"); up.disabled = true; up.textContent = "Queued"; }
  if (sm && !sm.disabled) { await api("/api/process", { json: { kind: "interp", source: sm.dataset.smooth } }); toast("Smooth version added to the queue (about 1 min)", "good"); sm.disabled = true; sm.textContent = "Queued"; }
  if (c) { await api(`/api/jobs/${c.dataset.cancel}/cancel`'''),
]
for o, n in R:
    assert o in a, o[:70]
    a = a.replace(o, n)
open("web/app.js", "w", encoding="utf-8").write(a)

s = open("server.py", encoding="utf-8").read()
R = [
 ('''"cfg": float(d.get("cfg", settings["cfg"])), "template": d.get("template"), "image": d.get("image"), "demo": d.get("demo")}''',
  '''"cfg": float(d.get("cfg", settings["cfg"])), "template": d.get("template"), "image": d.get("image"), "demo": d.get("demo"),
            "upscale": bool(d.get("upscale")), "smooth": bool(d.get("smooth"))}'''),
 ('''            await blocking(make_thumb, os.path.join(settings["output_dir"], name), os.path.join(THUMBS, item["id"] + ".jpg"))''',
  '''            await blocking(make_thumb, os.path.join(settings["output_dir"], name), os.path.join(THUMBS, item["id"] + ".jpg"))
            # "1080p" / "1080p + smooth" chosen on Create: chain the follow-up step automatically.
            if j["kind"] in ("t2v", "i2v") and p.get("upscale"):
                new_job("upscale", {"source": item["id"], "prompt": p.get("prompt", ""), "then_smooth": bool(p.get("smooth"))})
            elif j["kind"] == "upscale" and p.get("then_smooth"):
                new_job("interp", {"source": item["id"], "prompt": p.get("prompt", "")})'''),
]
for o, n in R:
    assert o in s, o[:70]
    s = s.replace(o, n)
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)

c = open("web/style.css", encoding="utf-8").read()
c += '''
/* upscale / smooth actions */
.card-actions { margin-top: 6px; }
.vcard .card-actions .btn { flex: 1; }
#resSeg button { font-size: 13px; padding: 9px 8px; }
@media (max-width: 760px) { #resSeg { flex-direction: column; border-radius: 20px; } }
'''
open("web/style.css", "w", encoding="utf-8").write(c)
print("ok")
