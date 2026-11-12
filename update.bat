@echo off
rem ============================================================================
rem  update.bat - Tasks Standalone Updater & Repair Tool
rem
rem  Downloads the latest Tasks_Setup.exe from GitHub Releases and reinstalls
rem  (or repairs) the app into this directory. Works even if Tasks.exe is
rem  corrupt or missing - no Python, no TUI, no network tooling required.
rem
rem  Usage: Double-click update.bat (or run it from a terminal).
rem
rem  Tech: This batch self-extracts the embedded PowerShell helper between the
rem  @@POWERSHELL_BEGIN@@ / @@POWERSHELL_END@@ markers (see bottom of file),
rem  which then queries the GitHub API, downloads the installer with progress
rem  and launches the themed update_runner.ps1 via powershell.exe.
rem ============================================================================
setlocal EnableExtensions

set "INSTALL_DIR=%~dp0"
set "TEMP_SCRIPT=%TEMP%\Tasks_Update\update_helper.ps1"

echo.
echo ============================================================
echo   Tasks Update Manager
echo   Downloading and installing the latest version of Tasks...
echo   Install target: %INSTALL_DIR%
echo ============================================================
echo.

if not exist "%TEMP%\Tasks_Update" mkdir "%TEMP%\Tasks_Update" >nul 2>nul

rem -- Extract the embedded PowerShell helper (between the markers below) --
powershell -NoProfile -ExecutionPolicy Bypass -Command "$raw = [System.IO.File]::ReadAllText('%~f0'); $i = $raw.IndexOf('@@POWERSHELL_BEGIN@@') + 20; $j = $raw.IndexOf('@@POWERSHELL_END@@'); if ($j -le $i) { exit 1 }; [System.IO.File]::WriteAllText('%TEMP_SCRIPT%', $raw.Substring($i, $j - $i), (New-Object System.Text.UTF8Encoding($true)))"
if errorlevel 1 (
    echo [X] Failed to prepare the updater script.
    echo     Press Enter to close...
    pause >nul
    exit /b 1
)

rem -- Run the helper (downloads the release and launches update_runner.ps1) --
powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP_SCRIPT%" -InstallDir "%INSTALL_DIR%"
exit /b %ERRORLEVEL%

