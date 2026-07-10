@echo off
setlocal
cd /d "%~dp0"
title Sprite Design Tools - Setup

echo.
echo  Sprite Design Tools Setup
echo  =========================
echo.

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=py"
) else (
    where python >nul 2>nul || goto :no_python
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating a private Python environment...
    %PYTHON% -m venv .venv || goto :failed
) else (
    echo [1/4] Private Python environment already exists.
)

echo [2/4] Installing required image libraries...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto :failed

echo [3/4] Optional local AI background removal
echo       AI removal runs entirely on this computer using its own hardware.
echo       Images are not uploaded. Extra packages and a model download are required.
choice /C YN /N /M "Install local AI background removal? [Y/N]: "
if errorlevel 2 goto :skip_ai

echo       Installing rembg and ONNX Runtime...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check rembg onnxruntime
if errorlevel 1 (
    echo.
    echo       AI support could not be installed for this Python version.
    echo       The standard Connected and Color Key modes will still work.
) else (
    echo       Local AI support is ready. Its model downloads automatically on first use.
)
goto :check_ffmpeg

:skip_ai
echo       Skipped. Connected and Color Key background removal remain available.

:check_ffmpeg
echo [4/4] Checking video support...
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo       ffmpeg was not found. Video to Sprite Sheet will need it.
    echo       Install later with: winget install Gyan.FFmpeg
) else (
    echo       ffmpeg is ready.
)

echo.
echo Setup complete. Opening Sprite Design Tools...
start "" ".venv\Scripts\pythonw.exe" "launcher.py"
exit /b 0

:no_python
echo Python 3 was not found. Install it from https://python.org and run this file again.
pause
exit /b 1

:failed
echo.
echo Setup did not complete. Review the message above, then run Install.bat again.
pause
exit /b 1
