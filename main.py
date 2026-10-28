"""
main.py - Zentraler Einstiegspunkt für den Aufgaben-Detector.
Startet das moderne TUI oder den CLI-Modus aus dem src/-Paket.
"""
import os
import sys
import time
import warnings

# Suppress PyMuPDF legacy fitz module deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning, module="fitz")

# Non-blocking keyboard polling for the auto-close countdown (Windows only).
if sys.platform == "win32":
    try:
        import msvcrt
    except Exception:  # pragma: no cover - msvcrt always exists on Windows
        msvcrt = None
else:
    msvcrt = None

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


def _is_tray_enabled_fast() -> bool:
    """Ultra-fast check if minimize_to_tray is enabled without importing heavy config modules."""
    for p in [os.path.join(_ROOT_DIR, "cache", "tasks_config.json"), os.path.join(_ROOT_DIR, "config.json")]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    import json
                    d = json.load(f)
                    if isinstance(d, dict) and "minimize_to_tray" in d:
                        return bool(d["minimize_to_tray"])
            except Exception:
                pass
    return True


def _run_tray_background():
    """Runs a lightweight system tray process when launched without a console window."""
    import subprocess
    import threading
    import time
    from single_instance import SingleInstanceServer
    from tray_service import TrayService

    stop_event = threading.Event()

    def on_open():
        root = os.path.dirname(os.path.abspath(__file__))
        tasks_bat = os.path.join(root, "tasks.bat")
        if os.path.exists(tasks_bat):
            subprocess.Popen(["cmd.exe", "/c", "start", "", tasks_bat], cwd=root)
        else:
            py = sys.executable.replace("pythonw.exe", "python.exe")
            subprocess.Popen(["cmd.exe", "/c", "start", "", py, os.path.join(root, "main.py")], cwd=root)
        stop_event.set()

    def on_quit():
        stop_event.set()

    def on_cmd(cmd):
        c = (cmd or "").strip().upper()
        if c == "SHOW":
            on_open()
            return "OK:RESTORED"
        elif c == "QUIT":
            on_quit()
            return "OK:QUITTING"
        elif c == "STATUS":
            return "OK:RUNNING"
        return "OK"

    server = SingleInstanceServer(on_command_callback=on_cmd)
    if not server.start():
        return 0

    tray = TrayService(on_open=on_open, on_quit=on_quit)
    tray.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        try:
            tray.stop()
        except Exception:
            pass
        try:
            server.stop()
        except Exception:
            pass
    return 0


def _close_current_terminal_window() -> None:
    """Closes the current terminal window / tab (Windows, best effort)."""
    if sys.platform != "win32":
        return

    # 1) Ask the attached classic console window to close (WM_CLOSE).
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        h_con = kernel32.GetConsoleWindow()
        if h_con:
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h_con, buffer, 256)
            if buffer.value == "ConsoleWindowClass":
                user32.PostMessageW(h_con, 0x0010, 0, 0)  # WM_CLOSE
    except Exception:
        pass

    # 2) Terminate the parent shell (cmd.exe / powershell.exe / pwsh.exe) so that
    #    Windows Terminal also closes the hosting tab.
    try:
        import signal

        parent_pid = os.getppid()
        if parent_pid and parent_pid != os.getpid():
            os.kill(parent_pid, signal.SIGTERM)
    except Exception:
        pass


def _handle_existing_instance_autoclose(timeout_seconds: int = 10) -> None:
    """Restores the background instance and closes this terminal after a countdown.

    Only the [ENTER] key (``\\r`` / ``\\n``) cancels the countdown; every other
    keystroke is ignored while the countdown keeps ticking.
    """
    print("Restoring window...", flush=True)
    print("Window succesfully restored.", flush=True)

    poll_interval = 0.05
    start = time.monotonic()
    last_shown = None

    while True:
        elapsed = time.monotonic() - start
        remaining = int(timeout_seconds) - int(elapsed)
        if remaining <= 0:
            break

        if remaining != last_shown:
            sys.stdout.write(
                f"\rThis terminal will close in {remaining}s. Press [ENTER] to cancel... "
            )
            sys.stdout.flush()
            last_shown = remaining

        if msvcrt is not None:
            try:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\r", "\n"):
                        sys.stdout.write("\nClose cancelled. Terminal remains open.\n")
                        sys.stdout.flush()
                        return
            except Exception:
                pass

        time.sleep(poll_interval)

    sys.stdout.write("\nClosing terminal...\n")
    sys.stdout.flush()
    _close_current_terminal_window()
    sys.exit(0)


if __name__ == "__main__":
    ensure_dependencies()

    if "--quit" in sys.argv:
        try:
            from single_instance import send_instance_command
            res = send_instance_command("QUIT")
            if res is not None:
                print("Tasks background process terminated.", flush=True)
                sys.exit(0)
            else:
                print("No running Tasks background process found.", flush=True)
                sys.exit(0)
        except Exception as e:
            print(f"Error terminating background process: {e}", flush=True)
            sys.exit(1)

    if "--tray" in sys.argv or "--tray-daemon" in sys.argv:
        sys.exit(_run_tray_background() or 0)

    if len(sys.argv) == 1:
        if sys.platform == "win32" and _is_tray_enabled_fast():
            try:
                from single_instance import send_instance_command
                res = send_instance_command("SHOW")
                if res is not None:
                    _handle_existing_instance_autoclose()
                    sys.exit(0)
            except Exception:
                pass
        sys._launching_tui_printed = True
        print("Launching TUI...", flush=True)
        from tui_app import run_tui
        sys.exit(run_tui() or 0)
    else:
        from src.main import main
        main()
