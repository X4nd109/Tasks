@echo off
setlocal
chcp 65001 >nul
title Tasks - Windows Terminal Profil

set "SILENT=0"
echo %* | findstr /i /c:"/silent" /c:"--silent" /c:"/quiet" /c:"--quiet" >nul 2>nul
if not errorlevel 1 set "SILENT=1"

if "%SILENT%"=="0" (
    echo ======================================================================
    echo   Richte Windows-Terminal-Profil 'Tasks' mit Logo ein...
    echo ======================================================================
    echo.
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$raw = '%~dp0'.TrimEnd('\'); " ^
  "$rootDir = if (Test-Path (Join-Path $raw 'run.bat')) { $raw } else { Split-Path -Parent $raw }; " ^
  "$runBat = Join-Path $rootDir 'run.bat'; " ^
  "$pngIcon = Join-Path (Join-Path $rootDir 'assets') 'app_icon.png'; " ^
  "$icoIcon = Join-Path (Join-Path $rootDir 'assets') 'app_icon.ico'; " ^
  "$iconPath = if (Test-Path $pngIcon) { $pngIcon } elseif (Test-Path $icoIcon) { $icoIcon } else { $pngIcon }; " ^
  "$guid = '{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}'; " ^
  "$name = 'Tasks'; " ^
  "$candidates = @( " ^
  "  (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'), " ^
  "  (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json') " ^
  "); " ^
  "$settingsFile = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1; " ^
  "if (-not $settingsFile) { " ^
  "  if ('%SILENT%' -ne '1') { Write-Host '[-] Windows Terminal settings.json nicht gefunden.' -ForegroundColor Yellow }; " ^
  "  exit 1; " ^
  "}; " ^
  "try { " ^
  "  $jsonText = [System.IO.File]::ReadAllText($settingsFile, [System.Text.Encoding]::UTF8); " ^
  "  $data = $jsonText | ConvertFrom-Json; " ^
  "} catch { " ^
  "  if ('%SILENT%' -ne '1') { Write-Host ('[-] Fehler beim Parsen von settings.json: ' + $_) -ForegroundColor Red }; " ^
  "  exit 1; " ^
  "}; " ^
  "if ($data.profiles -is [System.Array]) { " ^
  "  $data.profiles = [PSCustomObject]@{ list = @($data.profiles) }; " ^
  "} elseif ($null -eq $data.profiles) { " ^
  "  $data | Add-Member -MemberType NoteProperty -Name 'profiles' -Value ([PSCustomObject]@{ list = @() }) -Force; " ^
  "} elseif ($null -eq $data.profiles.list) { " ^
  "  $data.profiles | Add-Member -MemberType NoteProperty -Name 'list' -Value @() -Force; " ^
  "}; " ^
  "$list = @($data.profiles.list); " ^
  "$entry = [ordered]@{ " ^
  "  guid = $guid; " ^
  "  name = $name; " ^
  "  commandline = ('cmd.exe /c \"' + $runBat + '\"'); " ^
  "  startingDirectory = $rootDir; " ^
  "  icon = $iconPath; " ^
  "  tabTitle = $name; " ^
  "  hidden = $false " ^
  "}; " ^
  "$newList = @($list | Where-Object { $_.guid -ne $guid -and $_.name -ne $name -and $_.name -ne 'Aufgaben-Detector' }); " ^
  "$newList += [PSCustomObject]$entry; " ^
  "$data.profiles.list = $newList; " ^
  "$newJson = $data | ConvertTo-Json -Depth 32; " ^
  "[System.IO.File]::WriteAllText($settingsFile, $newJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)); " ^
  "if ('%SILENT%' -ne '1') { " ^
  "  Write-Host '[+] Profil ''Tasks'' erfolgreich in Windows Terminal eingerichtet!' -ForegroundColor Green; " ^
  "  Write-Host ('    Icon:  ' + $iconPath) -ForegroundColor Cyan; " ^
  "  Write-Host ('    Start: ' + $runBat) -ForegroundColor Cyan; " ^
  "}; "

if errorlevel 1 (
    if "%SILENT%"=="0" (
        echo.
        echo [!] Das Windows-Terminal-Profil konnte nicht eingerichtet werden.
        echo.
        pause
    )
    exit /b 1
)

if "%SILENT%"=="0" (
    echo.
    echo ======================================================================
    echo Fertig! Das Profil 'Tasks' steht im Windows Terminal bereit.
    echo ======================================================================
    echo.
    pause
)
