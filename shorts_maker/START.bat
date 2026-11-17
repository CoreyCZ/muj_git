@echo off
setlocal
cd /d "%~dp0"
title Shorts Maker
echo ============================================================
echo    SHORTS MAKER
echo    Prvni spusteni muze trvat 10-20 minut - stahuji a instaluji
echo    vse potrebne. Okno NEZAVIREJ. Kdyby se Windows ptal, zda
echo    povolit zmeny, klikni na ANO.
echo ============================================================
echo.

where winget >nul 2>nul
if errorlevel 1 goto chyba_winget

call :obnov_path

rem ---------- 1) Python 3.12 ----------
call :najdi_python
if defined PY goto python_ok
echo [1/4] Instaluji Python 3.12 ...
winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
call :obnov_path
call :najdi_python
if not defined PY goto chyba_python
:python_ok
echo [1/4] Python je pripraveny.

rem ---------- 2) FFmpeg (strihani videa) ----------
where ffmpeg >nul 2>nul
if not errorlevel 1 goto ffmpeg_ok
echo [2/4] Instaluji FFmpeg ...
winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements
call :obnov_path
where ffmpeg >nul 2>nul
if errorlevel 1 goto chyba_ffmpeg
:ffmpeg_ok
echo [2/4] FFmpeg je pripraveny.

rem ---------- 3) Deno (potrebuje ho stahovani z YouTube) ----------
where deno >nul 2>nul
if not errorlevel 1 goto deno_ok
echo [3/4] Instaluji Deno ...
winget install --id DenoLand.Deno -e --silent --accept-package-agreements --accept-source-agreements
call :obnov_path
:deno_ok
echo [3/4] Deno je pripravene.

rem ---------- 4) Knihovny programu ----------
if exist "venv\hotovo.txt" goto knihovny_aktualizace
echo [4/4] Instaluji knihovny programu (cca 1 GB, nekolik minut) ...
winget install --id Microsoft.VCRedist.2015+.x64 -e --silent --accept-package-agreements --accept-source-agreements >nul 2>nul
if not exist "venv\Scripts\python.exe" %PY% -m venv venv
if not exist "venv\Scripts\python.exe" goto chyba_venv
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -U -r requirements.txt
if errorlevel 1 goto chyba_pip
echo ok> "venv\hotovo.txt"
goto spustit

:knihovny_aktualizace
echo [4/4] Kontroluji aktualizaci stahovace YouTube ...
"venv\Scripts\python.exe" -m pip install -U -q "yt-dlp[default]" >nul 2>nul

:spustit
echo.
echo ============================================================
echo    Vse pripraveno. Program se otevre v prohlizeci.
echo    Tohle cerne okno NEZAVIREJ, dokud program pouzivas.
echo ============================================================
"venv\Scripts\python.exe" shorts_maker.py
echo.
echo Program skoncil. Pokud vyse vidis chybu, zkopiruj ji a posli ji.
pause
exit /b 0

rem ================= pomocne casti =================

:obnov_path
rem Nacte aktualni PATH z Windows, aby byly videt prave nainstalovane programy.
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`) do set "PATH=%%p"
exit /b 0

:najdi_python
set "PY="
py -3.12 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3.12"
if defined PY exit /b 0
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
exit /b 0

:chyba_winget
echo CHYBA: Ve Windows chybi nastroj winget.
echo Otevri Microsoft Store, vyhledej "Instalacni program aplikace" (App Installer),
echo nainstaluj/aktualizuj ho a pak spust START.bat znovu.
pause
exit /b 1

:chyba_python
echo CHYBA: Python se nepodarilo nainstalovat. Restartuj pocitac a spust START.bat znovu.
pause
exit /b 1

:chyba_ffmpeg
echo CHYBA: FFmpeg je nainstalovany, ale zatim neni videt. Restartuj pocitac a spust START.bat znovu.
pause
exit /b 1

:chyba_venv
echo CHYBA: Nepodarilo se pripravit prostredi pro program. Restartuj pocitac a zkus to znovu.
pause
exit /b 1

:chyba_pip
echo CHYBA: Instalace knihoven selhala. Zkontroluj internet a spust START.bat znovu.
pause
exit /b 1
