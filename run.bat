@echo off
title LectureSnapPDF
cd /d "%~dp0"
python main.py
if errorlevel 1 (
    echo.
    echo App closed with error code %errorlevel%. Press any key to exit.
    pause
)
