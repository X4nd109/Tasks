"""
update_service.py - Asynchroner Versions- und Update-Checker für GitHub Releases.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple, Callable

from src.core.config import APP_VERSION, GITHUB_REPO, WORKSPACE_DIR

logger = logging.getLogger(__name__)

UPDATE_EXIT_CODE = 42


def parse_version(v_str: str) -> Tuple[int, ...]:
    """
    Parst einen Versions-String (z. B. 'v1.0.2', '1.0.3-beta', '2.0')
    in ein Tupel ganzer Zahlen zur zuverlässigen semantischen Versionsprüfung.
    """
    if not v_str:
        return (0,)
    # Entferne eventuelle führende Präfixe wie 'v' oder 'release-'
    cleaned = v_str.strip().lstrip("vV")
    numbers = re.findall(r"\d+", cleaned)
    if not numbers:
        return (0,)
    return tuple(int(n) for n in numbers)


def is_newer_version(latest_tag: str, current_version: str = APP_VERSION) -> bool:
    """
    Gibt True zurück, wenn latest_tag semantisch höher als current_version ist.
    Gleicht bei unterschiedlichen Längen (z. B. 1.0 vs 1.0.2) die Tupel mit Nullen an.
    """
    v_latest = list(parse_version(latest_tag))
    v_current = list(parse_version(current_version))

    max_len = max(len(v_latest), len(v_current))
    while len(v_latest) < max_len:
        v_latest.append(0)
    while len(v_current) < max_len:
        v_current.append(0)

    return tuple(v_latest) > tuple(v_current)


def check_for_updates(
    current_version: str = APP_VERSION,
    repo: str = GITHUB_REPO,
    timeout: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    Prüft geräuschlos über die GitHub REST-API, ob ein neuer Release vorliegt.
    
    Gibt bei einem neueren Release ein Dict mit Details zurück,
    andernfalls (keine neuere Version, Offline, Timeout, Rate-Limit) None.
    """
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": f"Tasks/{current_version}",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))

        tag_name = data.get("tag_name", "").strip()
        if not tag_name:
            return None

        if is_newer_version(tag_name, current_version):
            clean_latest = tag_name.lstrip("vV")

            # Installer-Asset (.exe) ermitteln
            installer_url: Optional[str] = None
            installer_name: Optional[str] = None
            installer_size: int = 0

            for asset in data.get("assets", []):
                aname = asset.get("name", "")
                if aname.lower().endswith(".exe"):
                    installer_url = asset.get("browser_download_url")
                    installer_name = aname
                    installer_size = asset.get("size", 0)
                    if "setup" in aname.lower():
                        break

            return {
                "current_version": current_version.lstrip("vV"),
                "latest_version": clean_latest,
                "tag_name": tag_name,
                "name": data.get("name") or tag_name,
                "html_url": data.get("html_url") or f"https://github.com/{repo}/releases/latest",
                "body": (data.get("body") or "").strip(),
                "published_at": data.get("published_at") or "",
                "installer_url": installer_url,
                "installer_name": installer_name,
                "installer_size": installer_size,
            }

        return None

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        # Geräuschloses Abfangen bei Offline-Betrieb oder Netzwerkausfällen
        return None
    except Exception as e:
        logger.debug("Unerwarteter Fehler bei Update-Prüfung: %s", e)
        return None


def get_update_temp_dir() -> str:
    """Gibt das dedizierte temporäre Verzeichnis für Update-Downloads zurück."""
    base_temp = tempfile.gettempdir()
    update_dir = os.path.join(base_temp, "Tasks_Update")
    os.makedirs(update_dir, exist_ok=True)
    return update_dir


