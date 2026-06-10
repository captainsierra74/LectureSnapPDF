@echo off
title LectureSnapPDF Installer
echo =============================================
echo  LectureSnapPDF — Installation
echo =============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python 3.10 or later from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Step 1: Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo Step 2: Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo Warning: Some dependencies may have failed.
)

echo Step 3: Downloading fonts...
python -c "from font_manager import FontManager; FontManager().download_fonts()"
if errorlevel 1 (
    echo Warning: Font download failed. App will use system fonts.
)

echo.
echo =============================================
echo  Installation complete!
echo.
echo  To run the app:
echo    call venv\Scripts\activate.bat
echo    python main.py
echo.
echo  Or double-click run.bat (create it with the two commands above)
echo =============================================
pause
