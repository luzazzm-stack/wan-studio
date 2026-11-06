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
