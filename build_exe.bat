@echo off
REM Builds a standalone Windows app in dist\FaceAttend\ (no Python needed on target PC).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run run.bat once first to create the environment.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\pyinstaller.exe" --noconfirm --windowed --name FaceAttend ^
    --add-data "assets;assets" --collect-data customtkinter main.py
echo.
echo Done. Copy the folder dist\FaceAttend to any Windows PC and run FaceAttend.exe
pause
