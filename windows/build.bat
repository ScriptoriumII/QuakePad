@echo off
REM Construit dist\QuakePad.exe (exécutable autonome, sans console)
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller || goto :error

pyinstaller --noconfirm --clean --onefile --windowed ^
  --name QuakePad ^
  --icon assets\quakepad.ico ^
  --add-data "assets;assets" ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.Qt3DCore ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml ^
  run_quakepad.py || goto :error

echo.
echo  OK : dist\QuakePad.exe
exit /b 0

:error
echo.
echo  ECHEC de la construction.
exit /b 1
