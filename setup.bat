@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Tasks - Setup

set "IS_SILENT=0"
if /i "%~1"=="/silent" set "IS_SILENT=1"
if /i "%~1"=="--silent" set "IS_SILENT=1"
if /i "%~1"=="-s" set "IS_SILENT=1"

echo =======================================================
echo          Tasks - Setup ^& Installation
echo =======================================================
echo.

REM -----------------------------------------------------------------
REM 1. Pruefen, ob Python bereits installiert ist
REM -----------------------------------------------------------------
set "PYTHON_CMD="

REM 1.1 Lokale User-Installationen pruefen (Standard unter Windows 10/11)
if defined LOCALAPPDATA (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
)

REM 1.2 System-weite Pfade pruefen
if not defined PYTHON_CMD if exist "C:\Python312\python.exe" set "PYTHON_CMD=C:\Python312\python.exe"
if not defined PYTHON_CMD if exist "C:\Python310\python.exe" set "PYTHON_CMD=C:\Python310\python.exe"

REM 1.3 Systemweites python im PATH pruefen (WindowsApps Store-Alias ausschliessen)
if not defined PYTHON_CMD (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PYTHON_CMD (
            echo %%i | findstr /i "WindowsApps" >nul 2>nul
            if errorlevel 1 set "PYTHON_CMD=%%i"
        )
    )
)

REM 1.4 Windows Python-Launcher (py.exe) pruefen
if not defined PYTHON_CMD (
    py -3 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if defined PYTHON_CMD goto :python_found

REM -----------------------------------------------------------------
REM Python nicht gefunden -> Automatisch installieren
REM -----------------------------------------------------------------
:install_python
echo [!] Python wurde nicht gefunden. Starte automatische Installation...
echo.

set "PY_INSTALLER=%TEMP%\python_installer_setup.exe"

REM Pruefe ob Installer mitgeliefert wurde oder lade ihn herunter
if exist "%~dp0python_installer.exe" (
    echo [*] Nutze mitgelieferten Python Installer...
    copy /y "%~dp0python_installer.exe" "!PY_INSTALLER!" >nul
) else (
    echo [*] Lade offiziellen Python 3.12 Installer herunter...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe', [System.IO.Path]::Combine($env:TEMP, 'python_installer_setup.exe'))"
)

if not exist "!PY_INSTALLER!" (
    echo [X] Download fehlgeschlagen. Bitte installiere Python 3.12 manuell von https://www.python.org
    if "!IS_SILENT!"=="0" pause
    exit /b 1
)

echo [*] Installiere Python 3.12 (bitte warten, dauert ca. 30-60 Sekunden)...
start /wait "" "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Shortcuts=0
del "!PY_INSTALLER!" >nul 2>nul

REM PATH fuer diesen CMD-Prozess direkt aktualisieren
if defined LOCALAPPDATA (
    set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;!PATH!"
)

:recheck_python
if defined LOCALAPPDATA (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        goto :python_found
    )
)
if exist "C:\Python312\python.exe" (
    set "PYTHON_CMD=C:\Python312\python.exe"
    goto :python_found
)
if exist "C:\Python310\python.exe" (
    set "PYTHON_CMD=C:\Python310\python.exe"
    goto :python_found
)

echo [X] Python konnte nicht automatisch eingerichtet werden.
echo     Bitte installiere Python manuell von: https://www.python.org/downloads/
echo     Wichtig: Beim Setup das Haekchen 'Add python.exe to PATH' setzen!
if "!IS_SILENT!"=="0" pause
exit /b 1

:python_found
echo [OK] Python ist verfuegbar:
"%PYTHON_CMD%" --version
echo.

REM -----------------------------------------------------------------
REM 2. Pruefen und Installieren der Python-Libraries
REM -----------------------------------------------------------------
echo [*] Ueberpruefe benoetigte Python-Libraries...

"%PYTHON_CMD%" -c "import playwright, requests, rich, textual, fpdf, pymupdf, PIL, pytesseract" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Alle benoetigten Python-Libraries sind bereits installiert!
) else (
    echo [*] Mindestens eine Library fehlt. Installiere aus requirements.txt...
    "%PYTHON_CMD%" -m pip install --upgrade pip --quiet --no-warn-script-location
    "%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" --no-warn-script-location
    if %ERRORLEVEL% neq 0 (
        echo [*] Fallback: Einzellinstallation...
        "%PYTHON_CMD%" -m pip install playwright requests rich textual fpdf2 PyMuPDF
    )
)

echo.

REM -----------------------------------------------------------------
REM 3. Playwright Chromium Browser pruefen
REM -----------------------------------------------------------------
echo [*] Ueberpruefe Playwright Chromium Browser...
"%PYTHON_CMD%" -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Playwright Chromium Browser ist bereits installiert!
) else (
    echo [*] Installiere Playwright Chromium Browser (wird fuer Teams-Login benoetigt)...
    "%PYTHON_CMD%" -m playwright install chromium
)

echo.
echo =======================================================
echo [OK] Setup erfolgreich abgeschlossen!
echo      Du kannst das Programm nun mit run.bat starten.
echo =======================================================
echo.
if "!IS_SILENT!"=="0" pause
