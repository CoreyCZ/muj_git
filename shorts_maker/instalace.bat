@echo off
cd /d "%~dp0"
echo === Instalace knihoven pro Shorts Maker ===
if not exist venv (
    py -3.12 -m venv venv
    if errorlevel 1 python -m venv venv
)
if not exist venv\Scripts\python.exe (
    echo CHYBA: Nepodarilo se vytvorit prostredi. Je nainstalovany Python 3.12?
    pause
    exit /b 1
)
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -U -r requirements.txt
echo.
echo === Hotovo. Program spustis souborem spustit.bat ===
pause
