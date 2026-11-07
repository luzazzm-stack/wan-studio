#!/usr/bin/env bash
# Rebuilds the Windows app (needed after changing server.py, kaggle_ctl.py or app_main.py; web/ changes need no rebuild).
cd "$(dirname "$0")"
W=$(cygpath -w "$(pwd)")
.venv-app/Scripts/python.exe -m PyInstaller --noconfirm --clean --windowed --name WanStudio --icon "$W\web\wanstudio.ico" --distpath app --workpath build/pyi --specpath build --collect-all webview --collect-all kagglesdk --collect-all kaggle --hidden-import server --hidden-import kaggle_ctl --paths "$W" app_main.py > build_log.txt 2>&1
tail -1 build_log.txt
