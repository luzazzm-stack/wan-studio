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
