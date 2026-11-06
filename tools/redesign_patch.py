# One-off patch for the 2026-09-30 UI redesign (copy, markup and state hooks in app.js).
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))

h = open('index.html', encoding='utf-8').read()
h = h.replace('''</header>
<div class="flags" id="flags" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>''', '''  <div class="flags" id="flags" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
</header>''')
open('index.html', 'w', encoding='utf-8').write(h)

c = open('style.css', encoding='utf-8').read()
c = c.replace(".flags { position: sticky; top: 64px; z-index: 29; display: grid;", ".flags { position: absolute; left: 0; right: 0; bottom: -5px; display: grid;")
c = c.replace("  .flags { top: 104px; }\n", "")
open('style.css', 'w', encoding='utf-8').write(c)

a = open('app.js', encoding='utf-8').read()
R = [
('const QUALITY = { turbo: { steps: 6, cfg: 1, label: "⚡ Turbo" }', 'const QUALITY = { turbo: { steps: 6, cfg: 1, label: "Turbo" }'),
('''  const p = S.power, L = S.live, box = $("#power");
  box.className = "power " + p;''', '''  const p = S.power, L = S.live, box = $("#power");
  box.className = "power " + p;
  document.body.dataset.power = p;
  document.body.dataset.busy = S.jobs.some(j => ["uploading", "running", "downloading"].includes(j.status)) ? "1" : "0";'''),
('''    $("#quotaVal").textContent = left.toFixed(1) + " h";
    $("#quotaRing").style.strokeDashoffset = 97.4 * (1 - left / q.total_h);''', '''    $("#quotaVal").textContent = left.toFixed(1) + " GPU h";
    $("#quotaRing").style.width = (100 * left / q.total_h).toFixed(1) + "%";'''),
('? `Auto-off in ${fmtMin(S.idle_left)} if unused`', '? `Turns off in ${fmtMin(S.idle_left)} if unused`'),
('toast(`✅ ${what} is ready', 'toast(`${what} is ready'),
('} else toast(`❌ ${what} failed:', '} else toast(`${what} failed:'),
('const KIND = { t2v: ["✍️", "Text → Video"], i2v: ["🖼️", "Photo → Video"], upscale: ["🔍", "Upscale to 1080p"], interp: ["🌊", "Smooth 2×"] };',
 'const KIND = { t2v: ["From words", "From words"], i2v: ["From a photo", "From a photo"], upscale: ["1080p", "Upscale to 1080p"], interp: ["Smooth", "Smooth to 48 fps"] };'),
('''      <div class="job-icon">${KIND[j.kind][0]}</div>''', '''      <div class="job-kind">${j.params.demo ? "Demo" : KIND[j.kind][0]}</div>'''),
('''    <div class="mq"><div class="mq-top"><span>${KIND[j.kind][0]} ${esc(jobLine(j))}</span>''', '''    <div class="mq"><div class="mq-top"><span>${esc(jobLine(j))}</span>'''),
('''+${active.length - 4} more in the queue →</a>''', '''${active.length - 4} more in the queue</a>'''),
('`<div class="empty">No jobs yet.</div>`', '`<div class="empty">Nothing in the queue. Videos you make show up here.</div>`'),
('btn.disabled = true; btn.textContent = "✨ Improving…";', 'btn.disabled = true; btn.textContent = "Improving… (about 40 s)";'),
('btn.disabled = false; btn.textContent = "✨ Improve my prompt";', 'btn.disabled = false; btn.textContent = "Improve my prompt";'),
('toast("✨ Prompt improved by AI", "good");', 'toast("Prompt improved", "good");'),
('toast(`🎬 ${r.jobs.length === 2 ? "2 videos" : "Video"} added to the queue`, "good");', 'toast(`${r.jobs.length === 2 ? "2 videos" : "Video"} added to the queue`, "good");'),
('''Short prompts often give random results. Press <b>✨ Improve my prompt</b> first, or generate anyway?", "Generate anyway"''', '''Short prompts often give random results. Press <b>Improve my prompt</b> first, or make it anyway?", "Make it anyway"'''),
('`<button data-c="all" class="${tplCat === "all" ? "on" : ""}">All (${TEMPLATES.length})</button>` +\n    TEMPLATE_CATEGORIES.map(c => `<button data-c="${c.id}" class="${tplCat === c.id ? "on" : ""}">${c.icon} ${c.name}</button>`).join("");',
 '`<button data-c="all" class="${tplCat === "all" ? "on" : ""}">All ${TEMPLATES.length}</button>` +\n    TEMPLATE_CATEGORIES.map(c => `<button data-c="${c.id}" class="${tplCat === c.id ? "on" : ""}">${c.name}</button>`).join("");'),
('''      <div class="thumb" data-use="${t.id}">
        ${demos.has(t.id) ? `<video src="/demos/${t.id}.mp4" muted loop playsinline preload="metadata"></video>` : `<div class="ph">${icon(t.cat)}</div>`}
        <span class="tag">${t.aspect}</span>${demos.has(t.id) ? `<span class="tag r">▶ demo</span>` : ""}
      </div>
      <div class="tbody"><b>${esc(t.title)}</b><p>${esc(t.prompt)}</p>
        <div class="row"><button class="btn small" data-use="${t.id}">Use</button><button class="btn small primary" data-gen="${t.id}">Generate now</button></div></div>''',
 '''      <button class="thumb" data-use="${t.id}" aria-label="Use the ${esc(t.title)} template">
        ${demos.has(t.id) ? `<video src="/demos/${t.id}.mp4" muted loop playsinline preload="metadata" aria-hidden="true"></video>` : `<span class="tile c-${t.cat}">${esc(t.title)}</span>`}
        <span class="tag">${t.aspect}</span>${demos.has(t.id) ? `<span class="tag r">Demo</span>` : ""}
      </button>
      <div class="tbody"><b>${esc(t.title)}</b><p>${esc(t.prompt)}</p>
        <div class="row"><button class="btn small" data-use="${t.id}">Use</button><button class="btn small primary" data-gen="${t.id}">Make now</button></div></div>'''),
('''$("#makeDemosBtn").textContent = missing ? `🎞️ Make ${missing} missing demos` : "🎞️ All demos made";''', '''$("#makeDemosBtn").textContent = missing ? `Make ${missing} missing demos` : "All demos made";'''),
('toast(`🎞️ ${missing.length} demos queued`, "good");', 'toast(`${missing.length} demos queued`, "good");'),
('''      <div class="thumb" data-view="${x.id}" style="aspect-ratio:${x.aspect === "9:16" ? "9/16" : x.aspect === "1:1" ? "1/1" : "16/9"}">
        <video src="/media/${encodeURIComponent(x.file)}#t=0.5" muted loop playsinline preload="metadata"></video>
        <span class="tag">${x.res || "720p"}${x.fps > 24 ? " · " + x.fps + "fps" : ""}</span>${x.favorite ? `<span class="star">⭐</span>` : ""}
      </div>
      <div class="tbody"><p>${esc(x.prompt)}</p><span class="hint">${ago(x.created)} · ${x.seconds || "?"} s · seed ${x.seed ?? "–"}</span></div>''',
 '''      <button class="thumb" data-view="${x.id}" aria-label="Open video" style="aspect-ratio:${x.aspect === "9:16" ? "9/16" : x.aspect === "1:1" ? "1/1" : "16/9"}">
        <video src="/media/${encodeURIComponent(x.file)}#t=0.5" muted loop playsinline preload="metadata" aria-hidden="true"></video>
        <span class="tag">${x.res || "720p"}${x.fps > 24 ? ", " + x.fps + " fps" : ""}</span>${x.favorite ? `<span class="star" aria-label="Favourite">★</span>` : ""}
      </button>
      <div class="tbody"><p>${esc(x.prompt)}</p><span class="hint num">${ago(x.created)}, ${x.seconds || "?"} s, seed ${x.seed ?? "–"}</span></div>'''),
('`<div class="empty">No videos yet. Make one on the Create page.</div>`', '`<div class="empty">No videos yet. Make one on the Create page, or start from a template.</div>`'),
('$("#vTitle").textContent = cur.kind === "upscale" ? "1080p upscale" : cur.kind === "interp" ? "Smooth version" : cur.kind === "i2v" ? "Photo → Video" : "Text → Video";',
 '$("#vTitle").textContent = cur.kind === "upscale" ? "1080p upscale" : cur.kind === "interp" ? "Smooth version" : cur.kind === "i2v" ? "Made from a photo" : "Made from words";'),
('["Made", new Date(cur.created * 1000).toLocaleString()]', '["Made", DTF.format(new Date(cur.created * 1000))]'),
('$("#vFav").textContent = cur.favorite ? "⭐ Favourite" : "☆ Favourite";\n  $("#vUpscale")', '$("#vFav").textContent = cur.favorite ? "Remove from favourites" : "Add to favourites";\n  $("#vUpscale")'),
('$("#vFav").textContent = cur.favorite ? "⭐ Favourite" : "☆ Favourite"; renderGallery(); };', '$("#vFav").textContent = cur.favorite ? "Remove from favourites" : "Add to favourites"; renderGallery(); };'),
('toast("🎲 2 variations added to the queue", "good");', 'toast("2 variations added to the queue", "good");'),
('toast("🔍 1080p upscale added to the queue", "good");', 'toast("1080p upscale added to the queue", "good");'),
('toast("🌊 Smooth version added to the queue", "good");', 'toast("Smooth version added to the queue", "good");'),
('''const ago = t => { const s = Date.now() / 1000 - t; return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : new Date(t * 1000).toLocaleDateString(); };''',
 '''const DTF = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const ago = t => { const s = Date.now() / 1000 - t; return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : DTF.format(new Date(t * 1000)); };'''),
('`Used ${q.used_h.toFixed(1)} of ${q.total_h} free GPU hours this week` + (q.refresh ? ` · resets ${new Date(q.refresh + "Z").toLocaleString()}` : "")',
 '`Used ${q.used_h.toFixed(1)} of ${q.total_h} free GPU hours this week` + (q.refresh ? `. Resets ${DTF.format(new Date(q.refresh + "Z"))}` : "")'),
('drop.onclick = e => { if (!e.target.closest("#dropClear")) $("#fileInput").click(); };',
 'drop.onclick = e => { if (!e.target.closest("#dropClear")) $("#fileInput").click(); };\ndrop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } };'),
]
missing = [o[:70] for o, n in R if o not in a]
if missing:
    raise SystemExit("not found: " + repr(missing))
for o, n in R:
    a = a.replace(o, n)
open('app.js', 'w', encoding='utf-8').write(a)
print("patched", len(R))
