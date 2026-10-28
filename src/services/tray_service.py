"""
tray_service.py - Windows system tray integration for the Tasks application.

Uses ``pystray`` for the tray icon / context menu and ``Pillow`` for the icon
image. If the bundled application icon is missing, a clean 64x64 fallback icon
is generated at runtime, so the tray always has something to display.

``TrayService.start()`` runs the tray loop in a daemon thread and therefore
never blocks the caller (the Textual UI keeps running in the main thread).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Callable, Optional

from PIL import Image, ImageDraw

try:
    import pystray  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    pystray = None  # type: ignore[assignment]

# Patch pystray's Win32 notify handler to safely handle both single-click and double-click
if sys.platform == "win32":
    try:
        import pystray._win32  # type: ignore[import-not-found]
        _orig_on_notify = pystray._win32.Icon._on_notify

        def _safe_win32_on_notify(self, wparam, lparam):
            # 0x0202 is WM_LBUTTONUP, 0x0203 is WM_LBUTTONDBLCLK
            if lparam in (0x0202, 0x0203):
                try:
                    self()
                except Exception:
                    pass
                return
            try:
                return _orig_on_notify(self, wparam, lparam)
            except Exception:
                pass

        pystray._win32.Icon._on_notify = _safe_win32_on_notify
    except Exception:
        pass


try:
    from src.services.autostart_service import is_autostart_enabled, set_autostart
except Exception:  # pragma: no cover - defensive

    def is_autostart_enabled() -> bool:  # type: ignore[misc]
        return False

    def set_autostart(enabled: bool) -> bool:  # type: ignore[misc]
        return False


ICON_SIZE = 64
APP_ICON_NAME = "app_icon"
ICON_EXTENSIONS = (".png", ".ico")

# Colors (Catppuccin-inspired, matching the Tasks TUI)
ICON_BACKGROUND = (30, 30, 46, 255)
ICON_ACCENT = (137, 180, 250, 255)


def _get_project_root() -> str:
    """Returns the absolute path to the project root directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # src/services -> src -> project root
    return os.path.abspath(os.path.join(current_dir, "..", ".."))


def get_assets_dir() -> str:
    """Returns the absolute path to the bundled ``assets`` directory."""
    return os.path.join(_get_project_root(), "assets")


def resolve_icon_path(explicit_path: Optional[str] = None) -> Optional[str]:
    """
    Finds the best available application icon.

    Preference order: ``explicit_path``, ``assets/app_icon.png``,
    ``assets/app_icon.ico``.
    """
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    for extension in ICON_EXTENSIONS:
        candidates.append(os.path.join(get_assets_dir(), f"{APP_ICON_NAME}{extension}"))

    for candidate in candidates:
        try:
            if candidate and os.path.exists(candidate):
                return candidate
        except (OSError, ValueError):  # pragma: no cover - defensive
            continue
    return None


