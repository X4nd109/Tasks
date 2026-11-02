# ─────────────────────────────────────────────────────────────────────────────
# update_launcher.ps1 - Standalone Update & Reinstall Launcher for Tasks
# ─────────────────────────────────────────────────────────────────────────────
param(
    [string]$TargetDir = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Tasks Update & Repair Manager"

$e = [char]27
$cLav    = "$e[38;2;180;190;254m"
$cBlue   = "$e[38;2;137;180;250m"
$cGreen  = "$e[38;2;166;227;161m"
$cRed    = "$e[38;2;243;139;168m"
$cYellow = "$e[38;2;249;226;175m"
$cSub    = "$e[38;2;166;173;200m"
$cDim    = "$e[38;2;108;112;134m"
$cBold   = "$e[1m"
$cReset  = "$e[0m"

$targetAppDir = $TargetDir
if (-not $targetAppDir -or -not (Test-Path -LiteralPath $targetAppDir)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $parentDir = Split-Path -Parent $scriptDir
    if (Test-Path (Join-Path $parentDir "Tasks.exe")) {
        $targetAppDir = $parentDir
    } else {
        $targetAppDir = (Get-Location).Path
    }
}
$targetAppDir = (Resolve-Path $targetAppDir).Path

$tempDir = Join-Path $env:TEMP "Tasks_Update"
if (-not (Test-Path -LiteralPath $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
}

Clear-Host
Write-Host ""
Write-Host "$cLav  ╭────────────────────────────────────────────────────────╮$cReset"
Write-Host "$cLav  │$cBold$cBlue                 TASKS UPDATE & REPAIR                  $cReset$cLav│$cReset"
Write-Host "$cLav  │$cSub              Download & Reinstall Component              $cReset$cLav│$cReset"
Write-Host "$cLav  ╰────────────────────────────────────────────────────────╯$cReset"
Write-Host ""

try {
    Write-Host "$cBlue  [*] Checking latest release from GitHub...$cReset"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $apiUrl = "https://api.github.com/repos/X4nd109/Tasks/releases/latest"
    $headers = @{ "User-Agent" = "Tasks-Updater"; "Accept" = "application/vnd.github.v3+json" }
    $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 15

    $asset = $release.assets | Where-Object { $_.name -like "*Setup*.exe" } | Select-Object -First 1
    if (-not $asset) {
        $asset = $release.assets | Where-Object { $_.name -like "*.exe" } | Select-Object -First 1
    }
    if (-not $asset) {
        throw "No installer asset found in latest GitHub release ($($release.tag_name))."
    }

    $tag = $release.tag_name
    $targetVer = $tag.TrimStart("vV")
    $installerPath = Join-Path $tempDir $asset.name
    $sizeMb = [math]::Round($asset.size / 1MB, 1)

    Write-Host "$cGreen        [✓] Latest release: $tag ($sizeMb MB)$cReset"
    Write-Host ""

    $downloadNeeded = $true
    if (Test-Path -LiteralPath $installerPath) {
        $existingLen = (Get-Item -LiteralPath $installerPath).Length
        if ($existingLen -eq $asset.size) {
            Write-Host "$cGreen        [✓] Valid installer package found in cache.$cReset"
            $downloadNeeded = $false
        }
    }

    if ($downloadNeeded) {
        Write-Host "$cBlue  [*] Downloading $($asset.name)...$cReset"
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("User-Agent", "Tasks-Updater")
        $wc.DownloadFile($asset.browser_download_url, $installerPath)
        Write-Host "$cGreen        [✓] Download completed successfully.$cReset"
    }
    Write-Host ""

    # Current version check
    $currentVer = ""
    $verFile = Join-Path $targetAppDir "version_info.txt"
    if (Test-Path -LiteralPath $verFile) {
        try {
            $lines = Get-Content -LiteralPath $verFile
            foreach ($line in $lines) {
                if ($line -like "*FileVersion*") {
                    $parts = $line.Split("'")
                    if ($parts.Length -ge 4) {
                        $currentVer = $parts[3]
                        break
                    }
                }
            }
        } catch {}
    }
    if (-not $currentVer) {
        $currentVer = $targetVer
    }

    Write-Host "$cBlue  [*] Preparing Update Manager runner...$cReset"

    $appliedFile = Join-Path $tempDir "update_just_applied.txt"
    $pendingFile = Join-Path $tempDir "pending_update.txt"
    $logFile     = Join-Path $tempDir "update.log"
    $psScript    = Join-Path $tempDir "update_runner.ps1"

    $runnerTemplate = @'
# Tasks Update Manager - Catppuccin Mocha Themed Runner
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "Tasks Update Manager"

$e = [char]27
$cLav    = "$e[38;2;180;190;254m"
$cBlue   = "$e[38;2;137;180;250m"
$cGreen  = "$e[38;2;166;227;161m"
$cRed    = "$e[38;2;243;139;168m"
$cYellow = "$e[38;2;249;226;175m"
$cSub    = "$e[38;2;166;173;200m"
$cDim    = "$e[38;2;108;112;134m"
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
            try {
                if ([Console]::KeyAvailable) {
                    $null = [Console]::ReadKey($true)
                    $sec = 0
                    break
                }
            } catch {}
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

    $scriptContent = $runnerTemplate.
        Replace('__INSTALLER_PATH__', $installerPath.Replace("'", "''")).
        Replace('__TARGET_APP_DIR__', $targetAppDir.Replace("'", "''")).
        Replace('__CURRENT_VERSION__', $currentVer.Replace("'", "''")).
        Replace('__TARGET_VERSION__', $targetVer.Replace("'", "''")).
        Replace('__TEMP_DIR__', $tempDir.Replace("'", "''"))

    [System.IO.File]::WriteAllText($psScript, $scriptContent, [System.Text.Encoding]::UTF8)

    # Run the updater directly in this session
    & $psScript
    exit $LASTEXITCODE

} catch {
    Write-Host ""
    Write-Host "$cRed  [X] Error during update setup: $($_.Exception.Message)$cReset"
    Write-Host "$cDim  $($_.Exception.ToString())$cReset"
    Write-Host ""
    Write-Host "$cSub  Press Enter to exit...$cReset"
    Read-Host
    exit 1
}
