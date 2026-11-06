# Replaces the static Guide page with the interactive "Prompt lab" (checker, camera moves with demos, time calculator).
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))

h = open("index.html", encoding="utf-8").read()
s = h.index('<section class="page" id="page-help">')
e = h.index("</section>", s) + len("</section>")
new = '''<section class="page" id="page-help">
  <div class="page-head"><div><h1>Prompt lab</h1></div></div>
  <div class="lab">
    <article class="glass card lab-check">
      <h2>Check a prompt</h2>
      <textarea id="labPrompt" rows="4" autocomplete="off" aria-label="Prompt to check" placeholder="Type or paste a prompt, e.g. a boat on Phewa Lake at dawn…"></textarea>
      <div class="lab-score"><div class="strength-bar"><i id="labFill"></i></div><b id="labVerdict">Start typing…</b><span class="hint" id="labWords"></span></div>
      <div class="checklist" id="labChecks"></div>
      <div class="row end"><button class="btn ghost" id="labClear">Clear</button><button class="btn glass-btn" id="labExample">Show me a good one</button><button class="btn primary" id="labUse">Use in Create<iconify-icon icon="solar:arrow-right-linear" aria-hidden="true"></iconify-icon></button></div>
    </article>

    <article class="glass card lab-calc">
      <h2>How long will it take?</h2>
      <div class="lbl">Quality</div>
      <div class="seg small" id="calcQuality"><button data-q="turbo">Turbo</button><button data-q="standard" class="on">Standard</button><button data-q="high">High</button></div>
      <label class="lbl" for="calcSeconds">Length <span class="hint accent" id="calcSecLabel">5 s</span></label>
      <input type="range" id="calcSeconds" min="2" max="5" step="1" value="5">
      <label class="lbl" for="calcCount">How many videos <span class="hint accent" id="calcCountLabel">4</span></label>
      <input type="range" id="calcCount" min="1" max="30" step="1" value="4">
      <div class="calc-out">
        <div><b id="calcTime">–</b><span>until all are done</span></div>
        <div><b id="calcHours">–</b><span>of your free GPU hours</span></div>
        <div><b id="calcLeft">–</b><span>left this week after that</span></div>
      </div>
      <p class="hint" id="calcNote"></p>
    </article>

    <article class="glass card lab-moves">
      <div class="lab-moves-head"><h2>Camera moves: tap one to watch it</h2><span class="hint">Each clip was made by Wan with that move</span></div>
      <div class="moves">
        <div class="move-player"><video id="moveVideo" muted loop playsinline preload="none"></video><div class="move-cap"><b id="moveName"></b><span id="movePhrase"></span><button class="btn small primary" id="moveAdd">Add to my prompt</button></div></div>
        <div class="move-list" id="moveList"></div>
      </div>
    </article>

    <article class="glass card lab-weak">
      <h2>Wan struggles with</h2>
      <div class="weak" id="weakChips"></div>
      <p class="hint" id="weakTip">Tap one to see what to do instead.</p>
    </article>
  </div>
</section>'''
h = h[:s] + new + h[e:]
h = h.replace('title="Guide"><iconify-icon icon="solar:notes-linear" aria-hidden="true"></iconify-icon><b>Guide</b>',
              'title="Prompt lab"><iconify-icon icon="solar:test-tube-minimalistic-linear" aria-hidden="true"></iconify-icon><b>Lab</b>')
open("index.html", "w", encoding="utf-8").write(h)

a = open("app.js", encoding="utf-8").read()
s = a.index("// camera glossary")
e = a.index("// ------------------------------------------------------------------ menu style")
lab = open("../tools/lab_code.js", encoding="utf-8").read()
a = a[:s] + lab + "\n" + a[e:]
old = '''  if (page === "settings") renderSettings();'''
assert old in a
a = a.replace(old, '''  if (page === "settings") renderSettings();
  if (page === "help") { labCheck(); renderMoves(); renderCalc(); } else { const mv = $("#moveVideo"); if (mv) mv.pause(); }''')
open("app.js", "w", encoding="utf-8").write(a)

c = open("style.css", encoding="utf-8").read()
c += "\n" + open("../tools/lab_style.css", encoding="utf-8").read()
open("style.css", "w", encoding="utf-8").write(c)
print("ok; old glossary left:", "camGlossary" in a)
