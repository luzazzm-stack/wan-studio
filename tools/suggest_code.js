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
  btn.disabled = true; label.textContent = S && S.power === "ready" ? "Writing 3 versions…" : "Improving…";
  try {
    const r = await api("/api/improve", { json: { prompt: idea, mode: form.mode, aspect: form.aspect } });
    if (r.options && r.options.length) showOptions(r.options, r.model && r.model.includes("7b") ? "written by the larger AI on the GPU" : "written by the AI");
    else showOptions([offlineImprove(idea)], S && S.power === "ready" ? "the AI didn't answer, so this uses built-in ideas" : "server is off, so this uses built-in ideas. Turn it on for 3 AI versions");
  } catch (e) { showOptions([offlineImprove(idea)], "built-in ideas"); }
  btn.disabled = false; label.textContent = "Improve my prompt";
};
