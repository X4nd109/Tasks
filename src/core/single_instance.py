"""
single_instance.py - Single-instance IPC for the Tasks application.

On Windows the primary transport is a per-user local Named Pipe:

    \\\\.\\pipe\\Tasks_App_Pipe_<username>

On other platforms (and whenever named pipes are unavailable) the module falls
back to a small TCP server bound to ``127.0.0.1`` on a deterministic per-user
port.

Clients can send short textual commands such as ``SHOW``, ``QUIT`` and
``STATUS``. The :class:`SingleInstanceServer` forwards every command to the
callbacks supplied by the application and answers with the callback's return
value.
"""

from __future__ import annotations

import ctypes
import getpass
import os
import socket
import sys
import threading
import zlib
from typing import Callable, Optional


PIPE_PREFIX = r"\\.\pipe\Tasks_App_Pipe_"
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT_BASE = 50000
SOCKET_PORT_RANGE = 10000

STATUS_COMMAND = "STATUS"
SHOW_COMMAND = "SHOW"
QUIT_COMMAND = "QUIT"


def _current_user() -> str:
    """Returns the current user name, falling back to a stable placeholder."""
    try:
        return getpass.getuser() or "user"
    except Exception:  # pragma: no cover - extremely defensive
        return "user"


def _get_pipe_name() -> str:
    return PIPE_PREFIX + _current_user()


def _get_socket_port() -> int:
    checksum = zlib.crc32(_current_user().encode("utf-8")) & 0xFFFFFFFF
    return SOCKET_PORT_BASE + (checksum % SOCKET_PORT_RANGE)


PIPE_NAME = _get_pipe_name()
SOCKET_PORT = _get_socket_port()


# --- Optional Windows Named Pipe bindings -----------------------------------

ERROR_FILE_NOT_FOUND = 2
ERROR_INVALID_HANDLE = 6
ERROR_BROKEN_PIPE = 109
ERROR_SEM_TIMEOUT = 121
ERROR_PIPE_BUSY = 231
ERROR_NO_DATA = 232
ERROR_PIPE_NOT_CONNECTED = 233
ERROR_PIPE_CONNECTED = 535

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_UNLIMITED_INSTANCES = 255

_K32 = None
_WINTYPES = None
_NAMED_PIPE_AVAILABLE = False


def _load_named_pipe_bindings() -> bool:
    """Loads the kernel32 functions required for named pipes."""
    global _K32, _WINTYPES, _NAMED_PIPE_AVAILABLE

    if os.name != "nt":
        return False

    try:
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        kernel32.ConnectNamedPipe.restype = wintypes.BOOL
        kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
        kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
        kernel32.ReadFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel32.ReadFile.restype = wintypes.BOOL
        kernel32.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        kernel32.WriteFile.restype = wintypes.BOOL
        kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel32.FlushFileBuffers.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        _K32 = kernel32
        _WINTYPES = wintypes
        _NAMED_PIPE_AVAILABLE = True
    except Exception:  # pragma: no cover - only if kernel32 is unavailable
        _K32 = None
        _WINTYPES = None
        _NAMED_PIPE_AVAILABLE = False

    return _NAMED_PIPE_AVAILABLE


_load_named_pipe_bindings()


def _use_named_pipe() -> bool:
    """
    Selects the IPC transport.

    Named pipes are used on Windows. Setting the environment variable
    ``TASKS_SINGLE_INSTANCE_TRANSPORT=socket`` forces the portable TCP fallback
    (useful for diagnostics and test environments).
    """
    override = os.environ.get("TASKS_SINGLE_INSTANCE_TRANSPORT", "").strip().lower()
    if override == "socket":
        return False
    if override == "pipe":
        return _NAMED_PIPE_AVAILABLE
    return _NAMED_PIPE_AVAILABLE


# --- Client -----------------------------------------------------------------


def send_instance_command(command: str, timeout: float = 2.0) -> Optional[str]:
    """
    Sends ``command`` to a running instance and returns its response.

    Returns ``None`` when no server is listening, when the request times out or
    when any transport error occurs.
    """
    if not command or not command.strip():
        return None

    payload = command.strip()
    try:
        wait = max(0.05, float(timeout))
    except (TypeError, ValueError):
        wait = 2.0

    if _use_named_pipe():
        return _send_via_pipe(payload, wait)

    return _send_via_socket(payload, wait)


