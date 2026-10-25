@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Tasks

set "RUN_FROM_BATCH=1"
set "UPDATE_FLAG_FILE=%TEMP%\Tasks_Update\pending_update.txt"
set "UPDATE_APPLIED_FILE=%TEMP%\Tasks_Update\update_just_applied.txt"

cls

REM -----------------------------------------------------------------
REM Python-Interpreter finden
REM -----------------------------------------------------------------
set "PYTHON_EXE="

if defined LOCALAPPDATA (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
)

if not defined PYTHON_EXE if exist "C:\Python312\python.exe" set "PYTHON_EXE=C:\Python312\python.exe"
if not defined PYTHON_EXE if exist "C:\Python310\python.exe" set "PYTHON_EXE=C:\Python310\python.exe"

REM System-Python pruefen (WindowsApps ausschliessen)
if not defined PYTHON_EXE (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PYTHON_EXE (
            echo %%i | findstr /i "WindowsApps" >nul 2>nul
            if errorlevel 1 set "PYTHON_EXE=%%i"
        )
    )
)

if not defined PYTHON_EXE (
    py -3 --version >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py -3"
)

REM Falls Python nirgends gefunden wurde:
if not defined PYTHON_EXE (
    echo.
    echo =======================================================
    echo  [!] Python wurde auf diesem Computer nicht gefunden!
    echo =======================================================
    echo.
    echo  Tasks benoetigt Python.
    echo.
    set /p "RUN_SETUP=Moechtest du das Setup jetzt starten? (J/N): "
    if /i "!RUN_SETUP!"=="J" (
        call "%~dp0setup.bat"
        exit /b 0
    )
    pause
    exit /b 9009
)

REM -----------------------------------------------------------------
REM Programm-Ausfuehrungsschleife (ermoeglicht In-Terminal-Updates)
REM -----------------------------------------------------------------
:run_loop
"%PYTHON_EXE%" "%~dp0main.py" %*
set "APP_EXIT_CODE=%ERRORLEVEL%"

REM Pruefe, ob ein In-App-Update angefordert wurde (Exit-Code 42 oder Pending-Datei)
if %APP_EXIT_CODE% equ 42 goto :do_update
if exist "%UPDATE_FLAG_FILE%" goto :do_update
goto :after_run

:do_update
set "INSTALLER_EXE="
if exist "%UPDATE_FLAG_FILE%" (
    set /p INSTALLER_EXE=<"%UPDATE_FLAG_FILE%"
)
if not defined INSTALLER_EXE (
    set "INSTALLER_EXE=%TEMP%\Tasks_Update\Tasks_Setup.exe"
)

echo.
echo =======================================================
echo  [*] Aktualisiere Tasks im gleichen Fenster...
echo =======================================================
echo.

if exist "!INSTALLER_EXE!" (
    start /wait "" "!INSTALLER_EXE!" /DIR="%~dp0." /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOTASKS=1 /UPDATE=1
    del /f /q "!INSTALLER_EXE!" 2>nul
)
del /f /q "%UPDATE_FLAG_FILE%" 2>nul

REM Marker setzen, damit die App das Update beim Start erkennt
echo 1 > "%UPDATE_APPLIED_FILE%" 2>nul

cls
goto :run_loop

:after_run
if %APP_EXIT_CODE% NEQ 0 (
    echo.
    echo Programm beendet mit Fehlercode %APP_EXIT_CODE%
    pause
)
