@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv311\Scripts\python.exe" (
    py -3.11 -m venv .venv311
    if errorlevel 1 goto error
)

".venv311\Scripts\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3, 11) else 1)"
if errorlevel 1 (
    echo The .venv311 folder is not using Python 3.11.
    goto error
)

".venv311\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

".venv311\Scripts\python.exe" GUI.py
if errorlevel 1 goto error
exit /b 0

:error
echo.
echo LUMI did not start. Read the error above, then press any key to close.
pause >nul
exit /b 1