def generate_fallback_image(size: int = ICON_SIZE) -> Image.Image:
    """Draws a clean task-list icon used when no asset file is available."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    scale = size / float(ICON_SIZE)
    inset = max(1, int(2 * scale))
    radius = max(2, int(14 * scale))

    draw.rounded_rectangle(
        (inset, inset, size - 1 - inset, size - 1 - inset),
        radius=radius,
        fill=ICON_BACKGROUND,
        outline=ICON_ACCENT,
        width=max(1, int(3 * scale)),
    )

    bar_left = int(16 * scale)
    bar_right = int(48 * scale)
    bar_height = max(2, int(5 * scale))
    for top in (22, 33, 44):
        y = int(top * scale)
        draw.rounded_rectangle(
            (bar_left, y, bar_right, y + bar_height),
            radius=max(1, int(2 * scale)),
            fill=ICON_ACCENT,
        )

    return image


def create_tray_image(icon_path: Optional[str] = None) -> Image.Image:
    """
    Loads the application icon or generates the fallback image.

    Never raises: unreadable image files fall back to the generated icon.
    """
    resolved = resolve_icon_path(icon_path)
    if resolved:
        try:
            with Image.open(resolved) as loaded:
                image = loaded.convert("RGBA")
                if image.size != (ICON_SIZE, ICON_SIZE):
                    image = image.resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
                return image
        except Exception:
            pass

    return generate_fallback_image(ICON_SIZE)


def _noop() -> None:
    """Default callback that intentionally does nothing."""


class TrayService:
    """
    Manages the Tasks tray icon and its context menu.

    All callbacks are optional so the service can be instantiated in tests or
    in headless environments without side effects.
    """

    def __init__(
        self,
        on_open: Optional[Callable[[], None]] = None,
        on_sync: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        icon_path: Optional[str] = None,
        autostart_checker: Optional[Callable[[], bool]] = None,
        autostart_toggler: Optional[Callable[[bool], bool]] = None,
        open_count: int = 0,
    ) -> None:
        self.on_open = on_open or _noop
        self.on_sync = on_sync or _noop
        self.on_quit = on_quit or _noop

        self._icon_path = icon_path
        self._autostart_checker = autostart_checker or is_autostart_enabled
        self._autostart_toggler = autostart_toggler or set_autostart

        self._open_count = max(0, int(open_count))
        self._status_text = f"Tasks: {self._open_count} open"
        self._tooltip = "Tasks"
        self._last_open_time: float = 0.0

        self._icon = None
        self._image: Optional[Image.Image] = None
        self._menu = None
        self._thread: Optional[threading.Thread] = None

    # -- Properties ----------------------------------------------------------

    @property
    def icon(self):
        """Returns the underlying ``pystray.Icon`` (or ``None``)."""
        return self._icon

    @property
    def image(self) -> Optional[Image.Image]:
        """Returns the currently used tray image."""
        return self._image

    @property
    def status_text(self) -> str:
        """Returns the menu status label."""
        return self._status_text

    @property
    def open_count(self) -> int:
        """Returns the number of open tasks shown in the tray."""
        return self._open_count

    @property
    def is_running(self) -> bool:
        """Returns ``True`` while the tray icon thread is alive."""
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    # -- Menu ----------------------------------------------------------------

    def _build_menu(self):
        """Creates the pystray context menu."""
        if pystray is None:
            return None

        return pystray.Menu(
            pystray.MenuItem("Open Tasks", self._handle_open, default=True),
            pystray.MenuItem("Sync Now", self._handle_sync),
            pystray.MenuItem(
                "Autostart with Windows",
                self._handle_autostart_toggle,
                checked=self._autostart_checked,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Tasks", self._handle_quit),
        )


    def _autostart_checked(self, item=None) -> bool:
        try:
            return bool(self._autostart_checker())
        except Exception:
            return False

    # -- Action handlers -----------------------------------------------------

    def _handle_open(self, icon=None, item=None) -> None:
        now = time.time()
        if now - getattr(self, "_last_open_time", 0.0) < 0.35:
            return
        self._last_open_time = now
        try:
            self.on_open()
        except Exception:
            pass

    def _handle_sync(self, icon=None, item=None) -> None:
        try:
            self.on_sync()
        except Exception:
            pass

    def _handle_autostart_toggle(self, icon=None, item=None) -> None:
        try:
            enabled = self._autostart_checked(item)
            self._autostart_toggler(not enabled)
        except Exception:
            pass
        self._refresh_menu()

    def _handle_quit(self, icon=None, item=None) -> None:
        try:
            self.on_quit()
        except Exception:
            pass


    # -- Lifecycle -----------------------------------------------------------

    def start(self) -> bool:
        """Creates the tray icon and runs its loop in a daemon thread."""
        if pystray is None:
            return False
        if self._icon is not None:
            return True

        self._image = create_tray_image(self._icon_path)
        self._menu = self._build_menu()

        try:
            self._icon = pystray.Icon("tasks", self._image, self._tooltip, self._menu)
        except Exception:
            self._icon = None
            return False

        thread = threading.Thread(
            target=self._run_icon,
            name="TasksTray",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return True

    def _run_icon(self) -> None:
        icon = self._icon
        if icon is None:
            return
        try:
            icon.run()
        except Exception:
            pass

    def stop(self) -> None:
        """Stops the tray icon and joins its thread."""
        icon = self._icon
        self._icon = None

        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def update_status(self, open_count: int) -> None:
        """Updates tooltip and menu status text with the current open count."""
        try:
            count = max(0, int(open_count))
        except (TypeError, ValueError):
            count = 0

        self._open_count = count
        self._status_text = f"Tasks: {count} open"
        self._tooltip = "Tasks"

        icon = self._icon
        if icon is None:
            return

        try:
            icon.title = "Tasks"
        except Exception:
            pass
        self._refresh_menu()


    def _refresh_menu(self) -> None:
        icon = self._icon
        if icon is None:
            return
        try:
            icon.update_menu()
        except Exception:
            pass
