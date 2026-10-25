@echo off
setlocal
chcp 65001 >nul
title Tasks - Windows Terminal Profil entfernen

set "SILENT=0"
echo %* | findstr /i /c:"/silent" /c:"--silent" /c:"/quiet" /c:"--quiet" >nul 2>nul
if not errorlevel 1 set "SILENT=1"

if "%SILENT%"=="0" (
    echo ======================================================================
    echo   Entferne Windows-Terminal-Profil 'Tasks'...
    echo ======================================================================
    echo.
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$guid = '{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}'; " ^
  "$name = 'Tasks'; " ^
  "$candidates = @( " ^
  "  (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'), " ^
  "  (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json') " ^
  "); " ^
  "$settingsFile = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1; " ^
  "if (-not $settingsFile) { exit 0 }; " ^
  "try { " ^
  "  $jsonText = [System.IO.File]::ReadAllText($settingsFile, [System.Text.Encoding]::UTF8); " ^
  "  $data = $jsonText | ConvertFrom-Json; " ^
  "} catch { exit 0 }; " ^
  "$list = if ($data.profiles.list) { $data.profiles.list } elseif ($data.profiles) { $data.profiles } else { $null }; " ^
  "if (-not $list) { exit 0 }; " ^
  "$newList = @($list | Where-Object { $_.guid -ne $guid -and $_.name -ne $name -and $_.name -ne 'Aufgaben-Detector' }); " ^
  "if ($data.profiles.list) { $data.profiles.list = $newList } else { $data.profiles = $newList }; " ^
  "$newJson = $data | ConvertTo-Json -Depth 32; " ^
  "[System.IO.File]::WriteAllText($settingsFile, $newJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)); " ^
  "if ('%SILENT%' -ne '1') { " ^
  "  Write-Host '[+] Profil ''Tasks'' erfolgreich aus Windows Terminal entfernt.' -ForegroundColor Green; " ^
  "}; "

if "%SILENT%"=="0" (
    echo.
    echo ======================================================================
    echo Profil 'Tasks' wurde erfolgreich entfernt.
    echo ======================================================================
    echo.
    pause
)
