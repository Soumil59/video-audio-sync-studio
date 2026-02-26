@echo off
REM Installation script for Video-Audio Sync Editor (Windows)

echo ======================================
echo Video-Audio Sync Editor Installation
echo ======================================
echo.

REM Check Python
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python %PYTHON_VERSION% detected
echo.

REM Check FFmpeg
echo Checking for FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo Warning: FFmpeg not found!
    echo.
    echo Please install FFmpeg:
    echo   1. Download from https://ffmpeg.org/download.html
    echo   2. Or use Chocolatey: choco install ffmpeg
    echo.
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
) else (
    echo FFmpeg detected
)
echo.

REM Create virtual environment
echo Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Skipping...
) else (
    python -m venv venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created
)
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo Virtual environment activated
echo.

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip --quiet
echo pip upgraded
echo.

REM Install dependencies
echo Installing dependencies...
echo (This may take a few minutes...)
pip install -r requirements.txt --quiet

if errorlevel 1 (
    echo Error: Failed to install some dependencies
    pause
    exit /b 1
)
echo All dependencies installed successfully
echo.

REM Create launch script
echo Creating launch script...
(
echo @echo off
echo REM Launch script for Video-Audio Sync Editor
echo.
echo call venv\Scripts\activate.bat
echo python video_audio_sync_app.py
echo.
echo pause
) > launch.bat

echo Launch script created
echo.

echo ======================================
echo Installation Complete!
echo ======================================
echo.
echo To run the application:
echo   Double-click launch.bat
echo.
echo Or manually:
echo   1. Run: venv\Scripts\activate.bat
echo   2. Run: python video_audio_sync_app.py
echo.
echo Enjoy!
echo.
pause