@@POWERSHELL_BEGIN@@
param(
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$Host.UI.RawUI.WindowTitle = "Tasks Update Manager"

$apiUrl = "https://api.github.com/repos/X4nd109/Tasks/releases/latest"

# Themed runner template (single quotes = literal here-string; placeholders
# are replaced below with .Replace(), the same way the Python service does).
$runnerTemplate = @'
# Tasks Update Manager - Catppuccin Mocha Themed Runner
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Tasks Update Manager"

$e = [char]27
$cLav    = "$e[38;2;180;190;254m"  # Catppuccin Lavender (#b4befe)
$cBlue   = "$e[38;2;137;180;250m"  # Catppuccin Blue (#89b4fa)
$cGreen  = "$e[38;2;166;227;161m"  # Catppuccin Green (#a6e3a1)
$cRed    = "$e[38;2;243;139;168m"  # Catppuccin Red (#f38ba8)
$cYellow = "$e[38;2;249;226;175m"  # Catppuccin Yellow (#f9e2af)
$cSub    = "$e[38;2;166;173;200m"  # Catppuccin Subtext0 (#a6adc8)
$cDim    = "$e[38;2;108;112;134m"  # Catppuccin Overlay0 (#6c7086)
$cBold   = "$e[1m"
$cReset  = "$e[0m"

$installerPath = '__INSTALLER_PATH__'
$targetAppDir  = '__TARGET_APP_DIR__'
$currentVer    = '__CURRENT_VERSION__'
$targetVer     = '__TARGET_VERSION__'
$tempDir       = '__TEMP_DIR__'
$pendingFile   = Join-Path $tempDir "pending_update.txt"
$appliedFile   = Join-Path $tempDir "update_just_applied.txt"
$logFile       = Join-Path $tempDir "update.log"

function Log-Message([string]$msg) {
    try {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $plain = $msg -replace "`e\[[0-9;]*m", ""
        Add-Content -LiteralPath $logFile -Value "[$timestamp] $plain" -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
}

function Show-Header {
    Clear-Host
    Write-Host ""
    Write-Host "$cLav  ╭────────────────────────────────────────────────────────╮$cReset"
    Write-Host "$cLav  │$cBold$cBlue                   TASKS UPDATE MANAGER                 $cReset$cLav│$cReset"
    if ($currentVer -and $targetVer) {
        $verLine = "                 v$currentVer  ➜  v$targetVer"
        $pad = 56 - $verLine.Length
        if ($pad -lt 0) { $pad = 0 }
        $verLineFormatted = $verLine + (" " * $pad)
        Write-Host "$cLav  │$cSub$verLineFormatted$cReset$cLav│$cReset"
    }
    Write-Host "$cLav  ╰────────────────────────────────────────────────────────╯$cReset"
    Write-Host ""
}

try {
    Log-Message "=== Tasks Update started: v$currentVer -> v$targetVer ==="
    Log-Message "Target directory: $targetAppDir"
    Log-Message "Installer: $installerPath"

    Show-Header

    # [1/5] Waiting for Tasks to close
    Write-Host "$cBlue  [1/5]$cReset Waiting for Tasks to close..."
    Log-Message "[1/5] Waiting for Tasks to close..."
    $waitCount = 0
    while ($waitCount -lt 15) {
        $procs = Get-Process -Name Tasks, TasksTray -ErrorAction SilentlyContinue
        if (-not $procs) {
            break
        }
        Start-Sleep -Milliseconds 800
        $waitCount++
    }
    $remaining = Get-Process -Name Tasks, TasksTray -ErrorAction SilentlyContinue
    if ($remaining) {
        $remaining | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    Write-Host "$cGreen        [✓] Tasks closed successfully.$cReset"
    Log-Message "[1/5] Tasks closed successfully."
    Write-Host ""

    # [2/5] Verify installation package
    Write-Host "$cBlue  [2/5]$cReset Verifying installation package..."
    Log-Message "[2/5] Verifying installation package..."
    if (-not (Test-Path -LiteralPath $installerPath)) {
        throw "Installation file not found: $installerPath"
    }
    $fileSize = (Get-Item -LiteralPath $installerPath).Length
    if ($fileSize -lt 1048576) {
        throw "Installation file looks incomplete ($fileSize Bytes)."
    }
    $sizeMb = [math]::Round($fileSize / 1MB, 1)
    Write-Host "$cGreen        [✓] Installation package verified ($sizeMb MB).$cReset"
    Log-Message "[2/5] Installation package verified ($sizeMb MB)."
    Write-Host ""

    # [3/5] Installing update files
    Write-Host "$cBlue  [3/5]$cReset Installing update files..."
    Log-Message "[3/5] Inno Setup installer starting..."
    $instArgs = @(
        "`"/DIR=$targetAppDir`"",
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOTASKS=1",
        "/UPDATE=1"
    )
    $proc = Start-Process -FilePath $installerPath -ArgumentList $instArgs -PassThru

    $spinner = @("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    $i = 0
    while (-not $proc.HasExited) {
        $char = $spinner[$i % $spinner.Length]
        $bar = "━" * (($i % 24) + 1)
        Write-Host -NoNewline "`r$e[2K$cYellow        $char [ $bar ] Extracting and updating components...$cReset"
        Start-Sleep -Milliseconds 120
        $i++
    }
    Write-Host "`r$e[2K$cGreen        [✓] Installation completed.$cReset"
    Log-Message "[3/5] Inno Setup finished with exit code $($proc.ExitCode)."
    Write-Host ""

    if ($proc.ExitCode -ne 0) {
        throw "Inno Setup installer exited with error code $($proc.ExitCode)."
    }

    # [4/5] Verify installation
    Write-Host "$cBlue  [4/5]$cReset Verifying installation..."
    Log-Message "[4/5] Verifying installation..."
    $exePath = Join-Path $targetAppDir "Tasks.exe"
    $cmdPath = Join-Path $targetAppDir "tasks.cmd"
    $runBat  = Join-Path $targetAppDir "run.bat"
    if (-not (Test-Path -LiteralPath $exePath) -and -not (Test-Path -LiteralPath $cmdPath) -and -not (Test-Path -LiteralPath $runBat)) {
        throw "Target application could not be found after installation ($targetAppDir)."
    }
    Set-Content -Path $appliedFile -Value "1" -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Host "$cGreen        [✓] Program files verified successfully.$cReset"
    Log-Message "[4/5] Program files verified successfully."
    Write-Host ""

    # [5/5] Cleanup and restart
    Write-Host "$cBlue  [5/5]$cReset Cleaning up temporary files and restarting Tasks..."
    Log-Message "[5/5] Cleaning up and restarting..."
    Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pendingFile -Force -ErrorAction SilentlyContinue
    Write-Host "$cGreen        [✓] Cleanup completed.$cReset"
    Write-Host ""

    Write-Host "$cLav  ╭────────────────────────────────────────────────────────╮$cReset"
    Write-Host "$cLav  │$cBold$cGreen        ✨ Update installed successfully!          $cReset$cLav│$cReset"
    Write-Host "$cLav  │$cSub           Tasks will restart automatically...        $cReset$cLav│$cReset"
    Write-Host "$cLav  ╰────────────────────────────────────────────────────────╯$cReset"
    Write-Host ""

    # Restart Tasks immediately
    Start-Sleep -Seconds 1
    if (Test-Path -LiteralPath $exePath) {
        Start-Process -FilePath $exePath -WorkingDirectory $targetAppDir
    } elseif (Test-Path -LiteralPath $cmdPath) {
        Start-Process -FilePath $cmdPath -WorkingDirectory $targetAppDir
    } elseif (Test-Path -LiteralPath $runBat) {
        Start-Process -FilePath $runBat -WorkingDirectory $targetAppDir
    }

    # 5-second auto-close countdown (press any key to exit immediately)
    for ($sec = 5; $sec -gt 0; $sec--) {
        Write-Host -NoNewline "`r$e[2K$cSub        Closing window in ${sec}s... (press any key to exit immediately)$cReset"
        for ($k = 0; $k -lt 10; $k++) {
            if ([Console]::KeyAvailable) {
                $null = [Console]::ReadKey($true)
                $sec = 0
                break
            }
            Start-Sleep -Milliseconds 100
        }
    }
    Write-Host ""
    exit 0

} catch {
    $errDetails = $_.Exception.ToString()
    Log-Message "UPDATE FAILED: $errDetails"
    Write-Host ""
    Write-Host "$cRed  ╭────────────────────────────────────────────────────────╮$cReset"
    Write-Host "$cRed  │$cBold                   UPDATE FAILED                  $cReset$cRed│$cReset"
    Write-Host "$cRed  ╰────────────────────────────────────────────────────────╯$cReset"
    Write-Host "$cRed  Error details: $($_.Exception.Message)$cReset"
    Write-Host "$cDim  Detailed log: $logFile$cReset"
    Write-Host ""
    Write-Host "$cSub  This window will remain open for troubleshooting.$cReset"
    Write-Host "$cSub  Press Enter to close...$cReset"
    Read-Host
    exit 1
}
'@

try {
    if ($InstallDir) {
        $InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
    }

    Write-Host ""
    Write-Host "  [1/3] Checking the latest Tasks release on GitHub..." -ForegroundColor Cyan
    $release = Invoke-RestMethod -Uri $apiUrl -Headers @{ "User-Agent" = "Tasks/update.bat"; "Accept" = "application/vnd.github.v3+json" } -TimeoutSec 30
    $latest = ($release.tag_name -replace "^v", "")
    $asset = $release.assets | Where-Object { $_.name -like "*.exe" -and $_.name -match "Setup" } | Select-Object -First 1
    if (-not $asset) { $asset = $release.assets | Where-Object { $_.name -like "*.exe" } | Select-Object -First 1 }
    if (-not $asset) { throw "No installer asset (.exe) found in the latest release." }
    $sizeMb = [math]::Round($asset.size / 1MB, 1)
    Write-Host "  [OK] Latest version: v$latest  ($($asset.name), $sizeMb MB)" -ForegroundColor Green

    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "Tasks_Update"
    New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
    $installerPath = Join-Path $tempDir $asset.name

    Write-Host "  [2/3] Downloading $($asset.name) to $installerPath ..." -ForegroundColor Cyan
    $partPath = "$installerPath.part"
    $maxRetries = 3
    $success = $false

    for ($attempt = 0; $attempt -le $maxRetries; $attempt++) {
        try {
            $existing = 0
            if (Test-Path -LiteralPath $partPath) {
                $existing = (Get-Item -LiteralPath $partPath).Length
            }

            $request = [System.Net.HttpWebRequest]::Create($asset.browser_download_url)
            $request.UserAgent = "Tasks/update.bat"
            $request.AllowAutoRedirect = $true
            $request.Timeout = 30000
            $request.ReadWriteTimeout = 30000

            if ($existing -gt 0) {
                $request.AddRange($existing)
                Write-Host "  [~] Resuming download from $([math]::Round($existing / 1MB, 1)) MB..." -ForegroundColor Yellow
            }

            $response = $request.GetResponse()
            $isPartial = ([int]$response.StatusCode -eq 206)
            $total = $response.ContentLength
            if ($isPartial) {
                $total += $existing
            } else {
                $existing = 0
            }

            $stream = $response.GetResponseStream()
            $buffer = New-Object byte[] 65536
            if ($isPartial -and (Test-Path -LiteralPath $partPath)) {
                $fileStream = [System.IO.File]::Open($partPath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write)
            } else {
                $fileStream = [System.IO.File]::Create($partPath)
            }
            $downloaded = [long]$existing

            try {
                while ($true) {
                    $read = $stream.Read($buffer, 0, $buffer.Length)
                    if ($read -le 0) { break }
                    $fileStream.Write($buffer, 0, $read)
                    $downloaded += $read
                    if ($total -gt 0) {
                        $pct = [math]::Round(($downloaded / $total) * 100, 1)
                        $doneMb = [math]::Round($downloaded / 1MB, 1)
                        Write-Progress -Activity "Downloading Tasks update" -Status "$doneMb / $sizeMb MB ($pct%)" -PercentComplete $pct
                    }
                }
            } finally {
                $fileStream.Close()
                $stream.Close()
                $response.Close()
            }

            if ($total -gt 0 -and $downloaded -lt $total) {
                throw "Incomplete download: received $downloaded of $total bytes."
            }

            if (Test-Path -LiteralPath $installerPath) {
                Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
            }
            Move-Item -LiteralPath $partPath -Destination $installerPath -Force
            $success = $true
            break
        } catch {
            $err = $_.Exception.Message
            if ($attempt -lt $maxRetries) {
                $delay = 2 * ($attempt + 1)
                Write-Host "  [!] Connection interrupted ($err). Retrying ($($attempt + 1)/$maxRetries) in ${delay}s..." -ForegroundColor Yellow
                Start-Sleep -Seconds $delay
            } else {
                throw "Download failed after $maxRetries retries: $err"
            }
        }
    }
    Write-Progress -Activity "Downloading Tasks update" -Completed
    Write-Host "  [OK] Download complete ($sizeMb MB)." -ForegroundColor Green

    Write-Host "  [3/3] Launching the Tasks update manager..." -ForegroundColor Cyan

    # Generate the themed update_runner.ps1 (same runner as the in-app updater)
    $runner = $runnerTemplate.
        Replace("__INSTALLER_PATH__", $installerPath.Replace("'", "''")).
        Replace("__TARGET_APP_DIR__", $InstallDir.Replace("'", "''")).
        Replace("__CURRENT_VERSION__", "").
        Replace("__TARGET_VERSION__", $latest).
        Replace("__TEMP_DIR__", $tempDir)
    $runnerPath = Join-Path $tempDir "update_runner.ps1"
    [System.IO.File]::WriteAllText($runnerPath, $runner, (New-Object System.Text.UTF8Encoding($true)))

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runnerPath
    exit $LASTEXITCODE

} catch {
    Write-Host ""
    Write-Host "UPDATE FAILED" -ForegroundColor Red
    Write-Host ("Error details: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host ""
    Write-Host "Check your internet connection and try again, or download the" -ForegroundColor Yellow
    Write-Host "latest installer manually from:" -ForegroundColor Yellow
    Write-Host "  https://github.com/X4nd109/Tasks/releases/latest" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press Enter to close..." -NoNewline
    $null = Read-Host
    exit 1
}
@@POWERSHELL_END@@
