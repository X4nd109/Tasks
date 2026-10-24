"""
directory_service.py - Management and quick access for linked local directories.
Saves linked folder paths locally in data/directories.json (without Git synchronization).
"""

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from config import DIRECTORIES_FILE, APP_DIRECTORIES_FILE
except ImportError:
    # Fallback for standalone or test contexts
    _workspace = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _data_dir = os.path.join(_workspace, "data")
    os.makedirs(_data_dir, exist_ok=True)
    DIRECTORIES_FILE = os.path.join(_data_dir, "directories.json")
    APP_DIRECTORIES_FILE = DIRECTORIES_FILE

logger = logging.getLogger("DirectoryService")

# Windows flag: prevent black cmd console popup in background
_NO_WINDOW_FLAG = 0x08000000 if sys.platform == "win32" else 0


class DirectoryService:
    """Service for managing and quickly opening local directories."""

    @staticmethod
    def _get_active_file() -> str:
        """Returns primary storage path and ensures directory exists."""
        primary = DIRECTORIES_FILE
        target_dir = os.path.dirname(primary)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        return primary

    @staticmethod
    def _get_fallback_file() -> Optional[str]:
        """Returns fallback storage path."""
        return APP_DIRECTORIES_FILE

    @classmethod
    def load_directories(cls) -> List[Dict[str, Any]]:
        """
        Loads all saved directories from the local JSON file.
        Returns a list of directory dictionaries.
        """
        for p in [cls._get_active_file(), cls._get_fallback_file()]:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return data
                except Exception as e:
                    logger.warning(f"Error reading from {p}: {e}")
        return []

    @classmethod
    def save_directories(cls, directories: List[Dict[str, Any]]) -> bool:
        """
        Saves the directories list atomically.
        """
        target = cls._get_active_file()
        temp_file = f"{target}.tmp.{os.getpid()}"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(directories, f, indent=2, ensure_ascii=False)
            if os.path.exists(target):
                os.replace(temp_file, target)
            else:
                os.rename(temp_file, target)

            fallback = cls._get_fallback_file()
            if fallback and fallback != target:
                try:
                    app_dir = os.path.dirname(fallback)
                    if app_dir:
                        os.makedirs(app_dir, exist_ok=True)
                    with open(fallback, "w", encoding="utf-8") as f2:
                        json.dump(directories, f2, indent=2, ensure_ascii=False)
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.error(f"Error saving directories: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
            return False

    @classmethod
    def add_directory(cls, path: str, title: Optional[str] = None) -> Dict[str, Any]:
        """
        Adds or updates a linked directory. Automatically determines title from folder name if omitted.
        """
        clean_path = path.strip().strip('"').strip("'")
        norm_path = os.path.abspath(os.path.expanduser(clean_path))

        if not title or not title.strip():
            derived = os.path.basename(norm_path.rstrip("\\/"))
            title = derived if derived else norm_path

        title_clean = title.strip()
        dirs = cls.load_directories()

        for d in dirs:
            if os.path.abspath(d.get("path", "")).lower() == norm_path.lower():
                d["title"] = title_clean
                cls.save_directories(dirs)
                return d

        entry = {
            "id": f"dir_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
            "title": title_clean,
            "path": norm_path,
            "created_at": time.time(),
        }
        dirs.append(entry)
        cls.save_directories(dirs)
        return entry

    @classmethod
    def remove_directory(cls, identifier: str) -> bool:
        """
        Removes a directory by ID, title, or path.
        """
        ident_clean = str(identifier).strip().lower()
        if not ident_clean:
            return False

        dirs = cls.load_directories()
        initial_len = len(dirs)

        # 1. By exact ID
        dirs = [d for d in dirs if d.get("id", "").strip().lower() != ident_clean]
        if len(dirs) < initial_len:
            cls.save_directories(dirs)
            return True

        # 2. By exact Title
        dirs = [d for d in dirs if d.get("title", "").strip().lower() != ident_clean]
        if len(dirs) < initial_len:
            cls.save_directories(dirs)
            return True

        # 3. By Path / Basename
        dirs = [
            d for d in dirs
            if os.path.abspath(d.get("path", "")).lower() != ident_clean
            and os.path.basename(d.get("path", "")).lower() != ident_clean
        ]
        if len(dirs) < initial_len:
            cls.save_directories(dirs)
            return True

        return False

    @classmethod
    def find_directory(cls, identifier: str) -> Optional[Dict[str, Any]]:
        """Finds a directory by ID, title, or path."""
        ident_clean = str(identifier).strip().lower()
        if not ident_clean:
            return None

        dirs = cls.load_directories()
        for d in dirs:
            if d.get("id", "").lower() == ident_clean:
                return d
            if d.get("title", "").lower() == ident_clean:
                return d

        # Partial search
        for d in dirs:
            if ident_clean in d.get("title", "").lower() or ident_clean in d.get("path", "").lower():
                return d
        return None

    @classmethod
    def find_matching_directory_for_course(
        cls, course: Optional[str], course_full: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Finds a linked directory matching a course code (e.g. 'BET', 'SWP')
        or full course name (e.g. 'Biomedizinische Technik').
        Checks exact matches first, then folder basename matches, then word boundaries, then containment.
        """
        import re

        c_code = (course or "").strip().lower()
        c_full = (course_full or "").strip().lower()
        if not c_code and not c_full:
            return None

        dirs = cls.load_directories()
        if not dirs:
            return None

        candidates = [c for c in [c_code, c_full] if c]

        # 1. Exact match on title or folder basename
        for c in candidates:
            for d in dirs:
                title = d.get("title", "").strip().lower()
                base = os.path.basename(d.get("path", "").rstrip("\/")).lower()
                if title == c or base == c:
                    return d

        # 2. Match as whole word in title or basename (e.g. "SWP" in "3AHWII - SWP" or "SWP PM")
        for c in candidates:
            if len(c) >= 2:
                pattern = r"\b" + re.escape(c) + r"\b"
                for d in dirs:
                    title = d.get("title", "").strip().lower()
                    base = os.path.basename(d.get("path", "").rstrip("\/")).lower()
                    if re.search(pattern, title) or re.search(pattern, base):
                        return d

        # 3. Substring match
        for c in candidates:
            if len(c) >= 3:
                for d in dirs:
                    title = d.get("title", "").strip().lower()
                    path = d.get("path", "").strip().lower()
                    if c in title or c in path:
                        return d

        return None

    @classmethod
    def open_directory(cls, identifier_or_dir: Union[str, Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Opens the specified directory in the system file explorer.
        Returns (success: bool, message: str).
        """
        if isinstance(identifier_or_dir, dict):
            directory = identifier_or_dir
        else:
            directory = cls.find_directory(identifier_or_dir)

        if not directory:
            return False, f"Directory '{identifier_or_dir}' not found."

        path = directory.get("path", "").strip()
        title = directory.get("title", "Directory")

        if not os.path.exists(path):
            return False, f"Folder not found:\n'{path}'"

        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return True, f"'{title}' opened in file explorer."
        except Exception as e:
            return False, f"Error opening folder: {e}"

    @classmethod
    def pick_directory(cls, dialog_title: str = "Select Folder to Link") -> Optional[str]:
        """
        Opens a high-resolution native Windows Explorer folder picker (IFileOpenDialog with FOS_PICKFOLDERS)
        with full Per-Monitor DPI scaling, falling back to Tkinter and PowerShell.
        """
        try:
            try:
                from src.core.win_dialogs import pick_directory
            except ImportError:
                try:
                    from core.win_dialogs import pick_directory
                except ImportError:
                    from win_dialogs import pick_directory

            return pick_directory(dialog_title=dialog_title)
        except Exception as e:
            logger.debug(f"win_dialogs.pick_directory failed or not available: {e}")
        # Attempt 1: Tkinter
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title=dialog_title)
            root.destroy()
            if selected and os.path.exists(selected):
                return os.path.abspath(selected)
            if selected == "":
                return None  # Cancelled by user
        except Exception as e:
            logger.debug(f"Tkinter filedialog not available or failed: {e}")

        # Attempt 2: PowerShell Windows Forms Fallback
        if sys.platform == "win32":
            try:
                ps_script = f"""
                [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
                $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
                $dlg.Description = '{dialog_title}'
                $dlg.ShowNewFolderButton = $false
                if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                    Write-Output $dlg.SelectedPath
                }}
                """
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    creationflags=_NO_WINDOW_FLAG,
                    timeout=60,
                )
                chosen = res.stdout.strip()
                if chosen and os.path.exists(chosen):
                    return os.path.abspath(chosen)
            except Exception as e2:
                logger.error(f"PowerShell folder picker failed: {e2}")

        return None