def _send_via_pipe(command: str, timeout: float) -> Optional[str]:
    """Sends a command through the Windows named pipe (with timeout)."""
    if not _NAMED_PIPE_AVAILABLE:
        return None

    # Ultra-schnelle Vorab-Prüfung in <0.1ms: Existiert die Pipe überhaupt?
    try:
        if _K32 is not None:
            if not _K32.WaitNamedPipeW(PIPE_NAME, 0):
                err = ctypes.get_last_error()
                if err in (2, 3, ERROR_FILE_NOT_FOUND):
                    return None
    except Exception:
        pass

    result: list[Optional[str]] = [None]


    def _worker() -> None:
        try:
            with open(PIPE_NAME, "r+b", buffering=0) as pipe:
                pipe.write((command + "\n").encode("utf-8"))
                raw = bytearray()
                while not raw.endswith(b"\n"):
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        break
                text = bytes(raw).decode("utf-8", errors="replace").strip()
                result[0] = text or None
        except Exception:
            result[0] = None

    worker = threading.Thread(target=_worker, name="TasksIpcClient", daemon=True)
    worker.start()
    worker.join(timeout)
    return result[0] if not worker.is_alive() else None


def _send_via_socket(command: str, timeout: float) -> Optional[str]:
    """Sends a command through the localhost TCP fallback."""
    try:
        with socket.create_connection((SOCKET_HOST, SOCKET_PORT), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall((command + "\n").encode("utf-8"))
            raw = bytearray()
            while not raw.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > 65536:
                    break
            text = bytes(raw).decode("utf-8", errors="replace").strip()
            return text or None
    except (OSError, ValueError):
        return None
    except Exception:  # pragma: no cover - defensive
        return None


# --- Server -----------------------------------------------------------------


class SingleInstanceServer:
    """
    Listens for single-instance commands in a daemon thread.

    Every received command is passed to ``on_command_callback``; its return
    value is sent back to the client. ``STATUS`` replies with ``"RUNNING"``
    when the callback does not provide an answer.
    """

    def __init__(
        self,
        on_command_callback: Callable[[str], str],
        pipe_name: Optional[str] = None,
        socket_port: Optional[int] = None,
    ) -> None:
        self.on_command_callback = on_command_callback
        self.pipe_name = pipe_name or PIPE_NAME
        self.socket_port = socket_port or SOCKET_PORT

        self._stop_event = threading.Event()
        self._running = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._transport: Optional[str] = None

        self._pipe_handle = None
        self._listener: Optional[socket.socket] = None

    # -- Public API ----------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Returns ``True`` while the listener thread is active."""
        return self._running.is_set()

    @property
    def transport(self) -> Optional[str]:
        """Returns ``"pipe"`` or ``"socket"`` once started."""
        return self._transport

    def start(self) -> bool:
        """Starts the listener thread. Returns ``True`` on success."""
        if self._running.is_set():
            return True

        self._stop_event.clear()

        started = False
        if _use_named_pipe():
            started = self._start_pipe()
            if started:
                self._transport = "pipe"

        if not started:
            if not self._start_socket():
                self._transport = None
                return False
            self._transport = "socket"

        self._running.set()
        target = self._pipe_loop if self._transport == "pipe" else self._socket_loop
        self._thread = threading.Thread(target=target, name="TasksIpcServer", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Shuts the listener down cleanly."""
        self._stop_event.set()

        if self._transport == "pipe":
            self._wake_pipe()
        elif self._transport == "socket":
            self._close_listener()

        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

        if self._transport == "pipe":
            self._close_pipe(self._pipe_handle)

        self._thread = None
        self._transport = None
        self._running.clear()

    # -- Command dispatch ----------------------------------------------------

    def _dispatch(self, command: str) -> str:
        """Runs the callback and normalises the reply."""
        try:
            response = self.on_command_callback(command)
        except Exception:
            response = None

        if not response and command.strip().upper() == STATUS_COMMAND:
            response = "RUNNING"

        if response is None or response == "":
            response = "OK"

        return str(response)

    def _handle_command_bytes(self, raw: bytes) -> Optional[str]:
        command = raw.decode("utf-8", errors="replace").strip()
        if not command:
            return None
        return self._dispatch(command)

    # -- Named pipe implementation ------------------------------------------

    def _start_pipe(self) -> bool:
        if not _NAMED_PIPE_AVAILABLE:
            return False
        try:
            self._pipe_handle = self._create_pipe_instance()
        except Exception:
            self._pipe_handle = None
        return bool(self._pipe_handle)

    def _create_pipe_instance(self):
        """Creates one named pipe instance and returns its handle."""
        if _K32 is None:
            return None
        handle = _K32.CreateNamedPipeW(
            self.pipe_name,
            PIPE_ACCESS_DUPLEX,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            PIPE_UNLIMITED_INSTANCES,
            65536,
            65536,
            0,
            None,
        )
        invalid = ctypes.c_void_p(-1).value
        if not handle or handle == invalid:
            return None
        return handle

    def _pipe_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                handle = self._pipe_handle
                if not handle:
                    try:
                        handle = self._create_pipe_instance()
                    except Exception:
                        break
                    if not handle:
                        break
                    self._pipe_handle = handle

                connected = _K32.ConnectNamedPipe(handle, None)
                error = ctypes.get_last_error()

                if not connected and error not in (
                    ERROR_PIPE_CONNECTED,
                    ERROR_NO_DATA,
                ):
                    self._close_pipe(handle)
                    self._pipe_handle = None
                    if self._stop_event.is_set() or error in (
                        ERROR_INVALID_HANDLE,
                        ERROR_BROKEN_PIPE,
                    ):
                        break
                    continue

                if self._stop_event.is_set():
                    break

                raw = self._read_pipe(handle)
                if raw:
                    reply = self._handle_command_bytes(raw)
                    if reply is not None:
                        self._write_pipe(handle, reply)

                try:
                    _K32.FlushFileBuffers(handle)
                except Exception:  # pragma: no cover - defensive
                    pass
                try:
                    _K32.DisconnectNamedPipe(handle)
                except Exception:  # pragma: no cover - defensive
                    pass
        finally:
            self._close_pipe(self._pipe_handle)
            self._pipe_handle = None
            self._running.clear()

    def _read_pipe(self, handle) -> bytes:
        if _K32 is None or _WINTYPES is None:
            return b""

        buffer = ctypes.create_string_buffer(4096)
        read = _WINTYPES.DWORD(0)
        data = bytearray()

        while len(data) < 65536:
            success = _K32.ReadFile(handle, buffer, len(buffer), ctypes.byref(read), None)
            if not success or read.value == 0:
                break
            data.extend(buffer.raw[: read.value])
            if data.endswith(b"\n"):
                break

        return bytes(data)

    def _write_pipe(self, handle, text: str) -> None:
        if _K32 is None or _WINTYPES is None:
            return

        payload = (text + "\n").encode("utf-8")
        written = _WINTYPES.DWORD(0)
        buffer = ctypes.create_string_buffer(payload, len(payload))
        try:
            _K32.WriteFile(handle, buffer, len(payload), ctypes.byref(written), None)
        except Exception:  # pragma: no cover - defensive
            pass

    def _wake_pipe(self) -> None:
        """Connects to our own pipe so a blocked ConnectNamedPipe() returns."""
        try:
            with open(self.pipe_name, "r+b", buffering=0):
                pass
        except Exception:
            pass

    @staticmethod
    def _close_pipe(handle) -> None:
        if _K32 is None or not handle:
            return
        try:
            _K32.CloseHandle(handle)
        except Exception:  # pragma: no cover - defensive
            pass

    # -- Socket fallback implementation -------------------------------------

    def _start_socket(self) -> bool:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((SOCKET_HOST, self.socket_port))
            listener.listen(5)
            listener.settimeout(0.2)
        except OSError:
            try:
                listener.close()
            except OSError:
                pass
            return False

        self._listener = listener
        return True

    def _socket_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                listener = self._listener
                if listener is None:
                    break
                try:
                    connection, _addr = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                with connection:
                    try:
                        connection.settimeout(1.0)
                        raw = self._read_socket(connection)
                        if raw:
                            reply = self._handle_command_bytes(raw)
                            if reply is not None:
                                connection.sendall((reply + "\n").encode("utf-8"))
                    except OSError:
                        continue
        finally:
            self._close_listener()
            self._running.clear()

    @staticmethod
    def _read_socket(connection: socket.socket) -> bytes:
        data = bytearray()
        while len(data) < 65536:
            try:
                chunk = connection.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            data.extend(chunk)
            if data.endswith(b"\n"):
                break
        return bytes(data)

    def _close_listener(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is None:
            return
        try:
            listener.close()
        except OSError:  # pragma: no cover - defensive
            pass


# --- Convenience helpers ----------------------------------------------------


def create_default_handler(
    on_show: Optional[Callable[[], None]] = None,
    on_quit: Optional[Callable[[], None]] = None,
    status_provider: Optional[Callable[[], str]] = None,
) -> Callable[[str], str]:
    """
    Builds a standard SHOW / QUIT / STATUS command handler.

    ``SHOW`` restores the main window, ``QUIT`` terminates the application and
    ``STATUS`` reports ``"RUNNING"`` (or custom stats from ``status_provider``).
    """

    def _handler(command: str) -> str:
        name = command.strip().upper()
        if name == SHOW_COMMAND:
            if on_show is not None:
                on_show()
            return "OK"
        if name == QUIT_COMMAND:
            if on_quit is not None:
                on_quit()
            return "OK"
        if name == STATUS_COMMAND:
            if status_provider is not None:
                try:
                    return str(status_provider())
                except Exception:
                    return "RUNNING"
            return "RUNNING"
        return "UNKNOWN_COMMAND"

    return _handler
