@echo off
REM Construit QuakePad : dist\QuakePad\ (dossier), puis l'installateur dist\QuakePad-Setup-X.exe
REM si Inno Setup 6 est installe (https://jrsoftware.org/isinfo.php).
REM Etapes : dependances verifiees (empreintes) -> analyse du code -> tests -> PyInstaller -> Inno Setup.
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
echo === Construction (PyInstaller) ===
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name QuakePad ^
  --icon assets\quakepad.ico ^
  --add-data "assets;assets" ^
  run_quakepad.py || goto :error

for /f %%v in ('%PY% -c "import sys; sys.path.insert(0, '.'); from quakepad.settings import APP_VERSION; print(APP_VERSION)"') do set VERSION=%%v

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
REM (pas de bloc entre parentheses : le chemin "(x86)" casserait la syntaxe du batch)
if not exist "%ISCC%" goto :no_inno
echo.
echo === Installateur (Inno Setup) ===
"%ISCC%" /Qp "/DAppVersion=%VERSION%" installer\QuakePad.iss || goto :error
echo.
echo  OK : dist\QuakePad-Setup-%VERSION%.exe
exit /b 0

:no_inno
echo.
echo  OK : dist\QuakePad\QuakePad.exe
echo  Installez Inno Setup 6 pour generer aussi l'installateur.
exit /b 0

:error
echo.
echo  ECHEC de la construction.
exit /b 1
