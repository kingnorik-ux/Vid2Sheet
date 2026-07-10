@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    call "Install.bat"
    exit /b
)
start "" ".venv\Scripts\pythonw.exe" "launcher.py"
