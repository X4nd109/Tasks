@echo off
chcp 65001 >nul
title Tasks - Command entfernen

echo ======================================================================
echo   Entferne globalen Terminal-Befehl 'tasks' aus dem PATH...
echo ======================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$raw = '%~dp0'.TrimEnd('\'); " ^
  "$dir = if (Test-Path (Join-Path $raw 'tasks.bat')) { $raw } else { Split-Path -Parent $raw }; " ^
  "$currentPath = [Environment]::GetEnvironmentVariable('Path', 'User'); " ^
  "if ($currentPath) { " ^
  "  $parts = $currentPath -split ';' | Where-Object { $_ -ne '' -and $_ -ne $dir -and $_ -ne $raw }; " ^
  "  $newPath = $parts -join ';'; " ^
  "  [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); " ^
  "  Write-Host 'Erfolgreich aus dem User-PATH entfernt:' -ForegroundColor Green; " ^
  "  Write-Host ('  ' + $dir) -ForegroundColor Cyan; " ^
  "} else { " ^
  "  Write-Host 'Kein User-PATH vorhanden.' -ForegroundColor Gray; " ^
  "}"

echo.
echo ======================================================================
echo Befehl 'tasks' wurde erfolgreich entfernt.
echo ======================================================================
echo.

if /i "%~1" neq "/silent" if /i "%~1" neq "/quiet" (
    pause
)
