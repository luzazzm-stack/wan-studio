# Adapts app.js to the dark-glass UI (2026-09-30): reuses the redesign copy/markup replacements where they still apply.
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))
src = open("../tools/redesign_patch.py", encoding="utf-8").read()
start = src.index("R = [")
end = src.index("\n]\n", start) + 3
ns = {}
exec(src[start:end], ns)
a = open("app.js", encoding="utf-8").read()
applied = 0
for old, new in ns["R"]:
    if old in a:
        a = a.replace(old, new)
        applied += 1
extra = [
    ('box.className = "power " + p;', 'box.className = "status " + p;'),
    ('btn.disabled = true; btn.textContent = "Improving… (about 40 s)";', 'btn.disabled = true; $("span", btn).textContent = "Improving… (about 40 s)";'),
    ('btn.disabled = false; btn.textContent = "Improve my prompt";', 'btn.disabled = false; $("span", btn).textContent = "Improve my prompt";'),
    ('btn.disabled = true; btn.textContent = "✨ Improving…";', 'btn.disabled = true; $("span", btn).textContent = "Improving… (about 40 s)";'),
    ('btn.disabled = false; btn.textContent = "✨ Improve my prompt";', 'btn.disabled = false; $("span", btn).textContent = "Improve my prompt";'),
    ('+${active.length - 4} more in the queue →</a>', '${active.length - 4} more in the queue</a>'),
    ('$("#makingTitle").classList.toggle("hidden", !active.length);', 'const mt = $("#makingTitle"); if (mt) mt.classList.toggle("hidden", !active.length);'),
]
for old, new in extra:
    if old in a:
        a = a.replace(old, new)
        applied += 1
open("app.js", "w", encoding="utf-8").write(a)
left = [s for s in ("✨", "🎬 ", "🎲", "🎞", "⭐", "❌", "✅", "🔍", "🌊", "→ Video", "power \" + p") if s in a]
print("applied", applied, "| leftovers:", left)
