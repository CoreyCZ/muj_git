@echo off
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo Nejdriv spust instalace.bat
    pause
    exit /b 1
)
venv\Scripts\python.exe shorts_maker.py
pause
