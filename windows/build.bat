@echo off
REM Construit dist\QuakePad.exe (executable autonome, sans console).
REM Etapes : dependances verifiees (empreintes) -> analyse du code -> tests -> PyInstaller.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)
set PY=.venv\Scripts\python.exe
%PY% -m pip install --disable-pip-version-check --require-hashes --no-deps -r requirements.txt -r requirements-dev.txt || goto :error
copy /y requirements.txt .venv\installed-requirements.txt >nul

echo.
echo === Analyse du code (ruff) ===
%PY% -m ruff check quakepad tests || goto :error

echo.
echo === Tests (pytest) ===
set QT_QPA_PLATFORM=offscreen
%PY% -m pytest || goto :error
set QT_QPA_PLATFORM=

echo.
echo === Construction de l'executable ===
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name QuakePad ^
  --icon assets\quakepad.ico ^
  --add-data "assets;assets" ^
  run_quakepad.py || goto :error

echo.
echo  OK : dist\QuakePad.exe
exit /b 0

:error
echo.
echo  ECHEC de la construction.
exit /b 1
