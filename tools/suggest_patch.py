# Wires the topic-aware suggestions and the 3-version picker into app.js / index.html / style.css.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))
a = open("app.js", encoding="utf-8").read()
# tips: render via renderTips()
old = '''  $("#tips").innerHTML = t ? missing.map(c => `<span class="tip" data-add="${esc(c.add)}">+ ${c.tip}: <i>${esc(c.add)}</i></span>`).join("") : "";
}'''
assert old in a
a = a.replace(old, '''  renderTips();
}''', 1)
# remove old offlineImprove + improve handler; insert new block
s0 = a.index("function offlineImprove(idea) {")
s1 = a.index('$("#surpriseBtn").onclick')
a = a[:s0] + open("../tools/suggest_code.js", encoding="utf-8").read() + "\n" + a[s1:]
open("app.js", "w", encoding="utf-8").write(a)

h = open("index.html", encoding="utf-8").read()
old = '      <div class="tips" id="tips"></div>'
assert old in h
h = h.replace(old, old + '\n      <div class="improve-opts hidden" id="improveOpts" aria-live="polite"></div>', 1)
open("index.html", "w", encoding="utf-8").write(h)

c = open("style.css", encoding="utf-8").read()
c += '''
/* topic-aware ideas + 3-version picker */
.tips { align-items: center; }
.tips-head { font-size: 12.5px; color: var(--muted); margin-right: 4px; }
.tip { font: 12.5px var(--body); text-align: left; }
.tip b { color: var(--accent); font-weight: 600; margin-right: 3px; }
.improve-opts { margin-top: 14px; display: grid; gap: 8px; padding: 14px; border-radius: var(--r-lg); border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent); background: var(--accent-soft); }
.opts-head { display: flex; align-items: baseline; gap: 10px; }
.opts-head b { font: 600 14px var(--head); }
.opts-head .hint { flex: 1; }
.opt { display: flex; gap: 12px; text-align: left; padding: 12px 14px; border-radius: var(--r); border: 1px solid var(--line); background: rgba(10,10,12,.7); color: var(--text-2); cursor: pointer; font-size: 13.5px; line-height: 1.5; transition: border-color .3s, color .3s; }
.opt:hover { border-color: var(--accent); color: var(--text); }
.opt-n { flex: none; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: var(--accent-ink); font-weight: 700; font-size: 12px; }
'''
open("style.css", "w", encoding="utf-8").write(c)
print("ok")
