"""
main.py - Zentraler Einstiegspunkt für den Aufgaben-Detector.
Startet das moderne TUI oder den CLI-Modus aus dem src/-Paket.
"""
import os
import sys
import time
import warnings
from typing import Optional

# Suppress PyMuPDF legacy fitz module deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning, module="fitz")


# Projekt-Root und Quellverzeichnisse im PYTHONPATH registrieren
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    _found_dev = None
    _cur = _exe_dir
    for _ in range(3):
        if os.path.isdir(os.path.join(_cur, ".git")):
            _found_dev = _cur
            break
        _parent = os.path.dirname(_cur)
        if _parent == _cur:
            break
        _cur = _parent
    _ROOT_DIR = _found_dev if _found_dev else _exe_dir
    _SRC_DIR = os.path.join(_exe_dir, "_internal", "src")
    if not os.path.isdir(_SRC_DIR):
        _SRC_DIR = os.path.join(_ROOT_DIR, "src")
else:
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



# Filled lazily by ``_send_instance_command``; also patchable in tests.
send_instance_command = None


def _send_instance_command(command: str):
    """Sends a single-instance command, importing the IPC client lazily."""
    global send_instance_command
    if send_instance_command is None:
        try:
            from single_instance import send_instance_command as _send
        except ImportError:
            from src.core.single_instance import send_instance_command as _send
        send_instance_command = _send
    return send_instance_command(command)


def _parse_protocol_uri(uri: str):
    """Parses a ``tasks://`` URI into ``(ipc_command, target_id_or_None)``.

    ``tasks://task/<id>`` -> ``("OPEN_TASK:<id>", "<id>")``
    ``tasks://exam/<id>`` -> ``("OPEN_EXAM:<id>", "<id>")``
    Everything else       -> ``("SHOW", None)``
    """
    from urllib.parse import urlparse

    raw = (uri or "").strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return "SHOW", None

    if parsed.scheme.lower() != "tasks":
        return "SHOW", None

    segments = []
    if parsed.netloc:
        segments.extend(parsed.netloc.split("/"))
    if parsed.path:
        segments.extend(parsed.path.split("/"))
    segments = [segment for segment in segments if segment]

    if len(segments) >= 2:
        kind = segments[0].strip().lower()
        target = segments[1].strip()
        if target:
            if kind == "task":
                return f"OPEN_TASK:{target}", target
            if kind == "exam":
                return f"OPEN_EXAM:{target}", target
    elif len(segments) == 1:
        if segments[0].strip().lower() == "update":
            return "OPEN_UPDATE", None

    return "SHOW", None


def _spawn_tui(*extra_args: str) -> None:
    """Starts a fresh TUI process, optionally with ``--open-task`` / ``--open-exam``."""
    import subprocess

    py_exe = sys.executable or "python.exe"
    try:
        if os.path.basename(py_exe).lower() == "pythonw.exe":
            candidate = os.path.join(os.path.dirname(py_exe), "python.exe")
            if os.path.exists(candidate):
                py_exe = candidate
    except Exception:
        pass

    args = [py_exe, os.path.join(_ROOT_DIR, "main.py"), *extra_args]
    try:
        subprocess.Popen(args, cwd=_ROOT_DIR)
    except Exception:
        pass


def _handle_protocol_uri(uri: str) -> bool:
    """Dispatches a ``tasks://`` URI to a running instance or a fresh TUI.

    Returns ``True`` when the command was delivered to an already running
    instance, ``False`` when a new TUI process had to be launched.
    """
    command, target = _parse_protocol_uri(uri)

    try:
        response = _send_instance_command(command)
    except Exception:
        response = None

    if response is not None:
        if command.startswith("OPEN_TASK:"):
            print(f"Opened assignment {target} in the running Tasks instance.", flush=True)
        elif command.startswith("OPEN_EXAM:"):
            print(f"Opened exam {target} in the running Tasks instance.", flush=True)
        elif command == "OPEN_UPDATE":
            print("Opened update reminder in the running Tasks instance.", flush=True)
        else:
            print("Tasks window restored.", flush=True)
        return True

    if command.startswith("OPEN_TASK:") and target:
        _spawn_tui("--open-task", target)
    elif command.startswith("OPEN_EXAM:") and target:
        _spawn_tui("--open-exam", target)
    elif command == "OPEN_UPDATE":
        _spawn_tui("--open-update")
    else:
        _spawn_tui()
    return False


def _get_arg_value(flag: str) -> str:
    """Returns the value following ``flag`` in ``sys.argv`` (or an empty string)."""
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return ""
    if index + 1 < len(sys.argv):
        return sys.argv[index + 1].strip()
    return ""


