#!/usr/bin/env bash
# Builds the PUBLIC Windows app (Git Bash on Windows):
#   build/dist_client/WanStudio/      the program folder (WanStudio.exe + web/ + kaggle/)
#   build/WanStudio-Windows.zip       portable copy of that folder
#   build/WanStudio-Setup.exe         installer (Inno Setup 6), per-user, no admin needed
# Every user signs in with their own Kaggle account; nothing from data/ or keys/ (tokens, settings, API keys, videos)
# is included. The developer build (build_app.sh -> app/WanStudio) is not touched.
#
# Needs: a Python 3.12 with requirements.txt + pyinstaller installed (set PY=... to point at it), and Inno Setup 6
# (set ISCC=... if it is not in the usual place).
set -e
cd "$(dirname "$0")"
W=$(cygpath -w "$(pwd)")
PY="${PY:-.venv-app/Scripts/python.exe}"
ISCC="${ISCC:-$LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe}"
VERSION="${VERSION:-1.0.0}"
OUT=build/dist_client
mkdir -p build
rm -rf "$OUT" build/pyi_client build/WanStudio-Windows.zip build/WanStudio-Setup.exe
PYTHONDONTWRITEBYTECODE=1 "$PY" -m PyInstaller --noconfirm --clean --windowed --name WanStudio --icon "$W\web\wanstudio.ico" \
  --distpath "$OUT" --workpath build/pyi_client --specpath build/client \
  --collect-all webview --collect-all kagglesdk --collect-all kaggle --hidden-import server --hidden-import kaggle_ctl \
  --paths "$W" app_main.py > build/build_client_log.txt 2>&1
tail -1 build/build_client_log.txt
APP="$OUT/WanStudio"
mkdir -p "$APP/kaggle"
cp -r web "$APP/web"
cp kaggle/wan_server.py "$APP/kaggle/"
rm -rf "$APP/data" "$APP/keys" "$APP/demos"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

# portable zip
"$PY" - "$OUT" <<'EOF'
import os, sys, zipfile
out = sys.argv[1]
src = os.path.join(out, "WanStudio")
dst = os.path.join(os.path.dirname(out), "WanStudio-Windows.zip")
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("data", "keys", "__pycache__")]
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.join("Wan Studio", os.path.relpath(p, src)))
print("zip:", dst, round(os.path.getsize(dst) / 1e6, 1), "MB")
EOF

# installer
MSYS2_ARG_CONV_EXCL="*" "$ISCC" /Q "/DAppVersion=$VERSION" "/DDistDir=$W\build\dist_client\WanStudio" "/DOutDir=$W\build" "$W\installer\WanStudio.iss"
ls -la build/WanStudio-Setup.exe
