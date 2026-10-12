@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    py -3 -m venv "%ROOT%.venv"
    if errorlevel 1 goto setup_error
    "%PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 goto setup_error
    "%PYTHON%" -m pip install -r "%ROOT%requirements.txt"
    if errorlevel 1 goto setup_error
)

"%PYTHON%" "%ROOT%GUI.py"
if errorlevel 1 pause
endlocal
exit /b

:setup_error
echo Python environment setup failed. Install Python 3.10+ and check your internet connection for pip packages.
pause
endlocal
exit /b 1
