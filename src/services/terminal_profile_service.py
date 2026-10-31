"""
terminal_profile_service.py - Manages and repairs the Windows Terminal profile for Tasks.

Automatically registers or updates the 'Tasks' profile in Windows Terminal settings.json,
ensuring obsolete commandlines (such as legacy run.bat or outdated python scripts) are
silently migrated to the modern Tasks.exe binary.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TASKS_PROFILE_GUID = "{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}"
TASKS_PROFILE_NAME = "Tasks"
LEGACY_PROFILE_NAMES = {"Tasks", "Aufgaben-Detector"}


def _workspace_root() -> str:
    """Returns the project root directory."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cur = exe_dir
        for _ in range(3):
            if os.path.isdir(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_windows_terminal_settings_file() -> Optional[str]:
    """
    Finds the active Windows Terminal settings.json file.
    Supports both MSIX packaged and unpackaged installations.
    """
    if sys.platform != "win32":
        return None

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    candidates = [
        os.path.join(
            local_app_data,
            "Packages",
            "Microsoft.WindowsTerminal_8wekyb3d8bbwe",
            "LocalState",
            "settings.json",
        ),
        os.path.join(local_app_data, "Microsoft", "Windows Terminal", "settings.json"),
        os.path.join(
            local_app_data,
            "Packages",
            "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe",
            "LocalState",
            "settings.json",
        ),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return None


def get_default_tasks_executable(app_dir: Optional[str] = None) -> str:
    """Returns the optimal executable commandline path for Tasks."""
    base_dir = os.path.abspath(app_dir or _workspace_root())

    # 1. Prefer compiled Tasks.exe in target/current directory
    exe_candidate = os.path.join(base_dir, "Tasks.exe")
    if os.path.isfile(exe_candidate):
        return exe_candidate

    # 2. Prefer running executable if frozen
    if getattr(sys, "frozen", False) and sys.executable:
        return os.path.abspath(sys.executable)

    # 3. Development fallback: python main.py
    main_py = os.path.join(base_dir, "main.py")
    if os.path.isfile(main_py):
        py_exe = sys.executable or "python.exe"
        return f'"{py_exe}" "{main_py}"'

    return exe_candidate


def get_default_icon_path(app_dir: Optional[str] = None) -> str:
    """Returns the path to the best available icon for the terminal profile."""
    base_dir = os.path.abspath(app_dir or _workspace_root())
    png_candidate = os.path.join(base_dir, "assets", "app_icon.png")
    if os.path.isfile(png_candidate):
        return png_candidate
    ico_candidate = os.path.join(base_dir, "assets", "app_icon.ico")
    if os.path.isfile(ico_candidate):
        return ico_candidate
    return png_candidate


def ensure_windows_terminal_profile(app_dir: Optional[str] = None) -> bool:
    """
    Ensures that the Tasks profile in Windows Terminal is present and configured
    with the current Tasks.exe commandline.
    
    Migrates legacy commandlines (e.g. run.bat) automatically.
    Returns True if successfully verified or updated, False if Windows Terminal is not found.
    """
    settings_file = find_windows_terminal_settings_file()
    if not settings_file:
        logger.debug("Windows Terminal settings.json not found on this system.")
        return False

    base_dir = os.path.abspath(app_dir or _workspace_root())
    target_cmd = get_default_tasks_executable(base_dir)
    target_icon = get_default_icon_path(base_dir)

    target_profile: Dict[str, Any] = {
        "guid": TASKS_PROFILE_GUID,
        "name": TASKS_PROFILE_NAME,
        "commandline": target_cmd,
        "startingDirectory": base_dir,
        "icon": target_icon,
        "tabTitle": TASKS_PROFILE_NAME,
        "hidden": False,
    }

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not read Windows Terminal settings.json: %s", e)
        return False

    profiles_obj = data.get("profiles")
    if isinstance(profiles_obj, dict):
        profile_list = profiles_obj.get("list")
        if not isinstance(profile_list, list):
            profile_list = []
            profiles_obj["list"] = profile_list
        target_container = profile_list
    elif isinstance(profiles_obj, list):
        target_container = profiles_obj
    else:
        profiles_obj = {"list": []}
        data["profiles"] = profiles_obj
        target_container = profiles_obj["list"]

    # Check existing entries
    existing_index = -1
    needs_update = True

    for idx, p in enumerate(target_container):
        if not isinstance(p, dict):
            continue
        p_guid = str(p.get("guid", "")).lower()
        p_name = str(p.get("name", ""))
        if p_guid == TASKS_PROFILE_GUID.lower() or p_name in LEGACY_PROFILE_NAMES:
            existing_index = idx
            # Check if all relevant properties already match
            if (
                p.get("commandline") == target_cmd
                and p.get("startingDirectory") == base_dir
                and p.get("icon") == target_icon
                and p.get("name") == TASKS_PROFILE_NAME
                and p.get("hidden") is False
            ):
                needs_update = False
            break

    if not needs_update:
        logger.debug("Windows Terminal Tasks profile is already up-to-date.")
        return True

    # Update or append
    if existing_index >= 0:
        # Preserve user customizations where possible, but enforce healthy commandline & icon
        existing = dict(target_container[existing_index])
        existing.update(target_profile)
        target_container[existing_index] = existing
    else:
        target_container.append(target_profile)

    try:
        tmp_file = settings_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_file, settings_file)
        logger.info("Successfully updated Windows Terminal Tasks profile in %s", settings_file)
        return True
    except Exception as e:
        logger.error("Failed to write updated Windows Terminal settings.json: %s", e)
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
        return False


def remove_windows_terminal_profile() -> bool:
    """Removes the Tasks profile from Windows Terminal settings.json."""
    settings_file = find_windows_terminal_settings_file()
    if not settings_file:
        return False

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False

    profiles_obj = data.get("profiles")
    if isinstance(profiles_obj, dict):
        profile_list = profiles_obj.get("list")
        if not isinstance(profile_list, list):
            return True
        target_container = profile_list
    elif isinstance(profiles_obj, list):
        target_container = profiles_obj
    else:
        return True

    filtered = [
        p for p in target_container
        if isinstance(p, dict)
        and str(p.get("guid", "")).lower() != TASKS_PROFILE_GUID.lower()
        and str(p.get("name", "")) not in LEGACY_PROFILE_NAMES
    ]

    if len(filtered) == len(target_container):
        return True

    if isinstance(profiles_obj, dict):
        profiles_obj["list"] = filtered
    else:
        data["profiles"] = filtered

    try:
        tmp_file = settings_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_file, settings_file)
        return True
    except Exception:
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
        return False


def get_windows_terminal_profile_status() -> Dict[str, Any]:
    """Returns diagnostic information about the Windows Terminal profile."""
    settings_file = find_windows_terminal_settings_file()
    if not settings_file:
        return {
            "installed": False,
            "configured": False,
            "settings_file": None,
            "commandline": None,
        }

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        profiles_obj = data.get("profiles")
        container = (
            profiles_obj.get("list")
            if isinstance(profiles_obj, dict)
            else profiles_obj
        ) or []
        for p in container:
            if isinstance(p, dict):
                p_guid = str(p.get("guid", "")).lower()
                p_name = str(p.get("name", ""))
                if p_guid == TASKS_PROFILE_GUID.lower() or p_name in LEGACY_PROFILE_NAMES:
                    return {
                        "installed": True,
                        "configured": True,
                        "settings_file": settings_file,
                        "commandline": p.get("commandline"),
                        "startingDirectory": p.get("startingDirectory"),
                        "icon": p.get("icon"),
                    }
        return {
            "installed": True,
            "configured": False,
            "settings_file": settings_file,
            "commandline": None,
        }
    except Exception:
        return {
            "installed": True,
            "configured": False,
            "settings_file": settings_file,
            "commandline": None,
        }
