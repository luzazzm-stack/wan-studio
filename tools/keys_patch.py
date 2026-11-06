# Adds the API keys manager to Settings (server routes, HTML card, JS, CSS).
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
s = open("server.py", encoding="utf-8").read()
anchor = "async def api_settings(req):"
assert anchor in s and "KEY_PROVIDERS" not in s
s = s.replace(anchor, open("tools/keys_server.py", encoding="utf-8").read() + "\n\n" + anchor, 1)
old = '''        web.post("/api/settings", api_settings),'''
assert old in s
s = s.replace(old, old + '''
        web.get("/api/keys", api_keys_list), web.post("/api/keys", api_keys_save),
        web.delete("/api/keys/{provider}", api_keys_delete), web.post("/api/keys/{provider}/test", api_keys_test),''', 1)
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)

h = open("web/index.html", encoding="utf-8").read()
old = '''    <article class="glass card" id="phoneCard">'''
assert old in h
h = h.replace(old, '''    <article class="glass card span2" id="keysCard">
      <div class="card-icon"><iconify-icon icon="solar:key-minimalistic-linear" aria-hidden="true"></iconify-icon></div>
      <div class="keys-head"><h2>API keys</h2><button class="btn small glass-btn" id="keyAdd"><iconify-icon icon="solar:add-circle-linear" aria-hidden="true"></iconify-icon>Add a key</button></div>
      <p class="hint">Keys stay on this laptop and are never shown in full. Only the laptop can change them, not the phone.</p>
      <div class="key-form hidden" id="keyForm">
        <select id="keyProvider" aria-label="Service"></select>
        <input id="keyValue" type="password" autocomplete="off" spellcheck="false" placeholder="Paste the key…" aria-label="API key">
        <button class="btn small primary" id="keySave">Save</button><button class="btn small ghost" id="keyCancel">Cancel</button>
      </div>
      <div class="key-list" id="keyList"></div>
    </article>
''' + old, 1)
open("web/index.html", "w", encoding="utf-8").write(h)

a = open("web/app.js", encoding="utf-8").read()
old = '''  if (page === "settings") renderSettings();'''
assert old in a
a = a.replace(old, '''  if (page === "settings") { renderSettings(); renderKeys(); }''', 1)
a = a.replace("// ------------------------------------------------------------------ boot", open("tools/keys_ui.js", encoding="utf-8").read() + "\n// ------------------------------------------------------------------ boot", 1)
assert "renderKeys()" in a and "async function renderKeys" in a
open("web/app.js", "w", encoding="utf-8").write(a)

c = open("web/style.css", encoding="utf-8").read()
c += '''
/* API keys manager */
.keys-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.keys-head h2 { margin: 0; }
.key-form { display: grid; grid-template-columns: minmax(150px, 220px) 1fr auto auto; gap: 8px; align-items: center; margin: 12px 0; }
.key-list { display: grid; gap: 8px; margin-top: 10px; }
.key-row { display: grid; grid-template-columns: 1fr auto auto; gap: 6px 14px; align-items: center; padding: 12px 14px; border-radius: var(--r); border: 1px solid var(--line); background: var(--panel-2); }
.key-main { display: flex; flex-direction: column; min-width: 0; }
.key-main b { font-weight: 600; }
.key-mask { font-size: 12.5px; }
.key-msg { grid-column: 1 / -1; }
.key-msg:empty { display: none; }
.key-msg.ok { color: var(--accent); }
.key-msg.bad { color: var(--bad); }
@media (max-width: 760px) { .key-form, .key-row { grid-template-columns: 1fr; } }
'''
open("web/style.css", "w", encoding="utf-8").write(c)
print("ok")
