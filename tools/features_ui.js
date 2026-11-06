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

// 1) picture first, then video
$("#makePicBtn").onclick = async () => {
  const idea = promptEl.value.trim();
  if (!idea) { toast("Describe the picture first, then press this"); promptEl.focus(); return; }
  const btn = $("#makePicBtn"), box = $("#picOpts");
  btn.disabled = true; btn.querySelector("span").textContent = "Making pictures…";
  box.innerHTML = `<div class="opts-head"><b>Making 2 pictures</b><span class="hint">About 15 seconds, using NVIDIA's free FLUX model</span></div>`
    + `<div class="pic-grid">${"<div class='pic skeleton'></div>".repeat(2)}</div>`;
  box.classList.remove("hidden");
  try {
    const r = await api("/api/make-image", { json: { prompt: idea, aspect: form.aspect, count: 2 } });
    box.innerHTML = `<div class="opts-head"><b>Pick a starting picture</b><span class="hint">Wan will bring it to life</span>`
      + `<button class="btn small ghost" id="picAgain">Try again</button><button class="btn small ghost" id="picClose">Close</button></div>`
      + `<div class="pic-grid">${r.images.map(n => `<button class="pic" data-pic="${esc(n)}"><img src="/uploads/${esc(n)}" alt="Picture option" width="${r.width}" height="${r.height}"></button>`).join("")}</div>`;
  } catch (e) {
    box.innerHTML = `<div class="opts-head"><b>Could not make a picture</b><span class="hint">${esc(e.message)}</span><button class="btn small ghost" id="picClose">Close</button></div>`;
  } finally { btn.disabled = false; btn.querySelector("span").textContent = "Make a picture first"; }
};
$("#picOpts").onclick = e => {
  if (e.target.closest("#picClose")) { $("#picOpts").classList.add("hidden"); return; }
  if (e.target.closest("#picAgain")) { $("#makePicBtn").click(); return; }
  const p = e.target.closest("[data-pic]"); if (!p) return;
  $('#modeSeg button[data-mode="i2v"]').click();
  showPhoto(p.dataset.pic);
  $("#picOpts").classList.add("hidden");
  toast("Picture chosen. Now describe how it should move, or press Suggest motion.", "good");
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
