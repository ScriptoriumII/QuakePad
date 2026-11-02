@echo off
REM Lance QuakePad depuis les sources (sans compiler).
REM Les dependances sont figees (versions + empreintes SHA-256 dans requirements.txt) et ne sont
REM (re)installees que lorsque requirements.txt change : pas de telechargement a chaque lancement.
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    py -3 -m venv .venv || python -m venv .venv || goto :error
)

fc /b requirements.txt .venv\installed-requirements.txt >nul 2>&1
if errorlevel 1 (
    echo Installation des dependances verifiees...
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check --require-hashes --no-deps -r requirements.txt || goto :error
    copy /y requirements.txt .venv\installed-requirements.txt >nul
)

start "" .venv\Scripts\pythonw.exe run_quakepad.py %*
exit /b 0

:error
echo.
echo  ECHEC de l'installation des dependances (voir le message ci-dessus).
pause
exit /b 1
