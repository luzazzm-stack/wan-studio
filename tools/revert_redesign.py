# Restores the pre-redesign look (user preferred it), keeping non-visual fixes.
import os, runpy
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))

# Reuse the replacement list from the redesign patch and apply it in reverse.
src = open("../tools/redesign_patch.py", encoding="utf-8").read()
start = src.index("R = [")
end = src.index("\n]\n", start) + 3
ns = {}
exec(src[start:end], ns)
R = ns["R"]
KEEP_NEW = ("drop.onclick", "const ago", "Used ${q.used_h", '["Made"', "const p = S.power, L = S.live")
a = open("app.js", encoding="utf-8").read()
for old, new in R:
    if old.startswith(KEEP_NEW) or old.lstrip().startswith(KEEP_NEW):
        continue
    if new not in a:
        print("skip (not found):", new[:60].replace("\n", " "))
        continue
    a = a.replace(new, old)
# The redesign deleted this helper; the old template cards need it again.
if "const icon = id =>" not in a:
    a = a.replace('  const list = TEMPLATES.filter(t => (tplCat === "all"',
                  '  const icon = id => (TEMPLATE_CATEGORIES.find(c => c.id === id) || {}).icon || "🎬";\n  const list = TEMPLATES.filter(t => (tplCat === "all"', 1)
# The "Making now" heading only exists in the new layout.
a = a.replace('$("#makingTitle").classList.toggle("hidden", !active.length);', 'const mt = $("#makingTitle"); if (mt) mt.classList.toggle("hidden", !active.length);')
open("app.js", "w", encoding="utf-8").write(a)
print("app.js reverted")
