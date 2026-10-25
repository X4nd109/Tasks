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


def launch_update_and_restart(installer_path: str, app_dir: Optional[str] = None) -> bool:
    """
    Bereitet das Update vor:
    Schreibt die Pfadangabe des Installers in eine Pending-Datei für run.bat.
    Wurde die App über run.bat gestartet, übernimmt run.bat das Update direkt im selben Terminal.
    Andernfalls wird ein schlanker Fallback-Prozess (ohne PowerShell und ohne setup.bat) ausgeführt.
    """
    target_app_dir = app_dir or WORKSPACE_DIR
    temp_dir = get_update_temp_dir()
    pending_file = os.path.join(temp_dir, "pending_update.txt")
    update_applied_file = os.path.join(temp_dir, "update_just_applied.txt")

    try:
        with open(pending_file, "w", encoding="utf-8") as f:
            f.write(os.path.abspath(installer_path))
    except Exception as e:
        logger.error("Fehler beim Schreiben von pending_update.txt: %s", e)
        return False

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
if exist "{target_app_dir}\\run.bat" (
    start "" "{target_app_dir}\\run.bat"
)
exit
"""

    try:
        with open(runner_script, "w", encoding="utf-8") as f:
            f.write(script_content)

        # Wenn run.bat aktiv ist, handhabt run.bat das Update direkt im gleichen Terminal
        if os.environ.get("RUN_FROM_BATCH") == "1":
            return True

        # Fallback für manuelle / eigenständige Python-Aufrufe
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = 0x00000008 | 0x00000200

        subprocess.Popen(
            ["cmd.exe", "/c", runner_script],
            creationflags=creation_flags,
            close_fds=True,
            shell=False,
        )
        return True
    except Exception as e:
        logger.error("Fehler beim Starten des Update-Runners: %s", e)
        return False
