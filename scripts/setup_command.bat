@echo off
chcp 65001 >nul
title Tasks - Command einrichten

echo ======================================================================
echo   Richte globalen Terminal-Befehl 'tasks' fuer dieses System ein...
echo ======================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$raw = '%~dp0'.TrimEnd('\'); " ^
  "$dir = if (Test-Path (Join-Path $raw 'tasks.bat')) { $raw } else { Split-Path -Parent $raw }; " ^
  "$currentPath = [Environment]::GetEnvironmentVariable('Path', 'User'); " ^
  "if (-not $currentPath) { $currentPath = '' }; " ^
  "$parts = $currentPath -split ';' | Where-Object { $_ -ne '' }; " ^
  "if ($parts -notcontains $dir) { " ^
  "  $newPath = ($parts + $dir) -join ';'; " ^
  "  [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); " ^
  "  Write-Host 'Erfolgreich hinzugefuegt zum User-PATH:' -ForegroundColor Green; " ^
  "  Write-Host ('  ' + $dir) -ForegroundColor Cyan; " ^
  "} else { " ^
  "  Write-Host 'Der Pfad war bereits im User-PATH vorhanden:' -ForegroundColor Yellow; " ^
  "  Write-Host ('  ' + $dir) -ForegroundColor Gray; " ^
  "}"

echo.
echo ======================================================================
echo Fertig! Du kannst ab sofort in jedem neuen Terminal 'tasks' eingeben.
echo ======================================================================
echo.
pause
