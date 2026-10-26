"""
main.py - Zentraler Einstiegspunkt für den Aufgaben-Detector.
Startet das moderne TUI oder den CLI-Modus aus dem src/-Paket.
"""
import os
import sys
import warnings

# Suppress PyMuPDF legacy fitz module deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning, module="fitz")

# Projekt-Root und Quellverzeichnisse im PYTHONPATH registrieren
_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _sub in [_ROOT_DIR, _SRC_DIR, os.path.join(_SRC_DIR, "core"), os.path.join(_SRC_DIR, "services"), os.path.join(_SRC_DIR, "ui")]:
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

# Enable Per-Monitor DPI Awareness v2 early for Windows processes
if sys.platform == "win32":
    try:
        from win_dialogs import enable_high_dpi_awareness
        enable_high_dpi_awareness()
    except Exception:
        pass

from dependency_checker import ensure_dependencies

if __name__ == "__main__":
    ensure_dependencies()
    if len(sys.argv) == 1:
        sys._launching_tui_printed = True
        print("Launching TUI...", flush=True)
        from tui_app import run_tui
        sys.exit(run_tui() or 0)
    else:
        from src.main import main
        main()
