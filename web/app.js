// Wan Studio front end.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const QUALITY = { turbo: { steps: 6, cfg: 1, label: "Turbo" }, quality: { steps: 10, cfg: 1, label: "Quality" }, standard: { steps: 20, label: "Standard" }, high: { steps: 30, label: "High" } };

let S = null;                 // last /api/state
let library = [];
let demos = new Set();
let seenDone = null;          // job ids already known to be finished
const form = { mode: "t2v", aspect: "16:9", quality: "standard", res: "720", image: null, imageUrl: null, template: null };

// ------------------------------------------------------------------ helpers
async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) { o.method = o.method || "POST"; o.headers = { "Content-Type": "application/json" }; o.body = JSON.stringify(o.json); delete o.json; }
  const r = await fetch(path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok && d.signin && typeof showSignIn === "function") showSignIn();
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind; t.innerHTML = msg;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 5200);
}
function confirmBox(title, text, okLabel = "OK") {
  return new Promise(res => {
    $("#cTitle").textContent = title; $("#cText").innerHTML = text; $("#cOk").textContent = okLabel;
    const m = $("#confirm"); m.classList.remove("hidden");
    const done = v => { m.classList.add("hidden"); $("#cOk").onclick = null; m.onclick = null; res(v); };
    $("#cOk").onclick = () => done(true);
    m.onclick = e => { if (e.target === m || e.target.closest("[data-close]")) done(false); };
  });
}
const fmtMin = s => s < 90 ? `${Math.max(1, Math.round(s))} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
const DTF = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const ago = t => { const s = Date.now() / 1000 - t; return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : DTF.format(new Date(t * 1000)); };
const frames = sec => sec * 24 + 1;
function estimate(p) {
  const rate = (S && S.rate) || 0.55;
  const q = QUALITY[p.quality] || QUALITY.standard;
  const eff = q.steps * (q.cfg === 1 ? 0.9 : 1);
  return rate * frames(p.seconds) * eff + 30 + 1.2 * frames(p.seconds);
}

// ------------------------------------------------------------------ navigation
function go(page) {
  $$("#nav a").forEach(a => a.classList.toggle("active", a.dataset.page === page));
  $$(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + page));
  if (location.hash !== "#" + page) history.replaceState(null, "", "#" + page);
  if (page === "gallery") loadLibrary();
  if (page === "templates") renderTemplates();
  if (page === "settings") { renderSettings(); renderKeys(); }
  if (page === "queue") loadLibrary();
  if (page === "help") { labCheck(); renderMoves(); renderCalc(); } else { const mv = $("#moveVideo"); if (mv) mv.pause(); }
  window.scrollTo({ top: 0 });
}
$$("#nav a, a.logo").forEach(a => a.onclick = e => { e.preventDefault(); go(a.dataset.page); });
window.addEventListener("hashchange", () => { const p = location.hash.slice(1); if ($("#page-" + p) && !$("#page-" + p).classList.contains("active")) go(p); });
document.addEventListener("click", e => { const g = e.target.closest("[data-goto]"); if (g) go(g.dataset.goto); });

// ------------------------------------------------------------------ state polling + top bar
async function poll() {
  try {
    S = await api("/api/state");
    renderTop(); renderJobs(); checkFinished(); renderEstimate(); maybeSignIn();
  } catch (e) { /* offline: keep last state */ }
  setTimeout(poll, document.hidden ? 8000 : 2000);
}

const STAGE_TEXT = {
  queued: "Asking Kaggle for 2 GPUs", booting: "Starting up", installing: "Installing software", downloading: "Downloading Wan 2.2",
  starting: "Starting both GPUs", warming: "Loading the model into both GPUs", ready: "Ready", stopping: "Turning off",
};
function renderTop() {
  const p = S.power, L = S.live, box = $("#power");
  box.className = "server glass " + p;
  const dp = $("#dockPower"); dp.className = "dock-power " + p; dp.setAttribute("aria-checked", p === "ready" || p === "starting" ? "true" : "false");
  document.body.dataset.power = p;
  const act = $("#activity"); if (act) act.className = "glass panel activity " + p;
  document.body.dataset.busy = S.jobs.some(j => ["uploading", "running", "downloading"].includes(j.status)) ? "1" : "0";
  document.body.dataset.power = p;
  document.body.dataset.busy = S.jobs.some(j => ["uploading", "running", "downloading"].includes(j.status)) ? "1" : "0";
  $("#powerSwitch").setAttribute("aria-checked", p === "ready" || p === "starting" ? "true" : "false");
  const bar = $("#powerBar");
  bar.classList.toggle("hidden", p !== "starting");
  if (p === "off") {
    $("#powerTitle").textContent = "Server off";
    $("#powerSub").textContent = S.last_stop_reason ? S.last_stop_reason : "Turn on to make videos (takes ~5 min)";
  } else if (p === "starting") {
    $("#powerTitle").textContent = "Starting… " + (L.pct || 0) + "%";
    $("#powerSub").textContent = (STAGE_TEXT[L.stage] || L.stage || "Starting") + (L.detail && L.stage === "downloading" ? " · " + L.detail : "");
    $("#powerBarFill").style.width = (L.pct || 2) + "%";
  } else if (p === "ready") {
    const busy = S.jobs.some(j => ["uploading", "running", "downloading"].includes(j.status));
    $("#powerTitle").textContent = busy ? "Working" : "Ready";
    $("#powerSub").textContent = busy ? "Making videos…" : (S.idle_left != null ? `Turns off in ${fmtMin(S.idle_left)} if unused` : "Ready");
  } else if (p === "stopping") {
    $("#powerTitle").textContent = "Turning off…"; $("#powerSub").textContent = "Stopping the Kaggle GPUs";
  } else if (p === "error") {
    $("#powerTitle").textContent = "Problem"; $("#powerSub").textContent = (S.error || "Something went wrong").slice(0, 140);
    $("#powerSub").title = S.error || "";
  }
  // GPUs
  $("#homeStatus").textContent = $("#powerTitle").textContent;
  $("#homeSub").textContent = $("#powerSub").textContent;
  $("#homePower").textContent = p === "ready" || p === "starting" ? "Turn off" : p === "stopping" ? "Stopping…" : "Turn on";
  $("#homePower").disabled = p === "stopping";
  $$(".gpu[data-g]").forEach(el => {
    const g = +el.dataset.g;
    const job = S.jobs.find(j => j.gpu === g && ["uploading", "running", "downloading"].includes(j.status));
    el.classList.toggle("idle", p === "ready" && !job);
    el.classList.toggle("busy", !!job);
    $(".gpu-fill", el).style.width = job ? (job.status === "running" ? Math.max(4, Math.round((job.progress || 0) * 100)) : 100) + "%" : "0%";
    $(".gpu-val", el).textContent = job ? (job.status === "running" ? (job.phase === "finishing" ? "saving" : job.progress ? Math.round(job.progress * 100) + "%" : "starting") : job.status) : p === "ready" ? "idle" : p === "starting" ? "…" : "off";
  });
  // quota
  const q = S.quota;
  if (q && q.total_h) {
    const left = Math.max(0, q.total_h - q.used_h - (q.reserved_h || 0));
    $("#quotaVal").textContent = left.toFixed(1) + " h";
    $("#quotaRing").style.width = (100 * left / q.total_h).toFixed(1) + "%";
    $("#quota").title = `Used ${q.used_h.toFixed(1)} of ${q.total_h} free GPU hours this week` + (q.refresh ? `. Resets ${DTF.format(new Date(q.refresh + "Z"))}` : "");
  }
  document.documentElement.dataset.theme = S.settings.theme || "dark";
  $$(".local-only").forEach(el => el.classList.toggle("hidden", !S.local));
}

$("#powerSwitch").onclick = async () => {
  const p = S?.power;
  if (p === "ready" || p === "starting") {
    const active = S.jobs.filter(j => ["uploading", "running", "downloading"].includes(j.status)).length;
    const ok = await confirmBox("Turn off the server?", active
      ? `<b>${active} video(s) are being made right now.</b> They will be stopped and will start again next time you turn the server on.`
      : "This stops the Kaggle GPUs so they don't use your free hours.", "Turn off");
    if (!ok) return;
    await api("/api/power", { json: { on: false } });
    toast("Turning off…");
  } else {
    if (needsSignIn()) return showSignIn();
    await api("/api/power", { json: { on: true } });
    toast("Starting the Kaggle server. It takes about 5 minutes. You can queue videos now.");
  }
  setTimeout(poll, 400);
};

// ------------------------------------------------------------------ job finished detection
function checkFinished() {
  const done = S.jobs.filter(j => ["done", "failed"].includes(j.status));
  if (seenDone === null) { seenDone = new Set(done.map(j => j.id)); return; }
  let newVideo = false;
  for (const j of done) {
    if (seenDone.has(j.id)) continue;
    seenDone.add(j.id);
    const what = j.params.demo ? "Demo video" : j.kind === "upscale" ? "1080p upscale" : j.kind === "interp" ? "Smooth version" : "Your video";
    if (j.status === "done") {
      newVideo = true;
      toast(`${what} is ready${j.took ? " (" + fmtMin(j.took) + ")" : ""}`, "good");
      if ($("#notifyDone").checked && "Notification" in window && Notification.permission === "granted" && document.hidden)
        new Notification("Wan Studio", { body: `${what} is ready` });
      if (j.params.demo) loadDemos();
    } else toast(`${what} failed: ${esc((j.error || "").slice(0, 120))}`, "bad");
  }
  if (newVideo) loadLibrary();
}

// ------------------------------------------------------------------ jobs (queue page + mini queue)
const KIND = { animate: ["Animate", "Animate"], enhance: ["Enhance", "Enhance"], t2v: ["From words", "From words"], i2v: ["From a photo", "From a photo"], upscale: ["1080p", "Upscale to 1080p"], interp: ["Smooth", "Smooth to 48 fps"] };
function jobLine(j) {
  const p = j.params;
  if (j.kind === "enhance") return `Enhance: ${p.title || "video"} (part ${p.index + 1} of ${p.total})`;
  if (j.kind === "upscale" || j.kind === "interp") return KIND[j.kind][1] + ": " + (p.prompt || "video");
  return (p.demo ? "Demo: " : "") + p.prompt;
}
function jobStatusText(j) {
  if (j.status === "queued") {
    if (S.power !== "ready") return "Waiting for the server to be on";
    const ahead = S.jobs.filter(x => x.status === "queued" && x.created < j.created).length;
    return ahead ? `${ahead} ahead` : "Starts next";
  }
  if (j.status === "uploading") return "Sending to GPU " + (j.gpu + 1);
  if (j.status === "running") {
    if (j.phase === "finishing") return `GPU ${j.gpu + 1} · finishing and saving…`;
    const pct = Math.round((j.progress || 0) * 100);
    return `GPU ${j.gpu + 1} · ${pct ? pct + "%" : "preparing"}${j.eta ? " · about " + fmtMin(j.eta) + " left" : ""}`;
  }
  if (j.status === "downloading") return "Saving to your laptop…";
  if (j.status === "done") return `Done ${ago(j.finished)}${j.took ? " · took " + fmtMin(j.took) : ""}`;
  if (j.status === "failed") return "Failed " + ago(j.finished || j.created);
  if (j.status === "cancelled") return "Cancelled";
  return j.status;
}
function jobMeta(j) {
  const p = j.params;
  if (!p.seconds) return "";
  return `${p.aspect} · ${p.seconds} s · ${(QUALITY[p.quality] || {}).label || p.steps + " steps"} · seed ${p.seed}`;
}
function renderJobs() {
  const jobs = [...S.jobs].reverse();
  const active = jobs.filter(j => ["queued", "uploading", "running", "downloading"].includes(j.status));
  // Queue page order: what is running now, then what runs next (in order), then finished work (newest first).
  const RUNNING = ["uploading", "running", "downloading"];
  const groups = [["Making now", S.jobs.filter(j => RUNNING.includes(j.status))],
                  ["Waiting", S.jobs.filter(j => j.status === "queued")],
                  ["Finished", jobs.filter(j => !RUNNING.includes(j.status) && j.status !== "queued")]];
  const badge = $("#queueBadge");
  badge.textContent = active.length; badge.classList.toggle("hidden", !active.length);
  const jobHtml = j => `
    <div class="job">
      <div class="job-kind">${j.params.demo ? "Demo" : KIND[j.kind][0]}</div>
      <div class="job-main">
        <div class="job-title">${esc(jobLine(j))}</div>
        <div class="job-sub"><span class="st ${j.status}">${j.status}</span> ${esc(jobStatusText(j))} ${jobMeta(j) ? "· " + esc(jobMeta(j)) : ""}</div>
        ${j.status === "running" ? `<div class="bar ${j.progress ? "" : "indet"}"><i style="width:${Math.round((j.progress || 0) * 100)}%"></i></div>` : ""}
        ${j.status === "uploading" || j.status === "downloading" ? `<div class="bar indet"><i></i></div>` : ""}
        ${j.error ? `<div class="job-err">${esc(j.error)}</div>` : ""}
        ${j.note && j.status === "queued" ? `<div class="job-note">${esc(j.note)}</div>` : ""}
      </div>
      <div class="row">
        ${["queued", "uploading", "running"].includes(j.status) ? `<button class="btn small danger" data-cancel="${j.id}">Cancel</button>` : ""}
        ${["failed", "cancelled"].includes(j.status) ? `<button class="btn small" data-retry="${j.id}">Try again</button>` : ""}
        ${j.status === "done" && j.result ? `<button class="btn small" data-open="${j.result}">View</button>` : ""}
      </div>
    </div>`;
  $("#jobList").innerHTML = jobs.length
    ? groups.filter(([, list]) => list.length).map(([name, list]) => `<div class="job-group">${name} (${list.length})</div>` + list.map(jobHtml).join("")).join("")
    : `<div class="empty">Nothing in the queue. Videos you make show up here.</div>`;
  // mini queue on the Create page
  const RUN = ["uploading", "running", "downloading"];
  const shown = [...active].sort((a, b) => (RUN.includes(b.status) - RUN.includes(a.status)) || a.created - b.created);
  const mt = $("#makingTitle"); if (mt) mt.classList.toggle("hidden", !active.length);
  $("#miniQueue").innerHTML = shown.slice(0, 4).map(j => `
    <div class="mq"><div class="mq-top"><span>${esc(jobLine(j))}</span><span class="hint">${esc(jobStatusText(j))}</span></div>
    ${j.status === "running" ? `<div class="bar ${j.progress ? "" : "indet"}"><i style="width:${Math.round((j.progress || 0) * 100)}%"></i></div>` : ""}</div>`).join("")
    + (!active.length ? `<div class="hint">Nothing is being made right now. Press Generate to start a video.</div>` : "")
    + (active.length > 4 ? `<a class="link" data-goto="queue">${active.length - 4} more in the queue</a>` : "");
}
document.addEventListener("click", async e => {
  const c = e.target.closest("[data-cancel]"), r = e.target.closest("[data-retry]"), o = e.target.closest("[data-open]");
  const up = e.target.closest("[data-up]"), sm = e.target.closest("[data-smooth]");
  if (up && !up.disabled) { await api("/api/process", { json: { kind: "upscale", source: up.dataset.up } }); toast("1080p upscale added to the queue (about 6 min)", "good"); up.disabled = true; up.textContent = "Queued"; }
  if (sm && !sm.disabled) { await api("/api/process", { json: { kind: "interp", source: sm.dataset.smooth } }); toast("Smooth version added to the queue (about 1 min)", "good"); sm.disabled = true; sm.textContent = "Queued"; }
  if (c) { await api(`/api/jobs/${c.dataset.cancel}/cancel`, { method: "POST" }); toast("Cancelling…"); poll(); }
  if (r) { await api(`/api/jobs/${r.dataset.retry}/retry`, { method: "POST" }); toast("Added to the queue again"); }
  if (o) { if (!library.length) await loadLibrary(); openViewer(o.dataset.open); }
});
$("#clearJobsBtn").onclick = async () => { await api("/api/jobs/clear", { method: "POST" }); poll(); };

// ------------------------------------------------------------------ create form
const promptEl = $("#prompt");
$$("#modeSeg button").forEach(b => b.onclick = () => {
  form.mode = b.dataset.mode;
  $$("#modeSeg button").forEach(x => x.classList.toggle("on", x === b));
  $("#drop").classList.toggle("hidden", form.mode !== "i2v");
  promptEl.placeholder = form.mode === "i2v" ? "Describe the movement: e.g. prayer flags flutter in the wind, clouds drift slowly, the camera gently pushes in" : "Example: A trekker walking along a Himalayan ridge with prayer flags, golden sunrise light, drone shot slowly following from the side, cinematic";
  renderEstimate();
});
$$("#aspects button").forEach(b => b.onclick = () => setAspect(b.dataset.a));
function setAspect(a) { form.aspect = a; $$("#aspects button").forEach(x => x.classList.toggle("on", x.dataset.a === a)); renderEstimate(); }
$("#seconds").oninput = () => { $("#secLabel").textContent = $("#seconds").value + " s"; renderEstimate(); };
$$("#qualitySeg button").forEach(b => b.onclick = () => setQuality(b.dataset.q));
function setQuality(q) {
  form.quality = q; $$("#qualitySeg button").forEach(x => x.classList.toggle("on", x.dataset.q === q));
  if (q === "quality" && form.res === "720") $('#resSeg button[data-r="1080"]').click();   // Quality = 10-step Turbo + 1080p (~18 min)
  renderEstimate();
}
$$("#resSeg button").forEach(b => b.onclick = () => {
  form.res = b.dataset.r; $$("#resSeg button").forEach(x => x.classList.toggle("on", x === b));
  $("#resHint").textContent = { "720": "720p is what Wan makes", "1080": "made at 720p, then sharpened to 1080p (+6 min)", "1080s": "1080p, plus doubled frames for smoother motion (+8 min)" }[form.res];
  renderEstimate();
});
$("#cfg").oninput = () => $("#cfgLabel").textContent = (+$("#cfg").value).toFixed(1);
$("#twoVersions").onchange = renderEstimate;
$("#diceBtn").onclick = () => $("#seed").value = Math.floor(Math.random() * 2 ** 31);
$("#seedClear").onclick = () => $("#seed").value = "";
$("#negReset").onclick = () => $("#negative").value = DEFAULT_NEGATIVE;
$("#negMeaning").textContent = "Means: " + DEFAULT_NEGATIVE_EN.split(", ").slice(0, 8).join(", ") + "…";
$("#negMeaning").title = DEFAULT_NEGATIVE_EN;
$("#negative").value = DEFAULT_NEGATIVE;
$("#clearBtn").onclick = () => { promptEl.value = ""; form.template = null; analyze(); };
$("#notifyDone").onchange = () => { if ($("#notifyDone").checked && "Notification" in window) Notification.requestPermission(); };

// photo drop
const drop = $("#drop");
drop.onclick = e => { if (!e.target.closest("#dropClear")) $("#fileInput").click(); };
drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } };
drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } };
$("#dropClear").onclick = e => { e.stopPropagation(); $("#fileInput").click(); };
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) uploadPhoto(e.dataTransfer.files[0]); };
$("#fileInput").onchange = () => { if ($("#fileInput").files[0]) uploadPhoto($("#fileInput").files[0]); };
async function uploadPhoto(file) {
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await fetch("/api/upload", { method: "POST", body: fd }).then(r => r.json());
    if (r.error) throw new Error(r.error);
    form.image = r.name; form.imageUrl = "/uploads/" + r.name;
    $("#dropImg").src = form.imageUrl;
    $("#dropEmpty").classList.add("hidden"); $("#dropFull").classList.remove("hidden"); updateFeatureButtons();
    const img = new Image(); img.onload = () => { const r2 = img.width / img.height; setAspect(r2 > 1.25 ? "16:9" : r2 < 0.8 ? "9:16" : "1:1"); }; img.src = form.imageUrl;
  } catch (e) { toast("Upload failed: " + esc(e.message), "bad"); }
}

// prompt analysis
const CHECKS = [
  { key: "motion", re: /\b(walk|run|fly|flies|flow|drift|turn|mov|danc|spin|float|swim|fall|ris|pour|splash|wave|flutter|sway|glid|roll|jump|smil|blow|crash|burst|rotat|lift|open|climb|circl|swirl|gallop|chas|ripple|stream|push|pull|toss|flicker|dance|soar|wander|cross|drive|driving|sail)/i,
    tip: "Say what moves", add: "with gentle natural motion" },
  { key: "camera", re: /\b(camera|shot|drone|pan|tilt|zoom|dolly|tracking|orbit|push-in|pull-back|close-up|closeup|wide|aerial|pov|first-person|handheld|angle|top-down|macro|follow|telephoto|gimbal)/i,
    tip: "Add a camera move", add: "slow cinematic camera push-in" },
  { key: "light", re: /\b(light|sun|golden hour|sunset|sunrise|dawn|dusk|night|neon|moon|glow|shadow|lit\b|lamp|candle|blue hour|overcast|bright|dark)/i,
    tip: "Add lighting", add: "soft golden hour light" },
  { key: "style", re: /\b(cinematic|documentary|film|realistic|anime|commercial|vlog|4k|detailed|style|vintage|dreamy|epic|photoreal|ultra|advert)/i,
    tip: "Add a style", add: "cinematic, highly detailed" },
];
function analyze() {
  const t = promptEl.value.trim();
  const words = t ? t.split(/\s+/).length : 0;
  $("#wordCount").textContent = words + " words";
  const missing = CHECKS.filter(c => !c.re.test(t));
  let score = Math.min(words / 30, 1) * 40 + (CHECKS.length - missing.length) * 15;
  if (form.mode === "i2v") score = Math.min(100, score + 15);
  const fill = $("#strengthFill");
  fill.style.width = (t ? Math.max(8, score) : 0) + "%";
  fill.style.background = score >= 75 ? "var(--good)" : score >= 45 ? "var(--warn)" : "var(--bad)";
  $("#strengthText").textContent = !t ? "Start typing…" : score >= 75 ? "Great prompt" : score >= 45 ? "Good, could be better" : words < 8 ? "Too short: describe more" : "Needs more detail";
  renderTips();
}
promptEl.oninput = () => { form.template = null; analyze(); };
$("#tips").onclick = e => {
  const tip = e.target.closest("[data-add]"); if (!tip) return;
  promptEl.value = promptEl.value.trim().replace(/[.,\s]+$/, "") + ", " + tip.dataset.add; analyze();
};

// ------------------------------------------------------------------ topic-aware suggestions
// Each topic gives ideas that fit what the video is about. The first matching topics win; GENERIC fills the gaps.
const TOPICS = [
  { name: "mountains", re: /everest|himalaya|mountain|peak|summit|annapurna|ama dablam|machapuchare|kailash|snow|ridge|glacier|range|base camp/i,
    motion: ["thin clouds drifting slowly past the summit", "snow blowing off the ridge in the wind", "prayer flags fluttering in the foreground"],
    camera: ["aerial view slowly gliding toward the peak", "slow pan across the mountain range", "slow push-in toward the summit"],
    light: ["golden sunrise light on the snow", "pink alpenglow at sunset", "crisp deep-blue sky, bright morning sun"] },
  { name: "trek", re: /trek|hike|hiker|trail|backpack|walker|porter|climber|pilgrim/i,
    motion: ["walking steadily up the stone trail, trekking poles swinging", "stopping to look back at the view", "boots stepping over rocks"],
    camera: ["tracking shot from the side as they walk", "camera following from behind", "low angle as they pass the camera"],
    light: ["warm early-morning sunlight", "soft overcast light in the valley", "late afternoon side lighting"] },
  { name: "water", re: /lake|boat|river|water|phewa|rafting|raft|waterfall|canoe|kayak|pool|manasarovar/i,
    motion: ["gliding slowly across calm water", "ripples spreading across the surface", "mist drifting low over the water"],
    camera: ["low angle shot close to the water surface", "static wide shot from the shore", "slow aerial view over the water"],
    light: ["soft dawn light with mirror-like reflections", "warm sunset glow on the water", "bright midday sun sparkling on the water"] },
  { name: "temple", re: /temple|stupa|monastery|pagoda|durbar|monk|prayer wheel|shrine|dzong|gompa|pashupati|swayambhu|boudha|aarti/i,
    motion: ["prayer wheels spinning as pilgrims walk past", "pigeons taking off from the square", "butter lamps flickering", "monks walking slowly in maroon robes"],
    camera: ["slow orbit around the stupa", "handheld walk through the courtyard", "low angle looking up at the carved roofs"],
    light: ["warm golden hour light", "soft morning haze", "warm lamp glow at dusk"] },
  { name: "city", re: /city|street|market|kathmandu|bazaar|thamel|bhaktapur|patan|lhasa|thimphu|festival|crowd/i,
    motion: ["people walking past in colourful clothes", "a rickshaw rolling slowly through the frame", "stalls with fabric moving in the breeze"],
    camera: ["handheld camera walking forward through the street", "static medium shot from a corner", "slow pan across the square"],
    light: ["warm afternoon sunlight", "evening street lamps and shop lights", "soft overcast daylight"] },
  { name: "food", re: /food|momo|tea|coffee|dal bhat|thali|cook|kitchen|dish|meal|breakfast|chai/i,
    motion: ["steam rising slowly from the food", "a hand lifting a piece with chopsticks", "tea being poured into a cup"],
    camera: ["close-up shot, shallow depth of field", "top-down view of the table", "slow push-in on the dish"],
    light: ["soft window light from the side", "warm restaurant lighting", "morning sunlight on a wooden table"] },
  { name: "stay", re: /hotel|room|lodge|resort|tea house|teahouse|bed|lobby|suite|balcony|guest ?house|homestay/i,
    motion: ["curtains opening to reveal the view", "a guest stepping onto the balcony with a cup of tea", "smoke curling from the chimney"],
    camera: ["slow gimbal walk into the room", "slow push-in toward the window", "wide shot from outside the building"],
    light: ["bright morning light through large windows", "warm lamp light at dusk", "soft golden light on the walls"] },
  { name: "wildlife", re: /jungle|safari|rhino|elephant|tiger|chitwan|bardia|wildlife|bird|leopard|deer|monal|yak|eagle|monkey/i,
    motion: ["the animal walking slowly through tall grass", "turning its head toward the camera", "birds lifting off from the water"],
    camera: ["telephoto tracking shot, wildlife documentary", "low angle from the grass", "static wide shot from a jeep"],
    light: ["soft early-morning mist and light", "warm late-afternoon sun", "dappled light through the trees"] },
  { name: "flight", re: /helicopter|heli|flight|plane|airplane|window seat|paraglid|zipline|aerial/i,
    motion: ["the helicopter rising slowly past the ridge", "the wing gently banking", "a paraglider drifting in slow circles"],
    camera: ["view through the window as it flies past the peaks", "aerial view following alongside", "first-person view looking down"],
    light: ["bright clear morning light", "golden light low in the sky", "crisp blue sky above white peaks"] },
  { name: "people", re: /people|woman|man|girl|boy|couple|family|group|tourist|guide|guest|traveler|traveller|selfie/i,
    motion: ["smiling and turning toward the camera", "laughing together and raising their arms", "pointing toward the view"],
    camera: ["medium shot, slow push-in", "tracking shot walking alongside them", "over-the-shoulder shot toward the view"],
    light: ["soft golden hour light on their faces", "bright natural daylight", "warm backlight from the setting sun"] },
];
const GENERIC = {
  motion: ["with gentle natural motion in the background", "leaves and flags moving in the breeze"],
  camera: ["slow cinematic push-in", "smooth tracking shot"],
  light: ["soft golden hour light", "bright natural daylight"],
  style: ["realistic travel documentary", "cinematic travel advert, highly detailed", "vertical travel reel, energetic"],
};
const CAT_LABEL = { motion: "Motion", camera: "Camera", light: "Light", style: "Style" };
function suggestionsFor(text) {
  const topics = TOPICS.filter(t => t.re.test(text)).slice(0, 2);
  const missing = CHECKS.filter(c => !c.re.test(text)).map(c => c.key);
  const out = [];
  for (const cat of missing) {
    const pool = [...topics.flatMap(t => t[cat] || []), ...(topics.length && cat !== "style" ? [] : GENERIC[cat] || [])];
    [...new Set(pool)].filter(s => !text.toLowerCase().includes(s.toLowerCase())).slice(0, 3).forEach(s => out.push({ cat, s }));
  }
  return { topics: topics.map(t => t.name), items: out };
}
function renderTips() {
  const t = promptEl.value.trim();
  if (!t) { $("#tips").innerHTML = ""; return; }
  const { topics, items } = suggestionsFor(t);
  if (!items.length) { $("#tips").innerHTML = `<span class="tips-head">Looks complete. Press Generate, or Improve for 3 polished versions.</span>`; return; }
  $("#tips").innerHTML = `<span class="tips-head">${topics.length ? `Ideas for this ${topics[0]} video` : "Ideas to add"}:</span>`
    + items.map(i => `<button class="tip" data-add="${esc(i.s)}"><b>${CAT_LABEL[i.cat]}</b> ${esc(i.s)}</button>`).join("");
}

// local fallback when the server is off: one tidy version built from the best-matching ideas
function offlineImprove(idea) {
  let t = idea.trim().replace(/[.\s]+$/, "");
  const { items } = suggestionsFor(t);
  const pick = {};
  for (const i of items) if (!pick[i.cat]) pick[i.cat] = i.s;
  const parts = [t];
  if (pick.motion) parts.push(pick.motion);
  if (pick.camera) parts.push(pick.camera);
  if (pick.light) parts.push(pick.light);
  parts.push(pick.style || "realistic travel documentary");
  t = parts.join(", ") + ".";
  return t.charAt(0).toUpperCase() + t.slice(1);
}

// three versions to choose from
function showOptions(opts, note) {
  $("#improveOpts").innerHTML = `<div class="opts-head"><b>Pick a version</b><span class="hint">${esc(note || "")}</span><button class="btn small ghost" id="optsClose">Keep mine</button></div>`
    + opts.map((o, i) => `<button class="opt" data-opt="${i}"><span class="opt-n">${i + 1}</span><span>${esc(o)}</span></button>`).join("");
  $("#improveOpts").classList.remove("hidden");
  $("#improveOpts").dataset.opts = JSON.stringify(opts);
}
$("#improveOpts").onclick = e => {
  if (e.target.closest("#optsClose")) { $("#improveOpts").classList.add("hidden"); return; }
  const b = e.target.closest("[data-opt]"); if (!b) return;
  promptEl.value = JSON.parse($("#improveOpts").dataset.opts)[+b.dataset.opt];
  form.template = null; $("#improveOpts").classList.add("hidden"); analyze(); toast("Prompt updated", "good");
};
$("#improveBtn").onclick = async () => {
  const idea = promptEl.value.trim();
  if (!idea) return toast("Write a short idea first, e.g. “boat on Phewa Lake at sunrise”");
  const btn = $("#improveBtn"), label = $("span", btn);
  btn.disabled = true; label.textContent = "Writing 3 versions…";
  try {
    const r = await api("/api/improve", { json: { prompt: idea, mode: form.mode, aspect: form.aspect, image: form.mode === "i2v" ? form.image : null } });
    if (r.options && r.options.length) showOptions(r.options, `written by ${r.model}${r.saw_photo ? ", which looked at your photo" : ""}`);
    else showOptions([offlineImprove(idea)], "the AI models are busy right now, so this uses built-in ideas. Try again in a minute");
  } catch (e) { showOptions([offlineImprove(idea)], "built-in ideas"); }
  btn.disabled = false; label.textContent = "Improve my prompt";
};

$("#surpriseBtn").onclick = () => useTemplate(TEMPLATES[Math.floor(Math.random() * TEMPLATES.length)].id);

// builder
const BUILDER_ROWS = [["subject", "Subject"], ["action", "What it does"], ["place", "Where"], ["lighting", "Light"], ["camera", "Camera"], ["style", "Style"], ["mood", "Mood"]];
const bsel = {};
function renderBuilder() {
  $("#builderRows").innerHTML = BUILDER_ROWS.map(([k, name]) => `
    <div class="brow"><div class="brow-title">${name}</div><div class="bopts" data-k="${k}">
      ${BUILDER[k].map(o => `<button class="${bsel[k] === o ? "on" : ""}">${esc(o)}</button>`).join("")}
      <input placeholder="or type your own" value="${esc(bsel[k] && !BUILDER[k].includes(bsel[k]) ? bsel[k] : "")}"></div></div>`).join("");
  $$("#builderRows .bopts").forEach(row => {
    const k = row.dataset.k;
    $$("button", row).forEach(b => b.onclick = () => { bsel[k] = bsel[k] === b.textContent ? null : b.textContent; renderBuilder(); });
    $("input", row).oninput = e => { bsel[k] = e.target.value || null; $$("button", row).forEach(b => b.classList.remove("on")); builderText(); };
  });
  builderText();
}
function builderText() {
  const s = bsel, parts = [];
  if (s.subject) parts.push(s.subject + (s.action ? " " + s.action : ""));
  else if (s.action) parts.push(s.action);
  if (s.place) parts.push(s.place);
  const tail = [s.lighting, s.camera, s.style, s.mood && s.mood + " mood"].filter(Boolean);
  let t = [parts.join(" "), ...tail].filter(Boolean).join(", ");
  t = t ? t.charAt(0).toUpperCase() + t.slice(1) : "";
  $("#builderOut").textContent = t || "Pick options above…";
  return t;
}
$("#builderBtn").onclick = () => { renderBuilder(); $("#builderModal").classList.remove("hidden"); };
$("#builderUse").onclick = () => { const t = builderText(); if (t) { promptEl.value = t; analyze(); } $("#builderModal").classList.add("hidden"); };
$$(".modal").forEach(m => m.addEventListener("click", e => { if (e.target === m || e.target.closest("[data-close]")) { if (m.id !== "confirm") m.classList.add("hidden"); if (m.id === "viewer") $("#vVideo").pause(); } }));
document.addEventListener("keydown", e => { if (e.key === "Escape") $$(".modal:not(.hidden)").forEach(m => { if (m.id !== "confirm") { m.classList.add("hidden"); $("#vVideo").pause(); } }); });

// estimate + generate
function currentParams() {
  const q = QUALITY[form.quality];
  const p = { prompt: promptEl.value.trim(), negative: $("#negative").value.trim(), aspect: form.aspect, seconds: +$("#seconds").value,
    quality: form.quality, steps: q.steps, cfg: q.cfg ?? +$("#cfg").value, template: form.template, two: $("#twoVersions").checked };
  const seed = $("#seed").value.trim(); p.seed = seed === "" ? -1 : +seed;
  if (form.mode === "i2v") p.image = form.image;
  p.upscale = form.res !== "720"; p.smooth = form.res === "1080s";
  return p;
}
function renderEstimate() {
  if (!S) return;
  const p = currentParams();
  const one = estimate(p);
  const queued = S.jobs.filter(j => ["queued", "uploading", "running"].includes(j.status)).length;
  const extra = (p.upscale ? 340 : 0) + (p.smooth ? 150 : 0);
  let txt = `About <b>${fmtMin(one + extra)}</b> per video` + (extra ? ` (${fmtMin(one)} to make it, ${fmtMin(extra)} to upscale${p.smooth ? " and smooth" : ""})` : "");
  if (p.two) txt += ", 2 versions at once";
  if (queued) txt += `. ${queued} ${queued === 1 ? "job" : "jobs"} ahead`;
  if (S.power === "off" || S.power === "error") txt += "<br>Server is off: the video will start once it's on.";
  if (S.power === "starting") txt += "<br>Server is starting: your video will begin when it's ready.";
  $("#estimate").innerHTML = txt;
}
$("#generateBtn").onclick = async () => {
  const p = currentParams();
  if (!p.prompt) { toast("Describe your video first, or pick a template"); promptEl.focus(); return; }
  if (form.mode === "i2v" && !p.image) { toast("Choose a photo first"); return; }
  if (p.prompt.split(/\s+/).length < 6 && !(await confirmBox("Short prompt", "Short prompts often give random results. Press <b>Improve my prompt</b> first, or make it anyway?", "Make it anyway"))) return;
  try {
    const r = await api("/api/generate", { json: p });
    toast(`${r.jobs.length === 2 ? "2 videos" : "Video"} added. <a class="link" data-goto="queue">See progress</a>`, "good");
    if ($("#notifyDone").checked && "Notification" in window && Notification.permission === "default") Notification.requestPermission();
    if (S.power === "off" || S.power === "error") {
      if (await confirmBox("Turn on the server?", "The Kaggle GPU server is off. Turn it on now? It takes about 5 minutes, then your video starts automatically.", "Turn on"))
        await api("/api/power", { json: { on: true } });
    }
    poll();
  } catch (e) { toast("Could not add: " + esc(e.message), "bad"); }
};

// ------------------------------------------------------------------ templates
let tplCat = "all";
function renderTemplates() {
  $("#tplCats").innerHTML = `<button data-c="all" class="${tplCat === "all" ? "on" : ""}">All ${TEMPLATES.length}</button>` +
    TEMPLATE_CATEGORIES.map(c => `<button data-c="${c.id}" class="${tplCat === c.id ? "on" : ""}">${c.name}</button>`).join("");
  $$("#tplCats button").forEach(b => b.onclick = () => { tplCat = b.dataset.c; renderTemplates(); });
  const q = $("#tplSearch").value.toLowerCase();
  const list = TEMPLATES.filter(t => (tplCat === "all" || t.cat === tplCat) && (!q || (t.title + " " + t.prompt).toLowerCase().includes(q)));
  $("#tplGrid").innerHTML = list.map(t => `
    <div class="tcard">
      <button class="thumb" data-use="${t.id}" aria-label="Use the ${esc(t.title)} template">
        ${demos.has(t.id) ? `<video src="/demos/${t.id}.mp4" poster="/demos/${t.id}.jpg" muted loop playsinline preload="none" aria-hidden="true"></video>` : `<span class="tile c-${t.cat}">${esc(t.title)}</span>`}
        <span class="tag">${t.aspect}</span>${demos.has(t.id) ? `<span class="tag r">Demo</span>` : ""}
      </button>
      <div class="tbody"><b>${esc(t.title)}</b><p>${esc(t.prompt)}</p>
        <div class="row"><button class="btn small" data-use="${t.id}">Use</button><button class="btn small primary" data-gen="${t.id}">Generate now</button></div></div>
    </div>`).join("") || `<div class="empty">No templates match.</div>`;
  $$("#tplGrid video").forEach(v => { const c = v.closest(".tcard"); c.onmouseenter = () => v.play().catch(() => {}); c.onmouseleave = () => { v.pause(); v.currentTime = 0; v.load(); }; });
  const missing = TEMPLATES.filter(t => !demos.has(t.id)).length;
  $("#makeDemosBtn").textContent = missing ? `Make ${missing} missing demos` : "All demos made";
  $("#makeDemosBtn").disabled = !missing;
}
$("#tplSearch").oninput = renderTemplates;
function useTemplate(id, andGenerate = false) {
  const t = TEMPLATES.find(x => x.id === id); if (!t) return;
  promptEl.value = t.prompt; form.template = t.id; setAspect(t.aspect);
  if (form.mode === "i2v") $$("#modeSeg button")[0].click();
  analyze(); go("create");
  if (andGenerate) $("#generateBtn").click(); else toast(`Loaded “${esc(t.title)}”. Edit it or press Generate.`);
}
$("#tplGrid").onclick = e => {
  const u = e.target.closest("[data-use]"), g = e.target.closest("[data-gen]");
  if (g) useTemplate(g.dataset.gen, true); else if (u) useTemplate(u.dataset.use);
};
$("#makeDemosBtn").onclick = async () => {
  const missing = TEMPLATES.filter(t => !demos.has(t.id) && !S.jobs.some(j => j.params.demo === t.id && ["queued", "uploading", "running", "downloading"].includes(j.status)));
  if (!missing.length) return toast("Demos for all templates are already made or queued");
  const each = estimate({ quality: "standard", seconds: 3 });
  const hours = missing.length * each / 2 / 3600;
  if (!(await confirmBox("Make demo videos?", `This makes a 3-second Standard-quality sample for <b>${missing.length} templates</b>, 2 at a time. It takes about <b>${hours.toFixed(1)} hours</b> of your free GPU time. You can cancel any time from the Queue.`, "Make demos"))) return;
  for (const t of missing) await api("/api/generate", { json: { prompt: t.prompt, negative: DEFAULT_NEGATIVE, aspect: t.aspect, seconds: 3, quality: "standard", seed: 42, template: t.id, demo: t.id } });
  toast(`${missing.length} demos queued`, "good");
  if (S.power === "off" && await confirmBox("Turn on the server?", "Start the Kaggle server now so the demos begin?", "Turn on")) await api("/api/power", { json: { on: true } });
};
async function loadDemos() { try { demos = new Set(await api("/api/demos")); } catch (e) {} if ($("#page-templates").classList.contains("active")) renderTemplates(); }

// ------------------------------------------------------------------ gallery + viewer
let galFilter = "all";
async function loadLibrary() {
  try { library = await api("/api/library"); } catch (e) { return; }
  renderGallery(); renderPreview();
}
function renderGallery() {
  const q = $("#galSearch").value.toLowerCase();
  const f = galFilter;
  const list = library.filter(x => (f === "all" || (f === "fav" && x.favorite) || (f === "1080p" && x.res === "1080p") || (f === "720p" && x.res === "720p")
    || (f === "smooth" && x.fps > 24) || (f === "i2v" && x.image)) && (!q || (x.prompt || "").toLowerCase().includes(q)));
  $("#galCount").textContent = `${library.length} video${library.length === 1 ? "" : "s"} · saved in your Videos folder`;
  $("#galGrid").innerHTML = list.map(x => `
    <div class="vcard">
      <button class="thumb" data-view="${x.id}" aria-label="Open video" style="aspect-ratio:${x.aspect === "9:16" ? "9/16" : x.aspect === "1:1" ? "1/1" : "16/9"}">
        <video src="/media/${encodeURIComponent(x.file)}" poster="/thumbs/${x.id}.jpg" muted loop playsinline preload="none" aria-hidden="true"></video>
        <span class="tag">${x.res || "720p"}${x.fps > 24 ? ", " + x.fps + " fps" : ""}</span>${x.favorite ? `<span class="star" aria-label="Favourite">★</span>` : ""}
      </button>
      <div class="tbody"><p>${esc(x.prompt)}</p><span class="hint num">${ago(x.created)}, ${x.seconds || "?"} s, seed ${x.seed ?? "–"}</span>
        <div class="row card-actions"><button class="btn small" data-up="${x.id}" ${x.res === "1080p" ? "disabled" : ""}>${x.res === "1080p" ? "Already 1080p" : "Upscale to 1080p"}</button><button class="btn small" data-smooth="${x.id}" ${(x.fps || 24) > 24 ? "disabled" : ""}>${(x.fps || 24) > 24 ? "Already smooth" : "Smooth 48 fps"}</button></div></div>
    </div>`).join("") || `<div class="empty">No videos yet. Make one on the Create page, or start from a template.</div>`;
  $$("#galGrid video").forEach(v => { const c = v.closest(".vcard"); c.onmouseenter = () => v.play().catch(() => {}); c.onmouseleave = () => { v.pause(); v.currentTime = 0; v.load(); }; });
}
$("#galSearch").oninput = renderGallery;
$$("#galFilters button").forEach(b => b.onclick = () => { galFilter = b.dataset.f; $$("#galFilters button").forEach(x => x.classList.toggle("on", x === b)); renderGallery(); });
$("#galGrid").onclick = e => { const v = e.target.closest("[data-view]"); if (v) openViewer(v.dataset.view); };
function renderRecent() {
  const el = $("#homeRecent"); if (!el) return;
  el.innerHTML = library.slice(0, 9).map(x => `<button class="rthumb" data-open="${x.id}" aria-label="Open video" style="aspect-ratio:${x.aspect === "9:16" ? "9/16" : x.aspect === "1:1" ? "1/1" : "16/9"}">
    <img src="/thumbs/${x.id}.jpg" alt="" loading="lazy"><span class="tag">${x.res || "720p"}</span></button>`).join("")
    || `<div class="hint">Your finished videos will show up here.</div>`;
}
function renderPreview() {
  renderRecent();
  const x = library[0];
  if (!x) return;
  if ($("#previewBody").dataset.id === x.id) return;
  $("#previewBody").dataset.id = x.id;
  $("#previewBody").innerHTML = `<video src="/media/${encodeURIComponent(x.file)}" controls loop playsinline muted autoplay></video>
    <p class="hint">${esc((x.prompt || "").length > 160 ? x.prompt.slice(0, 157) + "…" : x.prompt || "")}</p><div class="row"><button class="btn small" data-open="${x.id}">Open</button><button class="btn small" data-up="${x.id}" ${x.res === "1080p" ? "disabled" : ""}>Upscale to 1080p</button><button class="btn small" data-smooth="${x.id}" ${(x.fps || 24) > 24 ? "disabled" : ""}>Smooth 48 fps</button></div>`;
}

let cur = null;
function openViewer(id) {
  cur = library.find(x => x.id === id); if (!cur) return;
  const src = "/media/" + encodeURIComponent(cur.file);
  $("#vVideo").src = src; $("#vVideo").play().catch(() => {});
  $("#vTitle").textContent = cur.kind === "upscale" ? "1080p upscale" : cur.kind === "interp" ? "Smooth version" : cur.kind === "i2v" ? "Made from a photo" : "Made from words";
  $("#vTags").innerHTML = [cur.res || "720p", cur.aspect, (cur.fps || 24) + " fps", cur.seconds + " s"].map(t => `<span>${esc(t)}</span>`).join("");
  $("#vPrompt").textContent = cur.prompt || "";
  $("#vSocialBox").classList.add("hidden"); $("#vSocialBox").innerHTML = "";
  $("#vMeta").innerHTML = [["Made", DTF.format(new Date(cur.created * 1000))], ["Took", cur.took ? fmtMin(cur.took) : "–"], ["Seed", cur.seed ?? "–"],
    ["Steps", cur.steps ?? "–"], ["Size", cur.size ? (cur.size / 1048576).toFixed(1) + " MB" : "–"], ["File", cur.file]].map(([k, v]) => `<span>${k}</span><span>${esc(v)}</span>`).join("");
  $("#vDownload").href = src + "?dl=1";
  $("#vFav").textContent = cur.favorite ? "Remove from favourites" : "Add to favourites";
  $("#vUpscale").disabled = cur.res !== "720p" && !!cur.res;
  const cmp = $("#vCompare"); cmp.classList.toggle("hidden", !cur.original); cmp.textContent = "Show original"; cmp.dataset.on = "";
  $("#vSmooth").disabled = (cur.fps || 24) > 24;
  $("#viewer").classList.remove("hidden");
}
const qualityOf = v => QUALITY[v.quality] ? v.quality : v.steps <= 8 ? "turbo" : v.steps >= 30 ? "high" : "standard";
$("#vFav").onclick = async () => { cur.favorite = !cur.favorite; await api("/api/library/" + cur.id, { json: { favorite: cur.favorite } }); $("#vFav").textContent = cur.favorite ? "Remove from favourites" : "Add to favourites"; renderGallery(); };
$("#vReuse").onclick = () => {
  promptEl.value = cur.prompt || ""; setAspect(cur.aspect || "16:9"); $("#seconds").value = cur.seconds || 5; $("#seconds").oninput();
  $("#seed").value = cur.seed ?? ""; if (cur.negative) $("#negative").value = cur.negative;
  setQuality(qualityOf(cur));
  $("#viewer").classList.add("hidden"); $("#vVideo").pause(); analyze(); go("create");
  toast("Settings loaded, including the seed. Change one thing and generate.");
};
$("#vVariations").onclick = async () => {
  const q = qualityOf(cur);
  const r = await api("/api/generate", { json: { prompt: cur.prompt, negative: cur.negative, aspect: cur.aspect, seconds: cur.seconds, quality: q,
    steps: cur.steps, cfg: cur.cfg, seed: -1, two: true, image: cur.image, template: cur.template } });
  toast("2 variations added to the queue", "good");
};
$("#vUpscale").onclick = async () => { await api("/api/process", { json: { kind: "upscale", source: cur.id } }); toast("1080p upscale added to the queue", "good"); };
$("#vSmooth").onclick = async () => { await api("/api/process", { json: { kind: "interp", source: cur.id } }); toast("Smooth version added to the queue", "good"); };
$("#vCopy").onclick = async () => { try { await navigator.clipboard.writeText(cur.prompt || ""); toast("Prompt copied"); } catch (e) { toast("Could not copy"); } };
$("#vDelete").onclick = async () => {
  if (!(await confirmBox("Delete this video?", "The file will be deleted from your Videos folder.", "Delete"))) return;
  await api("/api/library/" + cur.id, { method: "DELETE" });
  $("#viewer").classList.add("hidden"); $("#vVideo").pause(); $("#previewBody").dataset.id = ""; loadLibrary();
};
const openFolder = () => api("/api/open-folder", { method: "POST" });
$("#openFolderBtn").onclick = openFolder; $("#openFolderBtn2").onclick = openFolder;

// ------------------------------------------------------------------ settings
function renderSettings() {
  if (!S) return;
  const st = S.settings;
  $("#setIdle").value = st.idle_min; $("#idleLabel").textContent = st.idle_min + " min";
  $("#setMax").value = st.max_hours; $("#maxLabel").textContent = st.max_hours + " h";
  $("#setAspect").value = st.aspect; $("#setSeconds").value = st.seconds;
  $$("#themeSeg button").forEach(b => b.classList.toggle("on", b.dataset.t === (st.theme || "dark")));
  $("#outDir").textContent = st.output_dir;
  renderAccount();
  $("#pinShow").textContent = st.pin || "••••";
  $("#lanUrl").textContent = S.lan_url || "Not connected to Wi-Fi";
  if (S.lan_url && window.QRCode && $("#qr").dataset.u !== S.lan_url) {
    $("#qr").innerHTML = ""; new QRCode($("#qr"), { text: S.lan_url, width: 128, height: 128 }); $("#qr").dataset.u = S.lan_url;
  }
  const t = S.live.timings || {};
  $("#serverInfo").innerHTML = [["Status", S.power], ["Up for", S.live.uptime ? fmtMin(S.live.uptime) : "–"], ["Start-up time", t.ready_s ? fmtMin(t.ready_s) : "–"],
    ["AI prompt helper", S.live.llm ? "ready" : "off"], ["Speed", S.rate ? `${((S.rate * 121 * 20 + 175) / 60).toFixed(0)} min per 5 s Standard video` : "not measured yet"],
    ["GPU hours", S.quota ? `${S.quota.used_h.toFixed(1)} used of ${S.quota.total_h}` : "–"]].map(([k, v]) => `<span>${k}</span><span>${esc(v)}</span>`).join("");
}

// ------------------------------------------------------------------ Kaggle sign-in
let signInLater = false;
const needsSignIn = () => !!(S && S.local && S.kaggle && !S.kaggle.signed_in);
function showSignIn() {
  $("#siErr").classList.add("hidden");
  $("#signin").classList.remove("hidden");
  setTimeout(() => ($("#siUser").value ? $("#siToken") : $("#siUser")).focus(), 50);
}
function maybeSignIn() { if (needsSignIn() && !signInLater && $("#signin").classList.contains("hidden")) showSignIn(); }
function renderAccount() {
  if (!S || !$("#accText")) return;
  const k = S.kaggle || {};
  $("#accText").innerHTML = k.signed_in ? `Signed in as <b>${esc(k.user)}</b>. The server runs in your account (<code translate="no">${esc(k.kernel)}</code>).`
    : "Not signed in. Sign in to turn the Kaggle server on.";
  $("#signInBtn2").classList.toggle("hidden", !!k.signed_in);
  $("#signOutBtn").classList.toggle("hidden", k.source !== "app");
}
$("#siLater").onclick = () => { signInLater = true; $("#signin").classList.add("hidden"); };
$("#siGo").onclick = async () => {
  const username = $("#siUser").value.trim(), token = $("#siToken").value.trim();
  const err = m => { $("#siErr").textContent = m; $("#siErr").classList.remove("hidden"); };
  if (!token) return err("Paste your API token from kaggle.com/settings.");
  $("#siGo").disabled = true; $("#siGo").textContent = "Checking…";
  try {
    const r = await api("/api/signin", { json: { username, token } });
    $("#siToken").value = ""; $("#signin").classList.add("hidden");
    toast(`Signed in as <b>${esc(r.user)}</b>. Flip the power switch to start your server.`, "good");
    S = await api("/api/state"); renderTop(); renderSettings();
  } catch (e) { err(e.message); }
  finally { $("#siGo").disabled = false; $("#siGo").textContent = "Sign in"; }
};
$("#siToken").onkeydown = e => { if (e.key === "Enter") $("#siGo").click(); };
$("#signInBtn2").onclick = showSignIn;
$("#signOutBtn").onclick = async () => {
  if (!await confirmBox("Sign out of Kaggle?", "The token is removed from this computer. Your videos stay.", "Sign out")) return;
  try { await api("/api/signout", { json: {} }); signInLater = true; toast("Signed out."); S = await api("/api/state"); renderSettings(); renderTop(); }
  catch (e) { toast(esc(e.message), "bad"); }
};
const saveSetting = async d => { await api("/api/settings", { json: d }); S = await api("/api/state"); renderSettings(); renderTop(); };
$("#setIdle").oninput = () => $("#idleLabel").textContent = $("#setIdle").value + " min";
$("#setIdle").onchange = () => saveSetting({ idle_min: +$("#setIdle").value });
$("#setMax").oninput = () => $("#maxLabel").textContent = $("#setMax").value + " h";
$("#setMax").onchange = () => saveSetting({ max_hours: +$("#setMax").value });
$("#setAspect").onchange = () => saveSetting({ aspect: $("#setAspect").value });
$("#setSeconds").onchange = () => saveSetting({ seconds: +$("#setSeconds").value });
$$("#themeSeg button").forEach(b => b.onclick = () => saveSetting({ theme: b.dataset.t }));
$("#savePin").onclick = async () => {
  const v = $("#setPin").value.trim();
  if (!/^\d{4,8}$/.test(v)) return toast("PIN must be 4 to 8 digits");
  await saveSetting({ pin: v }); $("#setPin").value = ""; toast("PIN changed. Phones will need the new PIN.", "good");
};

// ------------------------------------------------------------------ enhance (upload your own videos)
let enhVideos = [], enhSel = 0, enhSize = "1080p";
const vdrop = $("#vdrop");
const pickVideos = () => $("#vfile").click();
vdrop.onclick = e => { if (!e.target.closest("video")) pickVideos(); };
vdrop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickVideos(); } };
vdrop.ondragover = e => { e.preventDefault(); vdrop.classList.add("over"); };
vdrop.ondragleave = () => vdrop.classList.remove("over");
vdrop.ondrop = e => { e.preventDefault(); vdrop.classList.remove("over"); uploadVideos([...e.dataTransfer.files]); };
$("#vfile").onchange = () => { uploadVideos([...$("#vfile").files]); $("#vfile").value = ""; };
$("#vAddMore").onclick = pickVideos;

async function uploadVideos(files) {
  files = files.filter(f => f.type.startsWith("video") || /\.(mp4|mov|webm|mkv|m4v)$/i.test(f.name));
  if (!files.length) return toast("Choose video files (MP4, MOV or WEBM)");
  $("#enhBtn").disabled = true;
  for (let i = 0; i < files.length; i++) {
    $("#enhEstimate").textContent = `Uploading and checking ${files.length > 1 ? `video ${i + 1} of ${files.length}` : "the video"}…`;
    const fd = new FormData(); fd.append("file", files[i]);
    try {
      const r = await fetch("/api/upload-video", { method: "POST", body: fd }).then(r => r.json());
      if (r.error) throw new Error(r.error);
      enhVideos.push(r); enhSel = enhVideos.length - 1;
    } catch (e) { toast(`Could not use ${esc(files[i].name)}: ${esc(e.message)}`, "bad"); }
  }
  renderEnhance();
}
const enhTarget = v => v.targets.find(t => t.key === enhSize);
function renderEnhance() {
  const has = enhVideos.length > 0;
  $("#vdropEmpty").classList.toggle("hidden", has); $("#vdropFull").classList.toggle("hidden", !has);
  $("#vAddMore").classList.toggle("hidden", !has);
  const up = $("#enhUp").checked, sm = $("#enhSmooth").checked;
  $("#enhSize").classList.toggle("off", !up);
  if (!has) { $("#vlist").innerHTML = ""; $("#enhEstimate").textContent = "Choose a video first."; $("#enhBtn").disabled = true; $("#enhBtnText").textContent = "Enhance video"; return; }
  enhSel = Math.min(enhSel, enhVideos.length - 1);
  const cur = enhVideos[enhSel], pv = $("#vPreview");
  if (pv.dataset.name !== cur.name) { pv.dataset.name = cur.name; pv.src = "/uploads/" + cur.name; }
  // which videos will actually be processed with the current options
  const plan = enhVideos.map(v => { const t = enhTarget(v); const doUp = up && t.ok; return { v, t, doUp, run: !v.too_long && (doUp || sm) }; });
  $("#vlist").innerHTML = plan.map((p, i) => `<div class="vrow ${i === enhSel ? "on" : ""} ${p.run ? "" : "skip"}" data-vsel="${i}">
      <div class="vrow-main"><b>${esc(p.v.title)}</b><span class="hint">${p.v.width}×${p.v.height}, ${p.v.duration.toFixed(1)} s, ${Math.round(p.v.fps)} fps${p.v.audio ? "" : ", no sound"}</span></div>
      <span class="vrow-out">${p.v.too_long ? "Longer than 60 s: trim it first" : p.run ? (p.doUp ? `${p.t.w}×${p.t.h}` : "same size") + (sm ? `, ${Math.round(Math.min(p.v.fps, 30) * 2)} fps` : "") : up ? "Already this size or bigger" : "Nothing to do"}</span>
      <button class="x" data-vdel="${i}" aria-label="Remove ${esc(p.v.title)}"><iconify-icon icon="solar:close-circle-linear" aria-hidden="true"></iconify-icon></button></div>`).join("");
  const todo = plan.filter(p => p.run);
  $("#enhUpHint").textContent = up ? `your video becomes ${enhTarget(cur).ok ? enhTarget(cur).w + "×" + enhTarget(cur).h : "no bigger: it is already this size"}` : "off: the size stays the same";
  $("#enhBtnText").textContent = todo.length > 1 ? `Enhance ${todo.length} videos` : "Enhance video";
  $("#enhBtn").disabled = !todo.length;
  if (!up && !sm) { $("#enhEstimate").textContent = "Switch on at least one option."; return; }
  if (!todo.length) { $("#enhEstimate").textContent = "None of these videos can use these options."; return; }
  let secs = 60;
  for (const p of todo) {
    const frames = p.v.duration * Math.min(p.v.fps, 30), mp = p.doUp ? Math.min(p.v.width * p.v.height, p.t.w * p.t.h / 4) / 1e6 : 0;
    secs += frames * ((p.doUp ? 3.1 * mp : 0) + (sm ? 0.35 : 0)) / 2;
  }
  $("#enhEstimate").innerHTML = `About <b>${fmtMin(secs)}</b> using both GPUs` + (S && S.power !== "ready" ? "<br>The server is off: it will start once it's on." : "");
}
$("#vlist").onclick = e => {
  const del = e.target.closest("[data-vdel]"), sel = e.target.closest("[data-vsel]");
  if (del) { enhVideos.splice(+del.dataset.vdel, 1); renderEnhance(); }
  else if (sel) { enhSel = +sel.dataset.vsel; renderEnhance(); }
};
$("#enhUp").onchange = renderEnhance; $("#enhSmooth").onchange = renderEnhance;
$$("#enhSize button").forEach(b => b.onclick = () => { enhSize = b.dataset.s; $$("#enhSize button").forEach(x => x.classList.toggle("on", x === b)); renderEnhance(); });
$("#enhBtn").onclick = async () => {
  const up = $("#enhUp").checked, sm = $("#enhSmooth").checked;
  const todo = enhVideos.filter(v => !v.too_long && ((up && enhTarget(v).ok) || sm));
  if (!todo.length) return;
  $("#enhBtn").disabled = true; $("#enhEstimate").textContent = "Preparing…";
  let parts = 0, okCount = 0;
  for (const v of todo) {
    try { const r = await api("/api/enhance", { json: { name: v.name, title: v.title, upscale: up, smooth: sm, size: enhSize } }); parts += r.parts; okCount++; }
    catch (e) { toast(`Could not start ${esc(v.title)}: ${esc(e.message)}`, "bad"); }
  }
  if (okCount) {
    toast(`${okCount} video${okCount === 1 ? "" : "s"} added (${parts} part${parts === 1 ? "" : "s"}). <a class="link" data-goto="queue">See progress</a>`, "good");
    enhVideos = enhVideos.filter(v => !todo.includes(v));
    if (S.power === "off" || S.power === "error") {
      if (await confirmBox("Turn on the server?", "The Kaggle GPU server is off. Turn it on now? It takes about 5 minutes, then the enhancing starts by itself.", "Turn on"))
        await api("/api/power", { json: { on: true } });
    }
    poll();
  }
  renderEnhance();
};

// ------------------------------------------------------------------ prompt lab (interactive guide)
const labEl = $("#labPrompt");
function labCheck() {
  const t = labEl.value.trim(), words = t ? t.split(/\s+/).length : 0;
  const NAMES = { motion: "Says what moves", camera: "Has a camera move", light: "Describes the light", style: "Names a style" };
  const items = [{ ok: words >= 25, name: "Long enough", tip: words ? `${words} words so far. Aim for 30 or more.` : "Aim for 30 or more words." },
    ...CHECKS.map(c => ({ ok: c.re.test(t), name: NAMES[c.key], tip: c.tip, add: c.add }))];
  const good = items.filter(i => i.ok).length;
  const score = t ? Math.round(good / items.length * 100) : 0;
  $("#labFill").style.width = score + "%";
  $("#labFill").style.background = score >= 80 ? "var(--accent)" : score >= 50 ? "var(--warn)" : "var(--bad)";
  $("#labVerdict").textContent = !t ? "Start typing…" : score >= 80 ? "Ready to use" : score >= 50 ? "Getting there" : "Needs more";
  $("#labWords").textContent = t ? `${good} of ${items.length} checks` : "";
  $("#labChecks").innerHTML = items.map(i => `<div class="check-item ${i.ok ? "ok" : ""}"><iconify-icon icon="${i.ok ? "solar:check-circle-bold" : "solar:close-circle-linear"}" aria-hidden="true"></iconify-icon>
    <span><b>${i.name}</b>${i.ok ? "" : `<em>${esc(i.tip)}</em>`}</span>${!i.ok && i.add ? `<button class="btn small glass-btn" data-labadd="${esc(i.add)}">Add “${esc(i.add)}”</button>` : ""}</div>`).join("");
}
labEl.oninput = labCheck;
const labAppend = phrase => { const cur = labEl.value.trim().replace(/[.,\s]+$/, ""); labEl.value = cur ? cur + ", " + phrase : phrase; labCheck(); };
$("#labChecks").onclick = e => { const b = e.target.closest("[data-labadd]"); if (b) labAppend(b.dataset.labadd); };
$("#labClear").onclick = () => { labEl.value = ""; labCheck(); };
$("#labExample").onclick = () => { labEl.value = TEMPLATES[Math.floor(Math.random() * TEMPLATES.length)].prompt; labCheck(); };
$("#labUse").onclick = () => {
  if (!labEl.value.trim()) return toast("Type a prompt first");
  promptEl.value = labEl.value.trim(); form.template = null; analyze(); go("create"); toast("Prompt moved to Create");
};

// [name, phrase added to the prompt, template whose demo shows this move]
const MOVES = [
  ["Aerial view", "aerial view slowly gliding forward", "everest-sunrise"], ["Orbit", "camera slowly circling around the subject", "boudhanath"],
  ["Tracking from the side", "wide tracking shot following from the side", "trekkers-ridge"], ["Slow push-in", "slow push-in", "tea-house"],
  ["Close-up", "close-up, shallow depth of field", "prayer-flags"], ["Static wide shot", "static wide shot", "phewa-boat"],
  ["First-person", "first-person view", "paragliding-pokhara"], ["Top-down", "top-down view", "coffee-pour"],
  ["Low angle", "low angle, slow motion", "puppy-run"], ["Handheld", "handheld documentary camera walking forward", "kathmandu-street"],
  ["Macro", "macro lens, very shallow depth of field", "watch-closeup"], ["Hyperlapse", "hyperlapse moving forward", "city-hyperlapse"],
];
let curMove = 0;
function renderMoves() {
  $("#moveList").innerHTML = MOVES.map((m, i) => `<button class="move ${i === curMove ? "on" : ""}" data-move="${i}" ${demos.has(m[2]) ? "" : "data-nodemo"}>${m[0]}</button>`).join("");
  const m = MOVES[curMove], v = $("#moveVideo");
  $("#moveName").textContent = m[0];
  $("#movePhrase").textContent = "“" + m[1] + "”";
  if (demos.has(m[2])) {
    if (v.dataset.id !== m[2]) { v.dataset.id = m[2]; v.poster = `/demos/${m[2]}.jpg`; v.src = `/demos/${m[2]}.mp4`; }
    if ($("#page-help").classList.contains("active")) v.play().catch(() => {});
  } else { v.removeAttribute("src"); v.removeAttribute("poster"); v.dataset.id = ""; v.load(); }
}
$("#moveList").onclick = e => { const b = e.target.closest("[data-move]"); if (b) { curMove = +b.dataset.move; renderMoves(); } };
$("#moveAdd").onclick = () => { labAppend(MOVES[curMove][1]); labEl.scrollIntoView({ behavior: "smooth", block: "center" }); toast("Added to the prompt checker"); };

let calcQ = "standard";
function renderCalc() {
  const secs = +$("#calcSeconds").value, n = +$("#calcCount").value;
  $("#calcSecLabel").textContent = secs + " s";
  $("#calcCountLabel").textContent = n;
  const each = estimate({ quality: calcQ, seconds: secs });
  const rounds = Math.ceil(n / 2), wall = rounds * each, hours = wall / 3600;   // two GPUs side by side; Kaggle counts session time
  $("#calcTime").textContent = fmtMin(wall);
  $("#calcHours").textContent = hours.toFixed(1) + " h";
  const q = S && S.quota, left = q ? q.total_h - q.used_h - hours : null;
  $("#calcLeft").textContent = left == null ? "–" : Math.max(0, left).toFixed(1) + " h";
  $("#calcNote").textContent = `About ${fmtMin(each)} per video. Both GPUs work at once, so ${n} video${n === 1 ? "" : "s"} take ${rounds} round${rounds === 1 ? "" : "s"}.`
    + (left != null && left < 0 ? " That is more than you have left this week." : "");
}
$$("#calcQuality button").forEach(b => b.onclick = () => { calcQ = b.dataset.q; $$("#calcQuality button").forEach(x => x.classList.toggle("on", x === b)); renderCalc(); });
$("#calcSeconds").oninput = renderCalc;
$("#calcCount").oninput = renderCalc;

const WEAK = [
  ["Readable text and logos", "Add text later in CapCut. Ask Wan for a clean sign or a blank banner instead."],
  ["Fast, busy action", "Pick one slow movement: a walk, a turn, a wave. Skip fights, sports and crowds."],
  ["Hands doing detailed work", "Keep hands out of the close-up, or show them from far away."],
  ["Real people's faces", "Describe the person (age, clothes, mood) instead of naming someone."],
  ["A story with several steps", "Make one video per step and join them in CapCut."],
  ["The word “drone”", "Write “aerial view”. Wan sometimes draws the drone into the sky."],
];
$("#weakChips").innerHTML = WEAK.map((w, i) => `<button data-weak="${i}">${esc(w[0])}</button>`).join("");
$("#weakChips").onclick = e => {
  const b = e.target.closest("[data-weak]"); if (!b) return;
  $$("#weakChips button").forEach(x => x.classList.toggle("on", x === b));
  $("#weakTip").textContent = WEAK[+b.dataset.weak][1];
  $("#weakTip").classList.add("tipon");
};

// ------------------------------------------------------------------ menu style (A/B/C/D)
function setNav(n, save = true) {
  document.documentElement.dataset.nav = n;
  $$("#navPick button[data-nav]").forEach(b => b.classList.toggle("on", b.dataset.nav === n));
  if (save) { try { localStorage.setItem("ws_nav", n); } catch (e) {} api("/api/settings", { json: { nav: n } }).catch(() => {}); }
}
$("#dockPower").onclick = () => $("#powerSwitch").click();
$("#homePower").onclick = () => $("#powerSwitch").click();
$("#vCompare").onclick = () => {
  const v = $("#vVideo"), t = v.currentTime, on = $("#vCompare").dataset.on === "1";
  v.src = on ? "/media/" + encodeURIComponent(cur.file) : "/uploads/" + encodeURIComponent(cur.original);
  v.currentTime = t; v.play().catch(() => {});
  $("#vCompare").dataset.on = on ? "" : "1"; $("#vCompare").textContent = on ? "Show original" : "Show enhanced";
};

// ------------------------------------------------------------------ API keys (Settings)
async function renderKeys() {
  const box = $("#keyList"); if (!box) return;
  if (S && !S.local) { $("#keysCard").classList.add("hidden"); return; }
  let keys = [];
  try { keys = await api("/api/keys"); } catch (e) { box.innerHTML = `<p class="hint">${esc(e.message)}</p>`; return; }
  box.innerHTML = keys.map(k => `
    <div class="key-row" data-p="${k.provider}">
      <div class="key-main"><b>${esc(k.label)}</b><span class="hint">${esc(k.used)}</span></div>
      <code class="key-mask">${k.set ? esc(k.masked) : "not set"}</code>
      <div class="row">
        ${k.set ? `<button class="btn small" data-ktest="${k.provider}">Test</button>` : ""}
        <button class="btn small" data-kedit="${k.provider}">${k.set ? "Edit" : "Add"}</button>
        ${k.set ? `<button class="btn small danger" data-kdel="${k.provider}">Remove</button>` : ""}
      </div>
      <div class="key-msg hint" id="kmsg-${k.provider}"></div>
    </div>`).join("");
  $("#keyProvider").innerHTML = keys.map(k => `<option value="${k.provider}">${esc(k.label)}</option>`).join("");
}
$("#keyList").onclick = async e => {
  const t = e.target.closest("[data-ktest]"), ed = e.target.closest("[data-kedit]"), del = e.target.closest("[data-kdel]");
  if (t) {
    const msg = $("#kmsg-" + t.dataset.ktest); msg.textContent = "Testing…"; msg.className = "key-msg hint";
    try { const r = await api(`/api/keys/${t.dataset.ktest}/test`, { method: "POST" }); msg.textContent = r.message; msg.className = "key-msg " + (r.ok ? "ok" : "bad"); }
    catch (err) { msg.textContent = err.message; msg.className = "key-msg bad"; }
  }
  if (ed) {
    $("#keyProvider").value = ed.dataset.kedit; $("#keyValue").value = ""; $("#keyForm").classList.remove("hidden");
    $("#keyValue").focus();
  }
  if (del) {
    const label = del.closest(".key-row").querySelector("b").textContent;
    if (!(await confirmBox(`Remove the ${label} key?`, "The app will stop using this service until you add a key again. The key itself is not cancelled at the provider.", "Remove"))) return;
    await api(`/api/keys/${del.dataset.kdel}`, { method: "DELETE" }); toast(`${esc(label)} key removed`); renderKeys();
  }
};
$("#keyAdd").onclick = () => { $("#keyValue").value = ""; $("#keyForm").classList.toggle("hidden"); $("#keyValue").focus(); };
$("#keyCancel").onclick = () => { $("#keyForm").classList.add("hidden"); $("#keyValue").value = ""; };
$("#keySave").onclick = async () => {
  const provider = $("#keyProvider").value, key = $("#keyValue").value.trim();
  try {
    await api("/api/keys", { json: { provider, key } });
    $("#keyValue").value = ""; $("#keyForm").classList.add("hidden");
    toast("Key saved", "good"); await renderKeys();
    const b = $(`[data-ktest="${provider}"]`); if (b) b.click();   // test it straight away
  } catch (e) { toast(esc(e.message), "bad"); }
};

// ------------------------------------------------------------------ extra AI features (NVIDIA free models)
function showPhoto(name) {
  form.image = name; form.imageUrl = "/uploads/" + name;
  $("#dropImg").src = form.imageUrl;
  $("#dropEmpty").classList.add("hidden"); $("#dropFull").classList.remove("hidden");
  updateFeatureButtons();
}
function updateFeatureButtons() {
  $("#motionBtn").classList.toggle("hidden", !(form.mode === "i2v" && form.image));
}
$$("#modeSeg button").forEach(b => b.addEventListener("click", updateFeatureButtons));

// 1) Pictures card: make a picture, then animate it
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

// 5) suggest motion from the photo
$("#motionBtn").onclick = async () => {
  if (!form.image) { toast("Choose a photo first"); return; }
  const btn = $("#motionBtn"); btn.disabled = true; btn.querySelector("span").textContent = "Looking at the photo…";
  try {
    const r = await api("/api/suggest-motion", { json: { image: form.image, prompt: promptEl.value.trim() } });
    showOptions(r.options, "Ideas from looking at your photo");
  } catch (e) { toast(esc(e.message), "bad"); }
  finally { btn.disabled = false; btn.querySelector("span").textContent = "Suggest motion"; }
};

// 4) social post kit in the video viewer
$("#vSocial").onclick = async () => {
  const box = $("#vSocialBox"), btn = $("#vSocial");
  btn.disabled = true; btn.textContent = "Writing…";
  box.innerHTML = `<p class="hint">Writing a title, caption and hashtags…</p>`; box.classList.remove("hidden");
  try {
    const r = await api("/api/social-kit", { json: { id: cur.id } });
    const all = [r.hook, "", r.caption, "", r.hashtags.join(" ")].join("\n");
    box.innerHTML = `<div class="kit-head"><b>For ${esc(r.platform)}</b><button class="btn small primary" data-copy="${esc(all)}">Copy all</button></div>`
      + [["Title", r.title], ["Hook", r.hook], ["Caption", r.caption], ["Hashtags", r.hashtags.join(" ")]].filter(([, v]) => v)
        .map(([k, v]) => `<div class="kit-row"><span class="hint">${k}</span><p>${esc(v)}</p><button class="btn small ghost" data-copy="${esc(v)}">Copy</button></div>`).join("");
  } catch (e) { box.innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  finally { btn.disabled = false; btn.textContent = "Caption & hashtags"; }
};
$("#vSocialBox").onclick = async e => {
  const b = e.target.closest("[data-copy]"); if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.copy); toast("Copied"); } catch (err) { toast("Could not copy"); }
};

// ------------------------------------------------------------------ boot
(async function boot() {
  try { S = await api("/api/state"); } catch (e) { S = null; }
  if (S) {
    setAspect(S.settings.aspect || "16:9");
    $("#seconds").value = S.settings.seconds || 5; $("#seconds").oninput();
    document.documentElement.dataset.theme = S.settings.theme || "dark";
  }
  setNav("d", false);
  analyze();
  await loadDemos();
  await loadLibrary();
  go((location.hash || "#create").slice(1) || "create");
  poll();
})();

// ------------------------------------------------------------------ Animate (Wan 2.2 Animate on GPU 2)
const anim = { image: null, video: null, aspect: "9:16", seconds: 5, dur: 0 };
function animReady() {
  const ok = anim.image && anim.video;
  $("#aBtn").disabled = !ok;
  if (!ok) { $("#aEstimate").textContent = !anim.image ? "Choose a character photo." : "Choose a motion video."; return; }
  const secs = anim.seconds === 5 && anim.dur >= 4.9 ? 5 : 3;
  const mins = Math.round((240 + 15.6 * (secs * 16 + 1)) / 60);
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
