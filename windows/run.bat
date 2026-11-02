@echo off
REM Lance QuakePad depuis les sources (sans compiler)
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
    pip install -q -r requirements.txt
)
start "" pythonw run_quakepad.py %*
