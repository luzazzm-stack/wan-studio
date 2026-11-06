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
