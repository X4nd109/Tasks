@echo off
setlocal
chcp 65001 >nul
title Tasks - Build Standalone Executables

echo =======================================================
echo          Tasks - Build Executables (Tasks.exe)
echo =======================================================
echo.

python "%~dp0scripts\build_exe.py"

if %ERRORLEVEL% equ 0 (
    echo.
    echo [OK] Build completed successfully.
    echo      Outputs located in dist\Tasks\
) else (
    echo.
    echo [X] Build failed with error code %ERRORLEVEL%.
)
echo.
pause