def download_update_installer(
    download_url: str,
    target_path: str,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    chunk_size: int = 65536,
) -> bool:
    """
    Lädt das Installer-Asset herunter.
    
    progress_callback(downloaded_bytes: int, total_bytes: int, percent: float)
    Gibt True bei Erfolg zurück, False bei Fehler oder Abbruch.
    """
    target_dir = os.path.dirname(target_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    part_path = target_path + ".part"
    if os.path.exists(part_path):
        try:
            os.remove(part_path)
        except Exception:
            pass

    req = urllib.request.Request(
        download_url,
        headers={
            "User-Agent": f"Tasks/{APP_VERSION}",
            "Accept": "*/*",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0

            with open(part_path, "wb") as f_out:
                while True:
                    if cancel_event and cancel_event.is_set():
                        logger.info("Update-Download wurde vom Benutzer abgebrochen.")
                        f_out.close()
                        if os.path.exists(part_path):
                            try:
                                os.remove(part_path)
                            except Exception:
                                pass
                        return False

                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    f_out.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback:
                        percent = (downloaded / total_size * 100.0) if total_size > 0 else 0.0
                        progress_callback(downloaded, total_size, percent)

        # Download erfolgreich abgeschlossen: atomar umbenennen
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass
        os.replace(part_path, target_path)
        return True

    except Exception as e:
        logger.warning("Fehler beim Herunterladen des Updates: %s", e)
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except Exception:
                pass
        return False


def generate_powershell_updater_script(
    installer_path: str,
    target_app_dir: str,
    current_version: str = "",
    target_version: str = "",
) -> str:
    """
    Generates an isolated Catppuccin Mocha themed PowerShell updater script.
    
    The script runs from %TEMP%\\Tasks_Update\\update_runner.ps1 and provides:
    - Step-by-step progress reporting ([1/5] to [5/5]).
    - Catppuccin Mocha ANSI styling (lavender, green, blue, dark base).
    - Waiting for Tasks.exe / TasksTray.exe termination.
    - Verification of installer package.
    - Silent execution of Inno Setup installer with animated progress spinner.
    - Verification of installation files.
    - Cleanup of temporary files and graceful restart of Tasks.
    - Diagnostic error display with Read-Host pause so the window never vanishes abruptly.
    """
    temp_dir = get_update_temp_dir()
    template = '''# Tasks Update Manager - Catppuccin Mocha Themed Runner
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
    Log-Message "=== Tasks Update gestartet: v$currentVer -> v$targetVer ==="
    Log-Message "Zielverzeichnis: $targetAppDir"
    Log-Message "Installer: $installerPath"

    Show-Header

    # [1/5] Warten auf Beendigung von Tasks
    Write-Host "$cBlue  [1/5]$cReset Warten auf Beendigung von Tasks..."
    Log-Message "[1/5] Warten auf Beendigung von Tasks..."
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
    Write-Host "$cGreen        [✓] Tasks erfolgreich beendet.$cReset"
    Log-Message "[1/5] Tasks erfolgreich beendet."
    Write-Host ""

    # [2/5] Installationspaket überprüfen
    Write-Host "$cBlue  [2/5]$cReset Installationspaket überprüfen..."
    Log-Message "[2/5] Installationspaket überprüfen..."
    if (-not (Test-Path -LiteralPath $installerPath)) {
        throw "Installationsdatei wurde nicht gefunden: $installerPath"
    }
    $fileSize = (Get-Item -LiteralPath $installerPath).Length
    if ($fileSize -lt 1048576) {
        throw "Installationsdatei ist unvollständig ($fileSize Bytes)."
    }
    $sizeMb = [math]::Round($fileSize / 1MB, 1)
    Write-Host "$cGreen        [✓] Installationspaket verifiziert ($sizeMb MB).$cReset"
    Log-Message "[2/5] Installationspaket verifiziert ($sizeMb MB)."
    Write-Host ""

    # [3/5] Ausführung des Inno Setup Installers
    Write-Host "$cBlue  [3/5]$cReset Update-Dateien werden installiert..."
    Log-Message "[3/5] Inno Setup Installer wird gestartet..."
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
        Write-Host -NoNewline "`r$cYellow        $char [ $bar ] Extrahiere und aktualisiere Komponenten...$cReset"
        Start-Sleep -Milliseconds 120
        $i++
    }
    Write-Host "`r$cGreen        [✓] Installation abgeschlossen.                         $cReset"
    Log-Message "[3/5] Inno Setup beendet mit ExitCode $($proc.ExitCode)."
    Write-Host ""

    if ($proc.ExitCode -ne 0) {
        throw "Inno Setup Installer wurde mit Fehlercode $($proc.ExitCode) beendet."
    }

    # [4/5] Installation verifizieren
    Write-Host "$cBlue  [4/5]$cReset Installation überprüfen..."
    Log-Message "[4/5] Installation überprüfen..."
    $exePath = Join-Path $targetAppDir "Tasks.exe"
    $cmdPath = Join-Path $targetAppDir "tasks.cmd"
    if (-not (Test-Path -LiteralPath $exePath) -and -not (Test-Path -LiteralPath $cmdPath)) {
        throw "Zielanwendung konnte nach der Installation nicht gefunden werden ($targetAppDir)."
    }
    Set-Content -Path $appliedFile -Value "1" -Encoding UTF8 -ErrorAction SilentlyContinue
    Write-Host "$cGreen        [✓] Programmdateien erfolgreich verifiziert.$cReset"
    Log-Message "[4/5] Programmdateien erfolgreich verifiziert."
    Write-Host ""

    # [5/5] Bereinigung und Neustart
    Write-Host "$cBlue  [5/5]$cReset Temporäre Dateien bereinigen und Tasks neu starten..."
    Log-Message "[5/5] Bereinigung und Neustart..."
    Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pendingFile -Force -ErrorAction SilentlyContinue
    Write-Host "$cGreen        [✓] Bereinigung abgeschlossen.$cReset"
    Write-Host ""

    Write-Host "$cLav  ╭────────────────────────────────────────────────────────╮$cReset"
    Write-Host "$cLav  │$cBold$cGreen        ✨ Update erfolgreich installiert!              $cReset$cLav│$cReset"
    Write-Host "$cLav  │$cSub           Tasks wird automatisch neu gestartet...        $cReset$cLav│$cReset"
    Write-Host "$cLav  ╰────────────────────────────────────────────────────────╯$cReset"
    Write-Host ""

    Start-Sleep -Seconds 1
    if (Test-Path -LiteralPath $exePath) {
        Start-Process -FilePath $exePath -WorkingDirectory $targetAppDir
    } elseif (Test-Path -LiteralPath $cmdPath) {
        Start-Process -FilePath $cmdPath -WorkingDirectory $targetAppDir
    }
    exit 0

} catch {
    $errDetails = $_.Exception.ToString()
    Log-Message "UPDATE FEHLGESCHLAGEN: $errDetails"
    Write-Host ""
    Write-Host "$cRed  ╭────────────────────────────────────────────────────────╮$cReset"
    Write-Host "$cRed  │$cBold                   UPDATE FEHLGESCHLAGEN                  $cReset$cRed│$cReset"
    Write-Host "$cRed  ╰────────────────────────────────────────────────────────╯$cReset"
    Write-Host "$cRed  Fehlerdetails: $($_.Exception.Message)$cReset"
    Write-Host "$cDim  Detailliertes Log: $logFile$cReset"
    Write-Host ""
    Write-Host "$cSub  Das Fenster bleibt zur Fehleranalyse geöffnet.$cReset"
    Write-Host "$cSub  Drücken Sie die Eingabetaste zum Beenden...$cReset"
    Read-Host
    exit 1
}
'''
    script = (
        template.replace("__INSTALLER_PATH__", os.path.abspath(installer_path).replace("'", "''"))
        .replace("__TARGET_APP_DIR__", os.path.abspath(target_app_dir).replace("'", "''"))
        .replace("__CURRENT_VERSION__", (current_version or "").lstrip("vV").replace("'", "''"))
        .replace("__TARGET_VERSION__", (target_version or "").lstrip("vV").replace("'", "''"))
        .replace("__TEMP_DIR__", os.path.abspath(temp_dir).replace("'", "''"))
    )
    return script


def launch_update_and_restart(
    installer_path: str,
    app_dir: Optional[str] = None,
    current_version: str = "",
    target_version: str = "",
) -> bool:
    """
    Bereitet das Update vor und startet die Benutzeroberfläche:
    1. Schreibt die Pfadangabe des Installers in pending_update.txt.
    2. Generiert das Catppuccin-PowerShell-Update-Skript (%TEMP%\\Tasks_Update\\update_runner.ps1).
    3. Startet update_runner.ps1 in einem neuen Konsolenfenster.
    4. Schreibt weiterhin apply_update.cmd für Abwärtskompatibilität.
    """
    target_app_dir = app_dir or WORKSPACE_DIR
    temp_dir = get_update_temp_dir()
    pending_file = os.path.join(temp_dir, "pending_update.txt")
    update_applied_file = os.path.join(temp_dir, "update_just_applied.txt")

    abs_installer = os.path.abspath(installer_path)
    abs_app_dir = os.path.abspath(target_app_dir)

    try:
        with open(pending_file, "w", encoding="utf-8") as f:
            f.write(abs_installer)
    except Exception as e:
        logger.error("Fehler beim Schreiben von pending_update.txt: %s", e)
        return False

    # 1. PowerShell Runner generieren
    ps_content = generate_powershell_updater_script(
        installer_path=abs_installer,
        target_app_dir=abs_app_dir,
        current_version=current_version or APP_VERSION,
        target_version=target_version,
    )
    ps_script = os.path.join(temp_dir, "update_runner.ps1")
    try:
        with open(ps_script, "w", encoding="utf-8-sig") as f:
            f.write(ps_content)
    except Exception as e:
        logger.error("Fehler beim Schreiben von update_runner.ps1: %s", e)

    # 2. CMD Runner für Abwärtskompatibilität generieren
    runner_script = os.path.join(temp_dir, "apply_update.cmd")
    script_content = f"""@echo off
chcp 65001 >nul
title Tasks Update

:: 1. Kurz warten bis der Python-Prozess beendet ist
timeout /t 2 /nobreak >nul 2>nul
if %errorlevel% neq 0 ping 127.0.0.1 -n 3 >nul

:: 2. Inno Setup Installer stillschweigend ausfuehren (/NOTASKS=1 verhindert PATH-Aenderung)
"{installer_path}" /DIR="{target_app_dir}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOTASKS=1 /UPDATE=1

:: 3. Update-Marker setzen
echo 1 > "{update_applied_file}" 2>nul

:: 4. Temporaeren Installer und Flag bereinigen
del /f /q "{installer_path}" 2>nul
del /f /q "{pending_file}" 2>nul

:: 5. Anwendung wieder starten
if exist "{target_app_dir}\\Tasks.exe" (
    start "" "{target_app_dir}\\Tasks.exe"
) else if exist "{target_app_dir}\\run.bat" (
    start "" "{target_app_dir}\\run.bat"
)
exit
"""
    try:
        with open(runner_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        if os.environ.get("RUN_FROM_BATCH") == "1":
            return True

        # In neuem Konsolenfenster starten (CREATE_NEW_CONSOLE = 0x00000010)
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = 0x00000010

        subprocess.Popen(
            [
                "powershell.exe",
                "-NoExit",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps_script,
            ],
            creationflags=creation_flags,
            close_fds=True,
            shell=False,
        )
        return True
    except Exception as e:
        logger.error("Fehler beim Starten des Update-Runners: %s", e)
        return False

