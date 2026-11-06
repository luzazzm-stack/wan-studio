# Adds: make a picture first (FLUX), suggest motion (Llama vision), caption & hashtags (NVIDIA text).
import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def rep(s, old, new, label):
    assert old in s, label
    return s.replace(old, new, 1)


s = open("server.py", encoding="utf-8").read()
assert "api_make_image" not in s
s = rep(s, "async def api_settings(req):", open("tools/features_server.py", encoding="utf-8").read() + "\n\nasync def api_settings(req):", "anchor")
s = rep(s, '''        web.post("/api/upload", api_upload), web.post("/api/improve", api_improve),''',
        '''        web.post("/api/upload", api_upload), web.post("/api/improve", api_improve),
        web.post("/api/make-image", api_make_image), web.post("/api/suggest-motion", api_suggest_motion),
        web.post("/api/social-kit", api_social_kit),''', "routes")
s = s.replace('"nvidia": {"label": "NVIDIA", "used": "Not used yet (for extra features)"}',
              '"nvidia": {"label": "NVIDIA", "used": "Make a picture first, Suggest motion, Caption & hashtags"}')
s = s.replace('"openrouter": {"label": "OpenRouter", "used": "Not used yet (for extra features)"}',
              '"openrouter": {"label": "OpenRouter", "used": "Not used right now"}')
open("server.py", "w", encoding="utf-8").write(s)
import ast
ast.parse(s)

h = open("web/index.html", encoding="utf-8").read()
h = rep(h, '''      <div class="improve-opts hidden" id="improveOpts" aria-live="polite"></div>''',
        '''      <div class="improve-opts hidden" id="improveOpts" aria-live="polite"></div>
      <div class="improve-opts hidden" id="picOpts" aria-live="polite"></div>''', "picOpts")
h = rep(h, '''        <button class="btn glass-btn" id="builderBtn">''',
        '''        <button class="btn glass-btn hidden" id="motionBtn"><iconify-icon icon="solar:eye-scan-linear" aria-hidden="true"></iconify-icon><span>Suggest motion</span></button>
        <button class="btn glass-btn" id="makePicBtn"><iconify-icon icon="solar:gallery-add-linear" aria-hidden="true"></iconify-icon><span>Make a picture first</span></button>
        <button class="btn glass-btn" id="builderBtn">''', "tools")
h = rep(h, '''          <button class="btn glass-btn" id="vCopy">Copy prompt</button>''',
        '''          <button class="btn glass-btn" id="vCopy">Copy prompt</button>
          <button class="btn glass-btn" id="vSocial">Caption &amp; hashtags</button>''', "vSocial")
h = rep(h, '''        <div class="vbtns">''', '''        <div class="social-kit hidden" id="vSocialBox" aria-live="polite"></div>
        <div class="vbtns">''', "vSocialBox")
open("web/index.html", "w", encoding="utf-8").write(h)

a = open("web/app.js", encoding="utf-8").read()
# uploading a photo should also reveal "Suggest motion"
a = rep(a, '''    $("#dropEmpty").classList.add("hidden"); $("#dropFull").classList.remove("hidden");
    const img = new Image();''', '''    $("#dropEmpty").classList.add("hidden"); $("#dropFull").classList.remove("hidden"); updateFeatureButtons();
    const img = new Image();''', "upload hook")
# a fresh viewer should not show the previous video's caption
a = rep(a, '''  $("#vPrompt").textContent = cur.prompt || "";''', '''  $("#vPrompt").textContent = cur.prompt || "";
  $("#vSocialBox").classList.add("hidden"); $("#vSocialBox").innerHTML = "";''', "viewer reset")
a = a.replace("// ------------------------------------------------------------------ boot",
              open("tools/features_ui.js", encoding="utf-8").read() + "\n// ------------------------------------------------------------------ boot", 1)
assert "api/make-image" in a
open("web/app.js", "w", encoding="utf-8").write(a)

c = open("web/style.css", encoding="utf-8").read()
c += '''
/* make a picture first */
.pic-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
.pic { padding: 0; border-radius: var(--r); overflow: hidden; border: 2px solid var(--line); background: rgba(10,10,12,.7); cursor: pointer; transition: border-color .3s; min-height: 120px; }
.pic:hover, .pic:focus-visible { border-color: var(--accent); }
.pic img { display: block; width: 100%; height: auto; }
.pic.skeleton { aspect-ratio: 16 / 9; animation: pulse 1.4s ease-in-out infinite; cursor: default; }
@keyframes pulse { 50% { opacity: .45; } }
/* caption & hashtags */
.social-kit { display: grid; gap: 8px; padding: 12px; border-radius: var(--r); border: 1px solid color-mix(in srgb, var(--accent) 45%, transparent); background: var(--accent-soft); margin-bottom: 12px; }
.kit-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.kit-row { display: grid; grid-template-columns: 70px 1fr auto; gap: 8px; align-items: start; }
.kit-row p { margin: 0; font-size: 13px; line-height: 1.5; color: var(--text); }
'''
open("web/style.css", "w", encoding="utf-8").write(c)
print("ok")
