"""
tui_app.py - Moderne, interaktive Terminal-Benutzeroberfläche für Tasks.
Basiert auf Textual & Rich. Unterstützt vollständige Mausbedienung sowie Tastatur-Shortcuts.
"""

import datetime
import os
import re
import sys
import functools
import threading
import time
import urllib.parse
import webbrowser
import logging
from typing import List, Optional, Set, Dict, Tuple, Callable, Any

class _PlaywrightShutdownFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "TargetClosedError" in msg or "Target page, context or browser has been closed" in msg or "coro=<BrowserContext.close()" in msg:
            return False
        return True

logging.getLogger("asyncio").addFilter(_PlaywrightShutdownFilter())

if hasattr(sys, "unraisablehook"):
    _orig_unraisablehook = sys.unraisablehook
    def _clean_unraisablehook(unraisable):
        err_str = str(unraisable.exc_value) if unraisable.exc_value else ""
        err_type = unraisable.exc_type.__name__ if unraisable.exc_type else ""
        if "TargetClosedError" in err_type or "Target page, context or browser has been closed" in err_str or "BrowserContext.close" in err_str:
            return
        _orig_unraisablehook(unraisable)
    sys.unraisablehook = _clean_unraisablehook

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

from rich.text import Text
from rich.markup import escape
from textual.app import App, ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll, HorizontalScroll, Center
from textual import events
from textual.events import Resize, MouseDown, Click
from textual.geometry import Size
from textual.coordinate import Coordinate
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.widget import Widget
from textual.message import Message
from textual.widgets import Button, Checkbox, DataTable, Header, Input, Label, Markdown, Static, TextArea, LoadingIndicator, ProgressBar, Select
try:
    from core.task_manager import parse_deadline_for_sorting
except ImportError:
    try:
        from src.core.task_manager import parse_deadline_for_sorting
    except ImportError:
        from task_manager import parse_deadline_for_sorting
from textual.command import CommandPalette, Provider, DiscoveryHit, Hit, Hits, CommandInput, SearchIcon, CommandList
try:
    from src.ui.range_slider import TwoThumbRangeSlider
except ImportError:
    try:
        from range_slider import TwoThumbRangeSlider
    except ImportError:
        pass

from textual.theme import Theme
from textual.binding import Binding
import urllib.parse

OLED_THEME = Theme(
    name="oled",
    primary="#205EA6",
    secondary="#24837B",
    warning="#AD8301",
    error="#AF3029",
    success="#66800B",
    accent="#9B76C8",
    foreground="#FFFCF0",
    background="#000000",
    surface="#000000",
    panel="#000000",
    boost="#1c1b1a",
    dark=True,
    variables={
        "border": "#343331",
        "border-blurred": "#1c1b1a",
        "surface-active": "#1c1b1a",
        "block-cursor-background": "#205EA6",
        "block-cursor-foreground": "#FFFCF0",
        "input-cursor-foreground": "#9B76C8",
        "input-cursor-background": "#FFFCF0",
        "input-selection-background": "#24837B 40%",
        "button-color-foreground": "#FFFCF0",
        "footer-background": "#000000",
        "footer-foreground": "#CECDC3",
    },
)


def is_ctrl_pressed_win32() -> bool:
    """Prüft über die Windows Win32-API (GetAsyncKeyState), ob STRG physisch gehalten wird."""
    if os.name == "nt":
        try:
            # 0x11 = VK_CONTROL (prüft linke & rechte STRG-Taste)
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
        except Exception:
            return False
    return False


def is_shift_pressed_win32() -> bool:
    """Prüft über die Windows Win32-API (GetAsyncKeyState), ob SHIFT physisch gehalten wird."""
    if os.name == "nt":
        try:
            # 0x10 = VK_SHIFT, 0xA0 = VK_LSHIFT, 0xA1 = VK_RSHIFT
            u32 = ctypes.windll.user32
            return bool(
                (u32.GetAsyncKeyState(0x10) | u32.GetAsyncKeyState(0xA0) | u32.GetAsyncKeyState(0xA1)) & 0x8000
            )
        except Exception:
            return False
    return False


def patch_win32_event_monitor() -> None:
    """
    Behebt ein bekanntes Problem in Textual unter Windows (Win32 / Windows Terminal / ConPTY):
    Wenn STRG + Backspace gedrückt wird, liest Textuals win32.EventMonitor zwar das KeyEvent ein,
    wirft jedoch dwControlKeyState weg und übergibt nur uChar.UnicodeChar ('\x7f' oder '\x08')
    an XTermParser, welcher dies fälschlicherweise als einfaches 'backspace' anstelle von
    'ctrl+backspace' parst.
    Dieser Patch fängt STRG+Backspace auf Windows-Ebene ab und reicht die korrekte Sequenz
    (\\x1b[127;5u) an den Parser weiter, wodurch zuverlässig das Key-Event 'ctrl+backspace' erzeugt wird.
    """
    if os.name != "nt" or sys.platform != "win32":
        return

    try:
        from textual.drivers import win32
        from textual import constants
        from textual._xterm_parser import XTermParser
        from ctypes import byref, wintypes

        if getattr(win32.EventMonitor, "_ctrl_backspace_patched", False):
            return

        def patched_event_monitor_run(self: win32.EventMonitor) -> None:
            exit_requested = self.exit_event.is_set
            parser = XTermParser(debug=constants.DEBUG)

            try:
                read_count = wintypes.DWORD(0)
                hIn = win32.GetStdHandle(win32.STD_INPUT_HANDLE)

                MAX_EVENTS = 1024
                KEY_EVENT = 0x0001
                WINDOW_BUFFER_SIZE_EVENT = 0x0004

                arrtype = win32.INPUT_RECORD * MAX_EVENTS
                input_records = arrtype()
                ReadConsoleInputW = win32.KERNEL32.ReadConsoleInputW
                keys: list[str] = []
                append_key = keys.append

                while not exit_requested():
                    for event in parser.tick():
                        self.process_event(event)

                    # Warten auf neue Events
                    if win32.wait_for_handles([hIn], 100) is None:
                        continue

                    ReadConsoleInputW(
                        hIn, byref(input_records), MAX_EVENTS, byref(read_count)
                    )
                    read_input_records = input_records[: read_count.value]

                    del keys[:]
                    new_size = None

                    for input_record in read_input_records:
                        event_type = input_record.EventType

                        if event_type == KEY_EVENT:
                            key_event = input_record.Event.KeyEvent
                            key = key_event.uChar.UnicodeChar
                            if key_event.bKeyDown:
                                # Windows Terminal / ConPTY / conhost Ctrl+Backspace Erkennung:
                                # 0x0008 = LEFT_CTRL_PRESSED, 0x0004 = RIGHT_CTRL_PRESSED
                                is_ctrl = bool(key_event.dwControlKeyState & 0x000C)
                                if is_ctrl and (
                                    key_event.wVirtualKeyCode in (8, 0x48)
                                    or key in ("\x08", "\x7f")
                                ):
                                    append_key("\x1b[127;5u")
                                    continue

                                # Shift+Enter Erkennung (0x0010 = SHIFT_PRESSED, VK_RETURN = 13):
                                is_shift = bool(key_event.dwControlKeyState & 0x0010)
                                if is_shift and (
                                    key_event.wVirtualKeyCode == 13
                                    or key in ("\r", "\n")
                                ):
                                    append_key("\x1b[13;2u")
                                    continue

                                if (
                                    key_event.dwControlKeyState
                                    and key_event.wVirtualKeyCode == 0
                                    and not key
                                ):
                                    continue
                                append_key(key)
                        elif event_type == WINDOW_BUFFER_SIZE_EVENT:
                            size = input_record.Event.WindowBufferSizeEvent.dwSize
                            new_size = (size.X, size.Y)

                    if keys:
                        for event in parser.feed(
                            "".join(keys).encode("utf-16", "surrogatepass").decode("utf-16")
                        ):
                            self.process_event(event)
                    if new_size is not None:
                        self.on_size_change(*new_size)

            except Exception as error:
                self.app.log.error("EVENT MONITOR ERROR", error)

        win32.EventMonitor.run = patched_event_monitor_run
        win32.EventMonitor._ctrl_backspace_patched = True
    except Exception:
        pass


def configure_enhanced_text_inputs() -> None:
    """
    Rüstet alle Input- und TextArea-Widgets projektweit mit gängigen
    Windows-Tastaturkürzeln aus (STRG+A zum Markieren, wortweise Cursor-Bewegung,
    markieren mit SHIFT+STRG+Pfeiltasten, Pos1/Ende und wortweises Löschen).
    """
    patch_win32_event_monitor()

    # 1. Input & Subklassen (CommandInput, UnifiedCommandInput, etc.)
    new_input_bindings = []
    replaced_keys = {
        "ctrl+a",
        "home",
        "end",
        "ctrl+shift+a",
        "ctrl+left",
        "ctrl+right",
        "ctrl+shift+left",
        "shift+ctrl+left",
        "ctrl+shift+right",
        "shift+ctrl+right",
        "shift+home",
        "shift+end",
        "ctrl+backspace",
        "ctrl+delete",
        "ctrl+w",
        "ctrl+h",
    }

    for b in Input.BINDINGS:
        keys = [k.strip() for k in b.key.split(",")]
        rem = [k for k in keys if k not in replaced_keys]
        if not rem:
            continue
        if len(rem) != len(keys):
            new_input_bindings.append(
                Binding(
                    ",".join(rem),
                    b.action,
                    b.description,
                    show=b.show,
                    key_display=b.key_display,
                    priority=b.priority,
                    tooltip=b.tooltip,
                    id=b.id,
                    system=b.system,
                    group=b.group,
                )
            )
        else:
            new_input_bindings.append(b)

    new_input_bindings.extend(
        [
            Binding("ctrl+a", "select_all", "Select all", show=False),
            Binding("home", "home", "Go to start", show=False),
            Binding("end,ctrl+e", "end", "Go to end", show=False),
            Binding("shift+home", "home(True)", "Select line start", show=False),
            Binding("shift+end", "end(True)", "Select line end", show=False),
            Binding("ctrl+left", "cursor_left_word", "Move cursor left a word", show=False),
            Binding("ctrl+right", "cursor_right_word", "Move cursor right a word", show=False),
            Binding(
                "ctrl+shift+left,shift+ctrl+left",
                "cursor_left_word(True)",
                "Move cursor left a word and select",
                show=False,
            ),
            Binding(
                "ctrl+shift+right,shift+ctrl+right",
                "cursor_right_word(True)",
                "Move cursor right a word and select",
                show=False,
            ),
            Binding("ctrl+backspace,ctrl+w,ctrl+h", "delete_left_word", "Delete left to start of word", show=False),
            Binding("ctrl+delete,alt+delete", "delete_right_word", "Delete right to start of word", show=False),
        ]
    )
    Input.BINDINGS = new_input_bindings
    Input._merged_bindings = Input._merge_bindings()
    CommandInput._merged_bindings = CommandInput._merge_bindings()

    # Hook Input._on_key für unmittelbare Event-Interzeption vor jedem Bubbling
    if not getattr(Input, "_enhanced_on_key_patched", False):
        orig_input_on_key = Input._on_key

        async def enhanced_input_on_key(self: Input, event: events.Key) -> None:
            is_ctrl_backspace = event.key in ("ctrl+backspace", "ctrl+w", "ctrl+h") or (
                event.key == "backspace" and is_ctrl_pressed_win32()
            )
            if is_ctrl_backspace:
                event.prevent_default()
                event.stop()
                self.action_delete_left_word()
                return

            is_ctrl_del = event.key in ("ctrl+delete", "alt+delete") or (
                event.key == "delete" and is_ctrl_pressed_win32()
            )
            if is_ctrl_del:
                event.prevent_default()
                event.stop()
                self.action_delete_right_word()
                return

            await orig_input_on_key(self, event)

        Input._on_key = enhanced_input_on_key
        Input._enhanced_on_key_patched = True

    # 2. TextArea (Notizen, z.B. inp_exam_topics)
    new_ta_bindings = []
    ta_replaced = {
        "ctrl+a",
        "home",
        "end",
        "ctrl+left",
        "ctrl+right",
        "ctrl+shift+left",
        "shift+ctrl+left",
        "ctrl+shift+right",
        "shift+ctrl+right",
        "shift+home",
        "shift+end",
        "ctrl+backspace",
        "ctrl+delete",
        "ctrl+w",
        "ctrl+h",
    }

    for b in TextArea.BINDINGS:
        keys = [k.strip() for k in b.key.split(",")]
        rem = [k for k in keys if k not in ta_replaced]
        if not rem:
            continue
        if len(rem) != len(keys):
            new_ta_bindings.append(
                Binding(
                    ",".join(rem),
                    b.action,
                    b.description,
                    show=b.show,
                    key_display=b.key_display,
                    priority=b.priority,
                    tooltip=b.tooltip,
                    id=b.id,
                    system=b.system,
                    group=b.group,
                )
            )
        else:
            new_ta_bindings.append(b)

    new_ta_bindings.extend(
        [
            Binding("ctrl+a", "select_all", "Select all", show=False),
            Binding("home", "cursor_line_start", "Cursor line start", show=False),
            Binding("end,ctrl+e", "cursor_line_end", "Cursor line end", show=False),
            Binding("shift+home", "cursor_line_start(True)", "Cursor line start select", show=False),
            Binding("shift+end", "cursor_line_end(True)", "Cursor line end select", show=False),
            Binding("ctrl+left", "cursor_word_left", "Cursor word left", show=False),
            Binding("ctrl+right", "cursor_word_right", "Cursor word right", show=False),
            Binding(
                "ctrl+shift+left,shift+ctrl+left",
                "cursor_word_left(True)",
                "Cursor left word select",
                show=False,
            ),
            Binding(
                "ctrl+shift+right,shift+ctrl+right",
                "cursor_word_right(True)",
                "Cursor right word select",
                show=False,
            ),
            Binding("ctrl+backspace,ctrl+w,ctrl+h", "delete_word_left", "Delete left to start of word", show=False),
            Binding("ctrl+delete,alt+delete", "delete_word_right", "Delete right to start of word", show=False),
        ]
    )
    TextArea.BINDINGS = new_ta_bindings
    TextArea._merged_bindings = TextArea._merge_bindings()

    # Hook TextArea._on_key für unmittelbare Event-Interzeption vor jedem Bubbling
    if not getattr(TextArea, "_enhanced_on_key_patched", False):
        orig_textarea_on_key = TextArea._on_key

        async def enhanced_textarea_on_key(self: TextArea, event: events.Key) -> None:
            is_ctrl_backspace = event.key in ("ctrl+backspace", "ctrl+w", "ctrl+h") or (
                event.key == "backspace" and is_ctrl_pressed_win32()
            )
            if is_ctrl_backspace:
                event.prevent_default()
                event.stop()
                self.action_delete_word_left()
                return

            is_ctrl_del = event.key in ("ctrl+delete", "alt+delete") or (
                event.key == "delete" and is_ctrl_pressed_win32()
            )
            if is_ctrl_del:
                event.prevent_default()
                event.stop()
                self.action_delete_word_right()
                return

            await orig_textarea_on_key(self, event)

        TextArea._on_key = enhanced_textarea_on_key
        TextArea._enhanced_on_key_patched = True


configure_enhanced_text_inputs()


class ChatInputArea(TextArea):
    """
    3-line prompt and form input for the AI assistant and dialogs with vertical line centering & bottom scrolling:
    - Sends message / submits on Enter
    - Inserts newline on Shift+Enter (and Ctrl+J / Ctrl+Enter)
    - Stays fixed at 3 lines typing height (height: 5 with thin solid border)
    - Line 1: centered vertically in the middle row (padding: 1 1 1 1)
    - Line 2: line 1 shifts to top row, line 2 is in the middle row (padding: 0 1 1 1)
    - Line 3: lines 1, 2, 3 fill top, middle, bottom rows (padding: 0 1 0 1)
    - Line > 3: user writes on the bottom row, earlier lines scroll up, vertical scrollbar appears
    - Has .value property (get/set) for 100% compatibility with Textual Input
    - Posts Input.Submitted(self, self.value) on Enter for 100% compatibility with modal handlers
    """
    _is_chat_input_area: bool = True

    DEFAULT_CSS = """
    ChatInputArea {
        height: 5;
        min-height: 5;
        max-height: 5;
        border: solid #45475a;
        background: #1e1e2e;
        color: #cdd6f4;
        padding: 1 1 1 1;
        scrollbar-size: 1 1;
        scrollbar-color: #89b4fa #181825;
    }
    ChatInputArea:focus {
        border: solid #89b4fa;
    }
    """

    class Submitted(Message):
        def __init__(self, value: str, input: Optional[Any] = None) -> None:
            super().__init__()
            self.value = value
            self.input = input

    def __init__(
        self,
        value: str = "",
        placeholder: str = "",
        text: str = "",
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
        tooltip: Optional[str] = None,
        **kwargs,
    ) -> None:
        init_text = text if text else (value or "")
        super().__init__(
            text=init_text,
            show_line_numbers=False,
            soft_wrap=True,
            placeholder=placeholder,
            id=id,
            classes=classes,
            disabled=disabled,
            tooltip=tooltip,
            **kwargs,
        )
        self.styles.height = 5
        self.styles.padding = (1, 1, 1, 1)

    @property
    def value(self) -> str:
        return self.text

    @value.setter
    def value(self, v: str) -> None:
        self.text = v or ""
        self._update_line_layout()

    def on_mount(self) -> None:
        self._update_line_layout()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._update_line_layout()
        try:
            self.post_message(Input.Changed(self, self.value))
        except Exception:
            pass

    def _update_line_layout(self) -> None:
        lines = 1
        try:
            if hasattr(self, "wrapped_document") and self.wrapped_document:
                lines = max(1, self.wrapped_document.height)
            elif hasattr(self, "document") and self.document:
                lines = max(1, self.document.line_count)
        except Exception:
            lines = 1

        self.styles.height = 5
        if lines <= 1:
            self.styles.padding = (1, 1, 1, 1)
            self.show_vertical_scrollbar = False
        elif lines == 2:
            self.styles.padding = (0, 1, 1, 1)
            self.show_vertical_scrollbar = False
        elif lines == 3:
            self.styles.padding = (0, 1, 0, 1)
            self.show_vertical_scrollbar = False
        else:
            self.styles.padding = (0, 1, 0, 1)
            self.show_vertical_scrollbar = True
            try:
                self.scroll_cursor_visible()
            except Exception:
                pass

    def _update_height(self) -> None:
        self._update_line_layout()

    def on_key(self, event: events.Key) -> None:
        key_name = (event.key or "").lower()
        evt_name = (getattr(event, "name", "") or "").lower()
        evt_aliases = [str(a).lower() for a in getattr(event, "aliases", [])]

        is_shift = (
            key_name in ("shift+enter", "shift+return", "ctrl+j", "ctrl+enter", "alt+enter", "shift+linefeed")
            or "shift" in evt_name
            or any("shift" in a for a in evt_aliases)
            or ((key_name in ("enter", "return") or event.character in ("\n", "\r")) and is_shift_pressed_win32())
        )
        if is_shift:
            event.prevent_default()
            event.stop()
            try:
                if self.selected_text:
                    self.replace("\n", self.selection.start, self.selection.end)
                else:
                    self.insert("\n")
            except Exception:
                self.insert("\n")
            self._update_line_layout()
        elif key_name in ("enter", "return"):
            event.prevent_default()
            event.stop()
            val = self.text
            self.post_message(self.Submitted(val, input=self))
            self.post_message(Input.Submitted(self, val))


AutoExpandingInput = ChatInputArea

if not getattr(Input, "_chat_input_area_instancecheck_patched", False):
    _orig_input_instancecheck = type(Input).__instancecheck__
    _orig_input_subclasscheck = type(Input).__subclasscheck__

    def _custom_input_instancecheck(cls, instance):
        if (cls is Input or getattr(cls, "__name__", "") == "Input") and (
            getattr(instance, "_is_chat_input_area", False)
            or getattr(type(instance), "_is_chat_input_area", False)
            or type(instance).__name__ == "ChatInputArea"
        ):
            return True
        return _orig_input_instancecheck(cls, instance)

    def _custom_input_subclasscheck(cls, subclass):
        if (cls is Input or getattr(cls, "__name__", "") == "Input") and (
            getattr(subclass, "_is_chat_input_area", False)
            or getattr(subclass, "__name__", "") == "ChatInputArea"
        ):
            return True
        return _orig_input_subclasscheck(cls, subclass)

    type(Input).__instancecheck__ = _custom_input_instancecheck
    type(Input).__subclasscheck__ = _custom_input_subclasscheck
    Input._chat_input_area_instancecheck_patched = True


try:
    from update_service import (
        download_update_installer,
        launch_update_and_restart,
        get_update_temp_dir,
    )
except ImportError:
    from src.services.update_service import (
        download_update_installer,
        launch_update_and_restart,
        get_update_temp_dir,
    )

from config import (
    APP_VERSION,
    WORKSPACE_DIR,
    ALLOWED_THEMES,
    CONFIG_DIR,
    DEFAULT_THEME,
    DOWNLOADS_DIR,
    load_saved_theme,
    save_saved_theme,
    load_favorite_themes,
    save_favorite_themes,
    toggle_favorite_theme,
    UNTIS_GROUP,
    UNTIS_URL,
    save_untis_group,
    _load_untis_group,
    load_excuse_profile,
    save_excuse_profile,
    load_full_school_config,
    save_full_school_config,
    save_single_exam_note,
    load_exam_notes,
    sanitize_filename,
    get_task_download_dir,
    load_all_course_links,
    clean_browser_profile_caches,
    AUTO_CLEAN_BROWSER_CACHE,
    close_all_active_browser_contexts,
    set_shutting_down,
    is_shutting_down,
)
from models import (
    Task,
    SubjectAbsenceSummary,
    MissedLesson,
    DailyAbsenceSummary,
    UntisExam,
)
from task_manager import TaskManager
from untis_service import (
    load_untis_cache,
    sync_untis_data,
    open_untis_login_window,
    login_untis_direct,
    save_untis_cache,
    get_daily_absence_summaries,
    load_untis_exams_cache,
    save_untis_exams_cache,
    get_next_upcoming_exam,
    save_custom_exam,
    delete_custom_exam,
    lookup_untis_lesson_details,
)


def get_windows_console_window_size() -> Optional[tuple[int, int]]:
    """Ermittelt unter Windows die tatsächlichen Dimensionen des sichtbaren Terminalfensters."""
    if sys.platform != "win32":
        return None
    try:
        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [
                ("Left", wintypes.SHORT),
                ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT),
                ("Bottom", wintypes.SHORT),
            ]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD),
                ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD),
            ]

        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        kernel32 = ctypes.windll.kernel32

        # 1. Versuche Standard-Output Handle
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if h and h != -1 and kernel32.GetConsoleScreenBufferInfo(h, ctypes.byref(csbi)):
            w = int(csbi.srWindow.Right - csbi.srWindow.Left + 1)
            h_win = int(csbi.srWindow.Bottom - csbi.srWindow.Top + 1)
            if w > 0 and h_win > 0:
                return (w, h_win)

        # 2. Fallback: Öffne CONOUT$ direkt (funktioniert auch bei umgeleiteter stdout)
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 1
        FILE_SHARE_WRITE = 2
        OPEN_EXISTING = 3
        h_con = kernel32.CreateFileW(
            "CONOUT$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_con and h_con != -1:
            try:
                if kernel32.GetConsoleScreenBufferInfo(h_con, ctypes.byref(csbi)):
                    w = int(csbi.srWindow.Right - csbi.srWindow.Left + 1)
                    h_win = int(csbi.srWindow.Bottom - csbi.srWindow.Top + 1)
                    if w > 0 and h_win > 0:
                        return (w, h_win)
            finally:
                kernel32.CloseHandle(h_con)

        # 3. Fallback über shutil
        import shutil
        s = shutil.get_terminal_size()
        if s.columns > 0 and s.lines > 0:
            return (s.columns, s.lines)
    except Exception:
        pass

    return None


def ensure_terminal_window_size(target_cols: int = 123, min_height_px: int = 680) -> None:
    """
    Sorgt dafür, dass das Terminal-Fenster (Windows Terminal oder Console Host)
    beim Start auf mindestens target_cols Spalten und eine passende Mindesthöhe
    skaliert wird, ohne dass es zu Render-Desyncs in Textual / ConPTY kommt.
    Berücksichtigt Per-Monitor DPI Awareness v2 für gestochen scharfe, proportionale Skalierung.
    """
    if os.name != "nt" or sys.platform != "win32":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        # 1. Aktuelle Terminalgröße ermitteln
        win_size = get_windows_console_window_size()
        cur_cols = win_size[0] if win_size else 0
        cur_lines = win_size[1] if win_size else 0
        target_lines = max(cur_lines, 33)

        # 2. Direkte Win32-Konsolenpuffer-Anpassung via CONOUT$ (für conhost / Standard-Konsole)
        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [
                ("Left", wintypes.SHORT),
                ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT),
                ("Bottom", wintypes.SHORT),
            ]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD),
                ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD),
            ]

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 1
        FILE_SHARE_WRITE = 2
        OPEN_EXISTING = 3
        h_con = kernel32.CreateFileW(
            "CONOUT$",
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if h_con and h_con != -1:
            try:
                csbi = CONSOLE_SCREEN_BUFFER_INFO()
                if kernel32.GetConsoleScreenBufferInfo(h_con, ctypes.byref(csbi)):
                    c_w = csbi.srWindow.Right - csbi.srWindow.Left + 1
                    c_h = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
                    if c_w < target_cols or c_h < target_lines:
                        max_coord = COORD(300, 100)
                        try:
                            kernel32.GetLargestConsoleWindowSize.restype = COORD
                            mc = kernel32.GetLargestConsoleWindowSize(h_con)
                            if mc.X > 0 and mc.Y > 0:
                                max_coord = mc
                        except Exception:
                            pass

                        clamped_cols = min(target_cols, max_coord.X)
                        clamped_lines = min(target_lines, max_coord.Y)

                        new_buf_x = max(csbi.dwSize.X, clamped_cols)
                        new_buf_y = max(csbi.dwSize.Y, clamped_lines)
                        kernel32.SetConsoleScreenBufferSize(h_con, COORD(new_buf_x, new_buf_y))

                        rect = SMALL_RECT(0, 0, clamped_cols - 1, clamped_lines - 1)
                        if kernel32.SetConsoleWindowInfo(h_con, True, ctypes.byref(rect)):
                            kernel32.SetConsoleScreenBufferSize(h_con, COORD(clamped_cols, new_buf_y))
            finally:
                kernel32.CloseHandle(h_con)

        # 3. VT-Modus auf stdout aktivieren, bevor ANSI VT Resize-Sequenzen gesendet werden
        try:
            h_out = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            if h_out and h_out != -1:
                mode = wintypes.DWORD()
                if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
                    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                    if not (mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING):
                        kernel32.SetConsoleMode(h_out, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
                    sys.stdout.write(f"\x1b[8;{target_lines};{target_cols}t")
                    sys.stdout.flush()
        except Exception:
            pass

        # 4. Windows Terminal / GUI Window Handle finden und per SetWindowPos skalieren
        hwnd_target = None

        # a) Vordergrund-Fenster prüfen
        hwnd_fg = user32.GetForegroundWindow()
        if hwnd_fg:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_fg, buf, 256)
            if buf.value in ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"):
                hwnd_target = hwnd_fg
            else:
                GA_ROOT = 2
                h_root = user32.GetAncestor(hwnd_fg, GA_ROOT)
                if h_root:
                    user32.GetClassNameW(h_root, buf, 256)
                    if buf.value in ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"):
                        hwnd_target = h_root

        # b) Console Window bzw. Root-Ancestor (Windows Terminal Host)
        if not hwnd_target:
            h_con_win = kernel32.GetConsoleWindow()
            if h_con_win:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(h_con_win, buf, 256)
                if buf.value == "ConsoleWindowClass":
                    hwnd_target = h_con_win
                else:
                    GA_ROOT = 2
                    h_root = user32.GetAncestor(h_con_win, GA_ROOT)
                    if h_root:
                        hwnd_target = h_root

        # 5. Fenstergröße anpassen, falls erforderlich
        if hwnd_target:
            global _CACHED_TERMINAL_HWND
            _CACHED_TERMINAL_HWND = hwnd_target

            # DPI des Fensters ermitteln für proportionale Skalierung
            dpi = 96
            try:
                if hasattr(user32, "GetDpiForWindow"):
                    d = user32.GetDpiForWindow(hwnd_target)
                    if d and d > 0:
                        dpi = d
            except Exception:
                pass
            dpi_scale = max(1.0, dpi / 96.0)

            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd_target, ctypes.byref(rect)):
                cur_w = rect.right - rect.left
                cur_h = rect.bottom - rect.top

                col_width_px = 9.5 * dpi_scale
                if win_size and win_size[0] > 0:
                    measured = (cur_w - 40) / win_size[0]
                    if 6.0 <= measured <= 36.0:
                        col_width_px = measured

                line_height_px = 22.0 * dpi_scale
                if win_size and win_size[1] > 0:
                    measured_h = (cur_h - 50) / win_size[1]
                    if 12.0 <= measured_h <= 54.0:
                        line_height_px = measured_h

                min_width_px = int(target_cols * col_width_px + 40)
                # Mindestens 33 Textzeilen hoch skalieren
                effective_min_h = max(int(min_height_px * dpi_scale), int(target_lines * line_height_px + 50))

                max_screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
                max_screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN

                target_w = min(max(cur_w, min_width_px), max(max_screen_w - 40, 800))
                target_h = min(max(cur_h, effective_min_h), max(max_screen_h - 60, 600))

                if cur_w < target_w or cur_h < target_h:
                    x = rect.left
                    y = rect.top
                    if x + target_w > max_screen_w:
                        x = max(0, max_screen_w - target_w - 20)
                    if y + target_h > max_screen_h:
                        y = max(0, max_screen_h - target_h - 40)

                    SWP_NOZORDER = 0x0004
                    SWP_NOACTIVATE = 0x0010
                    user32.SetWindowPos(
                        hwnd_target,
                        0,
                        x,
                        y,
                        target_w,
                        target_h,
                        SWP_NOZORDER | SWP_NOACTIVATE,
                    )
                    # Warte kurz, bis Windows Terminal / ConPTY den neuen Buffer asynchron stabilisiert hat
                    for _ in range(4):
                        time.sleep(0.04)
                        updated = get_windows_console_window_size()
                        if updated and updated[0] >= target_cols:
                            break

        # Terminal-Titel auf 'Tasks' setzen
        if sys.platform == "win32":
            try:
                ctypes.windll.kernel32.SetConsoleTitleW("Tasks")
            except Exception:
                pass
        try:
            sys.stdout.write("\033]0;Tasks\007")
            sys.stdout.flush()
        except Exception:
            pass
    except Exception:
        pass


_CACHED_TERMINAL_HWND: Optional[int] = None


def get_terminal_window_hwnd() -> Optional[int]:
    """Finds the HWND of the console window or hosting terminal (e.g. Windows Terminal, ConHost)."""
    global _CACHED_TERMINAL_HWND
    if _CACHED_TERMINAL_HWND:
        try:
            if ctypes.windll.user32.IsWindow(_CACHED_TERMINAL_HWND):
                return _CACHED_TERMINAL_HWND
        except Exception:
            pass

    if sys.platform != "win32":
        return None

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Prüfe GetConsoleWindow()
        h_con_win = kernel32.GetConsoleWindow()
        if h_con_win:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h_con_win, buf, 256)
            if buf.value == "ConsoleWindowClass":
                _CACHED_TERMINAL_HWND = h_con_win
                return h_con_win
            GA_ROOT = 2
            h_root = user32.GetAncestor(h_con_win, GA_ROOT)
            if h_root:
                _CACHED_TERMINAL_HWND = h_root
                return h_root

        # 2. Prüfe Vordergrund-Fenster
        hwnd_fg = user32.GetForegroundWindow()
        if hwnd_fg:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd_fg, buf, 256)
            if buf.value in ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"):
                _CACHED_TERMINAL_HWND = hwnd_fg
                return hwnd_fg
            GA_ROOT = 2
            h_root = user32.GetAncestor(hwnd_fg, GA_ROOT)
            if h_root:
                user32.GetClassNameW(h_root, buf, 256)
                if buf.value in ("CASCADIA_HOSTING_WINDOW_CLASS", "ConsoleWindowClass"):
                    _CACHED_TERMINAL_HWND = h_root
                    return h_root

        # 3. Prozess-Hierarchie durchsuchen (findet Windows Terminal / Console zuverlässig)
        try:
            from ctypes import wintypes
            TH32CS_SNAPPROCESS = 0x00000002
            class PROCESSENTRY32(ctypes.Structure):
                _fields_ = [
                    ('dwSize', wintypes.DWORD),
                    ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long),
                    ('dwFlags', wintypes.DWORD),
                    ('szExeFile', ctypes.c_char * 260)
                ]
            hSnap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            pe = PROCESSENTRY32()
            pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
            parents = {}
            if kernel32.Process32First(hSnap, ctypes.byref(pe)):
                while True:
                    parents[pe.th32ProcessID] = pe.th32ParentProcessID
                    if not kernel32.Process32Next(hSnap, ctypes.byref(pe)):
                        break
            kernel32.CloseHandle(hSnap)

            chain = []
            curr = os.getpid()
            for _ in range(6):
                chain.append(curr)
                if curr in parents:
                    curr = parents[curr]
                else:
                    break

            found = []
            def enum_cb(h, _):
                p = wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                if p.value in chain:
                    b = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(h, b, 256)
                    if b.value in ('CASCADIA_HOSTING_WINDOW_CLASS', 'ConsoleWindowClass'):
                        found.append(h)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            if found:
                _CACHED_TERMINAL_HWND = found[0]
                return found[0]
        except Exception:
            pass

        if h_con_win:
            _CACHED_TERMINAL_HWND = h_con_win
            return h_con_win
        return None
    except Exception:
        return None



def is_app_window_foreground(app: Optional[App] = None, terminal_hwnd: Optional[int] = None) -> bool:
    """Checks whether the application's terminal window is currently focused / active."""
    # 1. Wenn Textual mitteilt, dass die App keinen Fokus hat (über VT FocusIn/FocusOut)
    if app is not None and hasattr(app, "app_focus") and not app.app_focus:
        return False

    if sys.platform != "win32":
        return True

    try:
        user32 = ctypes.windll.user32
        hwnd_fg = user32.GetForegroundWindow()
        if not hwnd_fg:
            return False

        # Wenn terminal_hwnd bekannt ist
        target_h = terminal_hwnd or get_terminal_window_hwnd()
        if target_h:
            if hwnd_fg == target_h:
                return True
            GA_ROOT = 2
            if user32.GetAncestor(hwnd_fg, GA_ROOT) == target_h:
                return True

        # Prüfe ob der Prozess des Vordergrundfensters direkt zu unserem Prozess gehört
        fg_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd_fg, ctypes.byref(fg_pid))
        if fg_pid.value == os.getpid():
            return True

        # Prüfe ConsoleProcessList
        kernel32 = ctypes.windll.kernel32
        p_list = (wintypes.DWORD * 32)()
        cnt = kernel32.GetConsoleProcessList(p_list, 32)
        if cnt > 0 and fg_pid.value in list(p_list)[:cnt]:
            return True

        return False
    except Exception:
        return True


FULL_WEEKDAYS = {
    "monday": 0, "montag": 0,
    "tuesday": 1, "dienstag": 1,
    "wednesday": 2, "mittwoch": 2,
    "thursday": 3, "donnerstag": 3,
    "friday": 4, "freitag": 4,
    "saturday": 5, "samstag": 5,
    "sunday": 6, "sonntag": 6,
}

ABBR_WEEKDAYS = {
    "mon": 0, "mo": 0,
    "tue": 1, "di": 1,
    "wed": 2, "mi": 2,
    "thu": 3, "do": 3,
    "fri": 4, "fr": 4,
    "sat": 5, "sa": 5,
    "sun": 6, "so": 6,
}


GERMAN_WEEKDAYS = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"
]


def format_german_weekday_date(dt: datetime.date, time_suffix: str = "") -> str:
    """Formats date as German Weekday, Day.Month.Year [HH:MM], e.g. 'Montag, 4.10.2026 08:00'."""
    wk = GERMAN_WEEKDAYS[dt.weekday()]
    date_part = f"{wk}, {dt.day}.{dt.month}.{dt.year}"
    clean_t = time_suffix.strip().lstrip(",").strip()
    return f"{date_part} {clean_t}" if clean_t else date_part


def resolve_natural_date_string(val: str, today: Optional[datetime.date] = None, allow_short_abbr: bool = False) -> str:
    """
    Replaces natural language expressions like 'Tomorrow', 'Tuesday', 'Dienstag',
    'Next Friday', 'Morgen', etc. OR numeric dates into the formatted string:
    'Montag, 4.10.2026' (or 'Montag, 4.10.2026 08:00' if time is provided).
    Preserves trailing time specifiers.
    """
    if not val:
        return val
    if today is None:
        today = datetime.date.today()

    val_s = val.strip()

    # If already formatted as German Weekday, Day.Month.Year [HH:MM]
    already_pattern = r"^(?:" + "|".join(GERMAN_WEEKDAYS) + r"),\s+\d{1,2}\.\d{1,2}\.\d{4}(?:\s+\d{1,2}:\d{2})?$"
    if re.match(already_pattern, val_s):
        return val_s

    # Extract time suffix if present:
    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", val_s)
    time_str = time_match.group(0) if time_match else ""

    # Check for numeric date (e.g. 4.10. or 4.10.2026 or 2026-10-04)
    has_numeric = bool(re.search(r"\b\d{1,2}\.\d{1,2}\.?(?:\d{2,4})?\b", val_s) or re.search(r"\b\d{4}-\d{2}-\d{2}\b", val_s))
    if has_numeric:
        # ISO format YYYY-MM-DD
        m_iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", val_s)
        if m_iso:
            try:
                dt = datetime.date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
                return format_german_weekday_date(dt, time_str)
            except Exception:
                pass

        # Full format DD.MM.YYYY or DD.MM.YY
        m_full = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", val_s)
        if m_full:
            y = int(m_full.group(3))
            if y < 100:
                y += 2000
            try:
                dt = datetime.date(y, int(m_full.group(2)), int(m_full.group(1)))
                return format_german_weekday_date(dt, time_str)
            except Exception:
                pass

        # Short format DD.MM. or DD.MM
        m_short = re.search(r"\b(\d{1,2})\.(\d{1,2})\.?(?!\d)", val_s)
        if m_short and (allow_short_abbr or val.endswith(" ") or time_str or val.strip().endswith(".")):
            try:
                d, m = int(m_short.group(1)), int(m_short.group(2))
                y = today.year
                cand = datetime.date(y, m, d)
                if (today - cand).days > 180:
                    cand = datetime.date(y + 1, m, d)
                return format_german_weekday_date(cand, time_str)
            except Exception:
                pass
        return val

    # Natural words (Tomorrow, Dienstag, Next Tuesday, etc.)
    pattern = r"^(?:(?:next|am|nächsten|naechsten)\s+)?([a-zA-ZäöüÄÖÜß]+)(.*)$"
    m = re.match(pattern, val_s, re.IGNORECASE)
    if not m:
        return val

    keyword = m.group(1).lower()
    suffix = m.group(2).strip()

    allow_abbr = allow_short_abbr or bool(suffix)
    target_date = None

    if keyword in ("tomorrow", "morgen"):
        target_date = today + datetime.timedelta(days=1)
    elif keyword in ("today", "heute"):
        target_date = today
    elif keyword in ("übermorgen", "uebermorgen"):
        target_date = today + datetime.timedelta(days=2)
    elif keyword in ("yesterday", "gestern"):
        target_date = today - datetime.timedelta(days=1)
    elif keyword in FULL_WEEKDAYS:
        target_wd = FULL_WEEKDAYS[keyword]
        days_ahead = (target_wd - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target_date = today + datetime.timedelta(days=days_ahead)
    elif allow_abbr and keyword in ABBR_WEEKDAYS:
        target_wd = ABBR_WEEKDAYS[keyword]
        days_ahead = (target_wd - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        target_date = today + datetime.timedelta(days=days_ahead)

    if target_date:
        return format_german_weekday_date(target_date, suffix)
    return val


def parse_flexible_date_input(val: str) -> Optional[tuple[str, str, int]]:
    """
    Parses flexible human-entered date strings into (YYYY-MM-DD, date_display, days_until).
    date_display is formatted as 'Montag, 4.10.2026'.
    Supports:
    - DD.MM.YYYY, DD.MM.YY, YYYY-MM-DD
    - DD.MM. or DD.MM (e.g. 5.10. or 5.10)
    - Formatted strings like 'Montag, 4.10.2026' or 'Montag, 4.10.2026 08:00'
    - 'tomorrow' / 'morgen', 'today' / 'heute', and all weekdays ('Tuesday', 'Dienstag', etc.)
    """
    val = val.strip()
    if not val:
        return None
    today = datetime.date.today()

    parsed_date = None

    # Check for ISO format
    m_iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", val)
    if m_iso:
        try:
            parsed_date = datetime.date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except Exception:
            pass

    # Check for DD.MM.YYYY or DD.MM.YY
    if not parsed_date:
        m_full = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b", val)
        if m_full:
            y = int(m_full.group(3))
            if y < 100:
                y += 2000
            try:
                parsed_date = datetime.date(y, int(m_full.group(2)), int(m_full.group(1)))
            except Exception:
                pass

    # Check for DD.MM. or DD.MM
    if not parsed_date:
        m_short = re.search(r"\b(\d{1,2})\.(\d{1,2})\.?(?!\d)", val)
        if m_short:
            try:
                d, m = int(m_short.group(1)), int(m_short.group(2))
                y = today.year
                cand = datetime.date(y, m, d)
                if (today - cand).days > 180:
                    cand = datetime.date(y + 1, m, d)
                parsed_date = cand
            except Exception:
                pass

    # Natural language fallback (Tomorrow, Tuesday, etc.)
    if not parsed_date:
        resolved = resolve_natural_date_string(val, allow_short_abbr=True)
        if resolved != val:
            return parse_flexible_date_input(resolved)

    if parsed_date:
        days_until = (parsed_date - today).days
        date_display = format_german_weekday_date(parsed_date)
        return parsed_date.strftime("%Y-%m-%d"), date_display, days_until
    return None


class AddTaskModal(ModalScreen[Optional[Task]]):
    """Dialog to manually add a new homework assignment with optional WebUntis autofill."""

    DEFAULT_CSS = """
    AddTaskModal {
        align: center middle;
    }
    #add_dialog {
        width: 65;
        max-height: 90%;
        height: auto;
        border: thick #a6e3a1;
        background: #1e1e2e;
        padding: 1 2;
    }
    #add_title {
        text-align: center;
        text-style: bold;
        color: #a6e3a1;
        margin-bottom: 1;
    }
    .add_label {
        color: #cdd6f4;
        text-style: bold;
        margin-top: 1;
    }
    .add_input {
        margin-bottom: 1;
        width: 100%;
    }
    #btn_add_autofill {
        width: 100%;
        margin-bottom: 1;
    }
    #add_status {
        color: #f38ba8;
        text-align: center;
        margin: 1 0;
        min-height: 1;
    }
    #add_buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #add_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.auto_group: str = _load_untis_group() or "X"
        self._lookup_counter: int = 0
        self._last_looked_up: Optional[tuple[str, str]] = None
        self._auto_filled_time: bool = False
        self._auto_filled_teacher: bool = False
        self._auto_filling: bool = False
        self._resolving_natural_date: bool = False
        self._autofill_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="add_dialog"):
            yield Label("➕ Add Homework / Task", id="add_title")
            with VerticalScroll():
                yield Label("Subject / Course:", classes="add_label")
                yield Input(placeholder="e.g. SWP, SWP PM, D, E, AMEC, NW2", id="inp_add_subject", classes="add_input")
                yield Label("Assignment Title:", classes="add_label")
                yield Input(placeholder="e.g. Exercise 4, Portfolio, Lab Report", id="inp_add_title", classes="add_input")
                yield Label("Due Date (DD.MM.YYYY or e.g. 5.10.):", classes="add_label")
                yield Input(placeholder="e.g. 5.10. or 24.10.2026 or Tomorrow", id="inp_add_due", classes="add_input")
                yield Button("🔍 Autofill from Untis Timetable", id="btn_add_autofill", variant="primary")
                yield Label("Due Time (optional):", classes="add_label")
                yield Input(placeholder="Auto-filled from Untis or e.g. 08:00 or 23:59", id="inp_add_time", classes="add_input")
                yield Label("Teacher (optional):", classes="add_label")
                yield Input(placeholder="Auto-filled from Untis or e.g. BIM, WAW", id="inp_add_teacher", classes="add_input")
                yield Label("Description (optional):", classes="add_label")
                yield ChatInputArea(placeholder="Optional details / instructions", id="inp_add_desc", classes="add_input")
                yield Label("", id="add_status")
            with Horizontal(id="add_buttons"):
                yield Button("💾 Save [Enter]", id="btn_add_save", variant="success")
                yield Button("↩️ Cancel [ESC]", id="btn_add_cancel", variant="default")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "inp_add_due" and not self._resolving_natural_date:
            resolved = resolve_natural_date_string(event.value, allow_short_abbr=False)
            if resolved != event.value:
                self._resolving_natural_date = True
                try:
                    event.input.value = resolved
                finally:
                    self._resolving_natural_date = False
                return

        if event.input.id in ["inp_add_subject", "inp_add_due"]:
            if getattr(self, "_autofill_timer", None) is not None:
                try:
                    self._autofill_timer.stop()
                except Exception:
                    pass
                self._autofill_timer = None
            try:
                self._autofill_timer = self.set_timer(1.0, lambda: self._trigger_untis_lookup(explicit=False))
            except Exception:
                pass
        elif event.input.id == "inp_add_time" and not self._auto_filling:
            self._auto_filled_time = False
        elif event.input.id == "inp_add_teacher" and not self._auto_filling:
            self._auto_filled_teacher = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_add_cancel":
            self.dismiss(None)
        elif event.button.id == "btn_add_save":
            self._save_task()
        elif event.button.id == "btn_add_autofill":
            if getattr(self, "_autofill_timer", None) is not None:
                try:
                    self._autofill_timer.stop()
                except Exception:
                    pass
                self._autofill_timer = None
            self._trigger_untis_lookup(explicit=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save_task()

    _parse_date_input = staticmethod(parse_flexible_date_input)

    def _trigger_untis_lookup(self, explicit: bool = False) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        try:
            subj = self.query_one("#inp_add_subject", Input).value.strip()
            date_raw = self.query_one("#inp_add_due", Input).value.strip()
        except Exception:
            return

        resolved_date = resolve_natural_date_string(date_raw, allow_short_abbr=True)
        if resolved_date != date_raw:
            self._resolving_natural_date = True
            try:
                self.query_one("#inp_add_due", Input).value = resolved_date
            finally:
                self._resolving_natural_date = False
            date_raw = resolved_date

        if not subj or not date_raw:
            if explicit:
                self.query_one("#add_status", Label).update("[yellow]Please enter Subject and Due Date first.[/yellow]")
            return

        parsed_date_info = self._parse_date_input(date_raw)
        if not parsed_date_info:
            if explicit:
                self.query_one("#add_status", Label).update("[red]Invalid date format! Use e.g. 5.10. or 24.10.2026[/red]")
            return

        date_iso, date_display, _ = parsed_date_info

        if (subj, date_iso) == self._last_looked_up and not explicit:
            return

        self._lookup_counter += 1
        current_req = self._lookup_counter

        if explicit:
            self.query_one("#add_status", Label).update("[yellow]Checking WebUntis timetable...[/yellow]")

        app = self.app

        def worker():
            data = lookup_untis_lesson_details(date_iso, subj, preferred_group=self.auto_group)
            if self._lookup_counter != current_req:
                return

            def update_ui():
                self._last_looked_up = (subj, date_iso)
                if data:
                    time_inp = self.query_one("#inp_add_time", Input)
                    teacher_inp = self.query_one("#inp_add_teacher", Input)
                    due_inp = self.query_one("#inp_add_due", Input)

                    lesson_time = data.get("start_time") or data.get("time_str") or ""
                    self._auto_filling = True
                    try:
                        if not time_inp.value or self._auto_filled_time:
                            time_inp.value = lesson_time
                            self._auto_filled_time = True
                        if not teacher_inp.value or self._auto_filled_teacher:
                            teacher_inp.value = data.get("teacher", "")
                            self._auto_filled_teacher = True

                        if lesson_time:
                            p_info = self._parse_date_input(due_inp.value or date_iso)
                            if p_info:
                                _, d_disp, _ = p_info
                                self._resolving_natural_date = True
                                try:
                                    due_inp.value = f"{d_disp} {lesson_time}"
                                finally:
                                    self._resolving_natural_date = False
                    finally:
                        self._auto_filling = False

                    if data.get("group"):
                        self.auto_group = data["group"]

                    self.query_one("#add_status", Label).update(
                        f"[green]✓ Untis: {lesson_time} | {data.get('teacher', '')}[/green]"
                    )
                    app.notify(
                        f"✓ Untis: {lesson_time} | {data.get('teacher', '')}",
                        severity="information",
                    )
                elif explicit:
                    self.query_one("#add_status", Label).update(
                        f"[yellow]No Untis lesson found for '{subj}' on {date_display}.[/yellow]"
                    )
            app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="UntisTaskAutofillWorker").start()

    def _save_task(self) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        subject = self.query_one("#inp_add_subject", Input).value.strip()
        title = self.query_one("#inp_add_title", Input).value.strip()
        due_raw = self.query_one("#inp_add_due", Input).value.strip()
        resolved_due = resolve_natural_date_string(due_raw, allow_short_abbr=True)
        if resolved_due != due_raw:
            self._resolving_natural_date = True
            try:
                self.query_one("#inp_add_due", Input).value = resolved_due
            finally:
                self._resolving_natural_date = False
        due_str = resolved_due
        time_str = self.query_one("#inp_add_time", Input).value.strip()
        teacher = self.query_one("#inp_add_teacher", Input).value.strip()
        desc = self.query_one("#inp_add_desc", Input).value.strip()

        if not subject or not title:
            self.query_one("#add_status", Label).update("[red]Please enter at least Subject and Assignment title.[/red]")
            return

        from config import normalize_subject_name, extract_teacher
        clean_subject = normalize_subject_name(subject)
        if not teacher:
            teacher = extract_teacher("", clean_subject, title, desc)
            if teacher == "-":
                teacher = ""

        # Time handling: if time_str exists and due_str doesn't already contain a time, combine them
        if time_str:
            has_time = bool(re.search(r"\b\d{1,2}:\d{2}\b", due_str))
            if not has_time and due_str:
                due_str = f"{due_str} {time_str}"
            elif not due_str:
                due_str = time_str

        if not due_str:
            due_str = "No deadline"

        from task_manager import parse_deadline_for_sorting
        due_ts = parse_deadline_for_sorting(due_str)

        task_id = f"manual_{int(time.time() * 1000)}"
        new_task = Task(
            id=task_id,
            platform="manual",
            course=clean_subject,
            course_full=subject,
            title=title,
            due_date_str=due_str,
            status="offen",
            status_display="Open",
            url="",
            teacher=teacher,
            description=desc,
            details_loaded=True,
            due_timestamp=due_ts,
        )
        self.dismiss(new_task)

    def action_cancel(self) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        self.dismiss(None)

    def key_escape(self) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        self.dismiss(None)


class StatusFilterModal(ModalScreen[Optional[str]]):
    """Selection dialog for status filter with clickable buttons."""

    DEFAULT_CSS = """
    StatusFilterModal {
        align: center middle;
    }
    #status_dialog {
        width: 52;
        height: auto;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
    }
    #status_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #89b4fa;
    }
    .status_btn {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="status_dialog"):
            yield Label("⚡ Select Status Filter", id="status_title")
            yield Button("🟢 Open only", id="btn_st_open", classes="status_btn", variant="success")
            yield Button("🔴 Overdue only", id="btn_st_overdue", classes="status_btn", variant="error")
            yield Button("⚪ Completed only", id="btn_st_completed", classes="status_btn", variant="default")
            yield Button("🔵 All assignments", id="btn_st_all", classes="status_btn", variant="primary")
            yield Button("↩️ Back [ESC]", id="btn_st_cancel", classes="status_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "btn_st_open": "open_only",
            "btn_st_overdue": "overdue",
            "btn_st_completed": "completed",
            "btn_st_all": "all",
            "btn_st_cancel": None,
        }
        self.dismiss(mapping.get(event.button.id))

    def key_escape(self) -> None:
        self.dismiss(None)


class PlatformFilterModal(ModalScreen[Optional[str]]):
    """Selection dialog for platform filter (Moodle, Teams, All, Manual)."""

    DEFAULT_CSS = """
    PlatformFilterModal {
        align: center middle;
    }
    #plat_dialog {
        width: 62;
        max-height: 90%;
        height: auto;
        border: thick #cba6f7;
        background: #1e1e2e;
        padding: 1 2;
    }
    #plat_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #cba6f7;
    }
    .plat_row {
        height: 3;
        margin-bottom: 1;
        align: center middle;
    }
    .plat_row Button {
        width: 1fr;
        margin: 0 1;
        min-width: 4;
    }
    #plat_cancel_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_all", "All Platforms", show=False),
        Binding("2", "choose_moodle", "Moodle", show=False),
        Binding("3", "choose_teams", "Teams", show=False),
        Binding("4", "choose_manual", "Manual", show=False),
        Binding("escape", "cancel", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="plat_dialog"):
            yield Label("🌐 Platform Filter", id="plat_title")
            with Horizontal(classes="plat_row"):
                yield Button("🌐 All", id="btn_plat_all", variant="primary", tooltip="All [1]")
                yield Button("🟧 Moodle", id="btn_plat_moodle", variant="warning", tooltip="Moodle [2]")
            with Horizontal(classes="plat_row"):
                yield Button("🟦 Teams", id="btn_plat_teams", variant="primary", tooltip="Teams [3]")
                yield Button("✏️ Manual", id="btn_plat_manual", variant="success", tooltip="Manual [4]")
            with Horizontal(id="plat_cancel_row"):
                yield Button("↩️ Back [ESC]", id="btn_plat_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        mapping = {
            "btn_plat_all": "all",
            "btn_plat_moodle": "moodle",
            "btn_plat_teams": "teams",
            "btn_plat_manual": "manual",
            "btn_plat_cancel": None,
        }
        self.dismiss(mapping.get(bid))

    def action_choose_all(self) -> None:
        self.dismiss("all")

    def action_choose_moodle(self) -> None:
        self.dismiss("moodle")

    def action_choose_teams(self) -> None:
        self.dismiss("teams")

    def action_choose_manual(self) -> None:
        self.dismiss("manual")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class TimeframeFilterModal(ModalScreen[Optional[str]]):
    """Selection dialog for max due date duration filter (1 Week, 2 Weeks, 4 Weeks, 8 Weeks, All)."""

    DEFAULT_CSS = """
    TimeframeFilterModal {
        align: center middle;
    }
    #tf_dialog {
        width: 56;
        height: auto;
        border: thick #a6e3a1;
        background: #1e1e2e;
        padding: 1 2;
    }
    #tf_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #a6e3a1;
    }
    .tf_btn {
        width: 100%;
        margin-bottom: 1;
    }
    #tf_cancel_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_1w", "1 Week", show=False),
        Binding("2", "choose_2w", "2 Weeks", show=False),
        Binding("3", "choose_4w", "4 Weeks", show=False),
        Binding("4", "choose_8w", "8 Weeks", show=False),
        Binding("5", "choose_all", "All", show=False),
        Binding("escape", "cancel", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="tf_dialog"):
            yield Label("⏳ Max Duration Until Due", id="tf_title")
            yield Button("🗓️ 1 Week", id="btn_tf_1w", classes="tf_btn", variant="primary", tooltip="1 Week [1]")
            yield Button("🗓️ 2 Weeks (Default)", id="btn_tf_2w", classes="tf_btn", variant="success", tooltip="2 Weeks [2]")
            yield Button("🗓️ 4 Weeks", id="btn_tf_4w", classes="tf_btn", variant="primary", tooltip="4 Weeks [3]")
            yield Button("🗓️ 8 Weeks", id="btn_tf_8w", classes="tf_btn", variant="primary", tooltip="8 Weeks [4]")
            yield Button("🌐 All (No Limit)", id="btn_tf_all", classes="tf_btn", variant="default", tooltip="All [5]")
            with Horizontal(id="tf_cancel_row"):
                yield Button("↩️ Back [ESC]", id="btn_tf_cancel", classes="tf_btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        mapping = {
            "btn_tf_1w": "1_week",
            "btn_tf_2w": "2_weeks",
            "btn_tf_4w": "4_weeks",
            "btn_tf_8w": "8_weeks",
            "btn_tf_all": "all",
            "btn_tf_cancel": None,
        }
        self.dismiss(mapping.get(bid))

    def action_choose_1w(self) -> None:
        self.dismiss("1_week")

    def action_choose_2w(self) -> None:
        self.dismiss("2_weeks")

    def action_choose_4w(self) -> None:
        self.dismiss("4_weeks")

    def action_choose_8w(self) -> None:
        self.dismiss("8_weeks")

    def action_choose_all(self) -> None:
        self.dismiss("all")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class FilterMenuModal(ModalScreen[Optional[str]]):
    """Unified filter hub for Status, Max. Dauer, Subject, and Platform."""

    DEFAULT_CSS = """
    FilterMenuModal {
        align: center middle;
    }
    #filter_dialog {
        width: 62;
        max-height: 90%;
        height: auto;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }
    #filter_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #89b4fa;
    }
    .filter_btn {
        width: 100%;
        margin-bottom: 1;
    }
    #filter_cancel_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_status", "Status", show=False),
        Binding("2", "choose_timeframe", "Duration", show=False),
        Binding("3", "choose_subject", "Subject", show=False),
        Binding("4", "choose_platform", "Platform", show=False),
        Binding("5", "choose_reset", "Reset", show=False),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        current_status: str = "open_only",
        current_subject: str = "all",
        current_platform: str = "all",
        current_timeframe: str = "2_weeks",
    ):
        super().__init__()
        self.current_status = current_status
        self.current_subject = current_subject
        self.current_platform = current_platform
        self.current_timeframe = current_timeframe

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="filter_dialog"):
            yield Label("🔍 Filter Menu", id="filter_title")
            st_disp = {
                "open_only": "Open only",
                "all": "All",
                "completed_only": "Completed",
                "overdue_only": "Overdue",
            }.get(self.current_status, self.current_status)
            plat_disp = {
                "all": "All",
                "moodle": "Moodle",
                "teams": "Teams",
                "manual": "Manual",
            }.get(self.current_platform, self.current_platform)
            subj_disp = "All" if self.current_subject == "all" else self.current_subject
            tf_disp = {
                "1_week": "1 Week",
                "2_weeks": "2 Weeks",
                "4_weeks": "4 Weeks",
                "8_weeks": "8 Weeks",
                "all": "All",
            }.get(self.current_timeframe, self.current_timeframe)

            yield Button(f"⚡ Status Filter: {st_disp}", id="btn_filter_status", classes="filter_btn", variant="primary", tooltip="Status Filter [1]")
            yield Button(f"⏳ Max Duration: {tf_disp}", id="btn_filter_timeframe", classes="filter_btn", variant="success", tooltip="Max Duration Filter [2]")
            yield Button(f"📚 Subject Filter: {subj_disp}", id="btn_filter_subject", classes="filter_btn", variant="warning", tooltip="Subject Filter [3]")
            yield Button(f"🌐 Platform Filter: {plat_disp}", id="btn_filter_platform", classes="filter_btn", variant="primary", tooltip="Platform Filter [4]")
            yield Button("🔄 Reset All Filters", id="btn_filter_reset", classes="filter_btn", variant="error", tooltip="Reset All [5]")
            with Horizontal(id="filter_cancel_row"):
                yield Button("↩️ Close [ESC]", id="btn_filter_close", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_filter_status":
            self.dismiss("status")
        elif bid == "btn_filter_timeframe":
            self.dismiss("timeframe")
        elif bid == "btn_filter_subject":
            self.dismiss("subject")
        elif bid == "btn_filter_platform":
            self.dismiss("platform")
        elif bid == "btn_filter_reset":
            self.dismiss("reset")
        elif bid == "btn_filter_close":
            self.dismiss(None)

    def action_choose_status(self) -> None:
        self.dismiss("status")

    def action_choose_timeframe(self) -> None:
        self.dismiss("timeframe")

    def action_choose_subject(self) -> None:
        self.dismiss("subject")

    def action_choose_platform(self) -> None:
        self.dismiss("platform")

    def action_choose_reset(self) -> None:
        self.dismiss("reset")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


HOTKEYS_CATALOG: list[tuple[str, str]] = [
    # Main Screen
    ("Add task", "A"),
    ("Tests & Exams", "E"),
    ("Open course / schoolbook", "Backspace / /"),
    ("Filter menu", "F"),
    ("Status filter", "S"),
    ("Platform filter", "P"),
    ("Max duration filter", "D"),
    ("Sync tasks", "R"),
    ("Absences menu", "U"),
    ("Hidden tasks", "G"),
    ("Login menu", "L"),
    ("Settings menu", "O"),
    ("Change theme", "T / Ctrl+P"),
    ("Open task", "1-9 / Enter"),
    ("Quit app", "Q"),
    # Task Details Modal
    ("Details: Browser", "O"),
    ("Details: Download", "D"),
    ("Details: Status", "E"),
    ("Details: Hide", "L"),
    ("Details: Restore", "W"),
    # Absences Screen
    ("Absences: Sync", "R"),
    ("Absences: Group", "G"),
    ("Absences: Excuse", "E"),
    # Excuse Letter Modal
    ("Excuse: Toggle", "Space"),
    ("Excuse: All", "A"),
    ("Excuse: Open", "O"),
    ("Excuse: Clear", "C"),
    ("Excuse: PDF", "P"),
    # Tests & Exams Screen
    ("Exams: Sync", "R"),
    ("Exams: Past", "V"),
    ("Exams: Browser", "O"),
    ("Exams: Save", "Ctrl+S"),
    # General
    ("Back / Close menu", "Esc / Mouse Back"),
]


class HotkeysProvider(Provider):
    """Provider for fuzzy searching all application hotkeys in the CommandPalette."""

    def _format_item(self, desc: str, key: str, width: int = 46) -> str:
        spaces = max(4, width - len(desc) - len(key))
        return f"{desc}{' ' * spaces}{key}"

    async def discover(self) -> Hits:
        for desc, key in HOTKEYS_CATALOG:
            line = self._format_item(desc, key)
            yield DiscoveryHit(
                display=line,
                command=lambda: None,
                text=f"{desc} {key}",
            )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for desc, key in HOTKEYS_CATALOG:
            full = f"{desc} {key}"
            score = matcher.match(full)
            if score > 0:
                line = self._format_item(desc, key)
                yield Hit(
                    score=score,
                    match_display=matcher.highlight(line),
                    command=lambda: None,
                    text=full,
                )


class UnifiedQuickOpenProvider(Provider):
    """Provider für das blitzschnelle Suchen und Öffnen von Moodle/Teams-Kursen und Schulbüchern (PDF/Web)."""

    @property
    def current_mode(self) -> str:
        """Ermittelt den aktuellen Modus der Palette ('courses', 'books' oder 'directories')."""
        try:
            if hasattr(self.app, "screen") and isinstance(self.app.screen, UnifiedCommandPalette):
                return getattr(self.app.screen, "active_mode", UnifiedCommandPalette.current_mode)
        except Exception:
            pass
        return getattr(UnifiedCommandPalette, "current_mode", "courses")

    async def discover(self) -> Hits:
        mode = self.current_mode
        if mode == "courses":
            yield DiscoveryHit(
                display="🔄 [b]Reload & sync courses[/b] (/r)",
                command=lambda: getattr(self.app, "action_reload_courses", lambda: None)(),
                text="/r reload courses sync refresh",
                help="Reloads all courses from Moodle & Teams and refreshes the list",
            )
            courses = load_all_course_links()
            for c in courses:
                p_name = c["platform"].capitalize()
                line = f"\\[{p_name}] {c['display_title']}"
                url = c["url"]
                name = c["display_title"]
                yield DiscoveryHit(
                    display=line,
                    command=lambda u=url, n=name: getattr(self.app, "open_course_url", lambda _u, _n: None)(u, n),
                    text=f"{c['platform']} {c['subject']} {c['display_title']}",
                    help=url,
                )
        elif mode == "books":
            # Schoolbooks mode
            try:
                from schoolbook_service import SchoolbookService
            except ImportError:
                from src.services.schoolbook_service import SchoolbookService

            yield DiscoveryHit(
                display="📂 [b]Link local PDF[/b] (/link)",
                command=lambda: getattr(self.app, "action_link_schoolbook_file", lambda: None)(),
                text="/link link local PDF select file Explorer",
                help="Opens file explorer to select a PDF schoolbook on your computer",
            )
            yield DiscoveryHit(
                display="🌐 [b]Link online book[/b] (/link <URL> or /url)",
                command=lambda: getattr(self.app, "prompt_add_schoolbook_url", lambda: None)(""),
                text="/link /url link online book web link URL website",
                help="Type '/link <URL>' or click here to link an online schoolbook",
            )
            yield DiscoveryHit(
                display="📥 [b]Download Digi4School book[/b] (/download)",
                command=lambda: getattr(self.app, "prompt_digi4school_download", lambda _c="": None)(""),
                text="/download /d4s /digi4school download Digi4School schoolbook pdf grabber",
                help="Type '/download' or '/download <access code>' to download a book from Digi4School as OCR PDF",
            )
            books = SchoolbookService.load_books()
            if not books:
                yield DiscoveryHit(
                    display="ℹ️ [dim]No schoolbooks linked yet. Type '/link' or '/download'.[/dim]",
                    command=lambda: getattr(self.app, "action_link_schoolbook_file", lambda: None)(),
                    text="/link /download",
                    help="Type /link for local file or /download for Digi4School book",
                )
            else:
                for b in books:
                    title = b.get("title", "Schoolbook")
                    b_type = b.get("type", "pdf")
                    path = b.get("path", "")
                    badge = "📕 [PDF]" if b_type == "pdf" else "🌐 [WEB]"
                    display = f"{badge} {title}"
                    yield DiscoveryHit(
                        display=display,
                        command=lambda item=b: getattr(self.app, "open_schoolbook", lambda _b: None)(item),
                        text=f"{title} {path} {b_type}",
                        help=path,
                    )
        else:
            # Directories mode
            try:
                from directory_service import DirectoryService
            except ImportError:
                from src.services.directory_service import DirectoryService

            yield DiscoveryHit(
                display="📂 [b]Link local folder[/b] (/link)",
                command=lambda: getattr(self.app, "action_link_directory", lambda: None)(),
                text="/link link local folder directory select folder Explorer",
                help="Opens folder picker to select a local directory on your computer",
            )
            dirs = DirectoryService.load_directories()
            if not dirs:
                yield DiscoveryHit(
                    display="ℹ️ [dim]No directories linked yet. Type '/link' to link a folder.[/dim]",
                    command=lambda: getattr(self.app, "action_link_directory", lambda: None)(),
                    text="/link",
                    help="Type /link to select and link a local folder",
                )
            else:
                for d in dirs:
                    title = d.get("title", "Directory")
                    path = d.get("path", "")
                    display = f"📁 [b]{title}[/b] [dim]({path})[/dim]"
                    yield DiscoveryHit(
                        display=display,
                        command=lambda item=d: getattr(self.app, "open_directory", lambda _d: None)(item),
                        text=f"{title} {path}",
                        help=path,
                    )

    async def search(self, query: str) -> Hits:
        mode = self.current_mode
        q_clean = query.strip()
        q_lower = q_clean.lower()

        if mode == "courses":
            is_reload = (
                q_lower in ("/r", "r", "/reload", "reload", "/refresh", "refresh", "/sync", "sync", "/")
                or q_lower.startswith("/r")
                or q_lower.startswith("/")
            )
            courses = load_all_course_links()

            if is_reload:
                yield Hit(
                    score=1.0,
                    match_display="🔄 [b]Reload & refresh courses now[/b] (/r)",
                    command=lambda: getattr(self.app, "action_reload_courses", lambda: None)(),
                    text="/r reload courses",
                    help="Press [Enter] to freshly load all Moodle & Teams courses from the server",
                )
                for idx, c in enumerate(courses):
                    p_name = c["platform"].capitalize()
                    line = f"\\[{p_name}] {c['display_title']}"
                    url = c["url"]
                    name = c["display_title"]
                    full = f"{c['display_badge']} {c['subject']} {c['display_title']}"
                    yield Hit(
                        score=0.95 - (idx * 0.001),
                        match_display=line,
                        command=lambda u=url, n=name: getattr(self.app, "open_course_url", lambda _u, _n: None)(u, n),
                        text=full,
                        help=url,
                    )
            else:
                matcher = self.matcher(query)
                for c in courses:
                    full = f"{c['display_badge']} {c['subject']} {c['display_title']}"
                    score = matcher.match(full)
                    if score > 0:
                        p_name = c["platform"].capitalize()
                        line = f"\\[{p_name}] {c['display_title']}"
                        url = c["url"]
                        name = c["display_title"]
                        yield Hit(
                            score=score,
                            match_display=matcher.highlight(line),
                            command=lambda u=url, n=name: getattr(self.app, "open_course_url", lambda _u, _n: None)(u, n),
                            text=full,
                            help=url,
                        )
        elif mode == "books":
            # Schoolbooks Mode
            try:
                from schoolbook_service import SchoolbookService
            except ImportError:
                from src.services.schoolbook_service import SchoolbookService

            is_link_cmd = q_lower.startswith("/link") or q_lower.startswith("/url") or q_lower == "link" or q_lower == "url"
            is_unlink_cmd = (
                q_lower in ("/unlink", "unlink", "/del", "del", "/delete", "delete", "/remove", "remove")
                or q_lower.startswith("/unlink")
                or q_lower.startswith("/delete")
            )
            is_download_cmd = (
                q_lower in ("/download", "download", "/d4s", "d4s", "/digi4school", "digi4school", "/digi", "digi")
                or q_lower.startswith("/download")
                or q_lower.startswith("/d4s")
                or q_lower.startswith("/digi4school")
                or q_lower.startswith("/digi ")
            )

            # Check if a URL was provided in query
            url_match = re.search(r"https?://\S+", q_clean, re.IGNORECASE)

            if url_match:
                url_found = url_match.group(0)
                yield Hit(
                    score=1.0,
                    match_display=f"🌐 [b]Link online book:[/b] [cyan]{url_found}[/cyan]",
                    command=lambda u=url_found: getattr(self.app, "prompt_add_schoolbook_url", lambda _u: None)(u),
                    text=f"/link {url_found}",
                    help="Press [Enter] to enter a title and save the link",
                )
            elif q_clean == "/":
                # List all commands if only "/" is entered
                yield Hit(
                    score=1.0,
                    match_display="📂 [b]Select local PDF in file explorer...[/b] (/link)",
                    command=lambda: getattr(self.app, "action_link_schoolbook_file", lambda: None)(),
                    text="/link select local PDF",
                    help="Opens file explorer to select a local PDF file",
                )
                yield Hit(
                    score=0.99,
                    match_display="🌐 [b]Add online book via web link...[/b] (/url)",
                    command=lambda: getattr(self.app, "prompt_add_schoolbook_url", lambda: None)(""),
                    text="/url add online book web link",
                    help="Opens a dialog to enter URL and title",
                )
                yield Hit(
                    score=0.985,
                    match_display="📥 [b]Download Digi4School book...[/b] (/download)",
                    command=lambda: getattr(self.app, "prompt_digi4school_download", lambda _c="": None)(""),
                    text="/download /d4s /digi4school download Digi4School book",
                    help="Downloads a digital schoolbook via 12-digit access code",
                )
                yield Hit(
                    score=0.98,
                    match_display="🗑️ [b]Delete schoolbook link...[/b] (/unlink)",
                    command=lambda: getattr(self.app, "action_prompt_unlink_schoolbook", lambda: None)(),
                    text="/unlink remove delete schoolbook",
                    help="Press [Enter] to show linked books for removal",
                )
                books = SchoolbookService.load_books()
                for idx, b in enumerate(books):
                    title = b.get("title", "")
                    path = b.get("path", "")
                    b_type = b.get("type", "pdf")
                    badge = "📕 [PDF]" if b_type == "pdf" else "🌐 [WEB]"
                    display = f"{badge} {title}"
                    yield Hit(
                        score=0.95 - (idx * 0.001),
                        match_display=display,
                        command=lambda item=b: getattr(self.app, "open_schoolbook", lambda _b: None)(item),
                        text=f"{title} {path} {b_type}",
                        help=path,
                    )
            elif is_download_cmd:
                code_candidate = ""
                parts = q_clean.split(maxsplit=1)
                if len(parts) > 1:
                    code_candidate = parts[1].strip()

                code_info = f" (Code: [cyan]{code_candidate}[/cyan])" if code_candidate else ""
                yield Hit(
                    score=1.0,
                    match_display=f"📥 [b]Download Digi4School book[/b]{code_info}",
                    command=lambda c=code_candidate: getattr(self.app, "prompt_digi4school_download", lambda _c="": None)(c),
                    text=q_clean,
                    help="Downloads the book with Tesseract OCR and table of contents to Downloads",
                )
            elif is_link_cmd:
                yield Hit(
                    score=1.0,
                    match_display="📂 [b]Select local PDF in file explorer...[/b] (/link)",
                    command=lambda: getattr(self.app, "action_link_schoolbook_file", lambda: None)(),
                    text="/link select local PDF",
                    help="Opens file explorer to select a local PDF file",
                )
                yield Hit(
                    score=0.99,
                    match_display="🌐 [b]Add online book via web link...[/b] (/url)",
                    command=lambda: getattr(self.app, "prompt_add_schoolbook_url", lambda: None)(""),
                    text="/url add online book web link",
                    help="Opens a dialog to enter URL and title",
                )

            if is_unlink_cmd:
                books = SchoolbookService.load_books()
                for idx, b in enumerate(books):
                    b_id = b.get("id")
                    title = b.get("title", "Schoolbook")
                    yield Hit(
                        score=0.98 - (idx * 0.001),
                        match_display=f"🗑️ [red]Delete:[/red] {title}",
                        command=lambda bid=b_id, t=title: getattr(self.app, "action_delete_schoolbook", lambda _id, _t: None)(bid, t),
                        text=f"/unlink {title}",
                        help=f"Press [Enter] to remove the link to '{title}'",
                    )
            elif not url_match and not is_download_cmd:
                # Normale Suche über Buchtitel und Pfad/URL
                matcher = self.matcher(query)
                books = SchoolbookService.load_books()
                for b in books:
                    title = b.get("title", "")
                    path = b.get("path", "")
                    b_type = b.get("type", "pdf")
                    full = f"{title} {os.path.basename(path)} {b_type}"
                    score = matcher.match(full)
                    if score > 0:
                        badge = "📕 [PDF]" if b_type == "pdf" else "🌐 [WEB]"
                        display = f"{badge} {title}"
                        yield Hit(
                            score=score,
                            match_display=matcher.highlight(display),
                            command=lambda item=b: getattr(self.app, "open_schoolbook", lambda _b: None)(item),
                            text=full,
                            help=path,
                        )
        else:
            # Directories Mode
            try:
                from directory_service import DirectoryService
            except ImportError:
                from src.services.directory_service import DirectoryService

            is_link_cmd = q_lower.startswith("/link") or q_lower == "link"
            is_unlink_cmd = (
                q_lower in ("/unlink", "unlink", "/del", "del", "/delete", "delete", "/remove", "remove")
                or q_lower.startswith("/unlink")
                or q_lower.startswith("/delete")
            )

            if q_clean == "/":
                yield Hit(
                    score=1.0,
                    match_display="📂 [b]Select local folder in file explorer...[/b] (/link)",
                    command=lambda: getattr(self.app, "action_link_directory", lambda: None)(),
                    text="/link select local folder directory",
                    help="Opens folder picker to select a local directory",
                )
                yield Hit(
                    score=0.98,
                    match_display="🗑️ [b]Delete directory link...[/b] (/unlink)",
                    command=lambda: getattr(self.app, "action_prompt_unlink_directory", lambda: None)(),
                    text="/unlink remove delete directory folder",
                    help="Press [Enter] to show linked directories for removal",
                )
                dirs = DirectoryService.load_directories()
                for idx, d in enumerate(dirs):
                    title = d.get("title", "")
                    path = d.get("path", "")
                    display = f"📁 [b]{title}[/b] [dim]({path})[/dim]"
                    yield Hit(
                        score=0.95 - (idx * 0.001),
                        match_display=display,
                        command=lambda item=d: getattr(self.app, "open_directory", lambda _d: None)(item),
                        text=f"{title} {path}",
                        help=path,
                    )
            elif is_link_cmd:
                yield Hit(
                    score=1.0,
                    match_display="📂 [b]Select local folder in file explorer...[/b] (/link)",
                    command=lambda: getattr(self.app, "action_link_directory", lambda: None)(),
                    text="/link select local folder directory",
                    help="Opens folder picker to select a local directory",
                )

            if is_unlink_cmd:
                dirs = DirectoryService.load_directories()
                for idx, d in enumerate(dirs):
                    d_id = d.get("id")
                    title = d.get("title", "Directory")
                    yield Hit(
                        score=0.98 - (idx * 0.001),
                        match_display=f"🗑️ [red]Delete:[/red] {title}",
                        command=lambda did=d_id, t=title: getattr(self.app, "action_delete_directory", lambda _id, _t: None)(did, t),
                        text=f"/unlink {title}",
                        help=f"Press [Enter] to remove the link to '{title}'",
                    )
            elif not is_link_cmd:
                matcher = self.matcher(query)
                dirs = DirectoryService.load_directories()
                for d in dirs:
                    title = d.get("title", "")
                    path = d.get("path", "")
                    full = f"{title} {os.path.basename(path)} {path}"
                    score = matcher.match(full)
                    if score > 0:
                        display = f"📁 [b]{title}[/b] [dim]({path})[/dim]"
                        yield Hit(
                            score=score,
                            match_display=matcher.highlight(display),
                            command=lambda item=d: getattr(self.app, "open_directory", lambda _d: None)(item),
                            text=full,
                            help=path,
                        )


# Rückwärtskompatibilität
CourseLinksProvider = UnifiedQuickOpenProvider


class UnifiedCommandInput(CommandInput):
    """CommandInput that closes the command palette when Backspace is pressed on an empty input."""

    def action_delete_left(self) -> None:
        if is_ctrl_pressed_win32():
            self.action_delete_left_word()
            return
        if not self.value:
            try:
                scr = self.screen
                if hasattr(scr, "_action_escape"):
                    scr._action_escape()
                elif hasattr(scr, "dismiss"):
                    scr.dismiss()
            except Exception:
                pass
            return
        super().action_delete_left()


UnifiedCommandInput._merged_bindings = UnifiedCommandInput._merge_bindings()


class UnifiedCommandPalette(CommandPalette):
    """
    Erweiterte Befehlspalette für schnelles Öffnen von Kursen, Schulbüchern und Verzeichnissen.
    Umschalten zwischen Kurse, Schulbücher und Verzeichnisse über die Tabulator-Taste (vorwärts),
    Shift+Tab (rückwärts) oder per Mausklick auf die Tab-Boxen.
    Zeigt die 3 Modi als Karussell an: [Vorheriger Tab] [AKTIVER TAB (Mitte)] [Nächster Tab].
    """

    current_mode: str = "courses"

    MODE_ORDER = ["courses", "books", "directories"]
    MODE_TITLES = {
        "courses": "Courses",
        "books": "Schoolbooks",
        "directories": "Directories",
    }

    DEFAULT_CSS = (
        CommandPalette.DEFAULT_CSS
        + "\n"
        + CommandPalette.DEFAULT_CSS.replace("CommandPalette", "UnifiedCommandPalette")
        + """
        UnifiedCommandPalette > Vertical {
            margin-top: 0;
        }
        UnifiedCommandPalette #--container {
            margin-top: 0;
        }
        UnifiedCommandPalette #palette-tabs-bar {
            visibility: visible;
            width: 100%;
            height: auto;
            align-horizontal: center;
            padding-top: 1;
            padding-bottom: 0;
        }
        UnifiedCommandPalette .palette-tab {
            visibility: visible;
            width: 18;
            height: 1;
            text-align: center;
            text-style: bold;
            margin: 0 1;
            background: #313244;
            color: #6c7086;
        }
        UnifiedCommandPalette .palette-tab:hover {
            color: #ffffff;
            background: #45475a;
        }
        UnifiedCommandPalette .palette-tab.-active-courses {
            background: #04a5e5;
            color: #ffffff;
        }
        UnifiedCommandPalette .palette-tab.-active-courses:hover {
            background: #04a5e5;
            color: #ffffff;
        }
        UnifiedCommandPalette .palette-tab.-active-books {
            background: #e64553;
            color: #ffffff;
        }
        UnifiedCommandPalette .palette-tab.-active-books:hover {
            background: #e64553;
            color: #ffffff;
        }
        UnifiedCommandPalette .palette-tab.-active-directories {
            background: #40a02b;
            color: #ffffff;
        }
        UnifiedCommandPalette .palette-tab.-active-directories:hover {
            background: #40a02b;
            color: #ffffff;
        }
        """
    )

    BINDINGS = [
        *CommandPalette.BINDINGS,
        Binding("tab", "switch_mode", "Nächster Tab", priority=True, show=False),
        Binding("shift+tab", "switch_mode_prev", "Vorheriger Tab", priority=True, show=False),
    ]

    def __init__(
        self,
        providers: list[type[Provider]] | None = None,
        placeholder: str = "",
        initial_mode: str = "courses",
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(providers=providers, placeholder=placeholder, id=id, classes=classes)
        self.active_mode = initial_mode
        UnifiedCommandPalette.current_mode = initial_mode

    def on_key(self, event: events.Key) -> None:
        if event.key == "backspace":
            try:
                inp = self.query_one(CommandInput)
                if not inp.value:
                    event.prevent_default()
                    event.stop()
                    self._action_escape()
            except Exception:
                pass

    def on_click(self, event: events.Click) -> None:
        if event.widget:
            w_id = getattr(event.widget, "id", None)
            if w_id == "palette-tab-courses":
                self._set_mode("courses")
                try:
                    self.query_one(CommandInput).focus()
                except Exception:
                    pass
            elif w_id == "palette-tab-books":
                self._set_mode("books")
                try:
                    self.query_one(CommandInput).focus()
                except Exception:
                    pass
            elif w_id == "palette-tab-directories":
                self._set_mode("directories")
                try:
                    self.query_one(CommandInput).focus()
                except Exception:
                    pass

    def _get_header_text(self) -> str:
        if self.active_mode == "courses":
            return "[bold cyan]Courses[/bold cyan]"
        elif self.active_mode == "books":
            return "[bold red]Schoolbooks[/bold red]"
        else:
            return "[bold green]Directories[/bold green]"

    def _get_placeholder(self) -> str:
        if self.active_mode == "courses":
            return "Search courses or /r to reload..."
        elif self.active_mode == "books":
            return "Search schoolbooks (/link, /url, /download)..."
        else:
            return "Search directories (/link, /unlink)..."

    def compose(self) -> ComposeResult:
        with Vertical(id="--container"):
            with Horizontal(id="palette-tabs-bar"):
                yield Static(
                    "Courses",
                    id="palette-tab-courses",
                    classes="palette-tab" + (" -active-courses" if self.active_mode == "courses" else ""),
                )
                yield Static(
                    "Schoolbooks",
                    id="palette-tab-books",
                    classes="palette-tab" + (" -active-books" if self.active_mode == "books" else ""),
                )
                yield Static(
                    "Directories",
                    id="palette-tab-directories",
                    classes="palette-tab" + (" -active-directories" if self.active_mode == "directories" else ""),
                )
            with Horizontal(id="--input"):
                yield SearchIcon()
                yield UnifiedCommandInput(placeholder=self._get_placeholder(), select_on_focus=False)
                if not self.run_on_select:
                    yield Button("▶")
            with Vertical(id="--results"):
                yield CommandList()
                yield LoadingIndicator()

    def _update_tabs(self) -> None:
        try:
            tab_courses = self.query_one("#palette-tab-courses", Static)
            tab_books = self.query_one("#palette-tab-books", Static)
            tab_dirs = self.query_one("#palette-tab-directories", Static)

            for tab in (tab_courses, tab_books, tab_dirs):
                tab.remove_class("-active-courses", "-active-books", "-active-directories")

            if self.active_mode == "courses":
                tab_courses.add_class("-active-courses")
            elif self.active_mode == "books":
                tab_books.add_class("-active-books")
            elif self.active_mode == "directories":
                tab_dirs.add_class("-active-directories")
        except Exception:
            pass

    def _update_header(self) -> None:
        self._update_tabs()

    def _set_mode(self, mode: str) -> None:
        self.active_mode = mode
        UnifiedCommandPalette.current_mode = self.active_mode
        self._update_tabs()

        try:
            inp = self.query_one(CommandInput)
            inp.placeholder = self._get_placeholder()
            self._cancel_gather_commands()
            self._stop_no_matches_countdown()
            self._gather_commands(inp.value)
        except Exception:
            pass

    def action_switch_mode(self) -> None:
        """Wechselt zum nächsten Modus (Courses -> Books -> Directories -> Courses), behält den eingegebenen Text und aktualisiert die Treffer."""
        idx = self.MODE_ORDER.index(self.active_mode) if self.active_mode in self.MODE_ORDER else 0
        next_mode = self.MODE_ORDER[(idx + 1) % len(self.MODE_ORDER)]
        self._set_mode(next_mode)

    def action_switch_mode_prev(self) -> None:
        """Wechselt zum vorherigen Modus (rückwärts), behält den eingegebenen Text und aktualisiert die Treffer."""
        idx = self.MODE_ORDER.index(self.active_mode) if self.active_mode in self.MODE_ORDER else 0
        prev_mode = self.MODE_ORDER[(idx - 1) % len(self.MODE_ORDER)]
        self._set_mode(prev_mode)


class SchoolbookUrlModal(ModalScreen[Optional[dict]]):
    """Eingabedialog für Online-Schulbücher (URL und Name)."""

    DEFAULT_CSS = """
    SchoolbookUrlModal {
        align: center middle;
    }
    #book_url_dialog {
        width: 65;
        height: auto;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
    }
    #book_url_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #89b4fa;
    }
    .book_input_label {
        color: #cdd6f4;
        margin-top: 1;
    }
    .book_input {
        width: 100%;
        margin-bottom: 1;
    }
    #book_url_btn_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #book_url_btn_row Button {
        margin: 0 1;
        min-width: 14;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, initial_url: str = "", initial_title: str = "") -> None:
        super().__init__()
        self.initial_url = initial_url
        self.initial_title = initial_title

    def compose(self) -> ComposeResult:
        with Vertical(id="book_url_dialog"):
            yield Label("🌐 Link Online Schoolbook", id="book_url_title")
            yield Label("Web Address (URL):", classes="book_input_label")
            yield Input(value=self.initial_url, placeholder="https://...", id="book_input_url", classes="book_input")
            yield Label("Book Title / Subject:", classes="book_input_label")
            yield Input(value=self.initial_title, placeholder="e.g. Trauner Digital English", id="book_input_name", classes="book_input")
            with Horizontal(id="book_url_btn_row"):
                yield Button("Save", variant="success", id="btn_save_book")
                yield Button("Cancel", variant="default", id="btn_cancel_book")

    def on_mount(self) -> None:
        if self.initial_url:
            self.query_one("#book_input_name", Input).focus()
        else:
            self.query_one("#book_input_url", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save_book":
            self._submit()
        elif event.button.id == "btn_cancel_book":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "book_input_url":
            self.query_one("#book_input_name", Input).focus()
        else:
            self._submit()

    def _submit(self) -> None:
        url = self.query_one("#book_input_url", Input).value.strip()
        title = self.query_one("#book_input_name", Input).value.strip()
        if not url:
            self.notify("Bitte gib eine gültige URL ein.", severity="warning")
            return
        if not title:
            try:
                parsed = urllib.parse.urlparse(url if url.startswith("http") else "https://" + url)
                title = parsed.netloc or "Online-Buch"
            except Exception:
                title = "Online-Buch"

        self.dismiss({"url": url, "title": title})


class Digi4SchoolDownloadModal(ModalScreen[Optional[dict]]):
    """Eingabedialog für Digi4School-Login und Zugangscode."""

    DEFAULT_CSS = """
    Digi4SchoolDownloadModal {
        align: center middle;
    }
    #digi_download_dialog {
        width: 68;
        height: auto;
        border: thick #f38ba8;
        background: #1e1e2e;
        padding: 1 2;
    }
    #digi_modal_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #f38ba8;
    }
    .digi_input_label {
        color: #cdd6f4;
        margin-top: 1;
    }
    .digi_input {
        width: 100%;
        margin-bottom: 1;
    }
    .digi_select {
        width: 100%;
        margin-bottom: 1;
    }
    #digi_download_btn_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #digi_download_btn_row Button {
        margin: 0 1;
        min-width: 16;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, initial_code: str = "", initial_email: str = "", initial_quality: str = "ultra") -> None:
        super().__init__()
        self.initial_code = initial_code.strip()
        self.initial_email = initial_email.strip()
        self.initial_quality = initial_quality.strip() if initial_quality else "ultra"

    def compose(self) -> ComposeResult:
        with Vertical(id="digi_download_dialog"):
            yield Label("📥 Download Digi4School Book", id="digi_modal_title")
            yield Label("Digi4School Email:", classes="digi_input_label")
            yield Input(value=self.initial_email, placeholder="your.email@example.com", id="digi_input_email", classes="digi_input")
            yield Label("Digi4School Password:", classes="digi_input_label")
            yield Input(placeholder="Password", password=True, id="digi_input_password", classes="digi_input")
            yield Label("12-Digit Book Access Code:", classes="digi_input_label")
            yield Input(value=self.initial_code, placeholder="e.g. 26s7dbu5qxvw", id="digi_input_code", classes="digi_input")
            yield Label("Render Quality:", classes="digi_input_label")
            yield Select(
                options=[
                    ("Ultra-HD (Scale 4.0x, ~600 DPI) [Sharpest]", "ultra"),
                    ("High-Res (Scale 3.0x, ~450 DPI) [Balanced]", "high"),
                    ("Standard (Scale 2.0x, ~300 DPI) [Fast]", "standard"),
                ],
                value=self.initial_quality,
                allow_blank=False,
                id="digi_select_quality",
                classes="digi_select",
            )
            with Horizontal(id="digi_download_btn_row"):
                yield Button("Next: Select Pages ➡️", variant="success", id="btn_start_digi_download")
                yield Button("Cancel", variant="default", id="btn_cancel_digi_download")

    def on_mount(self) -> None:
        self.query_one("#digi_input_email", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_start_digi_download":
            self._submit()
        elif event.button.id == "btn_cancel_digi_download":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "digi_input_email":
            self.query_one("#digi_input_password", Input).focus()
        elif event.input.id == "digi_input_password":
            self.query_one("#digi_input_code", Input).focus()
        elif event.input.id == "digi_input_code":
            self._submit()

    def _submit(self) -> None:
        try:
            from digi4school_service import find_tesseract
        except ImportError:
            from src.services.digi4school_service import find_tesseract

        email = self.query_one("#digi_input_email", Input).value.strip()
        password = self.query_one("#digi_input_password", Input).value.strip()
        code = self.query_one("#digi_input_code", Input).value.strip()
        quality_sel = self.query_one("#digi_select_quality", Select)
        quality = quality_sel.value if quality_sel.value != Select.NULL else "ultra"

        if not email:
            self.notify("Please enter your Digi4School email address.", severity="warning")
            return
        if not password:
            self.notify("Please enter your Digi4School password.", severity="warning")
            return
        if not code:
            self.notify("Please enter the 12-digit access code for the book.", severity="warning")
            return

        try:
            find_tesseract()
        except FileNotFoundError:
            self.notify(
                "⚠️ Tesseract OCR was not found!\n"
                "Please install via: winget install -e --id UB-Mannheim.TesseractOCR",
                severity="error",
                timeout=10,
            )
            return

        self.dismiss({"email": email, "password": password, "code": code, "quality": str(quality)})




class Digi4SchoolDetectModal(ModalScreen[Optional[dict]]):
    """Ladedialog für die automatische Erkennung der Gesamtseitenzahl und Buchmetadaten."""

    DEFAULT_CSS = """
    Digi4SchoolDetectModal {
        align: center middle;
    }
    #digi_detect_dialog {
        width: 68;
        height: auto;
        border: thick #f38ba8;
        background: #1e1e2e;
        padding: 1 2;
    }
    #digi_detect_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #f38ba8;
    }
    #digi_detect_status {
        text-align: center;
        color: #89b4fa;
        margin-top: 1;
        margin-bottom: 1;
    }
    #digi_detect_loading {
        align: center middle;
        height: auto;
        margin: 1 0;
    }
    #digi_detect_btn_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #digi_detect_btn_row Button {
        min-width: 16;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, email: str, password: str, code: str, quality: str = "ultra", pages: Optional[str] = None) -> None:
        super().__init__()
        self.email = email
        self.password = password
        self.code = code
        self.quality = quality
        self.pages = pages
        self._cancel_async_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="digi_detect_dialog"):
            yield Label("🔍 Digi4School Book Inspection", id="digi_detect_title")
            with Center(id="digi_detect_loading"):
                yield LoadingIndicator()
            yield Label("Connecting to Digi4School and detecting book pages...", id="digi_detect_status")
            with Horizontal(id="digi_detect_btn_row"):
                yield Button("Cancel", variant="error", id="btn_cancel_detect")

    def on_mount(self) -> None:
        threading.Thread(target=self._run_detect_thread, daemon=True).start()

    def action_cancel(self) -> None:
        if self._cancel_async_event and self._loop:
            self._loop.call_soon_threadsafe(self._cancel_async_event.set)
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel_detect":
            self.action_cancel()

    def _run_detect_thread(self) -> None:
        try:
            from digi4school_service import Digi4SchoolService
        except ImportError:
            from src.services.digi4school_service import Digi4SchoolService

        import asyncio
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._cancel_async_event = asyncio.Event()
            res = self._loop.run_until_complete(
                Digi4SchoolService.inspect_book(
                    email=self.email,
                    password=self.password,
                    code=self.code,
                    cancel_event=self._cancel_async_event,
                )
            )
            self.app.call_from_thread(self._on_success, res)
        except asyncio.CancelledError:
            self.app.call_from_thread(self.dismiss, None)
        except Exception as e:
            self.app.call_from_thread(self._on_error, str(e))

    def _on_success(self, res: dict) -> None:
        self.dismiss({
            "status": "ok",
            "email": self.email,
            "password": self.password,
            "code": self.code,
            "quality": self.quality,
            "title": res.get("title") or self.code,
            "total_pages": res.get("total_pages"),
        })

    def _on_error(self, err_msg: str) -> None:
        self.dismiss({
            "status": "error",
            "error": err_msg,
            "email": self.email,
            "password": self.password,
            "code": self.code,
            "quality": self.quality,
            "title": self.code,
            "total_pages": None,
        })


class Digi4SchoolPageRangeModal(ModalScreen[Optional[dict]]):
    """Menü zur interaktiven Auswahl des Seitenbereichs für den Digi4School-Buchdownload."""

    DEFAULT_CSS = """
    Digi4SchoolPageRangeModal {
        align: center middle;
    }
    #d4s_range_dialog {
        width: 76;
        height: auto;
        border: thick #f38ba8;
        background: #1e1e2e;
        padding: 1 2;
    }
    #d4s_range_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #f38ba8;
    }
    #d4s_book_info_box {
        background: #313244;
        border: solid #45475a;
        padding: 1;
        margin-bottom: 1;
        text-align: center;
    }
    #d4s_book_title_lbl {
        color: #cdd6f4;
        text-style: bold;
    }
    #d4s_book_code_lbl {
        color: #89b4fa;
        margin-top: 0;
    }
    #d4s_book_pages_lbl {
        color: #a6e3a1;
        margin-top: 0;
    }
    .warning {
        color: #f9e2af !important;
    }
    #d4s_inputs_row {
        height: auto;
        margin-top: 1;
    }
    .range_input_col {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    .range_input_label {
        color: #cdd6f4;
        margin-bottom: 0;
    }
    .range_num_input {
        width: 100%;
        margin-bottom: 1;
    }
    #range_quick_row {
        height: auto;
        align: center middle;
        margin-top: 0;
        margin-bottom: 1;
    }
    #range_quick_row Button {
        min-width: 16;
    }
    #d4s_range_btn_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #d4s_range_btn_row Button {
        margin: 0 1;
        min-width: 16;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        email: str,
        password: str,
        code: str,
        quality: str,
        title: str,
        total_pages: Optional[int] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.email = email
        self.password = password
        self.code = code
        self.quality = quality
        self.book_title = title
        self.detected_total = total_pages
        self.error_msg = error_msg
        self.max_pages = total_pages if (total_pages and total_pages > 0) else 100
        self.start_page = 1
        self.end_page = self.max_pages
        self._ignore_input_events = False

    def compose(self) -> ComposeResult:
        with Vertical(id="d4s_range_dialog"):
            yield Label("📖 Digi4School Page Range Selection", id="d4s_range_title")
            with Vertical(id="d4s_book_info_box"):
                yield Label(f"Book: {self.book_title}", id="d4s_book_title_lbl")
                yield Label(f"Code: {self.code}", id="d4s_book_code_lbl")
                if self.detected_total:
                    yield Label(f"✓ Detected Total Pages: {self.detected_total}", id="d4s_book_pages_lbl")
                else:
                    warning_text = "⚠️ Total pages could not be auto-detected. Please adjust range manually."
                    if self.error_msg:
                        warning_text += f" ({self.error_msg})"
                    yield Label(warning_text, id="d4s_book_pages_lbl", classes="warning")

            yield TwoThumbRangeSlider(
                min_val=1,
                max_val=self.max_pages,
                start_val=self.start_page,
                end_val=self.end_page,
                id="range_slider_widget",
            )

            with Horizontal(id="d4s_inputs_row"):
                with Vertical(classes="range_input_col"):
                    yield Label("From Page (Start):", classes="range_input_label")
                    yield Input(
                        value=str(self.start_page),
                        placeholder="1",
                        id="input_range_start",
                        classes="range_num_input",
                    )
                with Vertical(classes="range_input_col"):
                    yield Label("To Page (End):", classes="range_input_label")
                    yield Input(
                        value=str(self.end_page),
                        placeholder=str(self.max_pages),
                        id="input_range_end",
                        classes="range_num_input",
                    )

            with Horizontal(id="range_quick_row"):
                yield Button("All", variant="primary", id="btn_all_pages")

            with Horizontal(id="d4s_range_btn_row"):
                yield Button("Start Download", variant="success", id="btn_start_download_from_range")
                yield Button("Back", variant="default", id="btn_back_to_credentials")
                yield Button("Cancel", variant="error", id="btn_cancel_range")

    def on_mount(self) -> None:
        try:
            self.query_one("#range_slider_widget", TwoThumbRangeSlider).focus()
        except Exception:
            pass

    def on_two_thumb_range_slider_changed(self, message: TwoThumbRangeSlider.Changed) -> None:
        self.start_page = message.start
        self.end_page = message.end

        self._ignore_input_events = True
        try:
            inp_start = self.query_one("#input_range_start", Input)
            if inp_start.value != str(self.start_page):
                inp_start.value = str(self.start_page)

            inp_end = self.query_one("#input_range_end", Input)
            if inp_end.value != str(self.end_page):
                inp_end.value = str(self.end_page)
        finally:
            self._ignore_input_events = False

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._ignore_input_events:
            return
        inp_start = self.query_one("#input_range_start", Input)
        inp_end = self.query_one("#input_range_end", Input)
        try:
            s_val = int(inp_start.value.strip())
            e_val = int(inp_end.value.strip())
            if 1 <= s_val <= e_val <= self.max_pages:
                self.start_page = s_val
                self.end_page = e_val
                slider = self.query_one("#range_slider_widget", TwoThumbRangeSlider)
                slider.set_range(s_val, e_val, notify=False)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        slider = self.query_one("#range_slider_widget", TwoThumbRangeSlider)

        if btn_id == "btn_all_pages":
            self.start_page = 1
            self.end_page = self.max_pages
            slider.set_range(1, self.max_pages)
            inp_start = self.query_one("#input_range_start", Input)
            inp_end = self.query_one("#input_range_end", Input)
            self._ignore_input_events = True
            try:
                inp_start.value = "1"
                inp_end.value = str(self.max_pages)
            finally:
                self._ignore_input_events = False
        elif btn_id == "btn_start_download_from_range":
            self._submit_download()
        elif btn_id == "btn_back_to_credentials":
            self.dismiss({
                "action": "back",
                "code": self.code,
                "email": self.email,
                "quality": self.quality,
            })
        elif btn_id == "btn_cancel_range":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit_download(self) -> None:
        inp_start = self.query_one("#input_range_start", Input)
        inp_end = self.query_one("#input_range_end", Input)
        try:
            s = int(inp_start.value.strip())
            e = int(inp_end.value.strip())
        except ValueError:
            self.notify("Please enter valid page numbers.", severity="error")
            return

        if s < 1:
            self.notify("Start page must be at least 1.", severity="error")
            return
        if s > e:
            self.notify("Start page cannot be greater than end page.", severity="error")
            return
        if e > self.max_pages:
            self.notify(f"End page cannot exceed total pages ({self.max_pages}).", severity="error")
            return

        # Wenn der gesamte Buchumfang gewählt wurde, pages auf None belassen
        if self.detected_total and s == 1 and e == self.detected_total:
            pages_arg = None
        else:
            pages_arg = f"{s}-{e}"

        self.dismiss({
            "action": "download",
            "email": self.email,
            "password": self.password,
            "code": self.code,
            "quality": self.quality,
            "pages": pages_arg,
            "title": self.book_title,
        })


class Digi4SchoolProgressModal(ModalScreen[Optional[dict]]):
    """Fortschrittsdialog für den Digi4School Buch-Download mit Live-Fortschritt und Fehler 911 Warnung."""

    DEFAULT_CSS = """
    Digi4SchoolProgressModal {
        align: center middle;
    }
    #d4s_progress_dialog {
        width: 78;
        height: auto;
        border: thick #f38ba8;
        background: #1e1e2e;
        padding: 1 2;
    }
    #d4s_prog_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #f38ba8;
    }
    #d4s_warning_banner {
        color: #f38ba8;
        text-style: bold;
        text-align: center;
        background: #313244;
        padding: 1;
        margin-bottom: 1;
        border: solid #f38ba8;
    }
    #d4s_status_lbl {
        color: #89b4fa;
        text-style: bold;
        text-align: center;
        margin-top: 1;
    }
    #d4s_detail_lbl {
        color: #a6adc8;
        text-align: center;
        margin-bottom: 0;
    }
    #d4s_eta_lbl {
        color: #a6e3a1;
        text-style: bold;
        text-align: center;
        margin-top: 1;
        margin-bottom: 1;
    }
    #d4s_prog_btn_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #d4s_prog_btn_row Button {
        margin: 0 1;
        min-width: 16;
    }
    .hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel_or_close", "Schließen"),
    ]

    def __init__(self, email: str, password: str, code: str, quality: str = "ultra", pages: Optional[str] = None) -> None:
        super().__init__()
        self.email = email
        self.password = password
        self.code = code
        self.quality = quality
        self.pages = pages
        self.download_result: Optional[dict] = None
        self._cancel_async_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_running: bool = False
        self._start_time: float = time.time()
        self._phase_start: Optional[float] = None
        self._current_phase: str = ""

    def _format_time(self, seconds: float) -> str:
        """Formatiert Sekunden in lesbare Zeitangaben (z.B. '2m 15s' oder '45s')."""
        s = int(round(seconds))
        if s <= 0:
            return "0s"
        if s < 60:
            return f"{s}s"
        m = s // 60
        rem_s = s % 60
        if m < 60:
            return f"{m}m {rem_s:02d}s"
        h = m // 60
        rem_m = m % 60
        return f"{h}h {rem_m:02d}m"

    def compose(self) -> ComposeResult:
        with Vertical(id="d4s_progress_dialog"):
            yield Label("📥 Digi4School Book Download", id="d4s_prog_title")
            yield Label("⚠️ Do not open Digi4School in your browser during download!", id="d4s_warning_banner")
            yield ProgressBar(total=100, show_eta=False, show_percentage=True, id="d4s_pbar")
            quality_badge = f"[bold #f9e2af]{self.quality.upper()}[/]"
            pages_desc = f"Pages: [bold #89b4fa]{self.pages}[/]" if self.pages and self.pages != "all" else "Pages: [bold #89b4fa]All[/]"
            yield Label(f"Quality: {quality_badge} | {pages_desc} | Initializing download...", id="d4s_status_lbl")
            yield Label("Please wait...", id="d4s_detail_lbl")
            yield Label("⏳ Calculating remaining time...", id="d4s_eta_lbl")
            with Horizontal(id="d4s_prog_btn_row"):
                yield Button("Cancel", variant="error", id="btn_cancel_d4s")
                yield Button("Show in Downloads folder", variant="success", id="btn_open_folder_d4s", classes="hidden")
                yield Button("Close", variant="default", id="btn_close_d4s", classes="hidden")

    def on_mount(self) -> None:
        self._is_running = True
        self._start_time = time.time()
        threading.Thread(target=self._run_download_thread, daemon=True).start()

    def _run_download_thread(self) -> None:
        try:
            from digi4school_service import Digi4SchoolService
        except ImportError:
            from src.services.digi4school_service import Digi4SchoolService

        import asyncio
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._cancel_async_event = asyncio.Event()

            def progress_callback(phase: str, cur: int, tot: int, msg: str):
                self.app.call_from_thread(self._on_progress_update, phase, cur, tot, msg)

            res = self._loop.run_until_complete(
                Digi4SchoolService.download_book(
                    email=self.email,
                    password=self.password,
                    code=self.code,
                    quality=self.quality,
                    pages=self.pages,
                    progress_cb=progress_callback,
                    cancel_event=self._cancel_async_event,
                )
            )
            self._is_running = False
            self.app.call_from_thread(self._on_download_complete, res)
        except asyncio.CancelledError:
            self._is_running = False
            self.app.call_from_thread(self._on_download_cancelled)
        except Exception as e:
            self._is_running = False
            self.app.call_from_thread(self._on_download_error, str(e))
        finally:
            self._loop.close()

    def _on_progress_update(self, phase: str, cur: int, tot: int, msg: str) -> None:
        try:
            pbar = self.query_one("#d4s_pbar", ProgressBar)
            status_lbl = self.query_one("#d4s_status_lbl", Label)
            detail_lbl = self.query_one("#d4s_detail_lbl", Label)
            eta_lbl = self.query_one("#d4s_eta_lbl", Label)

            now = time.time()
            if phase != self._current_phase:
                self._current_phase = phase
                self._phase_start = now

            detail_lbl.update(msg)
            eta_str = ""

            if phase == "login":
                status_lbl.update("🔐 Logging into Digi4School...")
                pbar.update(total=100, progress=10)
                eta_str = "⏳ Estimated time remaining: ~1-2 min."
            elif phase == "resolving":
                status_lbl.update("🔍 Resolving e-book viewer...")
                pbar.update(total=100, progress=20)
                eta_str = "⏳ Estimated time remaining: Analyzing book structure..."
            elif phase == "pages":
                status_lbl.update(f"📄 Fetching pages ({cur}/{tot})...")
                pct = 20 + int((cur / max(1, tot)) * 40)
                pbar.update(total=100, progress=pct)

                if cur > 0 and tot > 0:
                    el = now - (self._phase_start or now)
                    rate = cur / max(0.001, el)
                    rem_sec = (tot - cur) / max(0.001, rate)
                    total_rem = rem_sec + (tot * 0.35)
                    eta_str = f"⏳ Estimated time remaining: ~{self._format_time(total_rem)} (Pages {cur}/{tot} | Elapsed: {self._format_time(now - self._start_time)})"
            elif phase == "ocr":
                status_lbl.update(f"⚙️ OCR text recognition ({cur}/{tot})...")
                pct = 60 + int((cur / max(1, tot)) * 30)
                pbar.update(total=100, progress=pct)

                if cur > 0 and tot > 0:
                    el = now - (self._phase_start or now)
                    rate = cur / max(0.001, el)
                    rem_sec = (tot - cur) / max(0.001, rate)
                    eta_str = f"⏳ Estimated time remaining: ~{self._format_time(rem_sec)} (OCR {cur}/{tot} | Elapsed: {self._format_time(now - self._start_time)})"
            elif phase == "toc":
                status_lbl.update("📑 Bookmarks & page numbers...")
                pbar.update(total=100, progress=95)
                eta_str = "⏳ Estimated time remaining: few seconds (table of contents)..."
            elif phase == "saving":
                status_lbl.update("💾 Saving PDF...")
                pbar.update(total=100, progress=98)
                eta_str = "⏳ Estimated time remaining: few seconds (writing PDF)..."
            elif phase == "finished":
                status_lbl.update("✓ Completed!")
                pbar.update(total=100, progress=100)
                eta_str = f"✨ Completed in {self._format_time(now - self._start_time)}"

            if eta_str:
                eta_lbl.update(eta_str)
        except Exception:
            pass

    def _on_download_complete(self, result: dict) -> None:
        self.download_result = result
        try:
            total_duration = self._format_time(time.time() - self._start_time)
            self.query_one("#d4s_prog_title", Label).update("✅ [bold green]Download successful![/bold green]")
            self.query_one("#d4s_status_lbl", Label).update(f"Saved: {result.get('title')}")
            self.query_one("#d4s_detail_lbl", Label).update(
                f"Path: {result.get('path')}\n"
                f"Pages: {result.get('pages')} | Size: {result.get('size_mb')} MB"
            )
            self.query_one("#d4s_eta_lbl", Label).update(f"✨ Total Duration: {total_duration}")
            self.query_one("#d4s_warning_banner", Label).update("[dim]Download completed. Saved to Downloads.[/dim]")

            self.query_one("#btn_cancel_d4s", Button).add_class("hidden")
            self.query_one("#btn_open_folder_d4s", Button).remove_class("hidden")
            self.query_one("#btn_close_d4s", Button).remove_class("hidden")
            self.notify(f"✓ Schoolbook '{result.get('title')}' downloaded!", severity="information", timeout=6)
        except Exception:
            pass

    def _on_download_cancelled(self) -> None:
        try:
            self.query_one("#d4s_prog_title", Label).update("⏹️ [bold yellow]Download Cancelled[/bold yellow]")
            self.query_one("#d4s_status_lbl", Label).update("The download was cancelled by the user.")
            self.query_one("#d4s_detail_lbl", Label).update("No complete PDF was generated.")
            self.query_one("#btn_cancel_d4s", Button).add_class("hidden")
            self.query_one("#btn_close_d4s", Button).remove_class("hidden")
            self.notify("Download cancelled.", severity="warning")
        except Exception:
            pass

    def _on_download_error(self, err_msg: str) -> None:
        try:
            self.query_one("#d4s_prog_title", Label).update("❌ [bold red]Download Error[/bold red]")
            self.query_one("#d4s_status_lbl", Label).update("The operation could not be completed.")
            self.query_one("#d4s_detail_lbl", Label).update(f"[red]{err_msg}[/red]")
            self.query_one("#btn_cancel_d4s", Button).add_class("hidden")
            self.query_one("#btn_close_d4s", Button).remove_class("hidden")
            self.notify(f"Error: {err_msg}", severity="error", timeout=8)
        except Exception:
            pass

    def _cancel_download(self) -> None:
        if self._is_running and self._cancel_async_event and self._loop:
            try:
                self.query_one("#d4s_status_lbl", Label).update("Cancelling download...")
                self._loop.call_soon_threadsafe(self._cancel_async_event.set)
            except Exception:
                self.dismiss(None)
        else:
            self.dismiss(self.download_result)

    def action_cancel_or_close(self) -> None:
        if self._is_running:
            self._cancel_download()
        else:
            self.dismiss(self.download_result)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cancel_d4s":
            self._cancel_download()
        elif event.button.id == "btn_close_d4s":
            self.dismiss(self.download_result)
        elif event.button.id == "btn_open_folder_d4s":
            try:
                from digi4school_service import Digi4SchoolService
            except ImportError:
                from src.services.digi4school_service import Digi4SchoolService

            downloads_dir = Digi4SchoolService.get_default_downloads_dir()
            try:
                if sys.platform == "win32":
                    os.startfile(downloads_dir)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", downloads_dir])
            except Exception:
                pass
            self.dismiss(self.download_result)


class UpdateReminderModal(ModalScreen[None]):
    """Modal dialog notifying the user about a newer GitHub release with 1-click auto-update."""

    DEFAULT_CSS = """
    UpdateReminderModal {
        align: center middle;
    }
    #update_dialog {
        width: 70;
        max-height: 85%;
        height: auto;
        border: thick #a6e3a1;
        background: #1e1e2e;
        padding: 1 2;
    }
    #update_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #a6e3a1;
    }
    #update_info_box {
        width: 100%;
        height: auto;
        border: solid #45475a;
        background: #181825;
        padding: 1 2;
        margin-bottom: 1;
    }
    .update_version_line {
        margin-bottom: 0;
    }
    #update_hint {
        width: 100%;
        text-align: center;
        margin-bottom: 1;
        color: #cdd6f4;
    }
    #update_progress_box {
        width: 100%;
        height: auto;
        border: solid #45475a;
        background: #181825;
        padding: 1 2;
        margin-bottom: 1;
        display: none;
    }
    #update_pbar {
        width: 100%;
        margin-bottom: 1;
    }
    #update_status_lbl {
        text-align: center;
        color: #89b4fa;
        text-style: bold;
        margin-bottom: 0;
    }
    #update_error_box {
        width: 100%;
        height: auto;
        border: solid #f38ba8;
        background: #181825;
        padding: 1 2;
        margin-bottom: 1;
        display: none;
    }
    #update_error_lbl {
        color: #f38ba8;
        text-align: center;
        text-style: bold;
    }
    #update_buttons_container, #update_error_buttons_container {
        height: auto;
        width: 100%;
        margin-top: 1;
    }
    .update_buttons_row {
        height: auto;
        width: 100%;
        align: center middle;
    }
    .update_secondary_row {
        margin-top: 1;
    }
    #update_download_buttons_row {
        height: auto;
        width: 100%;
        align: center middle;
        margin-top: 1;
        display: none;
    }
    #update_error_buttons_container {
        display: none;
    }
    .update_btn {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Dismiss"),
    ]

    def __init__(self, update_info: Dict[str, Any]) -> None:
        super().__init__()
        self.update_info = update_info
        self._cancel_event: Optional[threading.Event] = None
        self._is_downloading: bool = False

    def compose(self) -> ComposeResult:
        cur_v = self.update_info.get("current_version", APP_VERSION)
        lat_v = self.update_info.get("latest_version", "")
        rel_name = self.update_info.get("name") or f"v{lat_v}"

        with Vertical(id="update_dialog"):
            yield Label("🚀 New Version Available!", id="update_title")
            with Vertical(id="update_info_box"):
                yield Label(f"Current Version: [bold white]v{cur_v}[/]", classes="update_version_line")
                yield Label(f"Latest Version:   [bold #a6e3a1]v{lat_v}[/] ({escape(rel_name)})", classes="update_version_line")

            yield Label("A newer release with improvements and bug fixes is available on GitHub.", id="update_hint")

            with Vertical(id="update_progress_box"):
                yield ProgressBar(total=100, show_eta=False, show_percentage=True, id="update_pbar")
                yield Label("Initializing download...", id="update_status_lbl")

            with Vertical(id="update_error_box"):
                yield Label("", id="update_error_lbl")

            with Vertical(id="update_buttons_container"):
                with Horizontal(classes="update_buttons_row"):
                    yield Button("⬇️ Install Update Now", id="btn_update_install", variant="success", classes="update_btn")
                    yield Button("🌐 View in Browser", id="btn_update_open", variant="default", classes="update_btn")
                with Horizontal(classes="update_buttons_row update_secondary_row"):
                    yield Button(r"Later \[ESC]", id="btn_update_dismiss", variant="default", classes="update_btn")

            with Horizontal(id="update_download_buttons_row"):
                yield Button("❌ Cancel", id="btn_update_cancel", variant="error", classes="update_btn")

            with Vertical(id="update_error_buttons_container"):
                with Horizontal(classes="update_buttons_row"):
                    yield Button("🔄 Try Again", id="btn_update_retry", variant="primary", classes="update_btn")
                    yield Button("🌐 Download in Browser", id="btn_update_fallback", variant="success", classes="update_btn")
                with Horizontal(classes="update_buttons_row update_secondary_row"):
                    yield Button(r"Close \[ESC]", id="btn_update_error_close", variant="default", classes="update_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid in ("btn_update_install", "btn_update_retry"):
            self.action_start_install()
        elif bid in ("btn_update_open", "btn_update_fallback"):
            self.action_open_release()
        elif bid == "btn_update_cancel":
            self.action_cancel_download()
        elif bid in ("btn_update_dismiss", "btn_update_error_close"):
            self.action_dismiss_modal()

    def action_start_install(self) -> None:
        if self._is_downloading:
            return

        installer_url = self.update_info.get("installer_url")
        if not installer_url:
            self._show_error(
                "No installer package (.exe) found in this release.\n"
                "Please download the update manually from your browser."
            )
            return

        # UI in Download-Zustand versetzen
        try:
            self.query_one("#update_hint", Label).styles.display = "none"
            self.query_one("#update_error_box", Vertical).styles.display = "none"
            self.query_one("#update_progress_box", Vertical).styles.display = "block"
            self.query_one("#update_buttons_container", Vertical).styles.display = "none"
            self.query_one("#update_download_buttons_row", Horizontal).styles.display = "block"
            self.query_one("#update_error_buttons_container", Vertical).styles.display = "none"

            pbar = self.query_one("#update_pbar", ProgressBar)
            pbar.update(progress=0, total=100)
            self.query_one("#update_status_lbl", Label).update("Connecting to GitHub...")
        except Exception:
            pass

        self._is_downloading = True
        self._cancel_event = threading.Event()
        threading.Thread(target=self._download_worker, args=(installer_url,), daemon=True).start()

    def _download_worker(self, installer_url: str) -> None:
        try:
            app = self.app
        except Exception:
            return

        filename = self.update_info.get("installer_name") or "Tasks_Setup.exe"
        target_path = os.path.join(get_update_temp_dir(), filename)

        def progress_cb(cur: int, tot: int, pct: float) -> None:
            try:
                app.call_from_thread(self._on_download_progress, cur, tot, pct)
            except Exception:
                pass

        success = download_update_installer(
            download_url=installer_url,
            target_path=target_path,
            progress_callback=progress_cb,
            cancel_event=self._cancel_event,
        )

        try:
            if self._cancel_event and self._cancel_event.is_set():
                app.call_from_thread(self._on_download_cancelled)
            elif success:
                app.call_from_thread(self._on_download_success, target_path)
            else:
                app.call_from_thread(
                    self._on_download_error,
                    "Download failed. Please check your internet connection."
                )
        except Exception:
            pass

    def _on_download_progress(self, cur: int, tot: int, pct: float) -> None:
        try:
            pbar = self.query_one("#update_pbar", ProgressBar)
            pbar.update(progress=pct, total=100)
            cur_mb = cur / (1024 * 1024)
            tot_mb = tot / (1024 * 1024)
            status_lbl = self.query_one("#update_status_lbl", Label)
            if tot > 0:
                status_lbl.update(f"Downloading: {cur_mb:.1f} MB / {tot_mb:.1f} MB ({pct:.0f}%)")
            else:
                status_lbl.update(f"Downloading: {cur_mb:.1f} MB")
        except Exception:
            pass

    def _on_download_cancelled(self) -> None:
        self._is_downloading = False
        try:
            self.query_one("#update_progress_box", Vertical).styles.display = "none"
            self.query_one("#update_download_buttons_row", Horizontal).styles.display = "none"
            self.query_one("#update_hint", Label).styles.display = "block"
            self.query_one("#update_buttons_container", Vertical).styles.display = "block"
        except Exception:
            pass

    def _on_download_error(self, err_msg: str) -> None:
        self._is_downloading = False
        self._show_error(err_msg)

    def _show_error(self, err_msg: str) -> None:
        try:
            self.query_one("#update_progress_box", Vertical).styles.display = "none"
            self.query_one("#update_download_buttons_row", Horizontal).styles.display = "none"
            self.query_one("#update_buttons_container", Vertical).styles.display = "none"
            self.query_one("#update_hint", Label).styles.display = "none"

            err_lbl = self.query_one("#update_error_lbl", Label)
            err_lbl.update(f"⚠️ {err_msg}")
            self.query_one("#update_error_box", Vertical).styles.display = "block"
            self.query_one("#update_error_buttons_container", Vertical).styles.display = "block"
        except Exception:
            pass

    def _on_download_success(self, target_path: str) -> None:
        self._is_downloading = False
        try:
            pbar = self.query_one("#update_pbar", ProgressBar)
            pbar.update(progress=100, total=100)
            status_lbl = self.query_one("#update_status_lbl", Label)
            status_lbl.update("[bold #a6e3a1]✓ Download complete! Preparing installation...[/]")
            self.query_one("#update_download_buttons_row", Horizontal).styles.display = "none"
        except Exception:
            pass

        # Installer im Hintergrund starten und Anwendung beenden
        launched = launch_update_and_restart(target_path, WORKSPACE_DIR)
        if launched:
            # Kurzer visueller Übergang vor dem Schließen
            self.set_timer(1.2, lambda: self.app.exit(return_code=42))
        else:
            self._show_error("Update runner could not be started. Please run the installer manually.")

    def action_cancel_download(self) -> None:
        if self._cancel_event:
            self._cancel_event.set()

    def action_open_release(self) -> None:
        url = self.update_info.get("html_url")
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        self.dismiss()

    def action_dismiss_modal(self) -> None:
        if self._is_downloading:
            self.action_cancel_download()
        self.dismiss()

    def key_escape(self) -> None:
        self.action_dismiss_modal()


class SettingsModal(ModalScreen[Optional[str]]):
    """Settings dialog for themes, account logins, hidden tasks, and preferences."""

    DEFAULT_CSS = """
    SettingsModal {
        align: center middle;
    }
    #settings_dialog {
        width: 62;
        max-height: 96%;
        height: auto;
        border: thick #b4befe;
        background: #1e1e2e;
        padding: 1 2;
    }
    #settings_header_row {
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }
    #settings_title {
        width: 1fr;
        text-align: center;
        text-style: bold;
        color: #b4befe;
    }
    #settings_version_tag {
        dock: right;
        color: #ffffff;
        text-style: bold;
    }
    .settings_row {
        width: 100%;
        height: 3;
        margin-bottom: 1;
    }
    .settings_btn {
        width: 1fr;
        margin-right: 1;
    }
    .settings_btn:last-child {
        margin-right: 0;
    }
    .settings_btn_full {
        width: 100%;
        margin-right: 0;
    }
    #settings_cancel_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_theme", "Theme", show=False),
        Binding("2", "choose_login", "Login", show=False),
        Binding("3", "choose_hidden", "Hidden", show=False),
        Binding("4", "choose_school_config", "School Config", show=False),
        Binding("5", "choose_hotkeys", "Hotkeys", show=False),
        Binding("6", "choose_hotkeys", "Hotkeys", show=False),
        Binding("h", "choose_hotkeys", "Hotkeys", show=False),
        Binding("7", "choose_ai_explain", "AI Explain", show=False),
        Binding("a", "choose_ai_explain", "AI Explain", show=False),
        Binding("8", "choose_tray", "Tray & Autostart", show=False),
        Binding("t", "choose_tray", "Tray & Autostart", show=False),
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings_dialog"):
            with Horizontal(id="settings_header_row"):
                yield Label("⚙️ Settings", id="settings_title")
                yield Label(f"v{APP_VERSION}", id="settings_version_tag")
            with Horizontal(classes="settings_row"):
                yield Button("🎨 Change Theme", id="btn_set_theme", classes="settings_btn", variant="primary", tooltip="Theme [1]")
                yield Button("🔑 Login", id="btn_set_login", classes="settings_btn", variant="warning", tooltip="Login [2]")
            with Horizontal(classes="settings_row"):
                yield Button("👁️ Hidden", id="btn_set_hidden", classes="settings_btn", variant="error", tooltip="Hidden [3]")
                yield Button("⚙️ School Config", id="btn_set_school_config", classes="settings_btn", variant="primary", tooltip="School & Student Config [4]")
            with Horizontal(classes="settings_row"):
                yield Button("⌨️ Hotkeys", id="btn_set_hotkeys", classes="settings_btn", variant="default", tooltip="Hotkeys [5/6]")
                yield Button("🤖 AI Explain", id="btn_set_ai_explain", classes="settings_btn", variant="primary", tooltip="AI Explain [7/A]")
            with Horizontal(classes="settings_row"):
                yield Button("🖥️ System Tray & Autostart", id="btn_set_tray", classes="settings_btn settings_btn_full", variant="default", tooltip="Tray & Autostart [8/T]")
            with Horizontal(id="settings_cancel_row"):
                yield Button("↩️ Close [ESC]", id="btn_set_cancel", variant="default")


    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_set_theme":
            self.dismiss("change_theme")
        elif bid == "btn_set_login":
            self.dismiss("login_menu")
        elif bid == "btn_set_hidden":
            self.dismiss("show_trash")
        elif bid in ("btn_set_school_config", "btn_set_excuse_profile", "btn_set_group"):
            self.dismiss("school_config")
        elif bid == "btn_set_hotkeys":
            self.dismiss("show_hotkeys")
        elif bid in ("btn_set_ai_config", "btn_set_ai_explain"):
            self.dismiss("ai_config_menu")
        elif bid == "btn_set_tray":
            self.dismiss("tray_config")
        elif bid == "btn_set_cancel":
            self.dismiss(None)

    def action_choose_theme(self) -> None:
        self.dismiss("change_theme")

    def action_choose_login(self) -> None:
        self.dismiss("login_menu")

    def action_choose_hidden(self) -> None:
        self.dismiss("show_trash")

    def action_choose_school_config(self) -> None:
        self.dismiss("school_config")

    def action_choose_group(self) -> None:
        self.dismiss("school_config")

    def action_choose_excuse_profile(self) -> None:
        self.dismiss("school_config")

    def action_choose_hotkeys(self) -> None:
        self.dismiss("show_hotkeys")

    def action_choose_ai_explain(self) -> None:
        self.dismiss("ai_config_menu")

    def action_choose_tray(self) -> None:
        self.dismiss("tray_config")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class TrayConfigModal(ModalScreen[bool]):
    """Dialog for configuring system tray and Windows autostart behavior."""

    DEFAULT_CSS = """
    TrayConfigModal {
        align: center middle;
    }
    #tray_config_dialog {
        width: 76;
        height: auto;
        border: thick #b4befe;
        background: #1e1e2e;
        padding: 1 2;
    }
    #tray_cfg_title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: #b4befe;
        margin-bottom: 1;
    }
    .tray_cfg_desc {
        color: #a6adc8;
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    .tray_toggle_btn {
        width: 100%;
        margin-top: 1;
        margin-bottom: 0;
        text-style: bold;
    }
    #tray_cfg_btn_row {
        width: 100%;
        height: auto;
        align: center middle;
        margin-top: 2;
    }
    #btn_tray_cfg_save {
        margin-right: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.is_tray = True
        try:
            from config import is_minimize_to_tray_enabled
            self.is_tray = is_minimize_to_tray_enabled()
        except Exception:
            try:
                from src.core.config import is_minimize_to_tray_enabled
                self.is_tray = is_minimize_to_tray_enabled()
            except Exception:
                pass

        self.is_auto = False
        try:
            from autostart_service import is_autostart_enabled
            self.is_auto = is_autostart_enabled()
        except Exception:
            try:
                from src.services.autostart_service import is_autostart_enabled
                self.is_auto = is_autostart_enabled()
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        with Vertical(id="tray_config_dialog"):
            yield Label("🖥️ System Tray & Autostart Settings", id="tray_cfg_title")
            yield Label(
                "Configure resident background behavior and startup on Windows boot.",
                classes="tray_cfg_desc",
            )

            yield Button(
                "🖥️ Minimize to System Tray on Close",
                id="btn_tray_toggle",
                variant="success" if self.is_tray else "default",
                classes="tray_toggle_btn",
            )
            yield Label(
                "  Keep app resident in memory for instant startup on close.",
                classes="tray_cfg_desc",
            )

            yield Button(
                "🚀 Windows Autostart",
                id="btn_auto_toggle",
                variant="success" if self.is_auto else "default",
                classes="tray_toggle_btn",
            )
            yield Label(
                "  Launches Tasks silently in the system tray when Windows boots.",
                classes="tray_cfg_desc",
            )

            with Horizontal(id="tray_cfg_btn_row"):
                yield Button("💾 Save Settings", id="btn_tray_cfg_save", variant="success")
                yield Button("↩️ Back", id="btn_tray_cfg_back", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_tray_toggle":
            self.is_tray = not self.is_tray
            btn = self.query_one("#btn_tray_toggle", Button)
            btn.variant = "success" if self.is_tray else "default"
        elif bid == "btn_auto_toggle":
            self.is_auto = not self.is_auto
            btn = self.query_one("#btn_auto_toggle", Button)
            btn.variant = "success" if self.is_auto else "default"
        elif bid == "btn_tray_cfg_save":
            try:
                from config import set_minimize_to_tray_enabled
                set_minimize_to_tray_enabled(self.is_tray)
            except Exception:
                try:
                    from src.core.config import set_minimize_to_tray_enabled
                    set_minimize_to_tray_enabled(self.is_tray)
                except Exception:
                    pass
            try:
                from autostart_service import set_autostart
                set_autostart(self.is_auto)
            except Exception:
                try:
                    from src.services.autostart_service import set_autostart
                    set_autostart(self.is_auto)
                except Exception:
                    pass
            self.dismiss(True)
        elif bid == "btn_tray_cfg_back":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)



class DownloadLocationModal(ModalScreen[Optional[str]]):
    """Selection modal for assignment download destination (Auto-Dir, Manual, Standard Downloads)."""

    DEFAULT_CSS = """
    DownloadLocationModal {
        align: center middle;
    }
    #dl_loc_dialog {
        width: 76;
        max-height: 90%;
        height: auto;
        border: thick #a6e3a1;
        background: #1e1e2e;
        padding: 1 2;
    }
    #dl_loc_title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: #a6e3a1;
        margin-bottom: 1;
    }
    .dl_loc_meta {
        color: #a6adc8;
        margin-bottom: 1;
        text-align: center;
    }
    .dl_loc_btn {
        width: 100%;
        margin-bottom: 1;
    }
    .dl_loc_hint {
        color: #6c7086;
        margin-bottom: 1;
        padding-left: 2;
    }
    #dl_loc_cancel_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_auto", "Auto", show=False),
        Binding("2", "choose_manual", "Manual", show=False),
        Binding("3", "choose_downloads", "Downloads", show=False),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, task: Task) -> None:
        super().__init__()
        self.target_task = task
        self.matched_dir: Optional[Dict[str, Any]] = None
        try:
            from services.directory_service import DirectoryService
            self.matched_dir = DirectoryService.find_matching_directory_for_course(
                task.course, task.course_full
            )
        except Exception:
            self.matched_dir = None

    def compose(self) -> ComposeResult:
        with Vertical(id="dl_loc_dialog"):
            yield Label("📥 Download Assignment", id="dl_loc_title")
            course_disp = self.target_task.course_full or self.target_task.course or "General"
            yield Label(f"Subject: {course_disp} | Title: {self.target_task.title}", classes="dl_loc_meta")

            # Option 1: Auto-Dir
            if self.matched_dir:
                dir_title = self.matched_dir.get("title", "Course Folder")
                dir_path = self.matched_dir.get("path", "")
                btn_label = f"🎯 Linked Course Folder: {dir_title} [1]"
                yield Button(btn_label, id="btn_dl_auto", classes="dl_loc_btn", variant="primary")
                subfolder_preview = os.path.join(dir_path, self.target_task.title)
                yield Label(f"→ Subfolder: {subfolder_preview}", classes="dl_loc_hint")
            else:
                c_name = self.target_task.course or "Subject"
                yield Button(f"⚠️ No linked folder for '{c_name}' [1]", id="btn_dl_auto", classes="dl_loc_btn", variant="default", disabled=True)
                yield Label(f"Tip: Link a course folder via 'tasks dirs add <path>' to enable auto-download.", classes="dl_loc_hint")

            # Option 2: Manual
            yield Button("📂 Choose Folder Manually... [2]", id="btn_dl_manual", classes="dl_loc_btn", variant="warning")
            yield Label("→ Select destination via Windows Explorer folder picker", classes="dl_loc_hint")

            # Option 3: Standard Downloads
            yield Button("📥 Standard Downloads Folder [3]", id="btn_dl_downloads", classes="dl_loc_btn", variant="success")
            yield Label("→ Downloads\\<Subject> - <Title>", classes="dl_loc_hint")

            with Horizontal(id="dl_loc_cancel_row"):
                yield Button("↩️ Cancel [ESC]", id="btn_dl_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_dl_auto":
            self.action_choose_auto()
        elif bid == "btn_dl_manual":
            self.action_choose_manual()
        elif bid == "btn_dl_downloads":
            self.action_choose_downloads()
        elif bid == "btn_dl_cancel":
            self.action_cancel()

    def action_choose_auto(self) -> None:
        if self.matched_dir:
            self.dismiss("auto")

    def action_choose_manual(self) -> None:
        self.dismiss("manual")

    def action_choose_downloads(self) -> None:
        self.dismiss("downloads")

    def action_cancel(self) -> None:
        self.dismiss(None)


class AiConfigModal(ModalScreen[bool]):
    """Clean configuration modal for AI Chat Assistant (API Key, Model Dropdown, Test Connection, Language)."""

    DEFAULT_CSS = """
    AiConfigModal, AiExplainModal {
        align: center middle;
    }
    #ai_config_dialog {
        width: 76;
        max-height: 90%;
        height: auto;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
        scrollbar-gutter: stable;
    }
    #ai_config_title {
        text-align: center;
        text-style: bold;
        color: #89b4fa;
        margin-bottom: 1;
    }
    .ai_label {
        color: #cdd6f4;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    .ai_hint {
        color: #a6adc8;
        margin-bottom: 1;
        width: 100%;
        height: auto;
    }
    #inp_ai_key {
        margin-bottom: 1;
    }
    #ai_model_row {
        height: 3;
        width: 100%;
        align: left middle;
        margin-bottom: 1;
    }
    #sel_ai_model {
        width: 1fr;
        height: 3;
        margin-right: 1;
    }
    #btn_ai_fetch_models {
        min-width: 14;
        height: 3;
    }
    #ai_test_row {
        height: auto;
        min-height: 3;
        width: 100%;
        align: left middle;
        margin-top: 1;
        margin-bottom: 1;
    }
    #btn_ai_test_conn {
        min-width: 18;
        height: 3;
        margin-right: 1;
    }
    #lbl_ai_test_status {
        width: 1fr;
        height: auto;
        min-height: 1;
        text-style: bold;
    }
    #ai_lang_row {
        height: 3;
        align: left middle;
        margin-top: 1;
        margin-bottom: 1;
    }
    #btn_ai_lang {
        min-width: 32;
        height: 3;
    }
    #ai_buttons {
        height: 3;
        width: 100%;
        align: center middle;
        margin-top: 1;
        margin-bottom: 1;
    }
    #ai_buttons Button {
        margin: 0 1;
        min-width: 14;
        height: 3;
    }
    .-theme-oled #ai_config_dialog {
        background: #000000;
        border: thick #343331;
    }
    .-theme-oled #btn_ai_test_conn,
    .-theme-oled #btn_ai_fetch_models,
    .-theme-oled #btn_ai_lang,
    .-theme-oled #ai_buttons Button {
        background: #282726;
        color: #ffffff;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
        Binding("s", "save", "Save"),
    ]

    def __init__(self):
        super().__init__()
        from core.config import load_ai_chat_config, load_ai_explain_config, AI_EXPLAIN_PRESETS
        self.presets = AI_EXPLAIN_PRESETS
        self.chat_cfg = load_ai_chat_config()
        self.explain_cfg = load_ai_explain_config()
        self.current_provider = self.chat_cfg.get("provider", "gemini")
        self.current_api_key = self.chat_cfg.get("api_key", "")
        self.current_model = self.chat_cfg.get("model", "gemini-2.0-flash")
        self.current_base_url = self.chat_cfg.get("base_url", "https://api.openai.com/v1")
        self.current_language = self.chat_cfg.get("language", "de")
        self.current_app_path = self.explain_cfg.get("app_path") or ""
        self.current_url = self.explain_cfg.get("url_template", "")

        from services.ai_chat_service import fetch_available_models
        raw_options = fetch_available_models(self.current_api_key, provider=self.current_provider, base_url=self.current_base_url)
        found = any(m_id == self.current_model for _, m_id in raw_options)
        if not found and self.current_model:
            raw_options.insert(0, (f"{self.current_model} (Configured)", self.current_model))
        self.model_options = raw_options

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="ai_config_dialog"):
            yield Label("🤖 AI Assistant Configuration", id="ai_config_title")

            yield Label("API Key:", classes="ai_label")
            yield Label("Enter your Google Gemini or OpenAI API key (from Google AI Studio or OpenAI):", classes="ai_hint")
            yield Input(
                value=self.current_api_key,
                placeholder="Paste your API key here (e.g. AIzaSy...)",
                password=True,
                id="inp_ai_key",
            )

            yield Label("AI Model:", classes="ai_label")
            yield Label("Select an available model from the dropdown or click 'Load Models':", classes="ai_hint")
            with Horizontal(id="ai_model_row"):
                init_val = self.current_model if any(m_id == self.current_model for _, m_id in self.model_options) else (self.model_options[0][1] if self.model_options else "gemini-2.0-flash")
                yield Select(options=self.model_options, value=init_val, id="sel_ai_model")
                yield Button("🔄 Load Models", id="btn_ai_fetch_models", variant="primary", tooltip="Fetch models available for this API key")

            with Horizontal(id="ai_test_row"):
                yield Button("🔌 Test Connection", id="btn_ai_test_conn", variant="primary")
                yield Label("", id="lbl_ai_test_status")

            yield Label("Prompt / Response Language:", classes="ai_label")
            with Horizontal(id="ai_lang_row"):
                lang_label = "🌐 Language: German (DE)" if self.current_language == "de" else "🌐 Language: English (EN)"
                yield Button(lang_label, id="btn_ai_lang", variant="success")

            with Horizontal(id="ai_buttons"):
                yield Button("💾 Save [S]", id="btn_ai_save", variant="success")
                yield Button("↩️ Back [ESC]", id="btn_ai_cancel", variant="default")

    def on_mount(self) -> None:
        self._last_fetched_key = self.current_api_key

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "inp_ai_key":
            val = event.value.strip()
            if len(val) >= 15 and val != getattr(self, "_last_fetched_key", None):
                self._last_fetched_key = val
                self.action_fetch_models()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "inp_ai_key":
            self.action_fetch_models()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_ai_fetch_models":
            self.action_fetch_models()
        elif bid == "btn_ai_test_conn":
            self.action_test_connection()
        elif bid == "btn_ai_lang":
            self.action_toggle_language()
        elif bid == "btn_ai_save":
            self.action_save()
        elif bid == "btn_ai_cancel":
            self.action_cancel()

    def action_fetch_models(self) -> None:
        key = ""
        try:
            key = self.query_one("#inp_ai_key", Input).value.strip()
        except Exception:
            pass

        lbl = self.query_one("#lbl_ai_test_status", Label)
        lbl.update("[yellow]Fetching available models...[/yellow]")

        prov = "openai_compatible" if key.startswith("sk-") else "gemini"

        def worker():
            from services.ai_chat_service import fetch_available_models
            options = fetch_available_models(key, provider=prov, base_url=self.current_base_url)

            def update_ui():
                try:
                    sel = self.query_one("#sel_ai_model", Select)
                    sel.set_options(options)
                    if options:
                        sel.value = options[0][1]
                    lbl.update(f"[bold green]✓ Loaded {len(options)} models![/bold green]")
                except Exception as e:
                    lbl.update(f"[bold red]✗ Failed to update: {e}[/bold red]")

            self.app.call_from_thread(update_ui)

        import threading
        threading.Thread(target=worker, daemon=True, name="AiFetchModelsWorker").start()

    def action_test_connection(self) -> None:
        key = ""
        model = ""
        try:
            key = self.query_one("#inp_ai_key", Input).value.strip()
            sel = self.query_one("#sel_ai_model", Select)
            model = sel.value if sel.value != Select.BLANK else "gemini-2.0-flash"
        except Exception:
            pass

        lbl = self.query_one("#lbl_ai_test_status", Label)
        lbl.update("[yellow]Testing connection...[/yellow]")

        prov = "openai_compatible" if key.startswith("sk-") else "gemini"
        test_cfg = {
            "provider": prov,
            "api_key": key,
            "model": model or ("gemini-2.0-flash" if prov == "gemini" else "gpt-4o-mini"),
            "base_url": self.current_base_url or "https://api.openai.com/v1",
            "language": self.current_language,
        }

        def test_worker():
            try:
                from services.ai_chat_service import test_ai_connection
                success, msg = test_ai_connection(test_cfg)
            except Exception as e:
                success, msg = False, str(e)

            def update_lbl():
                if success:
                    lbl.update(f"[bold green]✓ {msg}[/bold green]")
                else:
                    if "prepayment" in msg.lower():
                        lbl.update(
                            "[bold red]✗ Prepayment-Fehler: Dein Google-Projekt erfordert Guthaben (Prepayment).\n"
                            "Tipp: Erstelle auf aistudio.google.com einen Key in 'New Project' ohne Billing für das kostenlose Free-Tier![/bold red]"
                        )
                    else:
                        lbl.update(f"[bold red]✗ {msg}[/bold red]")

            self.app.call_from_thread(update_lbl)

        import threading
        threading.Thread(target=test_worker, daemon=True, name="AiTestConnectionWorker").start()

    def action_toggle_language(self) -> None:
        self.current_language = "en" if self.current_language == "de" else "de"
        try:
            btn = self.query_one("#btn_ai_lang", Button)
            btn.label = "🌐 Language: German (DE)" if self.current_language == "de" else "🌐 Language: English (EN)"
        except Exception:
            pass

    def action_save(self) -> None:
        from core.config import save_ai_explain_config, save_ai_chat_config
        key = ""
        model = ""
        try:
            key = self.query_one("#inp_ai_key", Input).value.strip()
            sel = self.query_one("#sel_ai_model", Select)
            model = sel.value if sel.value != Select.BLANK else "gemini-2.0-flash"
        except Exception:
            pass

        prov = "openai_compatible" if key.startswith("sk-") else "gemini"
        save_ai_chat_config({
            "provider": prov,
            "api_key": key,
            "model": model or ("gemini-2.0-flash" if prov == "gemini" else "gpt-4o-mini"),
            "base_url": self.current_base_url or "https://api.openai.com/v1",
            "language": self.current_language,
        })

        save_ai_explain_config({
            "provider": prov,
            "url_template": "https://gemini.google.com/app",
            "app_path": None,
            "language": self.current_language,
        })
        self.app.notify("AI Assistant configuration saved!", severity="information")
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    # Legacy dummy method for backwards test compatibility
    def _select_preset(self, preset_key: str) -> None:
        self.current_provider = preset_key


AiExplainModal = AiConfigModal



class ThemeButton(Button):
    """Button widget that detects right-clicks to toggle favorite themes."""

    class RightClicked(Message):
        def __init__(self, button: "ThemeButton") -> None:
            super().__init__()
            self.button = button

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 3:  # Right Click
            event.stop()
            event.prevent_default()
            self.post_message(self.RightClicked(self))

    async def _on_click(self, event: events.Click) -> None:
        if event.button == 3:
            event.stop()
            event.prevent_default()


class ThemeSelectModal(ModalScreen[Optional[str]]):
    """Selection dialog for all available terminal themes with favorites and right-click toggle."""

    DEFAULT_CSS = """
    ThemeSelectModal {
        align: center middle;
    }
    #theme_dialog {
        width: 62;
        max-height: 85%;
        border: thick #cba6f7;
        background: #1e1e2e;
        padding: 1 2;
    }
    #theme_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #cba6f7;
    }
    .theme_btn {
        width: 100%;
        margin-bottom: 1;
    }
    .theme_btn:hover, .theme_btn:focus {
        background: #343331;
        color: #ffffff;
    }
    #theme_cancel_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_catppuccin", "Catppuccin Mocha", show=False),
        Binding("2", "choose_dracula", "Dracula", show=False),
        Binding("3", "choose_tokyo_night", "Tokyo Night", show=False),
        Binding("4", "choose_nord", "Nord", show=False),
        Binding("5", "choose_monokai", "Monokai", show=False),
        Binding("escape", "cancel", "Back"),
    ]

    THEMES_INFO = [
        ("catppuccin-mocha", "🍵 Catppuccin Mocha (Modern & Smooth)"),
        ("dracula", "🧛 Dracula (Dark & High-Contrast)"),
        ("tokyo-night", "🌃 Tokyo Night (Clean & Vibrant)"),
        ("nord", "❄️ Nord (Cool & Minimalist)"),
        ("monokai", "🎨 Monokai (Classic Retro)"),
        ("gruvbox", "🪵 Gruvbox (Warm & Earthy)"),
        ("rose-pine", "🌸 Rosé Pine (Dark & Dreamy)"),
        ("rose-pine-moon", "🌙 Rosé Pine Moon (Muted & Cozy)"),
        ("rose-pine-dawn", "🌅 Rosé Pine Dawn (Warm & Light)"),
        ("solarized-dark", "🌌 Solarized Dark (Classic Contrast)"),
        ("solarized-light", "☀️ Solarized Light (Clean & Crisp)"),
        ("catppuccin-macchiato", "☕ Catppuccin Macchiato (Medium Dark)"),
        ("catppuccin-frappe", "🍧 Catppuccin Frappé (Soft Dark)"),
        ("catppuccin-latte", "🥛 Catppuccin Latte (Bright & Pastel)"),
        ("atom-one-dark", "⚛️ Atom One Dark (Classic Editor)"),
        ("atom-one-light", "💡 Atom One Light (Clean Modern)"),
        ("flexoki", "🌿 Flexoki (Inky Earth Tones)"),
        ("oled", "🌑 OLED (Pure Black & Flexoki Accents)"),
        ("textual-dark", "🖤 Textual Dark (Deep Midnight)"),
        ("textual-light", "🤍 Textual Light (Pure Paper)"),
        ("ansi-dark", "📟 ANSI Dark (Vintage Terminal)"),
        ("ansi-light", "📄 ANSI Light (Vintage Paper)"),
    ]

    def __init__(self, current_theme: str = "catppuccin-mocha"):
        super().__init__()
        self.current_theme = current_theme

    def _get_sorted_theme_items(self):
        favs = load_favorite_themes()
        fav_list = []
        regular_list = []
        for t_id, t_name in self.THEMES_INFO:
            is_active = (t_id == self.current_theme)
            is_fav = (t_id in favs)
            star = "⭐ " if is_fav else ""
            prefix = "✓ " if is_active else ""
            label = f"{star}{prefix}{t_name}"
            item = (t_id, label, is_active)
            if is_fav:
                fav_list.append(item)
            else:
                regular_list.append(item)
        return fav_list + regular_list

    def compose(self) -> ComposeResult:
        with Vertical(id="theme_dialog"):
            yield Label("🎨 Choose Color Theme / Palette", id="theme_title")
            with VerticalScroll(id="theme_scroll"):
                for t_id, label, is_active in self._get_sorted_theme_items():
                    variant = "success" if is_active else "default"
                    yield ThemeButton(label, id=f"btn_thm_{t_id.replace('-', '_')}", classes="theme_btn", variant=variant)
            with Horizontal(id="theme_cancel_row"):
                yield Button("↩️ Back [ESC]", id="btn_theme_cancel", variant="default")

    def refresh_buttons(self) -> None:
        favs = load_favorite_themes()
        scroll = self.query_one("#theme_scroll", VerticalScroll)

        # 1. Labels aktualisieren
        for t_id, t_name in self.THEMES_INFO:
            bid = f"#btn_thm_{t_id.replace('-', '_')}"
            try:
                btn = scroll.query_one(bid, ThemeButton)
                is_active = (t_id == self.current_theme)
                is_fav = (t_id in favs)
                star = "⭐ " if is_fav else ""
                prefix = "✓ " if is_active else ""
                btn.label = f"{star}{prefix}{t_name}"
            except Exception:
                pass

        # 2. Re-order: Favoriten ganz nach oben
        fav_buttons = []
        regular_buttons = []
        for t_id, _ in self.THEMES_INFO:
            bid = f"#btn_thm_{t_id.replace('-', '_')}"
            try:
                btn = scroll.query_one(bid, ThemeButton)
                if t_id in favs:
                    fav_buttons.append(btn)
                else:
                    regular_buttons.append(btn)
            except Exception:
                pass

        desired_order = fav_buttons + regular_buttons
        for btn in reversed(desired_order):
            if scroll.children and btn != scroll.children[0]:
                scroll.move_child(btn, before=scroll.children[0])

    def on_theme_button_right_clicked(self, event: ThemeButton.RightClicked) -> None:
        bid = event.button.id or ""
        if bid.startswith("btn_thm_"):
            raw_id = bid[len("btn_thm_"):].replace("_", "-")
            if raw_id in ALLOWED_THEMES:
                is_fav = toggle_favorite_theme(raw_id)
                if is_fav:
                    self.app.notify(f"⭐ Marked '{raw_id}' as favorite!", severity="information")
                else:
                    self.app.notify(f"Removed '{raw_id}' from favorites.", severity="warning")
                self.refresh_buttons()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid in ["btn_theme_cancel", "btn_cancel"]:
            self.dismiss(None)
        elif bid.startswith("btn_thm_"):
            raw_id = bid[len("btn_thm_"):].replace("_", "-")
            if raw_id in ALLOWED_THEMES:
                self.dismiss(raw_id)

    def action_choose_catppuccin(self) -> None:
        self.dismiss("catppuccin-mocha")

    def action_choose_dracula(self) -> None:
        self.dismiss("dracula")

    def action_choose_tokyo_night(self) -> None:
        self.dismiss("tokyo-night")

    def action_choose_nord(self) -> None:
        self.dismiss("nord")

    def action_choose_monokai(self) -> None:
        self.dismiss("monokai")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class FavoriteThemeProvider(Provider):
    """A provider for themes that places favorite themes at the top with a golden star."""

    @property
    def commands(self) -> list[tuple[str, Callable[[], None], str]]:
        themes = self.app.available_themes
        favs = load_favorite_themes()

        def set_app_theme(name: str) -> None:
            self.app.theme = name

        fav_cmds = []
        regular_cmds = []

        for theme in sorted(themes.values(), key=lambda t: t.name):
            name = theme.name
            if name in favs:
                prompt = f"⭐ {name}"
                fav_cmds.append((prompt, functools.partial(set_app_theme, name), name))
            else:
                prompt = name
                regular_cmds.append((prompt, functools.partial(set_app_theme, name), name))

        return fav_cmds + regular_cmds

    async def discover(self) -> Hits:
        for prompt, callback, _ in self.commands:
            yield DiscoveryHit(prompt, callback)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        favs = load_favorite_themes()
        for prompt, callback, raw_name in self.commands:
            m1 = matcher.match(prompt)
            m2 = matcher.match(raw_name)
            score = max(m1, m2)
            if score > 0:
                if raw_name in favs:
                    score += 100.0
                yield Hit(score, matcher.highlight(prompt), callback)


class ThemeCommandList(CommandList):
    """Custom CommandList that intercepts right-clicks to toggle favorite themes."""

    async def _on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 3:  # Right Click
            event.stop()
            event.prevent_default()

    async def _on_click(self, event: events.Click) -> None:
        if event.button == 3:  # Right Click
            event.stop()
            event.prevent_default()
            opt_idx = event.style.meta.get("option")
            if opt_idx is not None and 0 <= opt_idx < len(self._options):
                opt = self.get_option_at_index(opt_idx)
                hit = getattr(opt, "hit", None)
                if hit:
                    raw_text = str(getattr(hit, "text", "") or getattr(hit, "prompt", ""))
                    clean_name = raw_text.replace("⭐", "").replace("★", "").strip()
                    if clean_name in ALLOWED_THEMES:
                        is_fav = toggle_favorite_theme(clean_name)
                        if is_fav:
                            self.app.notify(f"⭐ Marked '{clean_name}' as favorite!", severity="information")
                        else:
                            self.app.notify(f"Removed '{clean_name}' from favorites.", severity="warning")
                        palette = self.screen
                        if isinstance(palette, CommandPalette):
                            input_w = palette.query_one(CommandInput)
                            palette._gather_commands(input_w.value)


class ThemeCommandPalette(CommandPalette):
    """CommandPalette for themes with right-click favorite toggle."""

    def compose(self) -> ComposeResult:
        with Vertical(id="--container"):
            with Horizontal(id="--input"):
                yield SearchIcon()
                yield CommandInput(placeholder=self._placeholder, select_on_focus=False)
                if not self.run_on_select:
                    yield Button("▶")
            with Vertical(id="--results"):
                yield ThemeCommandList()
                yield LoadingIndicator()


class SubjectFilterModal(ModalScreen[Optional[str]]):
    """Selection dialog for subject filter with clickable buttons."""

    DEFAULT_CSS = """
    SubjectFilterModal {
        align: center middle;
    }
    #subj_dialog {
        width: 60;
        max-height: 80%;
        border: thick #f9e2af;
        background: #1e1e2e;
        padding: 1 2;
    }
    #subj_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #f9e2af;
    }
    .subj_btn {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def __init__(self, subjects: List[str]):
        super().__init__()
        self.subjects = subjects

    def compose(self) -> ComposeResult:
        with Vertical(id="subj_dialog"):
            yield Label("📚 Filter by Subject", id="subj_title")
            with VerticalScroll():
                yield Button("🌟 All Subjects", id="btn_subj_all", classes="subj_btn", variant="primary")
                for idx, s in enumerate(self.subjects):
                    yield Button(f"📖 {s}", id=f"btn_subj_{idx}", classes="subj_btn")
            yield Button("↩️ Back [ESC]", id="btn_subj_cancel", classes="subj_btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid in ["btn_subj_cancel", "btn_cancel"]:
            self.dismiss(None)
        elif bid == "btn_subj_all":
            self.dismiss("all")
        elif bid.startswith("btn_subj_"):
            try:
                idx = int(bid[9:])
                self.dismiss(self.subjects[idx])
            except (ValueError, IndexError):
                self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class TaskDetailModal(ModalScreen[None]):
    """Vollständige interaktive Detailansicht einer Aufgabe mit Maus-Buttons."""

    DEFAULT_CSS = """
    TaskDetailModal {
        align: center middle;
    }
    #detail_dialog {
        width: 90%;
        height: 90%;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
    }
    #detail_header {
        height: auto;
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid #313244;
    }
    #detail_title {
        text-style: bold;
        color: #89dceb;
    }
    #detail_meta {
        color: #a6adc8;
    }
    #detail_scroll {
        height: 1fr;
        border: solid #313244;
        background: #181825;
        padding: 1;
        margin-bottom: 1;
    }
    #detail_buttons {
        height: auto;
        width: 100%;
        align: left middle;
    }
    #detail_left_buttons {
        width: 1fr;
        height: auto;
        align: left middle;
    }
    #detail_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("o", "open_browser", "Open in browser"),
        Binding("d", "download_files", "Download files"),
        Binding("a", "ai_explain", "Ai Explain"),
                Binding("e", "toggle_status", "Toggle status"),
        Binding("l", "delete_task", "Hide"),
        Binding("w", "restore_task", "Restore"),
        Binding("escape", "close", "Close"),
        Binding("z", "close", "Close"),
    ]

    def __init__(self, task: Task, mgr: TaskManager, is_deleted: bool = False):
        super().__init__()
        self.target_task = task
        self.mgr = mgr
        self.is_deleted = is_deleted

    def compose(self) -> ComposeResult:
        with Vertical(id="detail_dialog"):
            with Vertical(id="detail_header"):
                if self.target_task.platform == "moodle":
                    p_badge = "🟧 Moodle"
                elif self.target_task.platform == "teams":
                    p_badge = "🟦 Teams"
                else:
                    p_badge = "✏️ Manual"
                yield Label(f"[{p_badge}] {self.target_task.title}", id="detail_title")

                teacher_str = f" | Teacher: {self.target_task.teacher}" if self.target_task.teacher else ""
                status_disp = "Completed" if self.target_task.is_completed else ("Overdue" if self.target_task.is_overdue else "Open")
                status_str = f"Status: {status_disp}"
                due_str = f"Due: {self.target_task.due_date_str}"
                meta_line = f"Subject: {self.target_task.course_full or self.target_task.course} | {status_str} | {due_str}{teacher_str}"
                yield Label(meta_line, id="detail_meta")

            with VerticalScroll(id="detail_scroll"):
                content = self.target_task.description.strip() if self.target_task.description else ""
                if not content:
                    content = "*No written assignment description provided.*"

                if self.target_task.attachments:
                    content += "\n\n---\n### 📎 Attached Files:\n"
                    for a in self.target_task.attachments:
                        content += f"* **{a.name}**\n"

                yield Markdown(content)

            with Horizontal(id="detail_buttons"):
                with Horizontal(id="detail_left_buttons"):
                    if self.target_task.platform in ["manual", "custom"]:
                        if self.target_task.is_completed:
                            yield Button("↩️ Mark as Open [E]", id="btn_det_status", variant="warning")
                            yield Button("🗑️ Delete [L]", id="btn_det_delete", variant="error")
                        else:
                            yield Button("✓ Mark as Completed [E]", id="btn_det_status", variant="success")
                    else:
                        yield Button("🌐 Browser [O]", id="btn_det_browser", variant="primary")
                        yield Button("📥 Download [D]", id="btn_det_download", variant="success")
                        if not self.is_deleted:
                            yield Button("🗑️ Hide [L]", id="btn_det_delete", variant="error")
                        else:
                            yield Button("✨ Restore [W]", id="btn_det_restore", variant="warning")
                    yield Button("🤖 Ai Explain [A]", id="btn_det_ai_explain", variant="warning")
                yield Button("↩️ Close [ESC]", id="btn_det_close", variant="default")


    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_det_browser":
            self.action_open_browser()
        elif bid == "btn_det_download":
            self.action_download_files()
        elif bid == "btn_det_ai_explain":
            self.action_ai_explain()
        elif bid == "btn_det_status":
            self.action_toggle_status()
        elif bid == "btn_det_delete":
            self.action_delete_task()
        elif bid == "btn_det_restore":
            self.action_restore_task()
        elif bid == "btn_det_close":
            self.action_close()

    def action_download_files(self) -> None:
        if self.target_task.platform in ["manual", "custom"]:
            return

        def on_location_chosen(choice: Optional[str]) -> None:
            if not choice:
                return

            if choice == "auto":
                try:
                    from services.directory_service import DirectoryService
                except ImportError:
                    from directory_service import DirectoryService
                try:
                    from core.config import sanitize_filename
                except ImportError:
                    from config import sanitize_filename

                matched = DirectoryService.find_matching_directory_for_course(
                    self.target_task.course, self.target_task.course_full
                )
                if not matched:
                    self.app.notify(
                        f"No linked folder found for '{self.target_task.course}'.",
                        title="📥 Download",
                        severity="warning",
                    )
                    return
                safe_title = sanitize_filename(self.target_task.title)
                target_dir = os.path.join(matched.get("path", ""), safe_title)
                os.makedirs(target_dir, exist_ok=True)
                self._start_download_worker(target_dir)

            elif choice == "manual":
                def pick_and_download():
                    try:
                        from core.win_dialogs import pick_directory
                    except ImportError:
                        from win_dialogs import pick_directory
                    chosen = pick_directory(dialog_title="Select Destination Folder")
                    if not chosen:
                        return
                    self._start_download_worker(chosen)

                import threading
                threading.Thread(target=pick_and_download, daemon=True, name="ManualFolderPickerWorker").start()

            elif choice == "downloads":
                self._start_download_worker(dest_dir=None)

        self.app.push_screen(DownloadLocationModal(self.target_task), on_location_chosen)

    def _start_download_worker(self, dest_dir: Optional[str] = None) -> None:
        self.app.notify("Downloading attachments...", title="📥 Download", severity="information")

        def dl_worker():
            files = self.mgr.download_task_files(self.target_task, dest_dir=dest_dir)

            def update_ui():
                target_folder = self.target_task.download_dir or dest_dir
                if files:
                    self.app.notify(
                        f"✓ {len(files)} file(s) saved to: {target_folder}",
                        title="📥 Download",
                        severity="information",
                    )
                    try:
                        if target_folder and os.path.exists(target_folder):
                            os.startfile(target_folder)
                    except Exception:
                        pass
                else:
                    self.app.notify(
                        "No downloadable attachments found (angabe.md created).",
                        title="📥 Download",
                        severity="warning",
                    )

            self.app.call_from_thread(update_ui)

        import threading
        threading.Thread(target=dl_worker, daemon=True, name="DownloadWorker").start()

    def action_open_browser(self) -> None:
        if self.target_task.platform in ["manual", "custom"]:
            return
        if self.target_task and self.target_task.url:
            webbrowser.open(self.target_task.url)
            self.app.notify(f"Opening '{self.target_task.title}' in browser...", severity="information")
        else:
            self.app.notify("No URL available for this assignment.", severity="warning")

    def action_ai_explain(self) -> None:
        target_id = self.target_task.id
        self.dismiss(None)
        try:
            app_inst = self.app
        except Exception:
            app_inst = getattr(self, "_app", None)
        if app_inst and hasattr(app_inst, "action_show_ai_chat"):
            app_inst.action_show_ai_chat(initial_task_id=target_id, auto_explain=True)

    def action_toggle_status(self) -> None:
        if self.target_task.platform not in ["manual", "custom"]:
            return
        updated = self.mgr.toggle_task_status(self.target_task.id)
        if updated:
            self.target_task = updated
            status_disp = "Completed" if self.target_task.is_completed else ("Overdue" if self.target_task.is_overdue else "Open")
            self.app.notify(f"Status updated to: {status_disp}", severity="information")
            teacher_str = f" | Teacher: {self.target_task.teacher}" if self.target_task.teacher else ""
            status_str = f"Status: {status_disp}"
            due_str = f"Due: {self.target_task.due_date_str}"
            meta_line = f"Subject: {self.target_task.course_full or self.target_task.course} | {status_str} | {due_str}{teacher_str}"
            self.query_one("#detail_meta", Label).update(meta_line)
            try:
                btn = self.query_one("#btn_det_status", Button)
                left_box = self.query_one("#detail_left_buttons", Horizontal)
                existing_del = list(self.query("#btn_det_delete"))
                if self.target_task.is_completed:
                    btn.label = "↩️ Mark as Open [E]"
                    btn.variant = "warning"
                    if not existing_del:
                        left_box.mount(Button("🗑️ Delete [L]", id="btn_det_delete", variant="error"))
                else:
                    btn.label = "✓ Mark as Completed [E]"
                    btn.variant = "success"
                    if existing_del:
                        existing_del[0].remove()
            except Exception:
                pass

    def action_delete_task(self) -> None:
        if self.target_task.platform in ["manual", "custom"]:
            if not self.target_task.is_completed:
                return
            self.mgr.delete_custom_task(self.target_task.id)
            self.app.notify(f"Manual task '{self.target_task.title}' was deleted.", severity="warning")
            self.dismiss()
            return

        self.mgr.delete_task(self.target_task.id)
        self.app.notify(f"Assignment '{self.target_task.title}' was hidden.", severity="warning")
        self.dismiss()

    def action_restore_task(self) -> None:
        self.mgr.restore_task(self.target_task.id)
        self.app.notify(f"Assignment '{self.target_task.title}' restored.", severity="information")
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()


def format_status_english(task: Task) -> str:
    """Returns normalized English status string ('Completed', 'Overdue', or 'Open')."""
    if task.is_completed:
        return "Completed"
    if task.is_overdue:
        return "Overdue"
    dt = (task.status_display or "").lower()
    st = (task.status or "").lower()
    if any(neg in dt for neg in ["keine", "nicht", "noch nicht", "unvollständig"]):
        pass
    elif any(kw in dt for kw in ["abgegeben", "erledigt", "completed", "done", "submitted", "bewertet", "zur bewertung", "zurückgegeben", "zurueckgegeben", "returned"]):
        return "Completed"
    if any(kw in dt for kw in ["überfällig", "ueberfaellig", "overdue", "verspätet", "late"]) or any(kw in st for kw in ["überfällig", "ueberfaellig", "overdue"]):
        return "Overdue"
    return "Open"


class TrashModal(ModalScreen[None]):
    """Papierkorb-Ansicht für ausgeblendete/gelöschte Aufgaben."""

    DEFAULT_CSS = """
    TrashModal {
        align: center middle;
    }
    #trash_dialog {
        width: 85%;
        height: 80%;
        border: thick #eba0ac;
        background: #1e1e2e;
        padding: 1 2;
    }
    #trash_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #eba0ac;
    }
    #trash_table {
        height: 1fr;
        background: #181825;
        border: solid #313244;
        margin-bottom: 1;
    }
    #trash_buttons {
        height: auto;
        align: center middle;
    }
    #trash_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("w", "restore_all", "Restore all"),
        Binding("escape", "close", "Close"),
        Binding("z", "close", "Close"),
    ]

    def __init__(self, mgr: TaskManager):
        super().__init__()
        self.mgr = mgr
        self.deleted_tasks: List[Task] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="trash_dialog"):
            yield Label("🗑️ Hidden / Deleted Assignments", id="trash_title")
            dt = DataTable(id="trash_table", cursor_type="row")
            yield dt
            with Horizontal(id="trash_buttons"):
                yield Button("✨ Restore all [W]", id="btn_trash_restore_all", variant="success")
                yield Button("↩️ Back [ESC]", id="btn_trash_close", variant="default")

    def on_mount(self) -> None:
        if sys.platform == "win32":
            try:
                from win_dialogs import enable_high_dpi_awareness
                enable_high_dpi_awareness()
            except Exception:
                pass

        dt = self.query_one(DataTable)
        dt.cell_padding = 2
        dt.add_columns("#", "Platform", "Subject", "Assignment", "Due Date", "Status")
        self.refresh_trash_table()

    def refresh_trash_table(self) -> None:
        dt = self.query_one(DataTable)
        dt.clear()
        self.deleted_tasks = self.mgr.get_deleted_tasks()
        for idx, t in enumerate(self.deleted_tasks, 1):
            if t.platform == "moodle":
                plat_badge = Text("🟧 Moodle", style="bold orange3")
            elif t.platform == "teams":
                plat_badge = Text("🟦 Teams", style="bold dodger_blue1")
            else:
                plat_badge = Text("✏️ Manual", style="bold medium_purple")
            disp_txt = format_status_english(t)
            dt.add_row(
                str(idx),
                plat_badge,
                Text(t.course, style="bold cyan"),
                t.title,
                t.due_date_str,
                Text(disp_txt, style="dim"),
                height=2,
                key=t.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        task = next((t for t in self.deleted_tasks if t.id == row_key), None)
        if task:
            self.app.push_screen(TaskDetailModal(task, self.mgr, is_deleted=True), self._on_detail_closed)

    def _on_detail_closed(self, result=None) -> None:
        self.refresh_trash_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_trash_restore_all":
            self.action_restore_all()
        elif event.button.id == "btn_trash_close":
            self.action_close()

    def action_restore_all(self) -> None:
        for t in list(self.deleted_tasks):
            self.mgr.restore_task(t.id)
        self.app.notify("✓ All assignments restored!", severity="information")
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()


class MoodleLoginModal(ModalScreen[bool]):
    """Interactive Moodle login dialog directly inside the terminal."""

    DEFAULT_CSS = """
    MoodleLoginModal {
        align: center middle;
    }
    #moodle_dialog {
        width: 65;
        height: auto;
        border: thick #fab387;
        background: #1e1e2e;
        padding: 1 2;
    }
    #moodle_title {
        text-align: center;
        text-style: bold;
        color: #fab387;
        margin-bottom: 1;
    }
    #moodle_desc {
        color: #a6adc8;
        margin-bottom: 1;
        text-align: center;
    }
    #moodle_status {
        color: #f9e2af;
        margin-top: 1;
        margin-bottom: 1;
        text-align: center;
        width: 100%;
        height: auto;
    }
    .m_input {
        margin-bottom: 1;
    }
    #moodle_buttons {
        height: auto;
        align: center middle;
    }
    #moodle_buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        from config import MOODLE_BASE_URL, _load_moodle_base_url
        current_url = _load_moodle_base_url() or MOODLE_BASE_URL
        with Vertical(id="moodle_dialog"):
            yield Label("🎓 Moodle Login", id="moodle_title")
            yield Label("Credentials are stored locally on your PC only.", id="moodle_desc")
            yield Input(value=current_url, placeholder="Moodle URL (z.B. https://moodle.spengergasse.at)", id="inp_m_url", classes="m_input")
            yield Input(placeholder="Username", id="inp_m_user", classes="m_input")
            yield Input(placeholder="Password", password=True, id="inp_m_pass", classes="m_input")
            yield Label("", id="moodle_status")
            with Horizontal(id="moodle_buttons"):
                yield Button("🔐 Log In", id="btn_m_submit", variant="primary")
                yield Button("↩️ Back [ESC]", id="btn_m_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_m_cancel":
            self.dismiss(False)
        elif event.button.id == "btn_m_submit":
            self._start_login()

    def _start_login(self) -> None:
        url = self.query_one("#inp_m_url", Input).value.strip()
        u = self.query_one("#inp_m_user", Input).value.strip()
        p = self.query_one("#inp_m_pass", Input).value.strip()
        if not u or not p:
            self.query_one("#moodle_status", Label).update("[red]Please enter username and password.[/red]")
            return

        if not url:
            from config import MOODLE_BASE_URL
            url = MOODLE_BASE_URL

        self.query_one("#moodle_status", Label).update("[yellow]Checking Moodle credentials...[/yellow]")
        self.query_one("#btn_m_submit", Button).disabled = True

        def worker():
            from auth import login_moodle_direct

            res = login_moodle_direct(u, p, moodle_url=url)
            def update_ui():
                self.query_one("#btn_m_submit", Button).disabled = False
                if res.success:
                    self.app.notify("✓ Moodle successfully connected!", severity="information")
                    self.dismiss(True)
                else:
                    err = res.message or "Login failed. Please check your credentials and URL."
                    self.query_one("#moodle_status", Label).update(f"[red]✗ {err}[/red]")
            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="MoodleLoginWorker").start()

    def key_escape(self) -> None:
        self.dismiss(False)


class TeamsSetupModal(ModalScreen[bool]):
    """Microsoft Teams Direct Login dialog (just like Moodle & Untis)."""

    DEFAULT_CSS = """
    TeamsSetupModal {
        align: center middle;
    }
    #teams_dialog {
        width: 68;
        height: auto;
        border: thick #74c7ec;
        background: #1e1e2e;
        padding: 1 2;
    }
    #teams_title {
        text-align: center;
        text-style: bold;
        color: #74c7ec;
        margin-bottom: 1;
    }
    #teams_desc {
        color: #a6adc8;
        margin-bottom: 1;
        text-align: center;
    }
    .t_input {
        margin-bottom: 1;
    }
    #teams_status {
        color: #f9e2af;
        margin: 1 0;
        text-align: center;
    }
    #teams_2fa_box {
        border: round #a6e3a1;
        background: #181825;
        padding: 1;
        margin-bottom: 1;
        display: none;
        align: center middle;
    }
    #teams_2fa_title {
        text-align: center;
        text-style: bold;
        color: #a6e3a1;
    }
    #teams_2fa_number {
        text-align: center;
        text-style: bold;
        color: #fab387;
        margin: 1 0;
    }
    #teams_2fa_desc {
        text-align: center;
        color: #cdd6f4;
        margin-bottom: 1;
    }
    #teams_2fa_input_row {
        height: auto;
        display: none;
        align: center middle;
        margin-top: 1;
    }
    #teams_2fa_input_row Input,
    #teams_2fa_input_row ChatInputArea {
        width: 28;
        margin-right: 1;
    }
    #teams_btn_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #teams_btn_row Button {
        margin: 0 1;
    }
    .t_sec_btn {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mfa_code_event = threading.Event()
        self._mfa_code_val = None

    def compose(self) -> ComposeResult:
        with Vertical(id="teams_dialog"):
            yield Label("👥 Microsoft Teams Login", id="teams_title")
            yield Label("Log in directly with your school email and password:", id="teams_desc")
            yield Input(placeholder="School email (e.g. name@spengergasse.at)", id="inp_t_email", classes="t_input")
            yield Input(placeholder="Password", password=True, id="inp_t_pass", classes="t_input")

            with Vertical(id="teams_2fa_box"):
                yield Label("🔔 Two-Factor Authentication (2FA)", id="teams_2fa_title")
                yield Label("", id="teams_2fa_number")
                yield Label("Approve the number in your Microsoft Authenticator app on your phone.", id="teams_2fa_desc")
                with Horizontal(id="teams_2fa_input_row"):
                    yield Input(placeholder="6-digit SMS / verification code", id="inp_t_code")
                    yield Button("Send Code", id="btn_t_submit_code", variant="success")

            yield Label("", id="teams_status")

            with Horizontal(id="teams_btn_row"):
                yield Button("🔐 Log in with Password", id="btn_t_login", variant="primary")
                yield Button("↩️ Back [ESC]", id="btn_t_cancel", variant="default")

            yield Button("🔑 Log in with Passkey / Browser", id="btn_t_passkey", classes="t_sec_btn", variant="warning")
            yield Button("🔍 Check existing session", id="btn_t_check", classes="t_sec_btn", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_t_cancel":
            self.dismiss(False)
        elif bid == "btn_t_login":
            self._start_direct_login()
        elif bid == "btn_t_submit_code":
            self._submit_mfa_code()
        elif bid == "btn_t_check":
            self._check_session()
        elif bid in ("btn_t_fresh", "btn_t_passkey"):
            self._run_interactive_browser()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in ("inp_t_email", "inp_t_pass"):
            self._start_direct_login()
        elif event.input.id == "inp_t_code":
            self._submit_mfa_code()

    def _submit_mfa_code(self) -> None:
        try:
            val = self.query_one("#inp_t_code", Input).value.strip()
            if val:
                self._mfa_code_val = val
                self._mfa_code_event.set()
                self.query_one("#teams_status", Label).update("[yellow]Submitting verification code...[/yellow]")
        except Exception:
            pass

    def _start_direct_login(self) -> None:
        email = self.query_one("#inp_t_email", Input).value.strip()
        pwd = self.query_one("#inp_t_pass", Input).value.strip()

        if not email or not pwd:
            self.query_one("#teams_status", Label).update("[red]Please enter your school email and password.[/red]")
            return

        self.query_one("#teams_status", Label).update("[yellow]Logging into Microsoft...[/yellow]")
        self.query_one("#btn_t_login", Button).disabled = True
        self.query_one("#btn_t_check", Button).disabled = True

        self._mfa_code_event.clear()
        self._mfa_code_val = None

        def worker():
            from auth import login_teams_direct

            def on_status_cb(msg: str):
                self.app.call_from_thread(lambda: self.query_one("#teams_status", Label).update(f"[cyan]{msg}[/cyan]"))

            def on_mfa_num_cb(num: str):
                def update_box():
                    box = self.query_one("#teams_2fa_box", Vertical)
                    box.styles.display = "block"
                    self.query_one("#teams_2fa_number", Label).update(f"[bold yellow on black]   [  {num}  ]   [/bold yellow on black]")
                    self.query_one("#teams_2fa_desc", Label).update(f"Tap number [bold yellow]{num}[/bold yellow] in your Authenticator app on your smartphone!")
                self.app.call_from_thread(update_box)

            def on_mfa_code_cb():
                def show_input():
                    box = self.query_one("#teams_2fa_box", Vertical)
                    box.styles.display = "block"
                    self.query_one("#teams_2fa_number", Label).update("")
                    self.query_one("#teams_2fa_desc", Label).update("Enter the 6-digit verification code you received:")
                    row = self.query_one("#teams_2fa_input_row", Horizontal)
                    row.styles.display = "block"
                    self.query_one("#inp_t_code", Input).focus()
                self.app.call_from_thread(show_input)
                self._mfa_code_event.wait(timeout=120)
                return self._mfa_code_val

            success, msg = login_teams_direct(
                email=email,
                password=pwd,
                on_status=on_status_cb,
                on_mfa_number=on_mfa_num_cb,
                on_mfa_code_request=on_mfa_code_cb,
                headless=True,
                timeout_sec=180,
            )

            def on_done():
                self.query_one("#btn_t_login", Button).disabled = False
                self.query_one("#btn_t_check", Button).disabled = False
                if success:
                    self.app.notify("✓ Microsoft Teams successfully connected!", severity="information")
                    self.dismiss(True)
                else:
                    self.query_one("#teams_status", Label).update(f"[red]✗ {msg}[/red]")

            self.app.call_from_thread(on_done)

        threading.Thread(target=worker, daemon=True, name="TeamsDirectLoginWorker").start()

    def _check_session(self) -> None:
        self.query_one("#teams_status", Label).update("[yellow]Checking Teams session in background...[/yellow]")
        self.query_one("#btn_t_check", Button).disabled = True

        def worker():
            from auth import test_teams_session_live

            ok = test_teams_session_live()
            def update_ui():
                self.query_one("#btn_t_check", Button).disabled = False
                if ok:
                    try:
                        with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
                            json.dump({"configured": True, "last_login": time.time()}, f)
                    except Exception:
                        pass
                    self.app.notify("✓ Teams session is active and valid!", severity="information")
                    self.dismiss(True)
                else:
                    self.query_one("#teams_status", Label).update("[red]! Session expired. Please enter email & password.[/red]")
            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="TeamsCheckWorker").start()

    def _run_interactive_browser(self) -> None:
        email = ""
        try:
            email = self.query_one("#inp_t_email", Input).value.strip()
        except Exception:
            pass
        if not email:
            email = ""

        self.query_one("#teams_status", Label).update("[yellow]Browser opened: Please log in with passkey in the Teams window...[/yellow]")
        try:
            self.query_one("#btn_t_passkey", Button).disabled = True
            self.query_one("#btn_t_login", Button).disabled = True
            self.query_one("#btn_t_check", Button).disabled = True
        except Exception:
            pass

        def worker():
            from auth import setup_teams_interactive

            ok = setup_teams_interactive(console=None, fresh=True, email=email)
            def update_ui():
                try:
                    self.query_one("#btn_t_passkey", Button).disabled = False
                    self.query_one("#btn_t_login", Button).disabled = False
                    self.query_one("#btn_t_check", Button).disabled = False
                except Exception:
                    pass
                if ok:
                    self.app.notify("✓ Teams successfully connected!", severity="information")
                    self.dismiss(True)
                else:
                    self.query_one("#teams_status", Label).update("[yellow]Teams login not completed.[/yellow]")
            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="TeamsPasskeyLoginWorker").start()

    def key_escape(self) -> None:
        self.dismiss(False)


class LoginReminderModal(ModalScreen[Optional[str]]):
    """Modal alert notifying the user when one or more school platforms are not signed in."""

    DEFAULT_CSS = """
    LoginReminderModal {
        align: center middle;
    }
    #login_reminder_dialog {
        width: 68;
        max-height: 85%;
        height: auto;
        border: thick #fab387;
        background: #1e1e2e;
        padding: 1 2;
    }
    #login_reminder_title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        color: #fab387;
    }
    #login_reminder_desc {
        text-align: center;
        color: #cdd6f4;
        margin-bottom: 1;
    }
    #login_reminder_box {
        width: 100%;
        height: auto;
        border: solid #45475a;
        background: #181825;
        padding: 1 2;
        margin-bottom: 1;
    }
    .login_platform_row {
        height: 1;
        margin-bottom: 1;
    }
    .login_platform_name {
        width: 24;
        text-style: bold;
        color: #cdd6f4;
    }
    .login_platform_status {
        width: auto;
        text-style: bold;
    }
    #login_reminder_buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #login_reminder_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Dismiss"),
        Binding("enter", "open_logins", "Open Login Menu"),
        Binding("l", "open_logins", "Open Login Menu", show=False),
    ]

    def compose(self) -> ComposeResult:
        from auth import get_platform_login_status
        from config import is_platform_enabled
        status = get_platform_login_status()

        def _fmt(plat: str) -> str:
            if not is_platform_enabled(plat):
                return "[dim]Disabled[/dim]"
            return "[green]✓ Signed in[/green]" if status.get(plat) else "[red]✗ Not signed in[/red]"

        moodle_lbl = _fmt("moodle")
        teams_lbl = _fmt("teams")
        untis_lbl = _fmt("untis")

        with Vertical(id="login_reminder_dialog"):
            yield Label("🔑 Action Required: Service Logins", id="login_reminder_title")
            yield Label(
                "One or more school services are not connected.\n"
                "Sign in to detect and synchronize all homework and absences:",
                id="login_reminder_desc",
            )
            with Vertical(id="login_reminder_box"):
                with Horizontal(classes="login_platform_row"):
                    yield Label("🎓 Moodle:", classes="login_platform_name")
                    yield Label(moodle_lbl, classes="login_platform_status")
                with Horizontal(classes="login_platform_row"):
                    yield Label("👥 Microsoft Teams:", classes="login_platform_name")
                    yield Label(teams_lbl, classes="login_platform_status")
                with Horizontal(classes="login_platform_row"):
                    yield Label("📅 WebUntis:", classes="login_platform_name")
                    yield Label(untis_lbl, classes="login_platform_status")
            with Horizontal(id="login_reminder_buttons"):
                yield Button("🔑 Open Login Menu [ENTER]", id="btn_open_login_menu", variant="primary")
                yield Button("Dismiss [ESC]", id="btn_dismiss_login", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_open_login_menu":
            self.dismiss("open_logins")
        elif bid == "btn_dismiss_login":
            self.dismiss(None)

    def action_open_logins(self) -> None:
        self.dismiss("open_logins")

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class LoginChoiceModal(ModalScreen[Optional[str]]):
    """Selection dialog for login (Teams, Moodle, WebUntis, Git) with combined Activate/Deactivate/Logout action buttons."""

    DEFAULT_CSS = """
    LoginChoiceModal {
        align: center middle;
    }
    #login_choice_dialog {
        width: 76;
        height: auto;
        border: thick #fab387;
        background: #1e1e2e;
        padding: 1 2;
    }
    #login_choice_title {
        text-align: center;
        text-style: bold;
        color: #fab387;
        margin-bottom: 1;
    }
    .login_choice_row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    .login_choice_btn {
        width: 28;
    }
    .login_status_lbl {
        width: 22;
        margin-left: 2;
        padding-top: 1;
        text-style: bold;
    }
    .login_action_btn {
        width: 15;
        min-width: 14;
        margin-left: 1;
        padding: 0 1;
    }
    #btn_login_cancel {
        width: 100%;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("1", "choose_teams", "Teams Login", show=False),
        Binding("t", "choose_teams", "Teams Login", show=False),
        Binding("2", "choose_moodle", "Moodle Login", show=False),
        Binding("m", "choose_moodle", "Moodle Login", show=False),
        Binding("3", "choose_untis", "Untis Login", show=False),
        Binding("u", "choose_untis", "Untis Login", show=False),
        Binding("4", "choose_git", "Git Sync", show=False),
        Binding("g", "choose_git", "Git Sync", show=False),
        Binding("escape", "cancel", "Back"),
    ]

    def _is_teams_logged_in(self) -> bool:
        from auth import is_teams_logged_in
        return is_teams_logged_in()

    def _is_moodle_logged_in(self) -> bool:
        from auth import is_moodle_logged_in
        return is_moodle_logged_in()

    def _is_untis_logged_in(self) -> bool:
        from auth import is_untis_logged_in
        return is_untis_logged_in()

    def _is_git_logged_in(self) -> bool:
        try:
            from git_sync_service import is_git_configured
            return is_git_configured()
        except Exception:
            return False

    def _is_plat_logged_in(self, plat: str) -> bool:
        if plat == "teams":
            return self._is_teams_logged_in()
        elif plat == "moodle":
            return self._is_moodle_logged_in()
        elif plat == "untis":
            return self._is_untis_logged_in()
        elif plat == "git":
            return self._is_git_logged_in()
        return False

    def _get_platform_info(self, plat: str) -> Tuple[bool, str, bool]:
        from config import is_platform_enabled
        enabled = is_platform_enabled(plat)
        logged_in = self._is_plat_logged_in(plat)

        if not enabled:
            return False, "[dim]Disabled[/dim]", False

        if logged_in:
            lbl = "[green]Signed in ✓[/green]" if plat != "git" else "[green]Connected ✓[/green]"
            return True, lbl, True
        else:
            lbl = "[red]Not signed in ✗[/red]" if plat != "git" else "[dim]Not configured ✗[/dim]"
            return True, lbl, False

    def _get_action_btn_props(self, plat: str) -> Tuple[str, str]:
        from config import is_platform_enabled
        enabled = is_platform_enabled(plat)
        logged_in = self._is_plat_logged_in(plat)

        if logged_in:
            return "🚪 Log Out", "error"
        elif not enabled:
            return "Enable", "success"
        else:
            return "Disable", "default"

    def compose(self) -> ComposeResult:
        with Vertical(id="login_choice_dialog"):
            yield Label("🔑 Select Login / Platform", id="login_choice_title")

            # 1. Teams
            t_enabled, t_lbl, t_logged = self._get_platform_info("teams")
            t_act_lbl, t_act_var = self._get_action_btn_props("teams")
            with Horizontal(classes="login_choice_row"):
                yield Button("👥 Teams [1/T]", id="btn_login_teams", classes="login_choice_btn", variant="primary", disabled=not t_enabled)
                yield Label(t_lbl, id="lbl_status_teams", classes="login_status_lbl")
                yield Button(t_act_lbl, id="btn_action_teams", classes="login_action_btn", variant=t_act_var)

            # 2. Moodle
            m_enabled, m_lbl, m_logged = self._get_platform_info("moodle")
            m_act_lbl, m_act_var = self._get_action_btn_props("moodle")
            with Horizontal(classes="login_choice_row"):
                yield Button("🎓 Moodle [2/M]", id="btn_login_moodle", classes="login_choice_btn", variant="warning", disabled=not m_enabled)
                yield Label(m_lbl, id="lbl_status_moodle", classes="login_status_lbl")
                yield Button(m_act_lbl, id="btn_action_moodle", classes="login_action_btn", variant=m_act_var)

            # 3. Untis
            u_enabled, u_lbl, u_logged = self._get_platform_info("untis")
            u_act_lbl, u_act_var = self._get_action_btn_props("untis")
            with Horizontal(classes="login_choice_row"):
                yield Button("📅 Untis [3/U]", id="btn_login_untis", classes="login_choice_btn", variant="success", disabled=not u_enabled)
                yield Label(u_lbl, id="lbl_status_untis", classes="login_status_lbl")
                yield Button(u_act_lbl, id="btn_action_untis", classes="login_action_btn", variant=u_act_var)

            # 4. Git (Clean single row without toggle/logout buttons)
            g_enabled, g_lbl, g_logged = self._get_platform_info("git")
            with Horizontal(classes="login_choice_row"):
                yield Button("🐙 Git Sync [4/G]", id="btn_login_git", classes="login_choice_btn", variant="default")
                yield Label(g_lbl, id="lbl_status_git", classes="login_status_lbl")

            yield Button("↩️ Back [ESC]", id="btn_login_cancel", variant="default")

    def _refresh_row_status(self, plat: str) -> None:
        try:
            enabled, lbl_text, logged_in = self._get_platform_info(plat)
            lbl = self.query_one(f"#lbl_status_{plat}", Label)
            lbl.update(lbl_text)

            btn_login = self.query_one(f"#btn_login_{plat}", Button)
            btn_login.disabled = not enabled

            if plat in ("teams", "moodle", "untis"):
                action_lbl, action_var = self._get_action_btn_props(plat)
                btn_action = self.query_one(f"#btn_action_{plat}", Button)
                btn_action.label = action_lbl
                btn_action.variant = action_var
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if not bid:
            return
        if bid in ("btn_action_teams", "btn_action_moodle", "btn_action_untis"):
            plat = bid.replace("btn_action_", "")
            from config import is_platform_enabled, load_enabled_platforms, save_enabled_platforms
            if self._is_plat_logged_in(plat):
                if plat == "teams":
                    self._handle_logout_teams()
                elif plat == "moodle":
                    self._handle_logout_moodle()
                elif plat == "untis":
                    self._handle_logout_untis()
            else:
                is_enabled = is_platform_enabled(plat)
                enabled = load_enabled_platforms()
                enabled[plat] = not is_enabled
                save_enabled_platforms(enabled)
                self._refresh_row_status(plat)
        elif bid == "btn_login_teams":
            self.dismiss("teams")
        elif bid == "btn_login_moodle":
            self.dismiss("moodle")
        elif bid == "btn_login_untis":
            self.dismiss("untis")
        elif bid == "btn_login_git":
            self.dismiss("git")
        elif bid == "btn_login_cancel":
            self.dismiss(None)

    def _handle_logout_teams(self) -> None:
        from auth import logout_teams
        mgr = getattr(self.app, "mgr", None)
        ok, msg = logout_teams(mgr)
        if hasattr(self.app, "notify"):
            self.app.notify(msg, title="Logged Out", severity="information")
        self._refresh_row_status("teams")
        if hasattr(self.app, "refresh_table"):
            self.app.refresh_table()

    def _handle_logout_moodle(self) -> None:
        from auth import logout_moodle
        mgr = getattr(self.app, "mgr", None)
        ok, msg = logout_moodle(mgr)
        if hasattr(self.app, "notify"):
            self.app.notify(msg, title="Logged Out", severity="information")
        self._refresh_row_status("moodle")
        if hasattr(self.app, "refresh_table"):
            self.app.refresh_table()

    def _handle_logout_untis(self) -> None:
        from auth import logout_untis
        ok, msg = logout_untis()
        if hasattr(self.app, "notify"):
            self.app.notify(msg, title="Logged Out", severity="information")
        self._refresh_row_status("untis")

    def action_choose_teams(self) -> None:
        from config import is_platform_enabled
        if is_platform_enabled("teams"):
            self.dismiss("teams")

    def action_choose_moodle(self) -> None:
        from config import is_platform_enabled
        if is_platform_enabled("moodle"):
            self.dismiss("moodle")

    def action_choose_untis(self) -> None:
        from config import is_platform_enabled
        if is_platform_enabled("untis"):
            self.dismiss("untis")

    def action_choose_git(self) -> None:
        from config import is_platform_enabled
        if is_platform_enabled("git"):
            self.dismiss("git")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class GitSetupModal(ModalScreen[bool]):
    """Git Cloud-Sync Setup dialog (Repo URL, Token, Branch, Test & Sync)."""

    DEFAULT_CSS = """
    GitSetupModal {
        align: center middle;
    }
    #git_setup_dialog {
        width: 76;
        height: auto;
        border: thick #a6e3a1;
        background: #1e1e2e;
        padding: 1 2;
    }
    #git_setup_title {
        text-align: center;
        text-style: bold;
        color: #a6e3a1;
        margin-bottom: 1;
    }
    #git_setup_desc {
        color: #cdd6f4;
        text-align: center;
    }
    #git_setup_guide_link {
        color: #89b4fa;
        margin-bottom: 1;
        text-align: center;
    }
    .git_field_label {
        color: #fab387;
        text-style: bold;
        margin-top: 1;
    }
    .git_field {
        margin-bottom: 1;
    }
    #git_token_row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    #inp_git_token {
        width: 48;
    }
    #btn_git_toggle_token {
        width: 14;
        margin-left: 1;
    }
    #git_status {
        margin: 1 0;
        text-align: center;
        text-style: bold;
    }
    #git_buttons_top {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #git_buttons_top Button {
        margin: 0 1;
    }
    #git_buttons_bottom {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #git_buttons_bottom Button {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="git_setup_dialog"):
            yield Label("🐙 Git Cloud-Sync Setup", id="git_setup_title")
            yield Label(
                "Synchronize assignments, exams & notes via private Git repository.",
                id="git_setup_desc",
            )
            yield Label(
                "https://github.com/X4nd109/Tasks/blob/main/docs/tutorials/git-sync.md",
                id="git_setup_guide_link",
            )
            yield Label("Repository HTTPS URL:", classes="git_field_label")
            yield Input(placeholder="https://github.com/user/my-backup.git", id="inp_git_url", classes="git_field")

            yield Label("Personal Access Token (PAT):", classes="git_field_label")
            with Horizontal(id="git_token_row"):
                yield Input(placeholder="ghp_xxxxxxxxxxxxxxxxxxxx (optional)", password=True, id="inp_git_token")
                yield Button("👁️ Show", id="btn_git_toggle_token", variant="default")

            yield Label("Branch:", classes="git_field_label")
            yield Input(value="main", placeholder="main", id="inp_git_branch", classes="git_field")

            yield Label("", id="git_status")

            with Horizontal(id="git_buttons_top"):
                yield Button("🚀 Test & Connect", id="btn_git_save_sync", variant="primary")
                yield Button("🗑️ Disconnect", id="btn_git_disconnect", variant="error")
            with Horizontal(id="git_buttons_bottom"):
                yield Button("↩️ Back [ESC]", id="btn_git_close", variant="default")

    def on_mount(self) -> None:
        from config import get_git_sync_config
        cfg = get_git_sync_config()
        if cfg.get("repo_url"):
            try:
                self.query_one("#inp_git_url", Input).value = cfg.get("repo_url", "")
            except Exception:
                pass
        if cfg.get("token"):
            try:
                self.query_one("#inp_git_token", Input).value = cfg.get("token", "")
            except Exception:
                pass
        if cfg.get("branch"):
            try:
                self.query_one("#inp_git_branch", Input).value = cfg.get("branch", "main")
            except Exception:
                pass

        if cfg.get("enabled") and cfg.get("repo_url"):
            last_s = cfg.get("last_sync") or "Never"
            if last_s != "Never":
                try:
                    dt = datetime.datetime.fromisoformat(last_s)
                    last_s = dt.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    pass
            self.query_one("#git_status", Label).update(f"[green]Connected ✓ (Last Sync: {last_s})[/green]")
        else:
            try:
                self.query_one("#btn_git_disconnect", Button).disabled = True
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_git_close":
            self.dismiss(False)
        elif bid == "btn_git_toggle_token":
            inp = self.query_one("#inp_git_token", Input)
            btn = self.query_one("#btn_git_toggle_token", Button)
            inp.password = not inp.password
            btn.label = "🔒 Hide" if not inp.password else "👁️ Show"
        elif bid == "btn_git_disconnect":
            self._disconnect_git()
        elif bid == "btn_git_save_sync":
            self._save_and_sync()

    def _disconnect_git(self) -> None:
        from git_sync_service import GitSyncService
        self.query_one("#git_status", Label).update("[yellow]Disconnecting Git connection...[/yellow]")
        ok, msg = GitSyncService.disconnect()
        self.app.notify(msg, severity="information")
        self.dismiss(True)

    def _save_and_sync(self) -> None:
        repo_url = self.query_one("#inp_git_url", Input).value.strip()
        token = self.query_one("#inp_git_token", Input).value.strip()
        branch = self.query_one("#inp_git_branch", Input).value.strip() or "main"

        if not repo_url:
            self.query_one("#git_status", Label).update("[red]Please enter a repository URL![/red]")
            return

        if not repo_url.startswith("http://") and not repo_url.startswith("https://"):
            self.query_one("#git_status", Label).update("[red]URL must start with https://![/red]")
            return

        self.query_one("#git_status", Label).update("[yellow]Connecting and synchronizing...[/yellow]")
        btn_save = self.query_one("#btn_git_save_sync", Button)
        btn_save.disabled = True

        def worker():
            try:
                from git_sync_service import GitSyncService
                ok, msg = GitSyncService.setup_repository(repo_url=repo_url, token=token, branch=branch)
            except Exception as e:
                ok, msg = False, f"Connection error: {e}"

            def update_ui():
                try:
                    btn_save.disabled = False
                    if ok:
                        self.app.notify(f"✓ {msg}", severity="information")
                        self.dismiss(True)
                    else:
                        self.query_one("#git_status", Label).update(f"[red]✗ {msg}[/red]")
                except Exception:
                    pass

            try:
                self.app.call_from_thread(update_ui)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name="GitSetupWorker").start()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)



class UntisSetupModal(ModalScreen[bool]):
    """WebUntis Direct API Setup & Login dialog."""

    DEFAULT_CSS = """
    UntisSetupModal {
        align: center middle;
    }
    #untis_dialog {
        width: 62;
        height: auto;
        border: thick #b4befe;
        background: #1e1e2e;
        padding: 1 2;
    }
    #untis_title {
        text-align: center;
        text-style: bold;
        color: #b4befe;
        margin-bottom: 1;
    }
    #untis_desc {
        color: #cdd6f4;
        margin-bottom: 1;
        text-align: center;
    }
    .untis_field {
        margin-bottom: 1;
    }
    #untis_status {
        margin: 1 0;
        text-align: center;
    }
    #untis_buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #untis_buttons Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="untis_dialog"):
            yield Label("📅 WebUntis API Connection", id="untis_title")
            yield Label("Sign in with your school account:", id="untis_desc")
            yield Input(placeholder="School name (default: spengergasse)", id="inp_u_school", classes="untis_field")
            yield Input(placeholder="Username", id="inp_u_user", classes="untis_field")
            yield Input(placeholder="Password", password=True, id="inp_u_pass", classes="untis_field")
            yield Label("", id="untis_status")
            with Horizontal(id="untis_buttons"):
                yield Button("🔐 Log In", id="btn_u_login", variant="primary")
                yield Button("⚡ Use Moodle Account", id="btn_u_existing", variant="success")
                yield Button("↩️ Back [ESC]", id="btn_u_close", variant="default")

    def on_mount(self) -> None:
        from auth import get_existing_moodle_credentials, get_existing_untis_credentials
        path, creds = get_existing_moodle_credentials()
        if not creds:
            path, creds = get_existing_untis_credentials()
        if not creds:
            try:
                self.query_one("#btn_u_existing", Button).display = False
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_u_close":
            self.dismiss(False)
        elif bid == "btn_u_login":
            self._start_login()
        elif bid == "btn_u_existing":
            self._use_existing()

    def _start_login(self) -> None:
        sch = self.query_one("#inp_u_school", Input).value.strip()
        u = self.query_one("#inp_u_user", Input).value.strip()
        p = self.query_one("#inp_u_pass", Input).value.strip()
        if not sch:
            from config import _load_untis_school, UNTIS_SCHOOL
            sch = _load_untis_school() or UNTIS_SCHOOL or "spengergasse"
        if not u or not p:
            self.query_one("#untis_status", Label).update("[red]Please enter username and password.[/red]")
            return

        self.query_one("#untis_status", Label).update("[yellow]Authenticating with WebUntis API...[/yellow]")
        self.query_one("#btn_u_login", Button).disabled = True

        def worker():
            from untis_service import login_untis_direct
            res = login_untis_direct(u, p, school=sch)
            def update_ui():
                self.query_one("#btn_u_login", Button).disabled = False
                if res.success:
                    self.app.notify("✓ WebUntis connected successfully!", severity="information")
                    self.dismiss(True)
                else:
                    err = res.message or "Login failed. Please check school and credentials."
                    self.query_one("#untis_status", Label).update(f"[red]✗ {err}[/red]")
            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="UntisLoginWorker").start()

    def _use_existing(self) -> None:
        sch = self.query_one("#inp_u_school", Input).value.strip()
        if not sch:
            from config import _load_untis_school
            sch = _load_untis_school()
            if sch:
                self.query_one("#inp_u_school", Input).value = sch
            else:
                self.query_one("#untis_status", Label).update("[red]Please enter your school name.[/red]")
                return
        from auth import get_existing_moodle_credentials, get_existing_untis_credentials
        path, creds = get_existing_moodle_credentials()
        if not creds:
            path, creds = get_existing_untis_credentials()
        if not creds:
            self.query_one("#untis_status", Label).update("[red]No saved Moodle credentials found.[/red]")
            return

        u = creds.get("username", "").strip()
        p = creds.get("password", "").strip()
        self.query_one("#inp_u_user", Input).value = u
        self.query_one("#untis_status", Label).update("[yellow]Verifying Moodle credentials with WebUntis...[/yellow]")
        self.query_one("#btn_u_existing", Button).disabled = True

        def worker():
            from untis_service import login_untis_direct
            res = login_untis_direct(u, p, school=sch)
            def update_ui():
                self.query_one("#btn_u_existing", Button).disabled = False
                if res.success:
                    self.app.notify("✓ WebUntis connected successfully!", severity="information")
                    self.dismiss(True)
                else:
                    err = res.message or "Moodle credentials invalid for WebUntis."
                    self.query_one("#untis_status", Label).update(f"[red]✗ {err}[/red]")
            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="UntisExistingWorker").start()

    def key_escape(self) -> None:
        self.dismiss(False)



class AbsencesScreen(ModalScreen[None]):
    """Full-screen view for WebUntis absences and missed lessons."""

    DEFAULT_CSS = """
    AbsencesScreen {
        layout: vertical;
        background: $background;
        padding: 0;
        overflow-y: hidden;
    }
    #abs_header {
        dock: top;
        height: 3;
        padding: 0 1;
        align: center middle;
    }
    #abs_title {
        text-style: bold;
        content-align: left middle;
        height: 100%;
        width: auto;
    }
    #abs_sub_info {
        text-style: bold;
        content-align: right middle;
        height: 100%;
        width: 1fr;
    }
    #abs_split_container {
        height: 1fr;
        layout: vertical;
        overflow-y: hidden;
        padding: 0;
        margin: 0;
    }
    #abs_subject_box {
        height: 1fr;
        padding: 0 1;
        margin: 0;
    }
    #abs_detail_box {
        height: 1fr;
        padding: 0 1;
        margin: 0;
    }
    .abs_box_title {
        text-style: bold;
        margin-bottom: 0;
    }
    #abs_subject_table {
        height: 1fr;
    }
    #abs_detail_table {
        height: 1fr;
    }
    #abs_button_bar {
        dock: bottom;
        height: 3;
        width: 100%;
        align: left middle;
        padding: 0 1;
        overflow-x: hidden;
        overflow-y: hidden;
    }
    #abs_left_buttons {
        width: 1fr;
        height: 100%;
        align: left middle;
    }
    #abs_button_bar Button {
        margin: 0 1;
        min-width: 4;
        height: 100%;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back to Tasks"),
        Binding("t", "dismiss_screen", "Back to Tasks"),
        Binding("r", "sync_untis", "Sync"),
        Binding("g", "toggle_group", "Toggle Group"),
        Binding("e", "excuse_letter", "Excuse Letter"),
    ]

    def __init__(self):
        super().__init__()
        self.summaries: List[SubjectAbsenceSummary] = []
        self.selected_subject: Optional[str] = None
        self._is_syncing: bool = False
        full_cfg = load_full_school_config()
        self.current_group: str = (full_cfg.get("untis_group") or "X").strip().upper()
        self.current_class: str = (full_cfg.get("student_class") or "1AHIT").strip()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="abs_header"):
            yield Label("📅 WebUntis Missed Lessons", id="abs_title")
            yield Label("", id="abs_sub_info")

        with Vertical(id="abs_split_container"):
            with Vertical(id="abs_subject_box"):
                yield Label("📚 Missed Hours per Subject", classes="abs_box_title")
                yield DataTable(id="abs_subject_table", cursor_type="row")
            with Vertical(id="abs_detail_box"):
                yield Label("Details", id="abs_detail_title", classes="abs_box_title")
                yield DataTable(id="abs_detail_table", cursor_type="row")

        with Horizontal(id="abs_button_bar"):
            with Horizontal(id="abs_left_buttons"):
                yield Button("🔄 Sync Untis", id="btn_abs_sync", variant="success", tooltip="Sync Untis [R]")
                yield Button("📝 Excuse Letter", id="btn_abs_excuse", variant="warning", tooltip="Excuse Letter [E]")
            yield Button("↩️ Back", id="btn_abs_back", variant="default", tooltip="Back to tasks [T/Esc]")


    def on_mount(self) -> None:
        sub_dt = self.query_one("#abs_subject_table", DataTable)
        sub_dt.cell_padding = 2
        sub_dt.add_columns("#", "Subject", "Missed Hours", "Last Missed Date")

        det_dt = self.query_one("#abs_detail_table", DataTable)
        det_dt.cell_padding = 2
        det_dt.add_columns("#", "Date", "Time", "Teacher", "Room", "Reason", "Status")

        self.summaries = load_untis_cache()
        self.refresh_tables()

    def refresh_tables(self) -> None:
        sub_dt = self.query_one("#abs_subject_table", DataTable)
        sub_dt.clear()

        full_cfg = load_full_school_config()
        self.current_group = (full_cfg.get("untis_group") or "X").strip().upper()
        self.current_class = (full_cfg.get("student_class") or "1AHIT").strip()

        total_hours = sum(s.total_hours for s in self.summaries)
        info_label = self.query_one("#abs_sub_info", Label)
        info_label.update(f"Missed Hours: [bold red]{total_hours}[/bold red]  |  Class: {self.current_class}  |  Group: {self.current_group}")

        if not self.summaries:
            self.refresh_detail_table(None)
            return

        for idx, s in enumerate(self.summaries, 1):
            hours_str = f"{s.total_hours} hour" if s.total_hours == 1 else f"{s.total_hours} hours"
            sub_dt.add_row(
                str(idx),
                Text(s.subject, style="bold cyan"),
                Text(hours_str, style="bold red" if s.total_hours >= 5 else "bold yellow"),
                s.last_date or "-",
                height=2,
                key=s.subject,
            )

        target = self.selected_subject or self.summaries[0].subject
        self.selected_subject = target
        self.refresh_detail_table(target)

    def refresh_detail_table(self, subject: Optional[str]) -> None:
        det_dt = self.query_one("#abs_detail_table", DataTable)
        det_dt.clear()

        title_lbl = self.query_one("#abs_detail_title", Label)
        title_lbl.update("Details")

        if not subject:
            return

        summary = next((s for s in self.summaries if s.subject == subject), None)
        if not summary:
            return

        for idx, m in enumerate(summary.missed_lessons, 1):
            time_str = f"{m.start_time} - {m.end_time}"
            status_style = "green" if any(w in m.absence_status.lower() for w in ["entschuldigt", "excused"]) else "yellow"
            det_dt.add_row(
                str(idx),
                Text(m.date, style="bold"),
                time_str,
                m.teacher or "-",
                m.room or "-",
                m.reason or "Absent",
                Text(m.absence_status, style=status_style),
                height=2,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "abs_subject_table" and event.row_key:
            subj = event.row_key.value
            self.selected_subject = subj
            self.refresh_detail_table(subj)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "abs_subject_table" and event.row_key:
            subj = event.row_key.value
            self.selected_subject = subj
            self.refresh_detail_table(subj)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_abs_back":
            self.action_dismiss_screen()
        elif bid == "btn_abs_sync":
            self.action_sync_untis()
        elif bid == "btn_abs_group":
            self.action_toggle_group()
        elif bid == "btn_abs_excuse":
            self.action_excuse_letter()

    def action_dismiss_screen(self) -> None:
        self.dismiss()

    def action_excuse_letter(self) -> None:
        self.app.push_screen(ExcuseLetterModal(self.summaries))

    def action_sync_untis(self) -> None:
        if self._is_syncing:
            return
        self._is_syncing = True
        self.app.notify("🔄 Synchronizing WebUntis absences and timetable...", severity="information")
        self.query_one("#btn_abs_sync", Button).disabled = True

        def worker():
            ok, msg, res = sync_untis_data(headless=True)
            def update_ui():
                self._is_syncing = False
                self.query_one("#btn_abs_sync", Button).disabled = False
                if ok:
                    self.summaries = res
                    self.refresh_tables()
                    self.app.notify(f"✓ {msg}", severity="information")
                else:
                    self.app.notify(f"! {msg}", severity="warning")
            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="UntisSyncWorker").start()

    def action_toggle_group(self) -> None:
        new_grp = "Y" if self.current_group.upper() == "X" else "X"
        self.current_group = new_grp
        save_untis_group(new_grp)
        try:
            self.query_one("#btn_abs_group", Button).label = f"⚙️ Group: {new_grp}"
        except Exception:
            pass
        self.refresh_tables()
        self.app.notify(f"Untis group set to {new_grp}. Re-syncing...", severity="information")
        self.action_sync_untis()


class SchoolConfigModal(ModalScreen[bool]):
    """Modal for configuring student and school profile across all modules."""

    DEFAULT_CSS = """
    SchoolConfigModal {
        align: center middle;
    }
    #school_config_dialog {
        width: 72;
        max-height: 90%;
        height: auto;
        border: thick #fab387;
        background: #1e1e2e;
        padding: 1 2;
    }
    #school_config_title {
        text-align: center;
        text-style: bold;
        color: #fab387;
        margin-bottom: 1;
    }
    #cfg_scroll {
        max-height: 16;
        height: auto;
        scrollbar-gutter: stable;
        padding-right: 1;
    }
    .cfg_section_title {
        color: #b4befe;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    .cfg_label {
        color: #cdd6f4;
        margin-top: 1;
        text-style: bold;
    }
    .cfg_input {
        margin-bottom: 0;
    }
    #cfg_group_row {
        height: auto;
        align: left middle;
        margin-top: 1;
        margin-bottom: 0;
    }
    #cfg_group_label {
        color: #cdd6f4;
        text-style: bold;
        margin-right: 2;
        height: 3;
        content-align: left middle;
    }
    #btn_cfg_group {
        min-width: 16;
    }
    #cfg_buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #cfg_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
        Binding("g", "toggle_group", "Toggle Group"),
    ]

    def __init__(self):
        super().__init__()
        self.config_data = load_full_school_config()
        self.current_group = "X" if "x" in str(self.config_data.get("untis_group", "X")).lower() else "Y"

    def compose(self) -> ComposeResult:
        with Vertical(id="school_config_dialog"):
            yield Label("⚙️ School & Student Configuration", id="school_config_title")
            with VerticalScroll(id="cfg_scroll"):
                yield Label("👤 Student Details", classes="cfg_section_title")
                yield Label("Student Name:", classes="cfg_label")
                yield Input(value=self.config_data.get("student_name", ""), placeholder="e.g. Max Mustermann", id="inp_cfg_name", classes="cfg_input")

                yield Label("Class:", classes="cfg_label")
                yield Input(value=self.config_data.get("student_class", ""), placeholder="e.g. 1AHIT", id="inp_cfg_class", classes="cfg_input")

                with Horizontal(id="cfg_group_row"):
                    yield Label("Group:", id="cfg_group_label")
                    yield Button(f"⚙️ Group: {self.current_group}", id="btn_cfg_group", variant="primary", tooltip="Click or press 'g' to toggle group")

                yield Label("🏫 School & Absence Details", classes="cfg_section_title")
                yield Label("Untis School Name:", classes="cfg_label")
                yield Input(value=self.config_data.get("untis_school", ""), placeholder="e.g. beispiel-schule", id="inp_cfg_school", classes="cfg_input")

                yield Label("Class Teacher:", classes="cfg_label")
                yield Input(value=self.config_data.get("teacher_name", ""), placeholder="e.g. Prof. Erika Musterlehrer", id="inp_cfg_teacher", classes="cfg_input")

                yield Label("School Address:", classes="cfg_label")
                yield Input(value=self.config_data.get("school_address", ""), placeholder="e.g. Musterstraße 1", id="inp_cfg_address", classes="cfg_input")

                yield Label("Postal Code & City:", classes="cfg_label")
                yield Input(value=self.config_data.get("school_district", ""), placeholder="e.g. A-1010 Wien", id="inp_cfg_district", classes="cfg_input")

            with Horizontal(id="cfg_buttons"):
                yield Button("💾 Save Configuration", id="btn_cfg_save", variant="success")
                yield Button("↩️ Back", id="btn_cfg_cancel", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid in ("btn_cfg_save", "btn_ep_save"):
            self._save()
        elif bid in ("btn_cfg_cancel", "btn_ep_cancel"):
            self.dismiss(False)
        elif bid == "btn_cfg_group":
            self.action_toggle_group()

    def action_toggle_group(self) -> None:
        self.current_group = "Y" if self.current_group == "X" else "X"
        try:
            self.query_one("#btn_cfg_group", Button).label = f"⚙️ Group: {self.current_group}"
        except Exception:
            pass

    def _save(self) -> None:
        s_name = self.query_one("#inp_cfg_name", Input).value.strip()
        s_class = self.query_one("#inp_cfg_class", Input).value.strip()
        u_school = self.query_one("#inp_cfg_school", Input).value.strip()
        t_name = self.query_one("#inp_cfg_teacher", Input).value.strip()
        s_addr = self.query_one("#inp_cfg_address", Input).value.strip()
        s_dist = self.query_one("#inp_cfg_district", Input).value.strip()

        data = {
            "student_name": s_name,
            "student_class": s_class,
            "untis_group": self.current_group,
            "untis_school": u_school,
            "teacher_name": t_name,
            "school_address": s_addr,
            "school_district": s_dist,
        }
        save_full_school_config(data)
        self.app.notify("✓ School & student configuration saved!", severity="information")
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


ExcuseProfileModal = SchoolConfigModal


class ExcuseLetterModal(ModalScreen[None]):
    """Modal for selecting absence days via checkboxes and generating the official PDF."""

    DEFAULT_CSS = """
    ExcuseLetterModal {
        align: center middle;
    }
    #excuse_dialog {
        width: 92%;
        max-width: 105;
        height: 85%;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
        layout: vertical;
    }
    #excuse_title {
        text-align: center;
        text-style: bold;
        color: #89b4fa;
        margin-bottom: 0;
    }
    #excuse_profile_bar {
        height: 3;
        width: 100%;
        margin-bottom: 0;
        align: left middle;
    }
    #excuse_profile_info {
        width: 1fr;
        color: #a6adc8;
        content-align: left middle;
    }
    #excuse_actions_bar {
        height: 3;
        width: 100%;
        align: left middle;
        margin-bottom: 1;
    }
    #excuse_actions_bar Button {
        margin-right: 1;
        min-width: 12;
    }
    #excuse_table {
        height: 1fr;
        margin-bottom: 1;
    }
    #excuse_footer_bar {
        height: 3;
        width: 100%;
        align: left middle;
    }
    #excuse_footer_left {
        width: 1fr;
        height: 100%;
        align: left middle;
    }
    #excuse_footer_bar Button {
        margin-right: 1;
    }
    #btn_el_filter_lateness {
        margin-right: 0;
    }
    #excuse_count_lbl {
        width: 1fr;
        text-align: right;
        color: #fab387;
        text-style: bold;
        content-align: right middle;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_selected_row", "Toggle Row", show=False),
        Binding("a", "select_all", "Select All", show=False),
        Binding("o", "select_open", "Only Open", show=False),
        Binding("c", "clear_all", "Clear", show=False),
        Binding("p", "generate_pdf", "Generate PDF", show=False),
        Binding("l", "toggle_lateness", "Hide Lateness", show=False),
        Binding("escape", "cancel", "Back"),
    ]

    def __init__(self, summaries: Optional[List[SubjectAbsenceSummary]] = None):
        super().__init__()
        self.summaries = summaries or load_untis_cache()
        self.all_daily_absences: List[DailyAbsenceSummary] = get_daily_absence_summaries(self.summaries)
        self.hide_lateness: bool = True
        self.profile = load_excuse_profile()
        open_dates = {d.date for d in self.visible_absences if any(w in d.status.lower() for w in ["offen", "open"])}
        if open_dates:
            self.selected_dates: Set[str] = set(open_dates)
        else:
            self.selected_dates = {d.date for d in self.visible_absences}

    @staticmethod
    def _get_day_minutes(d: DailyAbsenceSummary) -> int:
        if d.duration_str and ":" in d.duration_str:
            try:
                parts = d.duration_str.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            except Exception:
                return d.school_hours * 50
        return d.school_hours * 50

    @property
    def visible_absences(self) -> List[DailyAbsenceSummary]:
        if self.hide_lateness:
            return [d for d in self.all_daily_absences if self._get_day_minutes(d) >= 50]
        return list(self.all_daily_absences)

    @property
    def daily_absences(self) -> List[DailyAbsenceSummary]:
        return self.visible_absences

    def compose(self) -> ComposeResult:
        with Vertical(id="excuse_dialog"):
            yield Label("📝 WebUntis Excuse Letter Generator", id="excuse_title")

            with Horizontal(id="excuse_profile_bar"):
                yield Label("", id="excuse_profile_info")
                yield Button("⚙️ Edit Profile", id="btn_el_profile", variant="primary", tooltip="Edit Profile Settings")

            with Horizontal(id="excuse_actions_bar"):
                yield Button("☑️ Select All", id="btn_el_all", variant="default", tooltip="Select All")
                yield Button("⚡ Only Open", id="btn_el_open", variant="warning", tooltip="Only Open")
                yield Button("◻️ Clear All", id="btn_el_clear", variant="default", tooltip="Clear All")
                yield Label("", id="excuse_count_lbl")

            yield DataTable(id="excuse_table", cursor_type="row")

            with Horizontal(id="excuse_footer_bar"):
                with Horizontal(id="excuse_footer_left"):
                    yield Button("🖨️ Generate PDF", id="btn_el_generate", variant="success", tooltip="Generate & Open PDF")
                    yield Button("↩️ Back", id="btn_el_back", variant="default", tooltip="Back")
                yield Button("⏳ Hide Lateness: ON", id="btn_el_filter_lateness", variant="primary", tooltip="Click to show lateness (< 50 min)")

    def on_mount(self) -> None:
        self._update_profile_label()
        dt = self.query_one("#excuse_table", DataTable)
        dt.cell_padding = 2
        dt.add_columns("Sel", "#", "Date", "Periods", "Duration", "Subjects", "Status")
        self.refresh_table()

    def _update_profile_label(self) -> None:
        info_lbl = self.query_one("#excuse_profile_info", Label)
        info_lbl.update(
            f"Student: [bold cyan]{self.profile.get('student_name', '')}[/] | "
            f"Class: [bold cyan]{self.profile.get('student_class', '')}[/] | "
            f"School: [bold cyan]{self.profile.get('school_address', '')}[/]"
        )

    def refresh_table(self) -> None:
        dt = self.query_one("#excuse_table", DataTable)
        dt.clear()

        total_sel_hours = 0
        total_sel_mins = 0

        for idx, d in enumerate(self.visible_absences, 1):
            is_sel = d.date in self.selected_dates
            sel_badge = Text("[X]", style="bold green") if is_sel else Text("[ ]", style="dim")
            if is_sel:
                total_sel_hours += d.school_hours
                day_mins = self._get_day_minutes(d)
                total_sel_mins += day_mins

            status_style = "green" if any(w in d.status.lower() for w in ["entschuldigt", "excused"]) else "yellow"
            subjs_str = ", ".join(d.subjects) if d.subjects else "-"

            dt.add_row(
                sel_badge,
                str(idx),
                Text(d.date_display, style="bold"),
                f"{d.school_hours} periods",
                d.duration_str,
                subjs_str,
                Text(d.status, style=status_style),
                height=2,
                key=d.date,
            )

        sel_visible_count = len([d for d in self.visible_absences if d.date in self.selected_dates])
        day_str = "day" if sel_visible_count == 1 else "days"
        dur_h = total_sel_mins // 60
        dur_m = total_sel_mins % 60
        dur_str = f"{dur_h}:{dur_m:02d}"
        cnt_lbl = self.query_one("#excuse_count_lbl", Label)
        cnt_lbl.update(f"Selected: [bold green]{sel_visible_count} {day_str}[/] ({total_sel_hours} periods | {dur_str})")

        try:
            btn_lat = self.query_one("#btn_el_filter_lateness", Button)
            if self.hide_lateness:
                btn_lat.label = "⏳ Hide Lateness: ON"
                btn_lat.variant = "primary"
                btn_lat.tooltip = "Click to show lateness (< 50 min)"
            else:
                btn_lat.label = "⏳ Hide Lateness: OFF"
                btn_lat.variant = "default"
                btn_lat.tooltip = "Click to hide lateness (< 50 min)"
        except Exception:
            pass

    def action_toggle_lateness(self) -> None:
        self.hide_lateness = not self.hide_lateness
        self.refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key:
            d_str = event.row_key.value
            self._toggle_date(d_str)

    def _toggle_date(self, d_str: str) -> None:
        if d_str in self.selected_dates:
            self.selected_dates.remove(d_str)
        else:
            self.selected_dates.add(d_str)
        self.refresh_table()

    def action_toggle_selected_row(self) -> None:
        dt = self.query_one("#excuse_table", DataTable)
        if dt.cursor_row is not None and 0 <= dt.cursor_row < len(self.visible_absences):
            day = self.visible_absences[dt.cursor_row]
            self._toggle_date(day.date)

    def action_select_all(self) -> None:
        self.selected_dates = {d.date for d in self.visible_absences}
        self.refresh_table()

    def action_select_open(self) -> None:
        self.selected_dates = {d.date for d in self.visible_absences if any(w in d.status.lower() for w in ["offen", "open"])}
        self.refresh_table()

    def action_clear_all(self) -> None:
        self.selected_dates.clear()
        self.refresh_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_el_all":
            self.action_select_all()
        elif bid == "btn_el_open":
            self.action_select_open()
        elif bid == "btn_el_clear":
            self.action_clear_all()
        elif bid == "btn_el_filter_lateness":
            self.action_toggle_lateness()
        elif bid == "btn_el_profile":
            self.app.push_screen(ExcuseProfileModal(), self._on_profile_updated)
        elif bid == "btn_el_generate":
            self.action_generate_pdf()
        elif bid == "btn_el_back":
            self.dismiss()

    def _on_profile_updated(self, saved: bool) -> None:
        self.profile = load_excuse_profile()
        self._update_profile_label()

    def action_generate_pdf(self) -> None:
        from excuse_service import create_excuse_pdf, open_pdf_in_system_viewer

        if not self.selected_dates:
            self.app.notify("Please select at least one absence date with [X].", severity="warning")
            return

        selected_days = [d for d in self.daily_absences if d.date in self.selected_dates]
        selected_days.sort(key=lambda d: d.date)
        try:
            pdf_path = create_excuse_pdf(selected_days, profile=self.profile)
            opened = open_pdf_in_system_viewer(pdf_path)
            fn = os.path.basename(pdf_path)
            if opened:
                self.app.notify(f"✓ Excuse PDF generated and opened: {fn}", severity="information")
            else:
                self.app.notify(f"✓ Excuse PDF saved to Downloads: {fn}", severity="information")
        except Exception as e:
            self.app.notify(f"! Error generating PDF: {e}", severity="error")

    def action_cancel(self) -> None:
        self.dismiss()

    def key_escape(self) -> None:
        self.dismiss()


class AddExamModal(ModalScreen[Optional[UntisExam]]):
    """Dialog to manually add a custom test or exam."""

    DEFAULT_CSS = """
    AddExamModal {
        align: center middle;
    }
    #add_exam_dialog {
        width: 68;
        max-height: 90%;
        height: auto;
        border: thick #89b4fa;
        background: #1e1e2e;
        padding: 1 2;
    }
    #add_exam_title {
        text-align: center;
        text-style: bold;
        color: #89b4fa;
        margin-bottom: 1;
    }
    .add_exam_label {
        color: #cdd6f4;
        text-style: bold;
        margin-top: 1;
    }
    .add_exam_input {
        margin-bottom: 1;
        width: 100%;
    }
    #btn_add_exam_type {
        width: 100%;
        margin-bottom: 1;
    }
    #add_exam_status {
        color: #f38ba8;
        text-align: center;
        margin: 1 0;
        min-height: 1;
    }
    #add_exam_buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    #add_exam_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    TYPE_OPTIONS = [
        {"code": "TE", "name": "TEST", "label": "📘 Type: TEST", "display": "Test", "variant": "primary"},
        {"code": "SA", "name": "SA", "label": "📕 Type: SA", "display": "School Exam", "variant": "error"},
        {"code": "PR", "name": "PR", "label": "📙 Type: PR", "display": "Oral Exam", "variant": "warning"},
        {"code": "WDH", "name": "WDH", "label": "🟩 Type: WDH", "display": "Retest", "variant": "success"},
    ]

    def __init__(self):
        super().__init__()
        self.type_index: int = 0
        self.exam_type: str = self.TYPE_OPTIONS[0]["code"]
        self.auto_group: str = _load_untis_group() or "X"
        self._lookup_counter: int = 0
        self._last_looked_up: Optional[tuple[str, str]] = None
        self._auto_filled_time: bool = False
        self._auto_filled_teacher: bool = False
        self._auto_filled_room: bool = False
        self._resolving_natural_date: bool = False
        self._autofill_timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="add_exam_dialog"):
            yield Label("➕ Add Custom Test / Exam", id="add_exam_title")
            with VerticalScroll():
                yield Label("Exam Type:", classes="add_exam_label")
                initial_opt = self.TYPE_OPTIONS[self.type_index]
                yield Button(initial_opt["label"], id="btn_add_exam_type", variant=initial_opt["variant"])
                yield Label("Subject / Course:", classes="add_exam_label")
                yield Input(placeholder="e.g. E, AMEC, D, POS, SWP, SWP PM", id="inp_add_exam_subject", classes="add_exam_input")
                yield Label("Date (DD.MM.YYYY or YYYY-MM-DD):", classes="add_exam_label")
                yield Input(placeholder="e.g. 5.10. or 24.10.2026", id="inp_add_exam_date", classes="add_exam_input")
                yield Button("🔍 Autofill from Untis Timetable", id="btn_add_exam_autofill", variant="primary")
                yield Label("Time (Start - End):", classes="add_exam_label")
                yield Input(placeholder="Auto-filled from Untis or e.g. 08:00 - 08:50", id="inp_add_exam_time", classes="add_exam_input")
                yield Label("Teacher (optional):", classes="add_exam_label")
                yield Input(placeholder="Auto-filled from Untis or e.g. BIM, WAW", id="inp_add_exam_teacher", classes="add_exam_input")
                yield Label("Room (optional):", classes="add_exam_label")
                yield Input(placeholder="Auto-filled from Untis or e.g. C3.08", id="inp_add_exam_room", classes="add_exam_input")
                yield Label("Exam Topics / Stoff (optional):", classes="add_exam_label")
                yield ChatInputArea(placeholder="e.g. Kapitel 1-3, SQL Queries", id="inp_add_exam_topics", classes="add_exam_input")
                yield Label("", id="add_exam_status")
            with Horizontal(id="add_exam_buttons"):
                yield Button("💾 Save [Enter]", id="btn_add_exam_save", variant="success")
                yield Button("↩️ Cancel [ESC]", id="btn_add_exam_cancel", variant="default")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "inp_add_exam_date" and not self._resolving_natural_date:
            resolved = resolve_natural_date_string(event.value, allow_short_abbr=False)
            if resolved != event.value:
                self._resolving_natural_date = True
                try:
                    event.input.value = resolved
                finally:
                    self._resolving_natural_date = False
                return

        if event.input.id in ["inp_add_exam_subject", "inp_add_exam_date"]:
            if getattr(self, "_autofill_timer", None) is not None:
                try:
                    self._autofill_timer.stop()
                except Exception:
                    pass
                self._autofill_timer = None
            try:
                self._autofill_timer = self.set_timer(1.0, lambda: self._trigger_untis_lookup(explicit=False))
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_add_exam_cancel":
            self.dismiss(None)
        elif bid == "btn_add_exam_save":
            self._save_exam()
        elif bid == "btn_add_exam_type":
            self._toggle_type()
        elif bid == "btn_add_exam_autofill":
            if getattr(self, "_autofill_timer", None) is not None:
                try:
                    self._autofill_timer.stop()
                except Exception:
                    pass
                self._autofill_timer = None
            self._trigger_untis_lookup(explicit=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save_exam()

    def _toggle_type(self) -> None:
        self.type_index = (self.type_index + 1) % len(self.TYPE_OPTIONS)
        current = self.TYPE_OPTIONS[self.type_index]
        self.exam_type = current["code"]
        btn = self.query_one("#btn_add_exam_type", Button)
        btn.label = current["label"]
        btn.variant = current["variant"]

    def action_cancel(self) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        self.dismiss(None)

    def key_escape(self) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        self.dismiss(None)

    def _trigger_untis_lookup(self, explicit: bool = False) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        try:
            subj = self.query_one("#inp_add_exam_subject", Input).value.strip()
            date_raw = self.query_one("#inp_add_exam_date", Input).value.strip()
        except Exception:
            return

        resolved_date = resolve_natural_date_string(date_raw, allow_short_abbr=True)
        if resolved_date != date_raw:
            self._resolving_natural_date = True
            try:
                self.query_one("#inp_add_exam_date", Input).value = resolved_date
            finally:
                self._resolving_natural_date = False
            date_raw = resolved_date

        if not subj or not date_raw:
            if explicit:
                self.query_one("#add_exam_status", Label).update("[yellow]Please enter Subject and Date first.[/yellow]")
            return

        parsed_date_info = self._parse_date_input(date_raw)
        if not parsed_date_info:
            if explicit:
                self.query_one("#add_exam_status", Label).update("[red]Invalid date format! Use e.g. 5.10. or 24.10.2026[/red]")
            return

        date_iso, date_display, _ = parsed_date_info
        if date_raw != date_display:
            self._resolving_natural_date = True
            try:
                self.query_one("#inp_add_exam_date", Input).value = date_display
            finally:
                self._resolving_natural_date = False

        if (subj, date_iso) == self._last_looked_up and not explicit:
            return

        self._lookup_counter += 1
        current_req = self._lookup_counter

        if explicit:
            self.query_one("#add_exam_status", Label).update("[yellow]Checking WebUntis timetable...[/yellow]")

        app = self.app

        def worker():
            data = lookup_untis_lesson_details(date_iso, subj, preferred_group=self.auto_group)
            if self._lookup_counter != current_req:
                return

            def update_ui():
                self._last_looked_up = (subj, date_iso)
                if data:
                    time_inp = self.query_one("#inp_add_exam_time", Input)
                    teacher_inp = self.query_one("#inp_add_exam_teacher", Input)
                    room_inp = self.query_one("#inp_add_exam_room", Input)

                    if not time_inp.value or self._auto_filled_time:
                        time_inp.value = data["time_str"]
                        self._auto_filled_time = True
                    if not teacher_inp.value or self._auto_filled_teacher:
                        teacher_inp.value = data["teacher"]
                        self._auto_filled_teacher = True
                    if not room_inp.value or self._auto_filled_room:
                        room_inp.value = data["room"]
                        self._auto_filled_room = True

                    if data.get("group"):
                        self.auto_group = data["group"]

                    self.query_one("#add_exam_status", Label).update(
                        f"[green]✓ Untis: {data['time_str']} | {data['teacher']} | {data['room']}[/green]"
                    )
                    app.notify(
                        f"✓ Untis: {data['time_str']} | {data['teacher']} | {data['room']}",
                        severity="information",
                    )
                elif explicit:
                    self.query_one("#add_exam_status", Label).update(
                        f"[yellow]No Untis lesson found for '{subj}' on {date_display}.[/yellow]"
                    )
            app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="UntisAutofillWorker").start()

    def _save_exam(self) -> None:
        if getattr(self, "_autofill_timer", None) is not None:
            try:
                self._autofill_timer.stop()
            except Exception:
                pass
            self._autofill_timer = None
        subj = self.query_one("#inp_add_exam_subject", Input).value.strip()
        date_inp = self.query_one("#inp_add_exam_date", Input)
        date_raw = date_inp.value.strip()
        resolved_date = resolve_natural_date_string(date_raw, allow_short_abbr=True)
        if resolved_date != date_raw:
            self._resolving_natural_date = True
            try:
                date_inp.value = resolved_date
            finally:
                self._resolving_natural_date = False
            date_raw = resolved_date
        time_raw = self.query_one("#inp_add_exam_time", Input).value.strip()
        teacher_raw = self.query_one("#inp_add_exam_teacher", Input).value.strip()
        room_raw = self.query_one("#inp_add_exam_room", Input).value.strip()
        topics_raw = self.query_one("#inp_add_exam_topics", Input).value.strip()

        if not subj:
            self.query_one("#add_exam_status", Label).update("[red]Please enter a subject.[/red]")
            return
        if not date_raw:
            self.query_one("#add_exam_status", Label).update("[red]Please enter an exam date.[/red]")
            return

        parsed_date_info = self._parse_date_input(date_raw)
        if not parsed_date_info:
            self.query_one("#add_exam_status", Label).update("[red]Invalid date format! Use e.g. 24.10.2026 or 24.10.[/red]")
            return

        date_iso, date_display, days_until = parsed_date_info
        start_t, end_t = self._parse_time_input(time_raw)

        from config import normalize_subject_name
        clean_subj = normalize_subject_name(subj)
        group = self.auto_group or _load_untis_group() or "X"
        teachers = [t.strip() for t in teacher_raw.split(",") if t.strip()] if teacher_raw else []
        rooms = [r.strip() for r in room_raw.split(",") if r.strip()] if room_raw else []
        current_opt = self.TYPE_OPTIONS[self.type_index]
        exam_type_display = current_opt["display"]

        exam_id = f"custom_{date_iso.replace('-', '')}_{int(time.time() * 1000) % 1000000}_{clean_subj.lower().replace(' ', '_')}"

        new_exam = UntisExam(
            id=exam_id,
            exam_type=self.exam_type,
            exam_type_display=exam_type_display,
            subject=clean_subj,
            name=clean_subj,
            text=topics_raw if topics_raw else exam_type_display,
            date=date_iso,
            date_display=date_display,
            start_time=start_t,
            end_time=end_t,
            teachers=teachers,
            rooms=rooms,
            custom_topics=topics_raw,
            is_past=days_until < 0,
            days_until=days_until,
            url="",
            group=group,
            is_custom=True,
        )

        save_custom_exam(new_exam)
        self.dismiss(new_exam)

    _parse_date_input = staticmethod(parse_flexible_date_input)

    @staticmethod
    def _parse_time_input(val: str) -> tuple[str, str]:
        val = val.strip()
        if not val:
            return "08:00", "08:50"
        if "-" in val:
            parts = val.split("-", 1)
            s = parts[0].strip()
            e = parts[1].strip()
            return s, e
        parts = val.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            start_str = f"{h:02d}:{m:02d}"
            end_m = m + 50
            end_h = h + (end_m // 60)
            end_m = end_m % 60
            end_str = f"{end_h:02d}:{end_m:02d}"
            return start_str, end_str
        except Exception:
            return "08:00", "08:50"


class ExamDetailModal(ModalScreen[bool]):
    """Modal showing all details of an exam and allowing editing of custom topics/notes."""

    DEFAULT_CSS = """
    ExamDetailModal {
        align: center middle;
    }
    #exam_detail_dialog {
        width: 82;
        max-width: 95%;
        height: auto;
        max-height: 88%;
        border: thick #cba6f7;
        background: #1e1e2e;
        padding: 1 2;
        layout: vertical;
    }
    #exam_detail_title {
        text-align: center;
        text-style: bold;
        color: #cba6f7;
        margin-bottom: 1;
    }
    #exam_detail_meta {
        height: auto;
        background: #181825;
        border: solid #313244;
        padding: 1;
        margin-bottom: 1;
    }
    .exam_meta_row {
        color: #cdd6f4;
        margin-bottom: 0;
    }
    .exam_section_label {
        color: #89b4fa;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }
    #inp_exam_topics {
        height: 3;
        margin-bottom: 1;
        border: none;
    }
    #exam_detail_buttons {
        height: 3;
        width: 100%;
        align: center middle;
    }
    #exam_detail_buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("o", "open_browser", "Browser"),
        Binding("d", "delete_exam", "Delete Exam"),
        Binding("escape", "cancel", "Back"),
        Binding("ctrl+s", "save_topics", "Save Notes"),
    ]

    def __init__(self, exam: UntisExam):
        super().__init__()
        self.exam = exam

    def compose(self) -> ComposeResult:
        with Vertical(id="exam_detail_dialog"):
            if self.exam.exam_type == "SA":
                badge_icon = "📕"
            elif self.exam.exam_type in ["TE", "TEST"]:
                badge_icon = "📘"
            elif self.exam.exam_type == "PR":
                badge_icon = "📙"
            elif self.exam.exam_type == "WDH":
                badge_icon = "🟩"
            else:
                badge_icon = "🟣"
            yield Label(f"{badge_icon} {self.exam.exam_type_display}: {self.exam.subject}", id="exam_detail_title")

            with Vertical(id="exam_detail_meta"):
                try:
                    dt = datetime.datetime.strptime(self.exam.date, "%Y-%m-%d").date()
                    weekdays = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
                    weekday_str = weekdays[dt.weekday()]
                except Exception:
                    weekday_str = ""
                if any(self.exam.date_display.startswith(w) for w in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Mo", "Tu", "We", "Th", "Fr", "Sa", "Su", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag", "Di", "Mi", "Do", "So"]):
                    full_date_str = self.exam.date_display
                else:
                    full_date_str = f"{weekday_str}, {self.exam.date_display}" if weekday_str else self.exam.date_display

                yield Label(f"📅 Date & Time:  [bold white]{full_date_str}[/] ({self.exam.start_time} - {self.exam.end_time})", classes="exam_meta_row")
                yield Label(f"⏳ Countdown:    [bold yellow]{self.exam.countdown_display}[/]", classes="exam_meta_row")
                teachers_str = ", ".join(self.exam.teachers) if self.exam.teachers else "-"
                yield Label(f"👨‍🏫 Teacher:      [bold white]{escape(teachers_str)}[/]", classes="exam_meta_row")
                rooms_str = ", ".join(self.exam.rooms) if self.exam.rooms else "-"
                yield Label(f"📍 Room:         [bold white]{escape(rooms_str)}[/]", classes="exam_meta_row")
                if self.exam.name and self.exam.name != self.exam.subject:
                    yield Label(f"🏷️ Untis Name:   [white]{escape(self.exam.name)}[/]", classes="exam_meta_row")
                if self.exam.text:
                    yield Label(f"ℹ️ Untis Note:   [white]{escape(self.exam.text)}[/]", classes="exam_meta_row")

            yield Label("✏️ Exam Topics / Notes:", classes="exam_section_label")
            ta = ChatInputArea(value=self.exam.custom_topics or "", id="inp_exam_topics")
            yield ta

            is_custom = getattr(self.exam, "is_custom", False) or str(self.exam.id).startswith("custom_")
            with Horizontal(id="exam_detail_buttons"):
                if is_custom:
                    yield Button("🗑️ Delete [D]", id="btn_exam_delete", variant="error")
                else:
                    yield Button("🌐 Browser [O]", id="btn_exam_browser", variant="primary")
                yield Button("💾 Save Notes [Ctrl+S]", id="btn_save_exam_topics", variant="success")
                yield Button("↩️ Back [ESC]", id="btn_cancel_exam_detail", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_exam_browser":
            self.action_open_browser()
        elif event.button.id == "btn_exam_delete":
            self.action_delete_exam()
        elif event.button.id == "btn_save_exam_topics":
            self.action_save_topics()
        elif event.button.id == "btn_cancel_exam_detail":
            self.dismiss(False)

    def action_open_browser(self) -> None:
        is_custom = getattr(self.exam, "is_custom", False) or str(self.exam.id).startswith("custom_")
        if is_custom:
            self.app.notify("No browser link for custom tests.", severity="warning")
            return
        import webbrowser
        from untis_service import get_exam_web_url
        url = get_exam_web_url(self.exam)
        if url:
            webbrowser.open(url)
            self.app.notify(f"Opening '{self.exam.subject}' test in browser...", severity="information")
        else:
            self.app.notify("No WebUntis URL available for this test.", severity="warning")

    def action_delete_exam(self) -> None:
        is_custom = getattr(self.exam, "is_custom", False) or str(self.exam.id).startswith("custom_")
        if not is_custom:
            self.app.notify("Only custom tests can be deleted.", severity="warning")
            return
        delete_custom_exam(self.exam.id)
        self.app.notify(f"🗑️ Test '{self.exam.subject}' deleted.", severity="information")
        self.dismiss(True)

    def action_save_topics(self) -> None:
        new_topic = self.query_one("#inp_exam_topics", TextArea).text.strip()
        save_single_exam_note(self.exam.id, new_topic)
        self.exam.custom_topics = new_topic
        if getattr(self.exam, "is_custom", False) or str(self.exam.id).startswith("custom_"):
            save_custom_exam(self.exam)
        self.app.notify("✓ Exam notes saved successfully!", severity="information")
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


class ExamsScreen(Screen):
    """Full-screen view displaying all WebUntis tests, exams and assignments."""

    DEFAULT_CSS = """
    ExamsScreen {
        layout: vertical;
    }
    #exams_header {
        dock: top;
        height: 3;
        padding: 0 1;
        align: left middle;
    }
    #exams_title {
        width: auto;
        text-style: bold;
        color: #89b4fa;
    }
    #exams_sub_info {
        width: 1fr;
        content-align: right middle;
        color: #a6adc8;
    }
    #exams_table_container {
        height: 1fr;
        padding: 0 1;
    }
    #exams_table {
        height: 1fr;
    }
    #exams_button_bar {
        dock: bottom;
        height: 3;
        width: 100%;
        align: left middle;
        padding: 0 1;
        overflow-x: hidden;
        overflow-y: hidden;
    }
    #exams_left_buttons {
        width: 1fr;
        height: 100%;
        align: left middle;
    }
    #exams_button_bar Button {
        margin: 0 1;
        min-width: 4;
        height: 100%;
        content-align: center middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back to Tasks"),
        Binding("t", "dismiss_screen", "Back to Tasks"),
        Binding("a", "add_exam", "Add Test"),
        Binding("v", "toggle_past_exams", "Toggle Past Exams"),
        Binding("g", "toggle_group", "Toggle Group"),
        Binding("r", "sync_exams", "Sync Untis"),
    ]

    def __init__(self):
        super().__init__()
        self.show_past: bool = False
        full_cfg = load_full_school_config()
        self.current_group: str = (full_cfg.get("untis_group") or "X").strip().upper()
        self.current_class: str = (full_cfg.get("student_class") or "1AHIT").strip()
        self.exams: List[UntisExam] = []
        self._is_syncing: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="exams_header"):
            yield Label("📝 WebUntis Tests & Exams", id="exams_title")
            yield Label("", id="exams_sub_info")

        with Vertical(id="exams_table_container"):
            dt = DataTable(id="exams_table", cursor_type="row")
            yield dt

        with Horizontal(id="exams_button_bar"):
            with Horizontal(id="exams_left_buttons"):
                yield Button("➕ Add [A]", id="btn_exams_add", variant="success", tooltip="Add Custom Test [A]")
                yield Button("🔄 Sync Untis", id="btn_exams_sync", variant="default", tooltip="Sync Untis [R]")
                yield Button("📅 Past Exams: OFF", id="btn_toggle_past_exams", variant="primary", tooltip="Toggle Past [V]")
            yield Button("↩️ Back", id="btn_exams_back", variant="default", tooltip="Back to tasks [T/Esc]")

    def on_mount(self) -> None:
        dt = self.query_one("#exams_table", DataTable)
        dt.cell_padding = 1
        dt.add_columns("#", "Type", "Subject", "Date", "Time", "Topic / Notes", "Teacher", "Room", "Countdown")
        self.reload_data()

    def reload_data(self) -> None:
        full_cfg = load_full_school_config()
        self.current_group = (full_cfg.get("untis_group") or "X").strip().upper()
        self.current_class = (full_cfg.get("student_class") or "1AHIT").strip()
        try:
            btn = self.query_one("#btn_exams_group", Button)
            btn.label = f"⚙️ Group: {self.current_group}"
        except Exception:
            pass
        self.exams = load_untis_exams_cache()
        self._populate_table()
        if not self.exams:
            self.action_sync_exams()

    def _populate_table(self, term_w_override: Optional[int] = None) -> None:
        dt = self.query_one("#exams_table", DataTable)
        dt.clear()

        matching_exams = [e for e in self.exams if not e.group or e.group.upper() == self.current_group]
        visible_exams = [e for e in matching_exams if self.show_past or not e.is_past or e.days_until == 0]
        visible_exams.sort(key=lambda x: (x.date, x.start_time))
        total_cnt = len(matching_exams)
        upcoming_cnt = len([e for e in matching_exams if not e.is_past or e.days_until == 0])
        past_cnt = total_cnt - upcoming_cnt

        info_lbl = self.query_one("#exams_sub_info", Label)
        info_lbl.update(
            f"Total: [bold white]{total_cnt}[/]  |  "
            f"Upcoming: [bold cyan]{upcoming_cnt}[/]  |  "
            f"Past: [bold white]{past_cnt}[/]  |  "
            f"Class: {self.current_class}  |  "
            f"Group: {self.current_group}"
        )

        btn_toggle = self.query_one("#btn_toggle_past_exams", Button)
        if self.show_past:
            btn_toggle.label = "📅 Past Exams: ON"
            btn_toggle.variant = "success"
        else:
            btn_toggle.label = "📅 Past Exams: OFF"
            btn_toggle.variant = "primary"

        # Dynamische Breitenberechnung: Verteilt alle 9 Spalten proportional über die volle Breite,
        # sodass rechts kein Platz frei bleibt und Themen/Notizen maximalen Raum erhalten.
        if term_w_override is not None and term_w_override > 0:
            term_w = term_w_override
        else:
            try:
                container = self.query_one("#exams_table_container")
                term_w = container.size.width if (container.size and container.size.width > 0) else (self.size.width - 2 if self.size and self.size.width > 0 else 121)
            except Exception:
                term_w = self.size.width - 2 if (self.size and self.size.width > 0) else 121

        avail_w = max(80, term_w - 1)  # 1 Spalte Puffer für vertikale Scrollbar
        total_padding = 9 * (2 * dt.cell_padding)  # 9 Spalten * (2 * 1) = 18 Zeichen Padding
        avail_content = avail_w - total_padding

        if avail_content < 60:
            col_widths = [3, 4, 6, 8, 11, max(10, avail_content - 44), 6, 4, 6]
        else:
            base_widths = [3, 4, 8, 10, 13, 20, 8, 6, 10]
            extra = max(0, avail_content - sum(base_widths))
            w_subj = 8 + int(extra * 0.12)
            w_date = 10 + int(extra * 0.04)
            w_teach = 8 + int(extra * 0.10)
            w_room = 6 + int(extra * 0.04)
            w_cd = 10 + int(extra * 0.10)
            assigned = (w_subj - 8) + (w_date - 10) + (w_teach - 8) + (w_room - 6) + (w_cd - 10)
            w_topic = 20 + (extra - assigned)
            col_widths = [3, 4, w_subj, w_date, 13, w_topic, w_teach, w_room, w_cd]

        # Spaltenbreiten der DataTable fest zuweisen, um den Leerraum rechts vollständig zu schließen
        if dt.columns:
            for col_obj, w in zip(dt.columns.values(), col_widths):
                col_obj.width = w
                col_obj.auto_width = False

        max_topic_len = col_widths[5]

        for idx, ex in enumerate(visible_exams, start=1):
            if ex.exam_type == "SA":
                type_styled = Text("SA", style="bold red")
            elif ex.exam_type in ["TE", "TEST"]:
                type_styled = Text("TEST", style="bold cyan")
            elif ex.exam_type == "PR":
                type_styled = Text("PR", style="bold yellow")
            elif ex.exam_type == "WDH":
                type_styled = Text("WDH", style="bold green")
            else:
                type_styled = Text(ex.exam_type or "EXAM", style="bold magenta")

            # Dim row if past
            dim_style = "dim" if ex.is_past and ex.days_until < 0 else ""

            subj_str = ex.subject
            if len(subj_str) > col_widths[2]:
                subj_str = subj_str[: max(0, col_widths[2] - 1)] + "…"
            subj_text = Text(subj_str, style=f"bold white {dim_style}".strip(), no_wrap=True, overflow="ellipsis")

            try:
                dt_obj = datetime.datetime.strptime(ex.date, "%Y-%m-%d").date()
                weekdays = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
                wk = weekdays[dt_obj.weekday()]
                date_str = f"{wk}, {dt_obj.day:02d}.{dt_obj.month:02d}."
            except Exception:
                date_str = ex.date_display
            date_styled = Text(date_str, style=f"white {dim_style}".strip(), no_wrap=True)

            time_str = f"{ex.start_time} - {ex.end_time}"
            time_styled = Text(time_str, style=f"dim {dim_style}".strip(), no_wrap=True)

            # Topic / Notes: Einzeilig halten (keine 2. Zeile), mit "..." kürzen
            raw_text = ""
            is_custom = False
            text_style = f"white {dim_style}".strip()

            if ex.custom_topics and ex.custom_topics.strip():
                raw_text = ex.custom_topics.strip()
                is_custom = True
                text_style = f"bold green {dim_style}".strip()
            elif ex.text and ex.text.strip():
                raw_text = ex.text.strip()
                text_style = f"white {dim_style}".strip()
            elif ex.name and ex.name.strip() and ex.name.strip() != ex.subject.strip():
                raw_text = ex.name.strip()
                text_style = f"white {dim_style}".strip()

            # Alle Zeilenumbrüche und überschüssige Leerzeichen entfernen, damit niemals eine 2. Zeile entsteht
            clean_text = " ".join(raw_text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())

            if clean_text:
                prefix = "✏️ " if is_custom else ""
                prefix_len = 3 if is_custom else 0
                avail_chars = max(10, max_topic_len - prefix_len)

                if len(clean_text) > avail_chars:
                    display_text = clean_text[: max(0, avail_chars - 3)].rstrip() + "..."
                else:
                    display_text = clean_text

                topic_str = f"{prefix}{display_text}"
                topic_styled = Text(topic_str, style=text_style, no_wrap=True, overflow="ellipsis")
            else:
                topic_styled = Text("- none -", style=f"italic dim {dim_style}".strip(), no_wrap=True)

            teachers_str = ", ".join(ex.teachers) if ex.teachers else "-"
            if len(teachers_str) > col_widths[6]:
                teachers_str = teachers_str[: max(0, col_widths[6] - 1)] + "…"
            teachers_styled = Text(teachers_str, style=f"white {dim_style}".strip(), no_wrap=True, overflow="ellipsis")

            rooms_str = ", ".join(ex.rooms) if ex.rooms else "-"
            if len(rooms_str) > col_widths[7]:
                rooms_str = rooms_str[: max(0, col_widths[7] - 1)] + "…"
            rooms_styled = Text(rooms_str, style=f"white {dim_style}".strip(), no_wrap=True, overflow="ellipsis")

            if ex.is_past and ex.days_until < 0:
                cd_styled = Text(ex.countdown_display, style="dim", no_wrap=True)
            elif ex.days_until == 0:
                cd_styled = Text(ex.countdown_display, style="bold red", no_wrap=True)
            elif ex.days_until <= 3:
                cd_styled = Text(ex.countdown_display, style="bold yellow", no_wrap=True)
            else:
                cd_styled = Text(ex.countdown_display, style="bold cyan", no_wrap=True)

            dt.add_row(
                Text(str(idx), style="dim"),
                type_styled,
                subj_text,
                date_styled,
                time_styled,
                topic_styled,
                teachers_styled,
                rooms_styled,
                cd_styled,
                key=ex.id,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = event.row_key.value
        ex = next((e for e in self.exams if e.id == row_key), None)
        if ex:
            self._open_exam_detail(ex)

    def _open_exam_detail(self, exam: UntisExam) -> None:
        def on_saved(saved: bool) -> None:
            if saved:
                self.reload_data()
        self.app.push_screen(ExamDetailModal(exam), on_saved)

    def on_resize(self, event: Resize) -> None:
        if self.is_mounted:
            override_w = (event.size.width - 2) if (event.size and event.size.width > 0) else None
            self._populate_table(term_w_override=override_w)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn_exams_add":
            self.action_add_exam()
        elif bid == "btn_toggle_past_exams":
            self.action_toggle_past_exams()
        elif bid == "btn_exams_group":
            self.action_toggle_group()
        elif bid == "btn_exams_sync":
            self.action_sync_exams()
        elif bid == "btn_exams_back":
            self.action_dismiss_screen()

    def action_add_exam(self) -> None:
        def on_added(exam: Optional[UntisExam]) -> None:
            if exam:
                self.reload_data()
                self.app.notify(f"✓ Test for '{exam.subject}' added!", severity="information")
        self.app.push_screen(AddExamModal(), on_added)

    def action_toggle_group(self) -> None:
        new_grp = "Y" if self.current_group == "X" else "X"
        self.current_group = new_grp
        save_untis_group(new_grp)
        try:
            self.query_one("#btn_exams_group", Button).label = f"⚙️ Group: {new_grp}"
        except Exception:
            pass
        self._populate_table()
        self.app.notify(f"WebUntis group set to {new_grp}.", severity="information")

    def action_toggle_past_exams(self) -> None:
        self.show_past = not self.show_past
        self._populate_table()

    def action_sync_exams(self) -> None:
        if self._is_syncing:
            return
        self._is_syncing = True
        self.app.notify("🔄 Synchronizing WebUntis exams...", severity="information")
        try:
            self.query_one("#btn_exams_sync", Button).disabled = True
        except Exception:
            pass

        def _bg_sync():
            ok, msg, _ = sync_untis_data()
            def _done():
                self._is_syncing = False
                try:
                    self.query_one("#btn_exams_sync", Button).disabled = False
                except Exception:
                    pass
                self.reload_data()
                try:
                    self.app.notify("✓ WebUntis exams updated!", severity="information")
                except Exception:
                    pass
            try:
                self.app.call_from_thread(_done)
            except Exception:
                pass

        threading.Thread(target=_bg_sync, daemon=True, name="ExamsSyncWorker").start()

    def action_dismiss_screen(self) -> None:
        self.dismiss()


ExamsModal = ExamsScreen


class ClearChatConfirmModal(ModalScreen[bool]):
    """Confirmation modal dialog before clearing the AI chat history."""

    DEFAULT_CSS = """
    ClearChatConfirmModal {
        align: center middle;
    }
    #clear_confirm_dialog {
        width: 56;
        height: auto;
        border: thick #e03131;
        background: #1e1e2e;
        padding: 1 2;
    }
    #clear_confirm_title {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: #f38ba8;
        margin-bottom: 1;
    }
    #clear_confirm_desc {
        width: 100%;
        text-align: center;
        color: #cdd6f4;
        margin-bottom: 2;
    }
    #clear_confirm_buttons {
        width: 100%;
        height: auto;
        align: center middle;
    }
    #clear_confirm_buttons Button {
        margin: 0 1;
        min-width: 12;
    }
    #btn_confirm_clear {
        background: #e03131;
        color: #ffffff;
    }
    #btn_confirm_clear:hover {
        background: #c92a2a;
    }
    .-theme-oled #clear_confirm_dialog {
        background: #000000;
        border: thick #af3029;
    }
    .-theme-oled #clear_confirm_title {
        color: #af3029;
    }
    .-theme-oled #clear_confirm_desc {
        color: #ffffff;
    }
    .-theme-oled #btn_confirm_clear {
        background: #af3029;
        color: #ffffff;
    }
    .-theme-oled #btn_confirm_clear:hover {
        background: #c33a32;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="clear_confirm_dialog"):
            yield Label("Clear Chat History?", id="clear_confirm_title")
            yield Label(
                "Are you sure you want to clear the chat history for this assignment?",
                id="clear_confirm_desc",
            )
            with Horizontal(id="clear_confirm_buttons"):
                yield Button("🗑️ Clear", id="btn_confirm_clear", variant="error")
                yield Button("Cancel", id="btn_cancel_clear", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_confirm_clear":
            self.dismiss(True)
        elif event.button.id == "btn_cancel_clear":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)


class AiChatScreen(Screen):
    """
    Interactive full-screen AI chat assistant with browser-style task tabs,
    deep context extraction, and Gemini / OpenAI API integration.
    """

    DEFAULT_CSS = """
    AiChatScreen {
        layout: vertical;
        background: $background;
        height: 100%;
        overflow: hidden;
    }
    #ai_top_bar {
        height: 1;
        width: 100%;
        background: $panel;
        padding: 0 1;
        align: left middle;
    }
    #ai_tab_scroll {
        width: 1fr;
        height: 1;
        align: left middle;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    #ai_tab_scroll Button.ai_tab_btn,
    .ai_tab_btn {
        margin-right: 1;
        min-width: 6;
        width: auto;
        height: 1;
        border: none;
        background: $surface;
        color: $text-muted;
        content-align: center middle;
    }
    #ai_tab_scroll Button.ai_tab_btn:hover,
    .ai_tab_btn:hover {
        background: $boost;
        color: $text;
    }
    #ai_tab_scroll Button.ai_tab_active,
    .ai_tab_active {
        border: none;
        background: $primary;
        color: $primary-background;
        text-style: bold;
        content-align: center middle;
    }
    #ai_tab_scroll Button.ai_tab_active:hover,
    .ai_tab_active:hover {
        background: $primary-lighten-1;
        color: $primary-background;
    }
    #ai_task_banner {
        height: 3;
        width: 100%;
        background: $surface;
        border-top: solid $border;
        border-bottom: solid $border;
        padding: 0 1;
        align: left middle;
    }
    #ai_task_banner_title {
        width: 1fr;
        text-style: bold;
        color: $primary;
    }
    #ai_task_banner_meta {
        width: auto;
        color: $text-muted;
    }
    #ai_chat_scroll {
        height: 1fr;
        width: 100%;
        padding: 1 2;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }
    .ai_msg_container {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    .ai_msg_user {
        border-left: thick $success;
        background: $surface;
        padding: 1 2;
    }
    .ai_msg_assistant {
        border-left: thick $primary;
        background: $panel;
        padding: 1 2;
    }
    .ai_msg_author {
        text-style: bold;
        margin-bottom: 0;
    }
    .ai_msg_user .ai_msg_author {
        color: $success;
    }
    .ai_msg_assistant .ai_msg_author {
        color: $primary;
    }
    .ai_msg_text {
        width: 100%;
        color: $text;
    }
    Markdown.ai_msg_markdown {
        background: transparent;
        padding: 0;
        margin: 0;
    }
    .ai_msg_assistant MarkdownFence {
        background: $background;
        border: solid $border;
        padding: 0 1;
        margin: 1 0;
    }
    .ai_msg_assistant MarkdownCodeInline {
        background: $surface-lighten-1;
        color: $accent;
        text-style: bold;
        padding: 0 1;
    }
    .ai_thinking_box {
        height: auto;
        padding: 0 2;
        margin-bottom: 1;
        color: $warning;
        text-style: bold italic;
    }
    #ai_input_bar {
        dock: bottom;
        height: 7;
        min-height: 7;
        max-height: 7;
        width: 100%;
        background: $panel;
        border-top: solid $border;
        border-bottom: solid $border;
        padding: 0 1;
        align: left middle;
    }
    #ai_chat_input,
    ChatInputArea {
        width: 1fr;
        height: 5;
        min-height: 5;
        max-height: 5;
        border: solid #45475a;
        background: $surface;
        color: $text;
        padding: 1 1 1 1;
        margin-right: 1;
        scrollbar-size: 1 1;
        scrollbar-color: $primary $panel;
    }
    #ai_chat_input:focus,
    ChatInputArea:focus {
        border: solid #89b4fa;
    }
    #ai_input_btn_box {
        width: 11;
        min-width: 11;
        max-width: 11;
        height: 5;
        layout: vertical;
        align: right bottom;
    }
    #btn_ai_clear_chat {
        width: 100%;
        min-width: 4;
        height: 1;
        min-height: 1;
        max-height: 1;
        margin-bottom: 1;
        border: none;
        background: #e03131;
        color: #ffffff;
        content-align: center middle;
        text-align: center;
        padding: 0;
    }
    #btn_ai_clear_chat:hover {
        background: #c92a2a;
    }
    #btn_ai_back {
        width: 100%;
        min-width: 4;
        height: 3;
        min-height: 3;
        max-height: 3;
        content-align: center middle;
        text-align: center;
    }
    #btn_ai_back:hover {
        background: $boost;
        color: $text;
    }
    .ai_empty_placeholder {
        width: 100%;
        content-align: center middle;
        text-align: center;
        color: $text-muted;
        padding: 4 2;
    }
    .-theme-oled #ai_top_bar {
        background: #000000;
        height: 1;
    }
    .-theme-oled #ai_tab_scroll {
        height: 1;
    }
    .-theme-oled #ai_task_banner {
        background: #000000;
        border-top: solid #343331;
        border-bottom: solid #343331;
    }
    .-theme-oled #ai_input_bar {
        background: #000000;
        border-top: solid #343331;
        border-bottom: solid #343331;
        height: 7;
        min-height: 7;
        max-height: 7;
    }
    .-theme-oled #ai_input_btn_box {
        width: 11;
        min-width: 11;
        max-width: 11;
        height: 5;
        layout: vertical;
        align: right bottom;
    }
    .-theme-oled .ai_msg_user {
        background: #000000;
        border-left: thick #66800b;
    }
    .-theme-oled .ai_msg_assistant {
        background: #000000;
        border-left: thick #205ea6;
    }
    .-theme-oled .ai_msg_assistant MarkdownFence {
        background: #181816;
        border: solid #343331;
    }
    .-theme-oled .ai_msg_assistant MarkdownCodeInline {
        background: #282726;
        color: #ffffff;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_btn,
    .-theme-oled .ai_tab_btn {
        background: #181816;
        color: #a6a69c;
        border: none;
        height: 1;
        content-align: center middle;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_btn:hover,
    .-theme-oled .ai_tab_btn:hover {
        background: #282726;
        color: #ffffff;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_active,
    .-theme-oled .ai_tab_active {
        background: #205ea6;
        border: none;
        color: #ffffff;
        text-style: bold;
        height: 1;
        content-align: center middle;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_active:hover,
    .-theme-oled .ai_tab_active:hover {
        background: #2868b2;
        color: #ffffff;
    }
    .-theme-oled #btn_ai_clear_chat {
        width: 100%;
        min-width: 4;
        height: 1;
        min-height: 1;
        max-height: 1;
        margin-bottom: 1;
        content-align: center middle;
        text-align: center;
        background: #e03131;
        color: #ffffff;
        border: none;
        padding: 0;
    }
    .-theme-oled #btn_ai_clear_chat:hover {
        background: #c92a2a;
    }
    .-theme-oled ChatInputArea {
        background: #181816;
        color: #ffffff;
        border: solid #343331;
        height: 5;
        min-height: 5;
        max-height: 5;
        padding: 1 1 1 1;
        scrollbar-size: 1 1;
        scrollbar-color: #58a6ff #000000;
    }
    .-theme-oled ChatInputArea:focus {
        border: solid #58a6ff;
    }
    .-theme-oled #ai_chat_input {
        width: 1fr;
        margin-right: 1;
    }
    .-theme-oled #btn_ai_back {
        width: 100%;
        background: #282726;
        color: #ffffff;
        border: none;
        height: 3;
        min-height: 3;
        max-height: 3;
        min-width: 4;
        content-align: center middle;
        text-align: center;
    }
    .-theme-oled #btn_ai_back:hover {
        background: #343331;
    }
    """

    _last_opened_task_id: Optional[str] = None

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back [ESC]"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("left", "prev_tab", "Previous Tab", show=False),
        Binding("right", "next_tab", "Next Tab", show=False),
    ]

    def __init__(
        self,
        mgr: TaskManager,
        initial_task_id: Optional[str] = None,
        auto_explain: bool = False,
        tasks: Optional[List[Task]] = None,
    ):
        super().__init__()
        self.mgr = mgr
        self.initial_task_id = initial_task_id
        self.auto_explain = auto_explain
        self.tasks_pool: Optional[List[Task]] = list(tasks) if tasks is not None else None
        self.open_tasks: List[Task] = []
        self.active_task_idx: int = 0
        self.active_task: Optional[Task] = None
        self.chat_history: Dict[str, List[Dict[str, Any]]] = {}
        self.is_waiting_for_ai: bool = False
        self._thinking_timer = None
        self._thinking_step: int = 1
        from core.config import load_ai_chat_config
        self.cfg = load_ai_chat_config()

    def compose(self) -> ComposeResult:
        with Horizontal(id="ai_top_bar"):
            with HorizontalScroll(id="ai_tab_scroll"):
                yield Label("Loading assignments...", id="ai_tab_loading")

        with Horizontal(id="ai_task_banner"):
            yield Label("", id="ai_task_banner_title")
            yield Label("", id="ai_task_banner_meta")

        with VerticalScroll(id="ai_chat_scroll"):
            yield Label("Select an assignment tab above to start.", classes="ai_empty_placeholder", id="ai_chat_empty_lbl")

        with Horizontal(id="ai_input_bar"):
            yield ChatInputArea(id="ai_chat_input", placeholder="Ask a question about this assignment...")
            with Vertical(id="ai_input_btn_box"):
                yield Button("🗑️ Clear", id="btn_ai_clear_chat", variant="error", tooltip="Clear chat for current task [Ctrl+L]")
                yield Button("↩️ Back", id="btn_ai_back", variant="default", tooltip="Back to tasks [ESC]")

    def on_mount(self) -> None:
        try:
            inp = self.query_one("#ai_chat_input", ChatInputArea)
            inp.focus()
        except Exception:
            pass

        self._load_open_tasks()
        self._populate_tabs()
        if self.open_tasks:
            target_idx = self.active_task_idx if (0 <= self.active_task_idx < len(self.open_tasks)) else 0
            self.select_task(target_idx, is_initial=True)
            try:
                self._refresh_chat_display()
            except Exception:
                pass

    def _load_open_tasks(self) -> None:
        tasks = []
        if self.tasks_pool is not None:
            tasks = [t for t in self.tasks_pool]
        else:
            if hasattr(self.mgr, "get_filtered_tasks"):
                try:
                    res = self.mgr.get_filtered_tasks(status_filter="open_only")
                    if isinstance(res, (list, tuple)):
                        tasks = [t for t in res if not getattr(t, "is_completed", False)]
                except Exception:
                    pass
            if not tasks and hasattr(self.mgr, "get_tasks"):
                try:
                    res = self.mgr.get_tasks()
                    if isinstance(res, (list, tuple)):
                        tasks = [
                            t for t in res
                            if not getattr(t, "is_completed", False) and str(getattr(t, "status", "")).lower() in ["offen", "ueberfaellig", "open", "overdue"]
                        ]
                except Exception:
                    pass
            if not tasks and hasattr(self.mgr, "tasks"):
                raw_tasks = getattr(self.mgr, "tasks", [])
                if isinstance(raw_tasks, (list, tuple)):
                    tasks = [
                        t for t in raw_tasks
                        if not getattr(t, "is_completed", False) and str(getattr(t, "status", "")).lower() in ["offen", "ueberfaellig", "open", "overdue"]
                    ]
            if not tasks and hasattr(self.mgr, "tasks"):
                raw_tasks = getattr(self.mgr, "tasks", [])
                if isinstance(raw_tasks, (list, tuple)):
                    tasks = [t for t in raw_tasks if not getattr(t, "is_completed", False)]

        self.open_tasks = list(tasks)
        if self.open_tasks:
            # Determine target task to select:
            # 1. Explicit initial_task_id (e.g. from Ai Explain button)
            # 2. Last opened task (from session or persistent cache)
            # 3. Default to 1st task (index 0)
            target_id = self.initial_task_id
            if not target_id:
                target_id = AiChatScreen._last_opened_task_id
                if not target_id:
                    try:
                        from services.ai_chat_service import load_last_active_ai_task_id
                        target_id = load_last_active_ai_task_id()
                    except Exception:
                        pass

            matched_idx = -1
            if target_id:
                for idx, t in enumerate(self.open_tasks):
                    if t.id == target_id:
                        matched_idx = idx
                        break

            if matched_idx >= 0:
                self.active_task_idx = matched_idx
                self.active_task = self.open_tasks[matched_idx]
            elif self.initial_task_id:
                all_pool = getattr(self.mgr, "tasks", [])
                found_task = None
                if isinstance(all_pool, (list, tuple)):
                    for t in all_pool:
                        if t.id == self.initial_task_id:
                            found_task = t
                            break
                if found_task:
                    self.open_tasks.insert(0, found_task)
                    self.active_task_idx = 0
                    self.active_task = found_task
                else:
                    self.active_task_idx = 0
                    self.active_task = self.open_tasks[0]
            else:
                self.active_task_idx = 0
                self.active_task = self.open_tasks[0]
        else:
            self.active_task_idx = 0
            self.active_task = None

    def _populate_tabs(self) -> None:
        tab_container = self.query_one("#ai_tab_scroll", HorizontalScroll)
        tab_container.remove_children()

        if not self.open_tasks:
            tab_container.mount(Label("No assignments found matching active filters.", classes="ai_empty_placeholder"))
            return

        for idx, t in enumerate(self.open_tasks):
            is_active = (idx == self.active_task_idx)
            course_code = (t.course or "TASK").strip()
            if is_active:
                short_title = t.title[:28] + "..." if len(t.title) > 28 else t.title
                lbl = Text(f"{course_code}: {short_title}")
                classes = "ai_tab_btn ai_tab_active"
            else:
                lbl = Text(f"{course_code}")
                classes = "ai_tab_btn ai_tab_inactive"

            btn = Button(lbl, id=f"btn_aitab_{idx}", classes=classes)
            tab_container.mount(btn)

    def select_task(self, idx: int, is_initial: bool = False) -> None:
        if idx < 0 or idx >= len(self.open_tasks):
            return

        old_idx = self.active_task_idx
        self.active_task_idx = idx
        self.active_task = self.open_tasks[idx]
        AiChatScreen._last_opened_task_id = self.active_task.id
        try:
            from services.ai_chat_service import save_last_active_ai_task_id
            save_last_active_ai_task_id(self.active_task.id)
        except Exception:
            pass

        for i, t in enumerate(self.open_tasks):
            try:
                b = self.query_one(f"#btn_aitab_{i}", Button)
                course_code = (t.course or "TASK").strip()
                if i == self.active_task_idx:
                    short_title = t.title[:28] + "..." if len(t.title) > 28 else t.title
                    b.label = Text(f"{course_code}: {short_title}")
                    b.remove_class("ai_tab_inactive")
                    b.add_class("ai_tab_active")
                else:
                    b.label = Text(f"{course_code}")
                    b.remove_class("ai_tab_active")
                    b.add_class("ai_tab_inactive")
                b.refresh(layout=True)
            except Exception:
                pass

        try:
            tab_container = self.query_one("#ai_tab_scroll", HorizontalScroll)
            tab_container.refresh(layout=True)
            active_btn = self.query_one(f"#btn_aitab_{self.active_task_idx}", Button)
            active_btn.scroll_visible(animate=False)
        except Exception:
            pass

        t = self.active_task
        try:
            self.query_one("#ai_task_banner_title", Label).update(f"{t.title}")
            meta_str = f"Due: {t.due_date_str or 'No deadline'}"
            if t.teacher:
                meta_str += f" | Teacher: {t.teacher}"
            if getattr(t, "attachments", None):
                meta_str += f" | 📎 {len(t.attachments)} attachment(s)"
            self.query_one("#ai_task_banner_meta", Label).update(meta_str)
        except Exception:
            pass

        from services.ai_chat_service import load_task_chat_cache
        self.chat_history[t.id] = load_task_chat_cache(t.id)

        try:
            self._refresh_chat_display()
        except Exception:
            pass

        if is_initial and self.auto_explain:
            from services.ai_chat_service import (
                is_task_ai_explained,
                set_task_ai_explained,
            )
            if not is_task_ai_explained(t.id):
                lang = self.cfg.get("language", "de")
                prompt = (
                    "Bitte erkläre mir diese Aufgabe verständlich, praxisnah und Schritt für Schritt. "
                    "Gehe dabei auf die Aufgabenstellung ein und erkläre, wie man am besten an die Lösung herangeht."
                    if lang == "de" else
                    "Please explain this assignment clearly, practically, and step-by-step. "
                    "Focus on the requirements and provide guidance on how to approach and solve the task."
                )
                self.send_user_message(prompt, is_explain=True)
            else:
                # The assignment was already explained in a previous session:
                # load the persisted explanation instead of sending it again.
                try:
                    self.app.notify("Existing explanation loaded.", severity="information")
                except Exception:
                    pass

    def _refresh_chat_display(self, scroll_to_assistant_top: bool = False) -> None:
        scroll = self.query_one("#ai_chat_scroll", VerticalScroll)
        scroll.remove_children()

        task = self.active_task
        if not task:
            scroll.mount(Label("No assignment selected.", classes="ai_empty_placeholder"))
            return

        msgs = self.chat_history.get(task.id, [])
        if not msgs and not self.is_waiting_for_ai:
            scroll.mount(Label(
                f"💬 Chat ready for '{task.title}'!\n\n"
                "Ask anything about requirements, theory, or step-by-step code examples below.",
                classes="ai_empty_placeholder"
            ))
            return

        last_assistant_bubble = None
        for m in msgs:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                bubble = Vertical(
                    Static(content, classes="ai_msg_text"),
                    classes="ai_msg_container ai_msg_user"
                )
                scroll.mount(bubble)
            else:
                bubble = Vertical(
                    Markdown(content, classes="ai_msg_text ai_msg_markdown"),
                    classes="ai_msg_container ai_msg_assistant"
                )
                scroll.mount(bubble)
                last_assistant_bubble = bubble

        if self.is_waiting_for_ai:
            dots = "." * getattr(self, "_thinking_step", 1)
            scroll.mount(Label(f"Thinking{dots}", classes="ai_thinking_box"))
            if getattr(self, "_thinking_timer", None) is None:
                try:
                    self._thinking_timer = self.set_interval(2.0 / 3.0, self._step_thinking_indicator)
                except Exception:
                    pass
        else:
            self._stop_thinking_timer()

        if scroll_to_assistant_top and last_assistant_bubble is not None:
            def _scroll_to_top():
                try:
                    last_assistant_bubble.scroll_visible(top=True, animate=False)
                except Exception:
                    pass
            self.call_after_refresh(_scroll_to_top)
        else:
            scroll.scroll_end(animate=False)

    def _stop_thinking_timer(self) -> None:
        if getattr(self, "_thinking_timer", None) is not None:
            try:
                self._thinking_timer.stop()
            except Exception:
                pass
            self._thinking_timer = None

    def _step_thinking_indicator(self) -> None:
        if not self.is_waiting_for_ai:
            self._stop_thinking_timer()
            return
        self._thinking_step = (getattr(self, "_thinking_step", 1) % 3) + 1
        dots = "." * self._thinking_step
        try:
            lbl = self.query_one(".ai_thinking_box", Label)
            lbl.update(f"Thinking{dots}")
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "btn_ai_clear_chat":
            self.action_clear_chat()
        elif bid in ("btn_ai_back", "btn_ai_close_screen"):
            self.action_dismiss_screen()
        elif bid.startswith("btn_aitab_"):
            try:
                idx = int(bid.replace("btn_aitab_", ""))
                self.select_task(idx)
            except Exception:
                pass

    def on_chat_input_area_submitted(self, event: ChatInputArea.Submitted) -> None:
        self.action_send_message()

    def on_input_submitted(self, event) -> None:
        if getattr(getattr(event, "input", None), "id", "") == "ai_chat_input":
            self.action_send_message()

    def action_send_message(self) -> None:
        try:
            inp = self.query_one("#ai_chat_input")
            text = (getattr(inp, "value", None) or getattr(inp, "text", "")).strip()
            if not text:
                return
            if hasattr(inp, "value"):
                inp.value = ""
            elif hasattr(inp, "clear"):
                inp.clear()
            self.send_user_message(text)
        except Exception:
            pass

    def send_user_message(self, text: str, is_explain: bool = False) -> None:
        if not text or self.is_waiting_for_ai or not self.active_task:
            return

        task = self.active_task
        task_id = task.id
        if task_id not in self.chat_history:
            self.chat_history[task_id] = []

        from services.ai_chat_service import save_task_chat_cache, build_task_ai_context, send_ai_chat_message

        user_msg = {"role": "user", "content": text, "timestamp": time.time()}
        if is_explain:
            user_msg["is_explain"] = True
        self.chat_history[task_id].append(user_msg)
        save_task_chat_cache(task_id, self.chat_history[task_id])

        self._thinking_step = 1
        self.is_waiting_for_ai = True
        self._refresh_chat_display()

        msgs_snapshot = list(self.chat_history[task_id])

        def worker():
            try:
                if not task.details_loaded:
                    try:
                        self.mgr.load_task_details(task)
                    except Exception:
                        pass

                files = []
                if getattr(task, "attachments", None):
                    try:
                        from core.config import CONFIG_DIR
                        dest = task.download_dir or os.path.join(CONFIG_DIR, "task_files", task.id)
                        files = self.mgr.download_task_files(task, dest_dir=dest)
                    except Exception:
                        pass

                lang = self.cfg.get("language", "de")
                system_prompt = build_task_ai_context(task, task_files=files, language=lang)
                reply = send_ai_chat_message(msgs_snapshot, system_prompt=system_prompt, config=self.cfg)
            except Exception as e:
                reply = f"Error during AI request: {e}"

            def update_ui():
                self.is_waiting_for_ai = False
                self.chat_history[task_id].append({
                    "role": "assistant",
                    "content": reply,
                    "timestamp": time.time()
                })
                save_task_chat_cache(task_id, self.chat_history[task_id])
                if (
                    is_explain
                    and isinstance(reply, str)
                    and not reply.startswith("Error:")
                    and not reply.startswith("AI request failed:")
                ):
                    try:
                        from services.ai_chat_service import set_task_ai_explained
                        set_task_ai_explained(task_id, True)
                    except Exception:
                        pass
                self._refresh_chat_display(scroll_to_assistant_top=True)

            self.app.call_from_thread(update_ui)

        threading.Thread(target=worker, daemon=True, name="AiChatRequestWorker").start()

    def action_clear_chat(self, force: bool = False) -> None:
        if not self.active_task:
            return
        task_id = self.active_task.id

        def _do_clear() -> None:
            from services.ai_chat_service import clear_task_chat_cache, set_task_ai_explained
            clear_task_chat_cache(task_id)
            set_task_ai_explained(task_id, False)
            self.chat_history[task_id] = []
            self._refresh_chat_display()
            self.app.notify("Chat cleared for current assignment.", severity="information")

        if force:
            _do_clear()
            return

        def _on_confirm(confirmed: Optional[bool]) -> None:
            if confirmed:
                _do_clear()

        self.app.push_screen(ClearChatConfirmModal(), _on_confirm)

    def action_prev_tab(self) -> None:
        if self.open_tasks and self.active_task_idx > 0:
            self.select_task(self.active_task_idx - 1)

    def action_next_tab(self) -> None:
        if self.open_tasks and self.active_task_idx < len(self.open_tasks) - 1:
            self.select_task(self.active_task_idx + 1)

    def action_dismiss_screen(self) -> None:
        self._stop_thinking_timer()
        self.dismiss()

    def on_unmount(self) -> None:
        self._stop_thinking_timer()


class SyncSpinner(Widget):
    """Animated sync spinner in the top right corner during background sync."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    DEFAULT_CSS = """
    SyncSpinner {
        width: 3;
        height: 1;
        content-align: right middle;
        text-align: right;
        display: block;
    }
    SyncSpinner.-active {
        display: block;
    }
    """

    active: reactive[bool] = reactive(False)
    frame_idx: reactive[int] = reactive(0)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._timer = None
        self.tooltip = "Syncing assignments..."

    def watch_active(self, active: bool) -> None:
        self.set_class(active, "-active")
        if active:
            if self._timer is None:
                self._timer = self.set_interval(0.25, self._advance_frame)
            else:
                self._timer.resume()
        else:
            if self._timer is not None:
                self._timer.pause()
        self.refresh()

    def _advance_frame(self) -> None:
        if self.active:
            self.frame_idx = (self.frame_idx + 1) % len(self.FRAMES)

    def render(self) -> RenderResult:
        if not self.active:
            return ""
        frame = self.FRAMES[self.frame_idx]
        return Text.from_markup(f"[bold #a6e3a1]{frame}[/]")

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None


class TasksDataTable(DataTable):
    """DataTable for Tasks with column-specific header hover highlighting for sortable columns."""

    def _should_highlight(self, cursor: Coordinate, target_cell: Coordinate, type_of_cursor: str) -> bool:
        cursor_row, cursor_col = cursor
        cell_row, cell_col = target_cell
        if cell_row == -1:
            if cursor_row == -1:
                sortable_cols = {1, 2, 4, 5, 6}
                return (cursor_col == cell_col) and (cell_col in sortable_cols)
            return False
        return super()._should_highlight(cursor, target_cell, type_of_cursor)

    def watch_hover_coordinate(self, old: Coordinate, value: Coordinate) -> None:
        super().watch_hover_coordinate(old, value)
        if old.row == -1 or value.row == -1:
            self.refresh_line(0)


class TasksApp(App):
    """
    Hauptanwendung von Tasks mit moderner Terminal-TUI und Maus-Buttons.
    """

    TITLE = "TASKS"
    SUB_TITLE = "School Assignment Hub"

    CSS = """
    #info_bar {
        dock: top;
        height: 1;
        margin-bottom: 1;
        padding: 0 1;
        align: left middle;
        overflow-x: hidden;
        overflow-y: hidden;
    }

    #info_stats {
        width: 1fr;
        height: 1;
        text-style: bold;
        overflow-x: hidden;
    }

    #tasks_table {
        height: 1fr;
    }
    #tasks_table > .datatable--header-hover {
        background: $accent 30%;
        color: $foreground;
        text-style: bold;
    }
    .-theme-oled #tasks_table > .datatable--header-hover {
        background: #1e1e2e;
        color: #89b4fa;
        text-style: bold;
    }

    #button_bar {
        dock: bottom;
        height: 3;
        width: 100%;
        padding: 0 1;
        overflow-x: hidden;
        overflow-y: hidden;
        align: left middle;
    }

    #main_center_buttons {
        width: 1fr;
        height: 100%;
        align: center middle;
    }

    #button_bar Button {
        margin: 0 1;
        min-width: 4;
        height: 100%;
        content-align: center middle;
    }

    /* Toast Notification Styling (Fix für Kontrast / Theme-Unabhängigkeit) */
    Toast {
        background: #1e1e2e;
        color: #cdd6f4;
        border-left: outer #89b4fa;
    }
    Toast:ansi {
        background: #1e1e2e;
        color: #cdd6f4;
    }
    Toast .toast--title {
        color: #89b4fa;
        text-style: bold;
    }
    Toast.-information {
        border-left: outer #89b4fa;
        background: #1e1e2e;
        color: #cdd6f4;
    }
    Toast.-information .toast--title {
        color: #89dceb;
    }
    Toast.-warning {
        border-left: outer #f9e2af;
        background: #1e1e2e;
        color: #cdd6f4;
    }
    Toast.-warning .toast--title {
        color: #f9e2af;
    }
    Toast.-error {
        border-left: outer #f38ba8;
        background: #1e1e2e;
        color: #cdd6f4;
    }
    Toast.-error .toast--title {
        color: #f38ba8;
    }

    /* OLED Theme: Pure black surfaces, styled bars & colored/gray buttons */
    .-theme-oled Screen {
        background: #000000;
    }
    .-theme-oled #tasks_table,
    .-theme-oled #exams_table_container,
    .-theme-oled #exams_table,
    .-theme-oled #abs_split_container,
    .-theme-oled #abs_subject_box,
    .-theme-oled #abs_detail_box,
    .-theme-oled #abs_subject_table,
    .-theme-oled #abs_detail_table {
        background: #000000;
    }
    .-theme-oled DataTable,
    .-theme-oled DataTable:focus {
        background: #000000;
        background-tint: transparent;
    }
    .-theme-oled DataTable > .datatable--header,
    .-theme-oled DataTable:focus > .datatable--header {
        background: #100f0f;
        background-tint: transparent;
        color: #ffffff;
        text-style: bold;
    }
    .-theme-oled DataTable > .datatable--cursor,
    .-theme-oled DataTable:focus > .datatable--cursor {
        background: #205ea6;
        color: #ffffff;
    }
    .-theme-oled DataTable > .datatable--even-row,
    .-theme-oled DataTable:focus > .datatable--even-row,
    .-theme-oled DataTable > .datatable--odd-row,
    .-theme-oled DataTable:focus > .datatable--odd-row {
        background: #000000;
    }
    .-theme-oled #info_bar {
        background: #000000;
    }
    .-theme-oled #button_bar {
        background: #000000;
    }
    .-theme-oled Header {
        background: #000000;
    }
    .-theme-oled #exams_header,
    .-theme-oled #exams_button_bar,
    .-theme-oled #absences_header,
    .-theme-oled #absences_button_bar {
        background: #000000;
    }
    .-theme-oled Button {
        height: 3;
        border: none;
        background: #282726;
        color: #ffffff;
        content-align: center middle;
    }
    .-theme-oled Button:hover {
        background: #343331;
        color: #ffffff;
    }
    .-theme-oled Button.-primary {
        background: #205ea6;
        color: #ffffff;
        border: none;
    }
    .-theme-oled Button.-primary:hover {
        background: #2868b2;
    }
    .-theme-oled Button.-success {
        background: #66800b;
        color: #ffffff;
        border: none;
    }
    .-theme-oled Button.-success:hover {
        background: #75920d;
    }
    .-theme-oled Button.-error {
        background: #af3029;
        color: #ffffff;
        border: none;
    }
    .-theme-oled Button.-error:hover {
        background: #c33a32;
    }
    .-theme-oled Button.-warning {
        background: #ad8301;
        color: #ffffff;
        border: none;
    }
    .-theme-oled Button.-warning:hover {
        background: #ba8d03;
    }
    .-theme-oled #button_bar Button {
        border: none;
        color: #ffffff;
    }
    #ai_top_bar {
        height: 1;
    }
    #ai_tab_scroll {
        height: 1;
    }
    #ai_tab_scroll Button.ai_tab_btn {
        margin-right: 1;
        min-width: 6;
        width: auto;
        height: 1;
        border: none;
        background: #1e1e2e;
        color: #a6adc8;
        content-align: center middle;
    }
    #ai_tab_scroll Button.ai_tab_btn:hover {
        background: #313244;
        color: #ffffff;
    }
    #ai_tab_scroll Button.ai_tab_active {
        border: none;
        background: #89b4fa;
        color: #11111b;
        text-style: bold;
        content-align: center middle;
    }
    #ai_tab_scroll Button.ai_tab_active:hover {
        background: #b4befe;
        color: #11111b;
    }
    .-theme-oled #ai_top_bar {
        height: 1;
        background: #000000;
    }
    .-theme-oled #ai_tab_scroll {
        height: 1;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_btn {
        background: #181816;
        color: #a6a69c;
        border: none;
        height: 1;
        content-align: center middle;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_btn:hover {
        background: #282726;
        color: #ffffff;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_active {
        background: #205ea6;
        border: none;
        color: #ffffff;
        text-style: bold;
        height: 1;
        content-align: center middle;
    }
    .-theme-oled #ai_tab_scroll Button.ai_tab_active:hover {
        background: #2868b2;
        color: #ffffff;
    }
    #ai_input_bar {
        dock: bottom;
        height: 7;
        min-height: 7;
        max-height: 7;
        border-top: solid #313244;
        border-bottom: solid #313244;
        padding: 0 1;
        align: left middle;
    }
    ChatInputArea {
        height: 5;
        min-height: 5;
        max-height: 5;
        border: solid #45475a;
        background: #1e1e2e;
        color: #cdd6f4;
        padding: 1 1 1 1;
        scrollbar-size: 1 1;
        scrollbar-color: #89b4fa #181825;
    }
    ChatInputArea:focus {
        border: solid #89b4fa;
    }
    #ai_chat_input {
        width: 1fr;
        margin-right: 1;
    }
    #ai_input_btn_box {
        width: 11;
        min-width: 11;
        max-width: 11;
        height: 5;
        layout: vertical;
        align: right bottom;
    }
    #btn_ai_clear_chat {
        width: 100%;
        min-width: 4;
        height: 1;
        min-height: 1;
        max-height: 1;
        margin-bottom: 1;
        border: none;
        background: #e03131;
        color: #ffffff;
        content-align: center middle;
        text-align: center;
        padding: 0;
    }
    #btn_ai_clear_chat:hover {
        background: #c92a2a;
    }
    #btn_ai_back {
        width: 100%;
        min-width: 4;
        height: 3;
        min-height: 3;
        max-height: 3;
        content-align: center middle;
        text-align: center;
    }
    #btn_ai_back:hover {
        background: #45475a;
        color: #ffffff;
    }
    .-theme-oled #ai_input_bar {
        background: #000000;
        border-top: solid #343331;
        border-bottom: solid #343331;
        height: 7;
        min-height: 7;
        max-height: 7;
    }
    .-theme-oled #ai_input_btn_box {
        width: 11;
        min-width: 11;
        max-width: 11;
        height: 5;
        layout: vertical;
        align: right bottom;
    }
    .-theme-oled #btn_ai_clear_chat {
        width: 100%;
        min-width: 4;
        height: 1;
        min-height: 1;
        max-height: 1;
        margin-bottom: 1;
        content-align: center middle;
        text-align: center;
        background: #e03131;
        color: #ffffff;
        border: none;
        padding: 0;
    }
    .-theme-oled #btn_ai_clear_chat:hover {
        background: #c92a2a;
    }
    .-theme-oled ChatInputArea {
        background: #181816;
        color: #ffffff;
        border: solid #343331;
        height: 5;
        min-height: 5;
        max-height: 5;
        padding: 1 1 1 1;
        scrollbar-size: 1 1;
        scrollbar-color: #58a6ff #000000;
    }
    .-theme-oled ChatInputArea:focus {
        border: solid #58a6ff;
    }
    .-theme-oled #ai_chat_input {
        width: 1fr;
        margin-right: 1;
    }
    .-theme-oled #btn_ai_back {
        background: #282726;
        color: #ffffff;
        border: none;
        height: 3;
        min-height: 3;
        max-height: 3;
        min-width: 4;
        content-align: center middle;
        text-align: center;
    }
    .-theme-oled #btn_ai_back:hover {
        background: #343331;
    }
    .-theme-oled .theme_btn:hover,
    .-theme-oled .theme_btn:focus {
        background: #343331;
        color: #ffffff;
    }
    .-theme-oled #add_dialog,
    .-theme-oled #status_dialog,
    .-theme-oled #plat_dialog,
    .-theme-oled #tf_dialog,
    .-theme-oled #filter_dialog,
    .-theme-oled #book_url_dialog,
    .-theme-oled #digi_download_dialog,
    .-theme-oled #d4s_progress_dialog,
    .-theme-oled #update_dialog,
    .-theme-oled #settings_dialog,
    .-theme-oled #tray_config_dialog,
    .-theme-oled #theme_dialog,
    .-theme-oled #subj_dialog,
    .-theme-oled #detail_dialog,
    .-theme-oled #trash_dialog,
    .-theme-oled #moodle_dialog,
    .-theme-oled #teams_dialog,
    .-theme-oled #login_choice_dialog,
    .-theme-oled #git_setup_dialog,
    .-theme-oled #untis_dialog,
    .-theme-oled #school_config_dialog,
    .-theme-oled #excuse_dialog,
    .-theme-oled #add_exam_dialog,
    .-theme-oled #exam_detail_dialog {
        background: #000000;
        border: thick #343331;
    }
    .-theme-oled UnifiedCommandPalette #--container {
        background: #000000;
        border: thick #24837b;
    }
    .-theme-oled UnifiedCommandPalette .palette-tab {
        background: #141414;
        color: #777777;
    }
    .-theme-oled UnifiedCommandPalette .palette-tab.-active-courses {
        background: #04a5e5;
        color: #ffffff;
    }
    .-theme-oled UnifiedCommandPalette .palette-tab.-active-books {
        background: #e64553;
        color: #ffffff;
    }
    .-theme-oled UnifiedCommandPalette .palette-tab.-active-directories {
        background: #40a02b;
        color: #ffffff;
    }
    .-theme-oled CommandPalette #--container {
        background: #000000;
        border: thick #205ea6;
    }
    .-theme-oled Toast {
        background: #000000;
        border-left: outer #24837b;
        color: #fffcf0;
    }
    """

    BINDINGS = [
        Binding("a", "add_task", "Add Task"),
        Binding("e", "show_exams", "Tests & Exams"),
        Binding("i", "show_ai_chat", "Ai Assistant"),
        Binding("backspace", "open_courses_palette", "Open Course", show=False),
        Binding("slash", "open_courses_palette", "Open Course", show=False),
        Binding("f", "open_filter_menu", "Filter"),
        Binding("s", "filter_status", "Status Filter", show=False),
        Binding("r", "sync_tasks", "Synchronize"),
        Binding("u", "show_absences", "Absences"),
        Binding("g", "show_trash", "Trash"),
        Binding("l", "login_menu", "Login"),
        Binding("o", "open_settings", "Settings"),
        Binding("p", "filter_platform", "Platform", show=False),
        Binding("d", "filter_timeframe", "Max Duration Filter", show=False),
        Binding("t", "change_theme", "Theme", show=False),
        Binding("ctrl+p", "change_theme", "Theme / Palette", show=False),
        Binding("m", "setup_moodle", "Moodle Setup", show=False),
        Binding("q", "quit_app", "Quit"),
        Binding("ctrl+c", "real_quit", "Force Quit to Terminal", show=False),
        # Direct selection 1-9
        Binding("1", "select_task(1)", "Task 1", show=False),
        Binding("2", "select_task(2)", "Task 2", show=False),
        Binding("3", "select_task(3)", "Task 3", show=False),
        Binding("4", "select_task(4)", "Task 4", show=False),
        Binding("5", "select_task(5)", "Task 5", show=False),
        Binding("6", "select_task(6)", "Task 6", show=False),
        Binding("7", "select_task(7)", "Task 7", show=False),
        Binding("8", "select_task(8)", "Task 8", show=False),
        Binding("9", "select_task(9)", "Task 9", show=False),
    ]

    NOTIFICATION_TIMEOUT: float = 3.0

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: Optional[float] = None,
        markup: bool = True,
    ) -> None:
        """Alle Benachrichtigungen rechts unten generell immer 3s anzeigen."""
        super().notify(
            message,
            title=title,
            severity=severity,  # type: ignore
            timeout=3.0 if timeout is None else timeout,
            markup=markup,
        )

    def __init__(self, mgr: Optional[TaskManager] = None, sync_on_startup: Optional[bool] = None, start_hidden: bool = False):
        super().__init__()
        self.mgr = mgr or TaskManager(autostart_prefetch=True)
        self.sync_on_startup = sync_on_startup
        self.start_hidden = start_hidden
        self.is_hidden_in_tray = False
        self._tray_service = None
        self._single_instance_server = None
        self.platform_filter = "all"
        self.status_filter = "open_only"
        self.subject_filter = "all"
        self.timeframe_filter = "2_weeks"
        self.current_tasks: List[Task] = []
        self._is_syncing = False
        self._sync_not_complete_printed: bool = False
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_mouse_listener = threading.Event()
        self._mouse_listener_thread: Optional[threading.Thread] = None
        self._terminal_hwnd: Optional[int] = None
        self._console_ctrl_handler_installed: bool = False
        self._console_ctrl_cb: Optional[Callable] = None
        self._conhost_close_disabled: bool = False
        self._last_sync_table_refresh: float = 0.0
        self.sort_column: Optional[str] = "due_date"
        self.sort_direction: str = "desc"
        self._task_fixed_ids_map: Dict[int, Task] = {}

        # Theme initialisieren & nur die erlaubten Themes behalten
        self.register_theme(OLED_THEME)
        saved_theme = load_saved_theme()
        if saved_theme in ALLOWED_THEMES:
            self.theme = saved_theme
        else:
            self.theme = DEFAULT_THEME

        for t in list(self.available_themes.keys()):
            if t not in ALLOWED_THEMES:
                self.unregister_theme(t)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="info_bar"):
            yield Label("Loading statistics...", id="info_stats")
            yield SyncSpinner(id="sync_spinner")
        dt = TasksDataTable(id="tasks_table", cursor_type="row")
        yield dt
        with Horizontal(id="button_bar"):
            yield Button("📋 Absences", id="btn_main_absences", variant="primary", tooltip="Untis absences [U]")
            yield Button("📅 Tests", id="btn_main_exams", variant="primary", tooltip="Exams & tests [E]")
            yield Button("🤖 Ai", id="btn_main_ai", variant="primary", tooltip="Ai assistant [I]")
            with Horizontal(id="main_center_buttons"):
                yield Button("➕ Add", id="btn_main_add", variant="success", tooltip="Add homework [A]")
                yield Button("🔄 Sync", id="btn_main_sync", variant="success", tooltip="Synchronize assignments [R]")
                yield Button("🔍 Filter", id="btn_main_filter", variant="primary", tooltip="Filter assignments [F]")
                yield Button("⚙️ Settings", id="btn_main_settings", variant="default", tooltip="Settings & theme [O]")
            yield Button("❌ Exit", id="btn_main_quit", variant="error", tooltip="Exit [Q / Ctrl+C]")


    def on_mount(self) -> None:
        dt = self.query_one(DataTable)
        dt.cell_padding = 2
        dt.add_columns("#", "Platform", "Subject", "Assignment", "Due Date", "Status", "Teacher")

        # Gecachte Aufgaben sofort anzeigen
        self.refresh_table()

        # Beim Start automatisch immer wie beim Klick auf den Sync-Button synchronisieren
        should_sync = self.sync_on_startup if self.sync_on_startup is not None else (not self.is_headless)
        if should_sync:
            self.action_sync_tasks()

        # Prüfe im Hintergrund auf neue Releases (geräuschlos, blockiert Start nicht)
        if not self.is_headless:
            self._start_update_checker()

        # Win32 Console Icon setzen (falls im klassischen conhost CMD-Fenster ausgeführt)
        if sys.platform == "win32" and not self.is_headless:
            self._set_win32_console_icon()

        # System Tray & Single-Instance IPC starten
        if sys.platform == "win32" and not self.is_headless:
            self._init_tray_and_ipc()


        # Starte Hintergrund-Thread für Maus-Zurück-Taste (Seitentaste XBUTTON1 / "Hinten")
        self._terminal_hwnd = get_terminal_window_hwnd() or _CACHED_TERMINAL_HWND
        if sys.platform == "win32" and not self.is_headless:
            self._start_mouse_back_listener()

        # Sicherstellen, dass das Terminal-Layout beim Start sauber synchronisiert ist
        self.call_after_refresh(self._sync_initial_viewport)

    def _set_win32_console_icon(self) -> None:
        """Sets the window icon for classic conhost console windows via WM_SETICON."""
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets")
                ico_path = os.path.join(assets_dir, "app_icon.ico")
                if os.path.exists(ico_path):
                    IMAGE_ICON = 1
                    LR_LOADFROMFILE = 0x00000010
                    hicon_sm = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                    hicon_big = ctypes.windll.user32.LoadImageW(None, ico_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
                    WM_SETICON = 0x0080
                    ICON_SMALL = 0
                    ICON_BIG = 1
                    if hicon_sm:
                        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
                    if hicon_big:
                        ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
        except Exception:
            pass

    def _init_tray_and_ipc(self) -> None:
        """Initialisiert den System-Tray-Dienst und den Single-Instance-Server."""
        try:
            from config import is_minimize_to_tray_enabled
            if not is_minimize_to_tray_enabled():
                return
        except Exception:
            pass

        try:
            from single_instance import SingleInstanceServer
            self._single_instance_server = SingleInstanceServer(on_command_callback=self._handle_ipc_command)
            self._single_instance_server.start()
        except Exception:
            pass

        try:
            from tray_service import TrayService
            open_cnt = len([t for t in getattr(self.mgr, "tasks", []) if not getattr(t, "completed", False) and not getattr(t, "deleted", False)])
            self._tray_service = TrayService(
                on_open=self.restore_from_tray,
                on_sync=lambda: self.call_from_thread(self.action_sync_tasks),
                on_quit=lambda: self.call_from_thread(self.action_real_quit),
                open_count=open_cnt,
            )
            self._tray_service.start()
        except Exception:
            pass

        if getattr(self, "start_hidden", False):
            self.call_after_refresh(self.hide_to_tray)

    def _ipc_show(self) -> str:
        """Stellt das versteckte Fenster wieder her (Single-Instance-Befehl ``SHOW``)."""
        self.restore_from_tray()
        return "RESTORED"

    def _handle_ipc_command(self, cmd: str) -> str:
        """Verarbeitet eingehende Single-Instance-Befehle von sekundären CLI-Aufrufen."""
        cmd_upper = (cmd or "").strip().upper()
        if cmd_upper == "SHOW":
            return self._ipc_show()
        elif cmd_upper == "QUIT":
            self.call_from_thread(self.action_real_quit)
            return "OK:QUITTING"
        elif cmd_upper == "STATUS":
            count = len([t for t in getattr(self.mgr, "tasks", []) if not getattr(t, "completed", False) and not getattr(t, "deleted", False)])
            return f"OK:TASKS={count}"
        return "ERROR:UNKNOWN"

    def hide_to_tray(self) -> None:
        """Minimiert das Konsolenfenster unsichtbar ins Windows System Tray (SW_HIDE)."""
        if sys.platform != "win32":
            return
        hwnd = self._terminal_hwnd or get_terminal_window_hwnd() or _CACHED_TERMINAL_HWND
        if hwnd:
            self._terminal_hwnd = hwnd
            try:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
                self.is_hidden_in_tray = True
            except Exception:
                pass

    def restore_from_tray(self) -> None:
        """Stellt das versteckte Fenster wieder her und bringt es zuverlässig in den Vordergrund."""
        if sys.platform != "win32":
            return
        hwnd = self._terminal_hwnd or get_terminal_window_hwnd() or _CACHED_TERMINAL_HWND
        if hwnd:
            self._terminal_hwnd = hwnd
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                # 1. Unhide & Restore
                SW_SHOW = 5
                SW_RESTORE = 9
                user32.ShowWindow(hwnd, SW_SHOW)
                user32.ShowWindow(hwnd, SW_RESTORE)

                # 2. Window Position & Visibility erzwingen
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                HWND_TOP = 0
                user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

                # 3. Windows Foreground-Lock zuverlässig umgehen
                user32.AllowSetForegroundWindow(-1)  # ASFW_ANY = -1
                fg_hwnd = user32.GetForegroundWindow()
                if fg_hwnd and fg_hwnd != hwnd:
                    cur_tid = kernel32.GetCurrentThreadId()
                    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                    if cur_tid != fg_tid and fg_tid != 0:
                        user32.AttachThreadInput(cur_tid, fg_tid, True)
                        user32.SetForegroundWindow(hwnd)
                        user32.BringWindowToTop(hwnd)
                        user32.SetFocus(hwnd)
                        user32.AttachThreadInput(cur_tid, fg_tid, False)
                    else:
                        user32.SetForegroundWindow(hwnd)
                        user32.BringWindowToTop(hwnd)
                else:
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)

                self.is_hidden_in_tray = False
            except Exception:
                pass


    def action_real_quit(self) -> None:
        """Beendet die Anwendung vollständig, auch wenn 'minimize_to_tray' aktiv ist."""
        self.action_quit_app(force=True)


    def _start_update_checker(self) -> None:
        """Startet die Prüfung auf neuere GitHub-Releases in einem Hintergrund-Thread."""
        def worker():
            try:
                try:
                    from update_service import check_for_updates
                except ImportError:
                    from src.services.update_service import check_for_updates

                update_info = check_for_updates()
                if update_info:
                    self.call_from_thread(self._show_update_modal, update_info)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name="UpdateCheckWorker").start()

    def _show_update_modal(self, update_info: Dict[str, Any]) -> None:
        """Öffnet das Update-Erinnerungsmodal im UI-Thread."""
        try:
            self.push_screen(UpdateReminderModal(update_info))
        except Exception:
            pass

    def _sync_initial_viewport(self) -> None:
        """
        Stellt sicher, dass das initiale Layout nach dem ersten Rendern stabil steht.
        Postet KEINE künstlichen Resize-Events in die Event-Queue, um ConPTY-Desynchronisationen
        und Render-Glitches (wiederholte Zeilen, Geistertext) vollständig zu verhindern.
        """
        if self.is_headless:
            return
        try:
            self.refresh(layout=True)
            self.refresh_table()
        except Exception:
            pass

    def on_resize(self, event: Resize) -> None:
        """Passt Spaltenbreiten bei echten Terminalgrößenänderungen dynamisch an."""
        if self.is_mounted and hasattr(self, "current_tasks"):
            override_w = (event.size.width - 2) if (event.size and event.size.width > 0) else None
            self.refresh_table(term_w_override=override_w)

    def refresh_table(self, term_w_override: Optional[int] = None) -> None:
        """Aktualisiert die Aufgaben-Tabelle und die Statusleiste."""
        try:
            dt = self.query_one(DataTable)
        except Exception:
            return
        if not dt.columns:
            return

        saved_row = dt.cursor_row
        dt.clear()

        # Gefilterte Aufgaben laden
        subj = None if self.subject_filter == "all" else self.subject_filter
        self.current_tasks = self.mgr.get_filtered_tasks(
            platform_filter=self.platform_filter,
            status_filter=self.status_filter,
            subject_filter=subj,
            timeframe_filter=self.timeframe_filter,
        )

        # Sortierung anwenden
        if self.sort_column:
            if self.sort_column == "due_date":
                def due_key(t: Task) -> tuple:
                    is_done = 1 if getattr(t, "is_completed", False) else 0
                    is_welcome = 0 if getattr(t, "id", "") == "manual_welcome_setup_guide" else 1
                    is_over = 0 if getattr(t, "is_overdue", False) else 1
                    ts = getattr(t, "due_timestamp", None)
                    if ts is None or ts <= 0:
                        ts = parse_deadline_for_sorting(getattr(t, "due_date_str", ""))
                    if self.sort_direction == "desc":
                        # Due Date ↓: Nächste Fälligkeit zuerst oben
                        val = ts if (ts and ts > 0) else time.time() + 9999999
                        return (is_done, is_welcome, is_over, val)
                    else:
                        # Due Date ↑: Späteste Fälligkeit zuerst oben
                        val = -ts if (ts and ts > 0) else float('inf')
                        return (is_done, is_welcome, is_over, val)
                self.current_tasks.sort(key=due_key)
            elif self.sort_column == "platform":
                reverse = (self.sort_direction == "desc")
                self.current_tasks.sort(
                    key=lambda t: (1 if t.is_completed else 0, (t.platform or "").lower()),
                    reverse=reverse,
                )
            elif self.sort_column == "subject":
                reverse = (self.sort_direction == "desc")
                self.current_tasks.sort(
                    key=lambda t: (1 if t.is_completed else 0, (t.course or "").lower()),
                    reverse=reverse,
                )
            elif self.sort_column == "status":
                reverse = (self.sort_direction == "desc")
                self.current_tasks.sort(
                    key=lambda t: format_status_english(t).lower(),
                    reverse=reverse,
                )
            elif self.sort_column == "teacher":
                reverse = (self.sort_direction == "desc")
                def teacher_key(t):
                    is_done = 1 if t.is_completed else 0
                    tch = (getattr(t, "teacher", None) or "").strip()
                    val = tch.lower() if tch and tch != "-" else ("zzzz" if not reverse else "")
                    return (is_done, val)
                self.current_tasks.sort(key=teacher_key, reverse=reverse)

        try:
            from services.ai_chat_service import cleanup_ai_chats_cache
            all_m_tasks = getattr(self.mgr, "tasks", [])
            open_task_ids = {
                t.id for t in all_m_tasks
                if not getattr(t, "is_completed", False) and str(getattr(t, "status", "")).lower() in ["offen", "ueberfaellig", "open", "overdue"]
            }
            if open_task_ids:
                cleanup_ai_chats_cache(open_task_ids)
        except Exception:
            pass

        # Dynamische Breitenberechnung: Verteilt alle 7 Spalten proportional über die gesamte Breite,
        # sodass rechts kein Platz frei bleibt und Assignment maximalen Raum erhält, ohne horizontal zu scrollen.
        if term_w_override is not None and term_w_override > 0:
            term_w = term_w_override
        else:
            try:
                term_w = dt.size.width if (dt.size and dt.size.width > 0) else (self.size.width - 2 if self.size and self.size.width > 0 else 121)
            except Exception:
                term_w = self.size.width - 2 if (self.size and self.size.width > 0) else 121

        avail_w = max(70, term_w - 1)  # 1 Spalte Puffer für vertikale Scrollbar
        total_padding = 7 * (2 * dt.cell_padding)
        avail_content = max(35, avail_w - total_padding)

        if avail_content < 76:
            w_idx = 2
            w_plat = 10 if self.sort_column == "platform" else 8
            w_subj = 9 if self.sort_column == "subject" else 4
            w_stat = 8
            w_teach = 9 if self.sort_column == "teacher" else 7
            w_assign = min(22, max(21, int(avail_content * 0.35)))
            w_due = max(9, avail_content - (w_idx + w_plat + w_subj + w_stat + w_teach + w_assign))
            w_assign = avail_content - (w_idx + w_plat + w_subj + w_due + w_stat + w_teach)
            col_widths = [w_idx, w_plat, w_subj, w_assign, w_due, w_stat, w_teach]
        else:
            w_idx = 3
            w_plat = 10  # "Platform ↑" = 10 Zeichen
            w_subj = 9   # "Subject ↑" = 9 Zeichen
            w_due = 28   # "Due Date ↑" = 10 Zeichen, Daten min. 28
            w_stat = 11  # "Status ↑" = 8 Zeichen, "✓ Completed" = 11
            w_teach = 9  # "Teacher ↑" = 9 Zeichen, min. 8 für Teacher-Kürzel
            fixed_sum = w_idx + w_plat + w_subj + w_due + w_stat + w_teach  # 70

            if avail_content >= fixed_sum + 17:
                extra = avail_content - (fixed_sum + 17)
                add_due = min(4, int(extra * 0.15))
                add_teach = min(2, int(extra * 0.05))
                add_subj = min(2, int(extra * 0.05))
                w_due += add_due
                w_teach += add_teach
                w_subj += add_subj
                w_assign = avail_content - (w_idx + w_plat + w_subj + w_due + w_stat + w_teach)
            else:
                w_subj = 7
                w_teach = 8
                w_assign = max(21, avail_content - (w_idx + w_plat + w_subj + 20 + w_stat + w_teach))
                w_due = max(16, avail_content - (w_idx + w_plat + w_subj + w_stat + w_teach + w_assign))
                w_assign = avail_content - (w_idx + w_plat + w_subj + w_due + w_stat + w_teach)

            col_widths = [w_idx, w_plat, w_subj, w_assign, w_due, w_stat, w_teach]

        # Spaltenbreiten der DataTable fest zuweisen und Sortierpfeile im Header aktualisieren
        base_labels = ["#", "Platform", "Subject", "Assignment", "Due Date", "Status", "Teacher"]
        col_names = [None, "platform", "subject", None, "due_date", "status", "teacher"]
        if dt.columns:
            arrow = " ↑" if self.sort_direction == "asc" else " ↓"
            for idx, (col_obj, w) in enumerate(zip(dt.columns.values(), col_widths)):
                if idx < len(base_labels):
                    base_lbl = base_labels[idx]
                    cname = col_names[idx]
                    if cname and self.sort_column == cname:
                        col_obj.label = Text(f"{base_lbl}{arrow}")
                    else:
                        col_obj.label = Text(base_lbl)
                col_obj.width = w
                col_obj.auto_width = False
            dt._clear_caches()

        max_title_len = col_widths[3]
        max_course_len = col_widths[2]
        max_due_len = col_widths[4]
        max_teach_len = col_widths[6]
        seen_row_keys = set()

        for idx, t in enumerate(self.current_tasks, 1):
            is_done = t.is_completed
            is_over = t.is_overdue

            # Platform badge
            if is_done:
                if t.platform == "moodle":
                    plat_badge = Text("🟧 Moodle", style="dim")
                elif t.platform == "teams":
                    plat_badge = Text("🟦 Teams", style="dim")
                else:
                    plat_badge = Text("✏️ Manual", style="dim")
            else:
                if t.platform == "moodle":
                    plat_badge = Text("🟧 Moodle", style="bold orange3")
                elif t.platform == "teams":
                    plat_badge = Text("🟦 Teams", style="bold dodger_blue1")
                else:
                    plat_badge = Text("✏️ Manual", style="bold green")

            # Subject styling with smart truncation
            clean_course = " ".join(t.course.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())
            if len(clean_course) > max_course_len:
                course_text = clean_course[: max(0, max_course_len - 3)].rstrip() + "..."
            else:
                course_text = clean_course
            subj_styled = Text(course_text, style="dim cyan" if is_done else "bold cyan", no_wrap=True, overflow="ellipsis")

            # Status styling & normalization
            disp_txt = format_status_english(t)

            st_lower = t.status.lower()
            if is_done or disp_txt == "Completed":
                status_styled = Text(f"✓ {disp_txt}", style="dim green", no_wrap=True, overflow="ellipsis")
            elif is_over or disp_txt == "Overdue" or "ueberfaellig" in st_lower or "überfällig" in st_lower or "overdue" in st_lower:
                status_styled = Text(f"⚠ {disp_txt}", style="bold red", no_wrap=True, overflow="ellipsis")
            elif disp_txt == "Open":
                status_styled = Text("Open", style="bold yellow", no_wrap=True, overflow="ellipsis")
            else:
                status_styled = Text(disp_txt, style="bold yellow", no_wrap=True, overflow="ellipsis")

            # Title styling (Open ones stand out immediately) with clean "..." truncation
            clean_title = " ".join(t.title.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())
            if len(clean_title) > max_title_len:
                title_text = clean_title[: max(0, max_title_len - 3)].rstrip() + "..."
            else:
                title_text = clean_title
            if is_done:
                title_styled = Text(title_text, style="dim white", no_wrap=True, overflow="ellipsis")
            elif is_over:
                title_styled = Text(title_text, style="bold red", no_wrap=True, overflow="ellipsis")
            else:
                title_styled = Text(title_text, style="bold white", no_wrap=True, overflow="ellipsis")

            # Due date styling with smart truncation
            due_raw = " ".join(t.due_date_str.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())
            if len(due_raw) > max_due_len:
                due_str = due_raw[: max(0, max_due_len - 3)].rstrip() + "..."
            else:
                due_str = due_raw
            due_styled = Text(due_str, no_wrap=True, overflow="ellipsis")
            due_lower = due_raw.lower()
            if is_done:
                due_styled.stylize("dim")
            elif is_over or "überfällig" in due_lower or "overdue" in due_lower or "vor " in due_lower:
                due_styled.stylize("bold red")
            elif "heute" in due_lower or "today" in due_lower:
                due_styled.stylize("bold yellow")
            elif "morgen" in due_lower or "tomorrow" in due_lower:
                due_styled.stylize("bold cyan")

            idx_styled = Text(str(idx), style="dim" if is_done else "bold", no_wrap=True)
            clean_teacher = " ".join((t.teacher or "").replace("\r\n", " ").replace("\n", " ").replace("\r", " ").split())
            teacher_str = clean_teacher if clean_teacher and clean_teacher != "-" else ""
            if len(teacher_str) > max_teach_len:
                teacher_str = teacher_str[: max(0, max_teach_len - 3)].rstrip() + "..."
            teacher_styled = Text(teacher_str, style="dim" if is_done else "white", no_wrap=True, overflow="ellipsis")

            row_key = t.id if t.id not in seen_row_keys else f"{t.id}_{idx}"
            seen_row_keys.add(row_key)

            dt.add_row(
                idx_styled,
                plat_badge,
                subj_styled,
                title_styled,
                due_styled,
                status_styled,
                teacher_styled,
                height=2,
                key=row_key,
            )

        if saved_row is not None and 0 <= saved_row < len(self.current_tasks):
            try:
                dt.move_cursor(row=saved_row)
            except Exception:
                pass

        # Update statistics via helper
        self.update_info_bar(term_w_override=term_w)

    def update_info_bar(self, term_w_override: Optional[int] = None) -> None:
        """Aktualisiert die Statistik- und Statuszeile im Info-Bar ohne DataTable-Neuaufbau."""
        try:
            visible_tasks = getattr(self, "current_tasks", []) or []
            moodle_cnt = len([t for t in visible_tasks if t.platform == "moodle"])
            teams_cnt = len([t for t in visible_tasks if t.platform == "teams"])
            manual_cnt = len([t for t in visible_tasks if t.platform in ["manual", "custom"]])
            del_cnt = len(self.mgr.get_deleted_tasks())

            open_tasks = [t for t in visible_tasks if not t.is_completed]
            overdue_cnt = len([t for t in visible_tasks if t.is_overdue])
            open_cnt = len(open_tasks)
            total_visible = len(visible_tasks)

            badges = []

            # 1. To Do / Status Badge
            if self.status_filter in ["completed", "abgegeben", "erledigt", "done"]:
                comp_cnt = len([t for t in visible_tasks if t.is_completed])
                txt = f" Done: {comp_cnt} completed "
                badges.append((txt, f"[bold white on #40a02b]{txt}[/]"))
            elif self.status_filter in ["overdue", "ueberfaellig", "überfällig"]:
                txt = f" Overdue: {total_visible} overdue! "
                badges.append((txt, f"[bold white on #d20f39]{txt}[/]"))
            elif overdue_cnt > 0:
                txt = f" To Do: {open_cnt} open ({overdue_cnt} overdue!) "
                badges.append((txt, f"[bold white on #d20f39]{txt}[/]"))
            elif open_cnt > 0:
                txt = f" To Do: {open_cnt} open "
                badges.append((txt, f"[bold #11111b on #fab387]{txt}[/]"))
            else:
                txt = " To Do: 0 open "
                badges.append((txt, f"[bold white on #40a02b]{txt}[/]"))

            if term_w_override is not None and term_w_override > 0:
                term_w = term_w_override
            else:
                try:
                    term_w = self.size.width - 2 if (self.size and self.size.width > 0) else 121
                except Exception:
                    term_w = 121

            # 2. Platform Badges
            if term_w >= 80 or moodle_cnt > 0:
                txt = f" Moodle: {moodle_cnt} "
                badges.append((txt, f"[bold white on #fe640b]{txt}[/]"))
            if term_w >= 80 or teams_cnt > 0:
                txt = f" Teams: {teams_cnt} "
                badges.append((txt, f"[bold white on #1e66f5]{txt}[/]"))
            if term_w >= 80 or manual_cnt > 0:
                txt = f" Manual: {manual_cnt} "
                badges.append((txt, f"[bold white on #40a02b]{txt}[/]"))

            # 3. Next Exam Badge (Next: [Fach] in [Tage]d)
            next_exam = get_next_upcoming_exam()
            if next_exam and term_w >= 85:
                cd = next_exam.countdown_display
                txt = f" Next: {next_exam.subject} {cd} "
                badges.append((txt, f"[bold white on #8839ef]{txt}[/]"))

            # 4. Sync Badge (Shows time of last sync)
            sync_time_str = "Never"
            if self.mgr.last_sync:
                try:
                    ts = float(self.mgr.last_sync)
                    sync_date = datetime.datetime.fromtimestamp(ts).date()
                    today = datetime.date.today()
                    if sync_date == today:
                        sync_time_str = time.strftime("%H:%M", time.localtime(ts))
                    else:
                        sync_time_str = time.strftime("%d.%m. %H:%M", time.localtime(ts))
                except Exception:
                    sync_time_str = str(self.mgr.last_sync)
            txt = f" Sync: {sync_time_str} "
            badges.append((txt, f"[bold #cdd6f4 on #45475a]{txt}[/]"))

            # Directly adjacent badges, centered as a single group across available width
            sep = " "
            total_len = sum(len(plain) for plain, _ in badges) + len(sep) * (len(badges) - 1)
            avail_w = max(30, term_w - 4)
            left_pad = max(0, (avail_w - total_len) // 2)

            stats_text = (" " * left_pad) + sep.join(markup for _, markup in badges)
            self.query_one("#info_stats", Label).update(stats_text)
        except Exception:
            pass

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handles clicking on a sortable column header to sort ascending/descending."""
        if event.data_table.id != "tasks_table":
            return
        col_idx = event.column_index
        col_map = {
            1: "platform",
            2: "subject",
            4: "due_date",
            5: "status",
            6: "teacher",
        }
        col_name = col_map.get(col_idx)
        if not col_name:
            return  # Column # (0) and Assignment (3) are non-sortable

        if self.sort_column == col_name:
            self.sort_direction = "asc" if self.sort_direction == "desc" else "desc"
        else:
            self.sort_column = col_name
            self.sort_direction = "desc" if col_name == "due_date" else "asc"

        self.refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Click with mouse or ENTER on a row opens details view."""
        row_key = event.row_key.value
        task = next((t for t in self.current_tasks if t.id == row_key), None)
        if task:
            self._open_task_details(task)

    def _open_task_details(self, task: Task) -> None:
        if not task.details_loaded:
            self.notify(f"Loading details for '{task.title}'...", severity="information")
            def worker():
                self.mgr.load_task_details(task)
                def update_ui():
                    self.push_screen(TaskDetailModal(task, self.mgr), self._on_detail_closed)
                self.call_from_thread(update_ui)

            threading.Thread(target=worker, daemon=True, name="TaskDetailsWorker").start()
        else:
            self.push_screen(TaskDetailModal(task, self.mgr), self._on_detail_closed)

    def _on_detail_closed(self, result=None) -> None:
        self.refresh_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Mouse clicks on bottom buttons."""
        bid = event.button.id
        if bid == "btn_main_add":
            self.action_add_task()
        elif bid == "btn_main_sync":
            self.action_sync_tasks()
        elif bid == "btn_main_filter":
            self.action_open_filter_menu()
        elif bid == "btn_main_absences":
            self.action_show_absences()
        elif bid == "btn_main_exams":
            self.action_show_exams()
        elif bid == "btn_main_ai":
            self.action_show_ai_chat()
        elif bid == "btn_main_trash":
            self.action_show_trash()
        elif bid == "btn_main_login":
            self.action_login_menu()
        elif bid == "btn_main_settings":
            self.action_open_settings()
        elif bid == "btn_main_status":
            self.action_filter_status()
        elif bid == "btn_main_subject":
            self.action_filter_subject()
        elif bid == "btn_main_platform":
            self.action_filter_platform()
        elif bid in ("btn_main_theme", "btn_main_palette"):
            self.action_change_theme()
        elif bid == "btn_main_quit":
            self.action_quit_app(force=False)


    # --- Actions (callable via mouse & keyboard) ---

    def action_open_filter_menu(self) -> None:
        def on_filter_chosen(action: Optional[str]) -> None:
            if not action:
                return
            if action == "status":
                self.action_filter_status(from_menu=True)
            elif action == "timeframe":
                self.action_filter_timeframe(from_menu=True)
            elif action == "subject":
                self.action_filter_subject(from_menu=True)
            elif action == "platform":
                self.action_filter_platform(from_menu=True)
            elif action == "reset":
                self.status_filter = "open_only"
                self.timeframe_filter = "2_weeks"
                self.subject_filter = "all"
                self.platform_filter = "all"
                self.refresh_table()
                self.notify("All filters reset to default (2 Weeks, Open only).", severity="information")

        self.push_screen(
            FilterMenuModal(self.status_filter, self.subject_filter, self.platform_filter, self.timeframe_filter),
            on_filter_chosen
        )

    def action_filter_timeframe(self, from_menu: bool = False) -> None:
        def on_selected(new_tf: Optional[str]) -> None:
            if new_tf:
                self.timeframe_filter = new_tf
                self.refresh_table()
                tf_names = {
                    "1_week": "1 Week",
                    "2_weeks": "2 Weeks",
                    "4_weeks": "4 Weeks",
                    "8_weeks": "8 Weeks",
                    "all": "All",
                }
                self.notify(f"Max Duration Filter: {tf_names.get(new_tf, new_tf)}", severity="information")
            elif from_menu:
                self.action_open_filter_menu()
        self.push_screen(TimeframeFilterModal(), on_selected)

    def action_open_settings(self) -> None:
        def on_setting_chosen(action: Optional[str]) -> None:
            if not action:
                return
            if action == "change_theme":
                self.action_change_theme()
            elif action == "show_hotkeys":
                self.action_show_hotkeys()
            elif action == "login_menu":
                self.action_login_menu(from_menu=True)
            elif action == "show_trash":
                self.action_show_trash(from_menu=True)
            elif action == "setup_teams":
                self.action_setup_teams(from_login_menu=False, from_settings=True)
            elif action == "setup_moodle":
                self.action_setup_moodle(from_login_menu=False, from_settings=True)
            elif action == "setup_untis":
                self.action_setup_untis(from_login_menu=False, from_settings=True)
            elif action in ("school_config", "excuse_profile"):
                def on_config_done(saved: bool) -> None:
                    self.refresh_table()
                    self.action_open_settings()
                self.push_screen(SchoolConfigModal(), on_config_done)
            elif action == "toggle_group":
                curr_grp = _load_untis_group() or "X"
                new_grp = "Y" if "x" in curr_grp.lower() else "X"
                save_untis_group(new_grp)
                self.notify(f"WebUntis group set to {new_grp}.", severity="information")
                self.action_open_settings()
            elif action in ("ai_config_menu", "ai_explain_config"):
                def on_explain_done(saved: bool) -> None:
                    self.action_open_settings()
                self.push_screen(AiExplainModal(), on_explain_done)
            elif action == "tray_config":
                def on_tray_done(saved: bool) -> None:
                    if saved:
                        self.notify("System tray and autostart settings saved.", severity="information")
                        try:
                            from config import is_minimize_to_tray_enabled
                            if is_minimize_to_tray_enabled():
                                if getattr(self, "_tray_service", None) is None:
                                    self._init_tray_and_ipc()
                            else:
                                if getattr(self, "_tray_service", None) is not None:
                                    try:
                                        self._tray_service.stop()
                                    except Exception:
                                        pass
                                    self._tray_service = None
                                if getattr(self, "_single_instance_server", None) is not None:
                                    try:
                                        self._single_instance_server.stop()
                                    except Exception:
                                        pass
                                    self._single_instance_server = None
                        except Exception:
                            pass
                    self.action_open_settings()
                self.push_screen(TrayConfigModal(), on_tray_done)


        self.push_screen(SettingsModal(), on_setting_chosen)

    def action_add_task(self) -> None:
        def on_task_added(new_task: Optional[Task]) -> None:
            if new_task:
                self.mgr.add_task(new_task)
                self.refresh_table()
                self.notify(f"Assignment '{new_task.title}' added successfully!", severity="information")
        self.push_screen(AddTaskModal(), on_task_added)

    def action_filter_status(self, from_menu: bool = False) -> None:
        def on_selected(new_status: Optional[str]) -> None:
            if new_status:
                self.status_filter = new_status
                self.refresh_table()
            elif from_menu:
                self.action_open_filter_menu()
        self.push_screen(StatusFilterModal(), on_selected)

    def action_filter_platform(self, from_menu: bool = False) -> None:
        def on_selected(action: Optional[str]) -> None:
            if not action:
                if from_menu:
                    self.action_open_filter_menu()
                return
            if action in ("all", "moodle", "teams", "manual"):
                self.platform_filter = action
                self.refresh_table()
                plat_names = {
                    "all": "All platforms",
                    "moodle": "Moodle",
                    "teams": "Teams",
                    "manual": "Manual",
                }
                self.notify(f"Platform filter set to: {plat_names.get(action, action)}", severity="information")

        self.push_screen(PlatformFilterModal(), on_selected)

    def action_filter_subject(self, from_menu: bool = False) -> None:
        subjects = sorted(list(set(t.course for t in self.mgr.tasks)))
        def on_selected(new_subj: Optional[str]) -> None:
            if new_subj:
                self.subject_filter = new_subj
                self.refresh_table()
            elif from_menu:
                self.action_open_filter_menu()
        self.push_screen(SubjectFilterModal(subjects), on_selected)

    def action_show_trash(self, from_menu: bool = False) -> None:
        def on_trash_closed(result=None) -> None:
            self.refresh_table()
            if from_menu:
                self.action_open_settings()
        self.push_screen(TrashModal(self.mgr), on_trash_closed)

    def action_sync_tasks(self) -> None:
        if self._is_syncing:
            return
        self._is_syncing = True
        self._sync_not_complete_printed = False

        # Dreh-Ladesymbol in der oberen rechten Ecke aktivieren
        try:
            self.query_one("#sync_spinner", SyncSpinner).active = True
        except Exception:
            pass

        def sync_worker():
            # 1. Wenn Git-Cloud-Sync eingerichtet ist: Remote-Pull & Smart-Merge ausführen
            try:
                from git_sync_service import is_git_configured, GitSyncService
                from config import is_platform_enabled
                if is_platform_enabled("git") and is_git_configured():
                    git_ok, git_msg, has_updates = GitSyncService.pull_and_sync()
                    if has_updates:
                        self.mgr.reload_custom_tasks()
                        try:
                            from config import load_saved_theme
                            remote_theme = load_saved_theme()
                            if hasattr(self, "theme") and self.theme != remote_theme:
                                self.theme = remote_theme
                        except Exception:
                            pass
                        self.call_from_thread(self.refresh_table)

            except Exception:
                pass

            def on_batch_update():
                now = time.time()
                # Throttling: Bei rascher Folge nur alle 0.8s die Tabelle leeren/neu zeichnen,
                # ansonsten nur die Statistik im Info-Bar aktualisieren, um ConPTY-Lags zu vermeiden.
                try:
                    if now - getattr(self, "_last_sync_table_refresh", 0.0) >= 0.8:
                        self._last_sync_table_refresh = now
                        self.call_from_thread(self.refresh_table)
                    else:
                        self.call_from_thread(self.update_info_bar)
                except (RuntimeError, Exception):
                    # Die App wurde inzwischen beendet (z.B. Strg+C) -> UI-Update verwerfen
                    pass

            try:
                self.mgr.sync(deep_scan=False, on_batch_complete=on_batch_update)
            except Exception:
                pass


            def update_ui():
                self._is_syncing = False
                try:
                    self.query_one("#sync_spinner", SyncSpinner).active = False
                except Exception:
                    pass
                self.refresh_table()
                if not getattr(self, "is_headless", False):
                    self._check_login_status_after_sync()

            try:
                # Bei beendeter App (Strg+C während des Syncs) wirft call_from_thread
                # RuntimeError("App is not running") -> sauber abfangen.
                if not self.is_running:
                    raise RuntimeError("App is not running")
                self.call_from_thread(update_ui)
            except (RuntimeError, Exception):
                self._is_syncing = False
                if not getattr(self, "_sync_not_complete_printed", False):
                    self._sync_not_complete_printed = True
                    print("Sync not Complete", flush=True)

        self._sync_thread = threading.Thread(target=sync_worker, daemon=True, name="SyncWorker")
        self._sync_thread.start()

    def _check_login_status_after_sync(self) -> None:
        """Checks if school platforms are logged in after sync and shows LoginReminderModal if on main screen."""
        try:
            from auth import has_missing_logins
            if not has_missing_logins():
                return

            # Nur einblenden, wenn der Nutzer sich auf dem Hauptbildschirm befindet
            if len(self.screen_stack) > 1 or isinstance(self.screen, ModalScreen):
                return

            def on_reminder_closed(action: Optional[str]) -> None:
                if action == "open_logins":
                    self.action_login_menu()

            self.push_screen(LoginReminderModal(), on_reminder_closed)
        except Exception:
            pass

    def action_login_menu(self, from_menu: bool = False) -> None:
        def on_choice(choice: Optional[str]) -> None:
            if choice == "teams":
                self.action_setup_teams(from_login_menu=True, from_settings=from_menu)
            elif choice == "moodle":
                self.action_setup_moodle(from_login_menu=True, from_settings=from_menu)
            elif choice == "untis":
                self.action_setup_untis(from_login_menu=True, from_settings=from_menu)
            elif choice == "git":
                self.action_setup_git(from_login_menu=True, from_settings=from_menu)
            elif choice is None and from_menu:
                self.action_open_settings()

        self.push_screen(LoginChoiceModal(), on_choice)

    def action_setup_git(self, from_login_menu: bool = False, from_settings: bool = False) -> None:
        def on_git_done(ok: bool) -> None:
            if ok:
                self.notify("✓ Git Cloud-Sync successfully configured!", severity="information")
                self.action_sync_tasks()
            elif from_login_menu:
                self.action_login_menu(from_menu=from_settings)
            elif from_settings:
                self.action_open_settings()
        self.push_screen(GitSetupModal(), on_git_done)

    def action_setup_teams(self, from_login_menu: bool = False, from_settings: bool = False) -> None:
        def on_teams_done(ok: bool) -> None:
            if ok:
                self.notify("✓ Microsoft Teams successfully connected!", severity="information")
                self.action_sync_tasks()
            else:
                self.notify("Teams login was not completed.", severity="warning")
                if from_login_menu:
                    self.action_login_menu(from_menu=from_settings)
                elif from_settings:
                    self.action_open_settings()
        self.push_screen(TeamsSetupModal(), on_teams_done)

    def action_setup_moodle(self, from_login_menu: bool = False, from_settings: bool = False) -> None:
        def on_moodle_done(ok: bool) -> None:
            if ok:
                self.action_sync_tasks()
            elif from_login_menu:
                self.action_login_menu(from_menu=from_settings)
            elif from_settings:
                self.action_open_settings()
        self.push_screen(MoodleLoginModal(), on_moodle_done)

    def action_setup_untis(self, from_login_menu: bool = False, from_settings: bool = False) -> None:
        def on_untis_done(ok: bool) -> None:
            if ok:
                self.action_show_absences()
            elif from_login_menu:
                self.action_login_menu(from_menu=from_settings)
            elif from_settings:
                self.action_open_settings()
        self.push_screen(UntisSetupModal(), on_untis_done)

    def action_show_absences(self) -> None:
        self.push_screen(AbsencesScreen())

    def action_show_exams(self) -> None:
        """Opens WebUntis Tests & Exams screen."""
        def on_exams_closed(result=None) -> None:
            self.refresh_table()
        self.push_screen(ExamsScreen(), on_exams_closed)

    def action_show_ai_chat(self, initial_task_id: Optional[str] = None, auto_explain: bool = False) -> None:
        """Opens the interactive full-screen AI chat assistant with assignments matching active main filters."""
        def on_ai_closed(result=None) -> None:
            self.refresh_table()
        visible_tasks = getattr(self, "current_tasks", None)
        self.push_screen(AiChatScreen(self.mgr, initial_task_id=initial_task_id, auto_explain=auto_explain, tasks=visible_tasks), on_ai_closed)

    def action_show_hotkeys(self) -> None:
        """Opens the CommandPalette with all application hotkeys."""
        self.push_screen(
            CommandPalette(
                providers=[HotkeysProvider],
                placeholder="Search for hotkeys…",
            )
        )

    def action_open_courses_palette(self, initial_mode: str = "courses") -> None:
        """Opens the UnifiedCommandPalette to quickly search and launch courses or schoolbooks."""
        # Verhindern, dass gehaltenes STRG bei versehentlichem Durchrutschen von Backspace das Menü öffnet
        if is_ctrl_pressed_win32():
            return
        self.push_screen(
            UnifiedCommandPalette(
                providers=[UnifiedQuickOpenProvider],
                initial_mode=initial_mode,
            )
        )

    def open_schoolbook(self, book: dict) -> None:
        """Opens a schoolbook (PDF in viewer, web link in browser)."""
        try:
            from schoolbook_service import SchoolbookService
        except ImportError:
            from src.services.schoolbook_service import SchoolbookService

        ok, msg = SchoolbookService.open_book(book)
        if ok:
            self.notify(f"✓ {msg}", severity="information")
        else:
            self.notify(f"⚠️ {msg}", severity="error")

    def action_link_schoolbook_file(self) -> None:
        """Opens Windows file explorer in background thread to link a local PDF file."""
        self.notify("📂 Opening file explorer for PDF selection...", severity="information")

        def _worker():
            try:
                from schoolbook_service import SchoolbookService
            except ImportError:
                from src.services.schoolbook_service import SchoolbookService

            try:
                pdf_path = SchoolbookService.pick_pdf_file()
                if pdf_path:
                    book = SchoolbookService.add_pdf_book(pdf_path)
                    title = book.get("title", "Schoolbook")
                    self.call_from_thread(
                        self.notify,
                        f"✓ Schoolbook '{title}' successfully linked!",
                        severity="information",
                    )
                    self.call_from_thread(lambda: self.action_open_courses_palette(initial_mode="books"))
                else:
                    self.call_from_thread(
                        self.notify,
                        "File selection cancelled.",
                        severity="warning",
                    )
                    self.call_from_thread(lambda: self.action_open_courses_palette(initial_mode="books"))
            except Exception as e:
                self.call_from_thread(
                    self.notify,
                    f"Error during file selection: {e}",
                    severity="error",
                )

        threading.Thread(target=_worker, daemon=True).start()

    def prompt_add_schoolbook_url(self, url: str = "") -> None:
        """Opens a modal dialog to enter URL and book title."""
        try:
            from schoolbook_service import SchoolbookService
        except ImportError:
            from src.services.schoolbook_service import SchoolbookService

        def _on_result(res: Optional[dict]) -> None:
            if res and res.get("url"):
                book = SchoolbookService.add_web_book(res["url"], res.get("title", ""))
                self.notify(f"✓ Online book '{book.get('title')}' linked!", severity="information")
                self.action_open_courses_palette(initial_mode="books")
            else:
                self.action_open_courses_palette(initial_mode="books")

        self.push_screen(SchoolbookUrlModal(initial_url=url), _on_result)

    def prompt_digi4school_download(self, initial_code: str = "") -> None:
        """Opens the dialog flow to detect pages and download a Digi4School book as OCR PDF."""

        def _on_range_result(range_res: Optional[dict]) -> None:
            if not range_res:
                self.action_open_courses_palette(initial_mode="books")
                return

            if range_res.get("action") == "back":
                self.push_screen(
                    Digi4SchoolDownloadModal(
                        initial_code=range_res.get("code", initial_code),
                        initial_email=range_res.get("email", ""),
                        initial_quality=range_res.get("quality", "ultra"),
                    ),
                    _on_input_result,
                )
                return

            if range_res.get("action") == "download":
                self.push_screen(
                    Digi4SchoolProgressModal(
                        email=range_res["email"],
                        password=range_res["password"],
                        code=range_res["code"],
                        quality=range_res.get("quality", "ultra"),
                        pages=range_res.get("pages"),
                    )
                )

        def _on_detect_result(detect_res: Optional[dict]) -> None:
            if not detect_res:
                self.action_open_courses_palette(initial_mode="books")
                return

            if detect_res.get("status") == "ok":
                self.push_screen(
                    Digi4SchoolPageRangeModal(
                        email=detect_res["email"],
                        password=detect_res["password"],
                        code=detect_res["code"],
                        quality=detect_res.get("quality", "ultra"),
                        title=detect_res.get("title") or detect_res["code"],
                        total_pages=detect_res.get("total_pages"),
                    ),
                    _on_range_result,
                )
            else:
                self.push_screen(
                    Digi4SchoolPageRangeModal(
                        email=detect_res["email"],
                        password=detect_res["password"],
                        code=detect_res["code"],
                        quality=detect_res.get("quality", "ultra"),
                        title=detect_res.get("title") or detect_res["code"],
                        total_pages=None,
                        error_msg=detect_res.get("error"),
                    ),
                    _on_range_result,
                )

        def _on_input_result(res: Optional[dict]) -> None:
            if res and res.get("code"):
                self.push_screen(
                    Digi4SchoolDetectModal(
                        email=res["email"],
                        password=res["password"],
                        code=res["code"],
                        quality=res.get("quality", "ultra"),
                    ),
                    _on_detect_result,
                )
            else:
                self.action_open_courses_palette(initial_mode="books")

        self.push_screen(Digi4SchoolDownloadModal(initial_code=initial_code), _on_input_result)

    def action_delete_schoolbook(self, book_id: str, title: str) -> None:
        """Deletes a schoolbook and reopens the palette in schoolbook mode."""
        try:
            from schoolbook_service import SchoolbookService
        except ImportError:
            from src.services.schoolbook_service import SchoolbookService

        SchoolbookService.remove_book(book_id)
        self.notify(f"✓ Schoolbook '{title}' removed.", severity="information")
        self.action_open_courses_palette(initial_mode="books")

    def action_prompt_unlink_schoolbook(self) -> None:
        """Sets the search bar to /unlink to list all books for removal."""
        try:
            if hasattr(self, "screen") and isinstance(self.screen, UnifiedCommandPalette):
                inp = self.screen.query_one(CommandInput)
                inp.value = "/unlink"
        except Exception:
            pass

    def open_directory(self, directory: dict) -> None:
        """Opens a directory in the system file explorer."""
        try:
            from directory_service import DirectoryService
        except ImportError:
            from src.services.directory_service import DirectoryService

        ok, msg = DirectoryService.open_directory(directory)
        if ok:
            self.notify(f"✓ {msg}", severity="information")
        else:
            self.notify(f"⚠️ {msg}", severity="error")

    def action_link_directory(self) -> None:
        """Opens Windows folder picker in background thread to link a local folder."""
        self.notify("📂 Opening folder picker...", severity="information")

        def _worker():
            try:
                from directory_service import DirectoryService
            except ImportError:
                from src.services.directory_service import DirectoryService

            try:
                folder_path = DirectoryService.pick_directory()
                if folder_path:
                    entry = DirectoryService.add_directory(folder_path)
                    title = entry.get("title", "Directory")
                    self.call_from_thread(
                        self.notify,
                        f"✓ Directory '{title}' successfully linked!",
                        severity="information",
                    )
                    self.call_from_thread(lambda: self.action_open_courses_palette(initial_mode="directories"))
                else:
                    self.call_from_thread(
                        self.notify,
                        "Folder selection cancelled.",
                        severity="warning",
                    )
                    self.call_from_thread(lambda: self.action_open_courses_palette(initial_mode="directories"))
            except Exception as e:
                self.call_from_thread(
                    self.notify,
                    f"Error during folder selection: {e}",
                    severity="error",
                )

        threading.Thread(target=_worker, daemon=True).start()

    def action_delete_directory(self, dir_id: str, title: str) -> None:
        """Deletes a linked directory and reopens the palette in directories mode."""
        try:
            from directory_service import DirectoryService
        except ImportError:
            from src.services.directory_service import DirectoryService

        DirectoryService.remove_directory(dir_id)
        self.notify(f"✓ Directory '{title}' removed.", severity="information")
        self.action_open_courses_palette(initial_mode="directories")

    def action_prompt_unlink_directory(self) -> None:
        """Sets the search bar to /unlink to list all directories for removal."""
        try:
            if hasattr(self, "screen") and isinstance(self.screen, UnifiedCommandPalette):
                inp = self.screen.query_one(CommandInput)
                inp.value = "/unlink"
        except Exception:
            pass

    def open_course_url(self, url: str, name: str) -> None:
        """Opens the given course URL in the default browser and shows a notification."""
        if url:
            webbrowser.open(url)
            self.notify(f"✓ Opening '{name}' in browser...", severity="information")
        else:
            self.notify(f"No link available for '{name}'.", severity="warning")

    def action_reload_courses(self, reopen_palette: bool = True) -> None:
        """Reloads the Moodle courses cache from the server in a background thread."""
        self.notify("🔄 Refreshing Moodle courses from server...", severity="information")

        def _worker():
            try:
                import moodle_service
                count = moodle_service.reload_moodle_courses_cache()
                if count > 0:
                    self.call_from_thread(
                        self.notify,
                        f"✓ {count} Moodle courses successfully refreshed!",
                        severity="information",
                    )
                    if reopen_palette:
                        self.call_from_thread(self.action_open_courses_palette)
                else:
                    self.call_from_thread(
                        self.notify,
                        "Warning: No Moodle courses found or Moodle session expired.",
                        severity="warning",
                    )
            except Exception as e:
                self.call_from_thread(
                    self.notify,
                    f"Error refreshing courses: {e}",
                    severity="error",
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _update_stats_display(self) -> None:
        """Alias for refreshing table and statistics."""
        self.refresh_table()

    def action_select_task(self, num: int) -> None:
        if 1 <= num <= len(self.current_tasks):
            self._open_task_details(self.current_tasks[num - 1])

    def watch_theme(self, theme: str) -> None:
        """Textual reactive watcher: speichert das ausgewählte Theme automatisch dauerhaft."""
        if theme in ALLOWED_THEMES:
            save_saved_theme(theme)

    def search_themes(self) -> None:
        """Show a search command palette containing all registered themes with favorites pinned at top."""
        self.push_screen(
            ThemeCommandPalette(
                providers=[FavoriteThemeProvider],
                placeholder="Search for themes... (Right-click to toggle ⭐ favorite)",
            )
        )

    def action_change_theme(self) -> None:
        """Öffnet die Theme-Auswahl (Textual CommandPalette mit allen Themes und Favoriten oben)."""
        self.search_themes()

    def action_command_palette(self) -> None:
        """Palette-Taste öffnet direkt die Schnellauswahl der Themes."""
        self.action_change_theme()

    def _start_mouse_back_listener(self) -> None:
        """Starts the lightweight mouse back listener and the console close ([X]) handler."""
        if self._mouse_listener_thread and self._mouse_listener_thread.is_alive():
            return
        self._stop_mouse_listener.clear()

        # Registriert SetConsoleCtrlHandler, damit Ctrl+C sauber beendet und [X] die Konsole schließt.
        self._install_console_close_handler()

        self._mouse_listener_thread = threading.Thread(
            target=self._run_mouse_back_listener,
            daemon=True,
            name="MouseBackListenerThread",
        )
        self._mouse_listener_thread.start()

    def _install_console_close_handler(self) -> None:
        """Installs a SetConsoleCtrlHandler that handles the console [X] (close) button and Ctrl+C."""
        if sys.platform != "win32" or getattr(self, "_console_ctrl_handler_installed", False):
            return
        try:
            kernel32 = ctypes.windll.kernel32
            PHANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

            def _on_console_ctrl(ctrl_type: int) -> bool:
                if ctrl_type == 0:  # CTRL_C_EVENT
                    try:
                        self.call_from_thread(self.action_real_quit)
                    except Exception:
                        pass
                    return True

                if ctrl_type == 2:  # CTRL_CLOSE_EVENT (red [X] on the console window)
                    # 1. Lokale IPC-Pipe sofort freigeben
                    if getattr(self, "_single_instance_server", None):
                        try:
                            self._single_instance_server.stop()
                        except Exception:
                            pass
                        self._single_instance_server = None
                    # 2. Lokales Tray-Icon sofort beenden
                    if getattr(self, "_tray_service", None):
                        try:
                            self._tray_service.stop()
                        except Exception:
                            pass
                        self._tray_service = None
                    # Windows darf die Konsole schließen und den Prozess beenden
                    return False

                return False

            self._console_ctrl_cb = PHANDLER(_on_console_ctrl)
            kernel32.SetConsoleCtrlHandler(self._console_ctrl_cb, True)
            self._console_ctrl_handler_installed = True
        except Exception:
            # Fallback, falls kein Ctrl-Handler registriert werden konnte.
            self._disable_conhost_close_button()

    def _uninstall_console_close_handler(self) -> None:
        """Removes the console control handler again (called on a real quit)."""
        if not getattr(self, "_console_ctrl_handler_installed", False):
            return
        try:
            ctypes.windll.kernel32.SetConsoleCtrlHandler(self._console_ctrl_cb, False)
        except Exception:
            pass
        finally:
            self._console_ctrl_handler_installed = False
            self._console_ctrl_cb = None
        if getattr(self, "_conhost_close_disabled", False):
            try:
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd:
                    user32 = ctypes.windll.user32
                    hmenu = user32.GetSystemMenu(hwnd, False)
                    if hmenu:
                        user32.EnableMenuItem(hmenu, 0xF060, 0x00000000)  # SC_CLOSE wieder aktivieren
            except Exception:
                pass
            self._conhost_close_disabled = False

    def _disable_conhost_close_button(self) -> None:
        """Fallback: greys out the [X] item (SC_CLOSE) of a classic conhost window's system menu."""
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value != "ConsoleWindowClass":
                return  # Windows Terminal & Co. bieten kein eigenes Systemmenü an
            hmenu = user32.GetSystemMenu(hwnd, False)
            if hmenu:
                MF_GRAYED = 0x00000001
                MF_DISABLED = 0x00000002
                user32.EnableMenuItem(hmenu, 0xF060, MF_GRAYED | MF_DISABLED)  # SC_CLOSE
                user32.DrawMenuBar(hwnd)
                self._conhost_close_disabled = True
        except Exception:
            pass

    def _run_mouse_back_listener(self) -> None:
        """Monitors Windows mouse back button state and navigates back when clicked in foreground."""
        VK_XBUTTON1 = 0x05  # Mouse Back Button (Seitentaste Hinten)
        user32 = ctypes.windll.user32
        prev_pressed = False
        while not self._stop_mouse_listener.is_set():
            time.sleep(0.05)
            try:
                is_pressed = bool(user32.GetAsyncKeyState(VK_XBUTTON1) & 0x8000)
                if is_pressed and not prev_pressed:
                    if is_app_window_foreground(self, self._terminal_hwnd):
                        self.call_from_thread(self.action_navigate_back)
                prev_pressed = is_pressed
            except Exception:
                pass

    def action_navigate_back(self) -> None:
        """Navigates one level back or closes modal/submenu (invoked via Mouse Back button or ESC)."""
        if len(self.screen_stack) <= 1:
            return  # Auf der Hauptseite, nichts zu schließen

        curr_screen = self.screen
        # Bevorzuge spezifische Back-/Cancel-/Dismiss-Aktionen des Screens
        if hasattr(curr_screen, "action_dismiss_screen"):
            curr_screen.action_dismiss_screen()
        elif hasattr(curr_screen, "action_cancel"):
            curr_screen.action_cancel()
        elif hasattr(curr_screen, "action_close"):
            curr_screen.action_close()
        elif hasattr(curr_screen, "key_escape"):
            curr_screen.key_escape()
        else:
            try:
                curr_screen.dismiss(None)
            except Exception:
                try:
                    self.pop_screen()
                except Exception:
                    pass

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Handles mouse down events reported directly by terminal drivers."""
        if getattr(event, "button", 0) in (4, 8):
            self.action_navigate_back()

    def on_click(self, event: events.Click) -> None:
        """Handles click events reported directly by terminal drivers."""
        if getattr(event, "button", 0) in (4, 8):
            self.action_navigate_back()

    def on_unmount(self) -> None:
        """Wird aufgerufen, wenn die Anwendung beendet wird (egal über welchen Weg)."""
        self._stop_mouse_listener.set()
        self._uninstall_console_close_handler()
        set_shutting_down()
        if hasattr(self, "mgr"):
            self.mgr.shutdown()
        try:
            close_all_active_browser_contexts()
        except Exception:
            pass
        if getattr(self, "_sync_thread", None) and self._sync_thread.is_alive():
            try:
                self._sync_thread.join(timeout=0.5)
            except Exception:
                pass
        if hasattr(self, "theme") and self.theme in ALLOWED_THEMES:
            save_saved_theme(self.theme)

    def action_quit_app(self, force: bool = False) -> None:
        if not force:
            focused = self.focused
            if focused is not None and (isinstance(focused, (Input, TextArea)) or getattr(focused, "selected_text", None)):
                return
            if sys.platform == "win32":
                try:
                    from config import is_minimize_to_tray_enabled
                    if is_minimize_to_tray_enabled() and self._tray_service is not None:
                        self.hide_to_tray()
                        return
                except Exception:
                    pass


        if getattr(self, "_single_instance_server", None):
            try:
                self._single_instance_server.stop()
            except Exception:
                pass
        if getattr(self, "_tray_service", None):
            try:
                self._tray_service.stop()
            except Exception:
                pass
        self._stop_mouse_listener.set()
        set_shutting_down()
        if hasattr(self, "mgr"):
            self.mgr.shutdown()
        try:
            close_all_active_browser_contexts()
        except Exception:
            pass
        if getattr(self, "_sync_thread", None) and self._sync_thread.is_alive():
            try:
                self._sync_thread.join(timeout=0.5)
            except Exception:
                pass
        if hasattr(self, "theme") and self.theme in ALLOWED_THEMES:
            save_saved_theme(self.theme)
        self.exit()




def run_tui(start_hidden: bool = False):
    """Startet die moderne Textual-TUI-Anwendung."""
    if not start_hidden and not getattr(sys, "_launching_tui_printed", False):
        sys._launching_tui_printed = True
        print("Launching TUI...", flush=True)
    if AUTO_CLEAN_BROWSER_CACHE:
        try:
            threading.Thread(target=clean_browser_profile_caches, daemon=True, name="BrowserCacheCleanup").start()
        except Exception:
            pass

    ensure_terminal_window_size(target_cols=123, min_height_px=680)
    app = TasksApp(start_hidden=start_hidden)

    try:
        app.run()
    finally:
        set_shutting_down()
        try:
            if hasattr(app, "mgr"):
                app.mgr.shutdown()
        except Exception:
            pass
        try:
            close_all_active_browser_contexts()
        except Exception:
            pass
        if hasattr(app, "_sync_thread") and app._sync_thread and app._sync_thread.is_alive():
            try:
                app._sync_thread.join(timeout=0.5)
            except Exception:
                pass
        # Wurde die App während eines laufenden Syncs beendet (Strg+C), darüber informieren
        try:
            if getattr(app, "_is_syncing", False) and not getattr(app, "_sync_not_complete_printed", False):
                app._sync_not_complete_printed = True
                print("Sync not Complete", flush=True)
        except Exception:
            pass
        if hasattr(app, "theme") and app.theme in ALLOWED_THEMES:
            try:
                save_saved_theme(app.theme)
            except Exception:
                pass
    return getattr(app, "return_code", 0) or 0


# Abwärtskompatibilitäts-Alias für Legacy-Imports
AufgabenDetectorApp = TasksApp


if __name__ == "__main__":
    code = run_tui()
    sys.exit(code or 0)
