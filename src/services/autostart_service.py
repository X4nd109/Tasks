"""
autostart_service.py - Windows Autostart manager for the Tasks application.

Registers (or removes) the application in the per-user Windows Registry Run key:

    HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

The registered value is named ``Tasks`` and points to ``main.py --tray``. When a
``pythonw.exe`` is available next to the running interpreter it is preferred so
that no console window flashes on boot.

All functions are defensive: on non-Windows platforms or when the registry is
not accessible they simply return ``False`` (or the default command) instead of
raising.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

try:
    import winreg  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - only on non-Windows platforms
    winreg = None  # type: ignore[assignment]

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "Tasks"
TRAY_FLAG = "--tray"


def _get_project_root() -> str:
    """Returns the absolute path to the project root directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # src/services -> src -> project root
    return os.path.abspath(os.path.join(current_dir, "..", ".."))


def get_main_py_path() -> str:
    """Returns the absolute path to the application entry point (``main.py``)."""
    return os.path.join(_get_project_root(), "main.py")


def _get_executable() -> str:
    """
    Returns the interpreter that should be registered for autostart.

    * Frozen builds (PyInstaller) use the executable itself.
    * Source runs prefer ``pythonw.exe`` (no console window on boot) and fall
      back to the current interpreter.
    """
    if getattr(sys, "frozen", False):
        return sys.executable

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    try:
        if os.path.exists(pythonw):
            return pythonw
    except (OSError, ValueError):  # pragma: no cover - defensive
        pass
    return sys.executable


def get_default_autostart_command() -> str:
    """Builds the command line that is registered for autostart."""
    executable = _get_executable()

    if getattr(sys, "frozen", False):
        return f'"{executable}" {TRAY_FLAG}'

    return f'"{executable}" "{get_main_py_path()}" {TRAY_FLAG}'


def is_windows() -> bool:
    """Returns ``True`` when the Windows registry is available."""
    return winreg is not None and os.name == "nt"


def is_autostart_enabled() -> bool:
    """Checks whether the ``Tasks`` value exists in the per-user Run key."""
    if not is_windows():
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except (FileNotFoundError, PermissionError, OSError):
        return False
    except Exception:  # pragma: no cover - defensive
        return False


def get_autostart_command() -> str:
    """
    Returns the currently registered command.

    If no value is registered yet, the command that *would* be registered is
    returned instead.
    """
    if is_windows():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                value, _value_type = winreg.QueryValueEx(key, APP_NAME)
            if isinstance(value, str) and value.strip():
                return value
        except (FileNotFoundError, PermissionError, OSError):
            pass
        except Exception:  # pragma: no cover - defensive
            pass

    return get_default_autostart_command()


def set_autostart(enabled: bool) -> bool:
    """
    Enables or disables autostart for the current user.

    Returns ``True`` on success and ``False`` on any error (or on platforms
    without a Windows registry).
    """
    if not is_windows():
        return False

    return _enable_autostart() if enabled else _disable_autostart()


def _enable_autostart() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key,
                APP_NAME,
                0,
                winreg.REG_SZ,
                get_default_autostart_command(),
            )
        return True
    except (FileNotFoundError, PermissionError, OSError):
        return False
    except Exception:  # pragma: no cover - defensive
        return False


def _disable_autostart() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        # Value (or key) did not exist -> autostart is already disabled.
        return True
    except (PermissionError, OSError):
        return False
    except Exception:  # pragma: no cover - defensive
        return False


def toggle_autostart() -> bool:
    """Toggles the autostart state and returns the new state, if known."""
    new_state = not is_autostart_enabled()
    return new_state if set_autostart(new_state) else is_autostart_enabled()
