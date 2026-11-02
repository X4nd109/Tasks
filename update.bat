@echo off
setlocal
chcp 65001 >nul
title Tasks Update ^& Repair Manager

REM -----------------------------------------------------------------------------
REM Tasks - Standalone Update and Repair Launcher
REM Runs even if Tasks.exe is corrupt or deleted.
REM -----------------------------------------------------------------------------

set "LAUNCHER=%~dp0scripts\update_launcher.ps1"
if not exist "%LAUNCHER%" set "LAUNCHER=%~dp0update_launcher.ps1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%" "%~dp0"
exit /b %ERRORLEVEL%
