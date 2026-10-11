@echo off
REM One-click launcher: creates a virtual environment on first run,
REM installs the requirements, then starts the application.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10-3.13 from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)

if not exist ".venv\installed.ok" (
    echo Installing requirements ^(first run only, needs internet^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
    echo ok> ".venv\installed.ok"
)

".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
exit /b 0

:error
echo.
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