def _run_tray_background():
    """Runs a lightweight system tray process when launched without a console window."""
    import subprocess
    import threading
    import time
    from single_instance import SingleInstanceServer
    from tray_service import TrayService

    stop_event = threading.Event()

    def on_open(extra_args=None):
        root = os.path.dirname(os.path.abspath(__file__))
        tasks_exe = os.path.join(root, "Tasks.exe")
        tasks_cmd = os.path.join(root, "tasks.cmd")
        if os.path.isfile(tasks_exe):
            cmd_args = [tasks_exe]
            if extra_args:
                cmd_args.extend(extra_args)
            subprocess.Popen(cmd_args, cwd=root)
        elif os.path.isfile(tasks_cmd):
            cmd_args = ["cmd.exe", "/c", "start", "", tasks_cmd]
            if extra_args:
                cmd_args.extend(extra_args)
            subprocess.Popen(cmd_args, cwd=root)
        else:
            py = sys.executable.replace("pythonw.exe", "python.exe")
            py_args = ["cmd.exe", "/c", "start", "", py, os.path.join(root, "main.py")]
            if extra_args:
                py_args.extend(extra_args)
            subprocess.Popen(py_args, cwd=root)
        stop_event.set()

    def on_quit():
        stop_event.set()

    def on_sync():
        def _do_sync():
            try:
                from task_manager import TaskManager
                mgr = TaskManager()
                mgr.sync(deep_scan=False)
                open_cnt = 0
                for t in mgr.tasks:
                    if getattr(t, "deleted", False):
                        continue
                    done = getattr(t, "completed", None)
                    if not isinstance(done, bool):
                        done = bool(getattr(t, "is_completed", False))
                    if not done:
                        open_cnt += 1
                tray.update_status(open_cnt)

                try:
                    from notification_engine import NotificationEngine
                    NotificationEngine().check_new_tasks(mgr.tasks)
                except Exception:
                    pass
            except Exception:
                pass
        threading.Thread(target=_do_sync, daemon=True, name="TrayBgSync").start()

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
        elif c.startswith("OPEN_TASK:"):
            tid = (cmd or "").strip().split(":", 1)[1]
            on_open(["--open-task", tid])
            return "OK:RESTORED"
        elif c.startswith("OPEN_EXAM:"):
            eid = (cmd or "").strip().split(":", 1)[1]
            on_open(["--open-exam", eid])
            return "OK:RESTORED"
        return "OK"

    try:
        from notification_service import ensure_tasks_protocol_registered
        ensure_tasks_protocol_registered()
    except Exception:
        pass

    server = SingleInstanceServer(on_command_callback=on_cmd)
    if not server.start():
        return 0

    tray = TrayService(on_open=on_open, on_sync=on_sync, on_quit=on_quit)
    tray.start()

    try:
        from config import get_auto_sync_interval_seconds
    except Exception:
        def get_auto_sync_interval_seconds(_interval=None):
            return 1800

    last_sync_time = time.time()
    last_notif_check = 0.0

    try:
        while not stop_event.is_set():
            now = time.time()
            try:
                interval_sec = get_auto_sync_interval_seconds()
            except Exception:
                interval_sec = 0
            if interval_sec > 0 and now - last_sync_time >= interval_sec:
                last_sync_time = now
                on_sync()

            if now - last_notif_check >= 30.0:
                last_notif_check = now
                try:
                    from notification_engine import NotificationEngine
                    from task_manager import TaskManager
                    from untis_service import load_untis_exams_cache, load_custom_exams
                    engine = NotificationEngine()
                    mgr = TaskManager()
                    engine.check_task_due_reminders(mgr.tasks)
                    all_exams = load_untis_exams_cache() + load_custom_exams()
                    engine.check_exam_reminders(all_exams)
                except Exception:
                    pass

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


def _get_process_name(pid: int) -> Optional[str]:
    """Returns the lowercase executable name of a process (e.g. 'explorer.exe')."""
    if sys.platform != "win32" or not pid:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_process:
            return None
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        try:
            if kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(h_process)
    except Exception:
        pass
    return None


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
    #    IMPORTANT: Never kill non-shell parents. When launched via a Desktop or
    #    Start Menu shortcut the parent is explorer.exe - killing it restarts the
    #    whole desktop shell (screen flicker, taskbar reset).
    try:
        import signal

        parent_pid = os.getppid()
        if parent_pid and parent_pid != os.getpid():
            parent_name = _get_process_name(parent_pid)
            if parent_name in ("cmd.exe", "powershell.exe", "pwsh.exe"):
                os.kill(parent_pid, signal.SIGTERM)
    except Exception:
        pass


def _handle_existing_instance_autoclose() -> None:
    """Closes this terminal immediately and silently after signaling the background instance."""
    _close_current_terminal_window()
    sys.exit(0)


if __name__ == "__main__":
    if "--install-playwright" in sys.argv:
        try:
            from playwright.__main__ import main as pw_main
            sys.argv = ["playwright", "install", "chromium"]
            pw_main()
            sys.exit(0)
        except SystemExit as se:
            sys.exit(se.code if se.code is not None else 0)
        except Exception as e:
            print(f"Error installing Playwright Chromium: {e}", flush=True)
            sys.exit(0)

    _exe_name = os.path.basename(sys.executable).lower()
    if "taskstray" in _exe_name and "--tray" not in sys.argv:
        sys.argv.append("--tray")

    if "--uri" in sys.argv:
        idx = sys.argv.index("--uri")
        uri = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        _handle_protocol_uri(uri)
        sys.exit(0)

    _open_task_arg = _get_arg_value("--open-task")
    _open_exam_arg = _get_arg_value("--open-exam")
    _open_update_arg = "--open-update" in sys.argv
    if _open_task_arg or _open_exam_arg or _open_update_arg:
        if sys.platform == "win32":
            try:
                from single_instance import send_instance_command as _send
                _send("SHOW")
            except Exception:
                pass
        sys._launching_tui_printed = True
        print("Launching TUI...", flush=True)
        from tui_app import run_tui
        sys.exit(
            run_tui(
                initial_task_id=_open_task_arg or None,
                initial_exam_id=_open_exam_arg or None,
                open_update_dialog=_open_update_arg,
            ) or 0
        )

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
