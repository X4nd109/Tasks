from __future__ import annotations

from typing import Optional
from rich.text import Text
from textual.widget import Widget
from textual.message import Message
from textual import events


class TwoThumbRangeSlider(Widget):
    """
    Ein interaktiver Textual-Slider mit 2 Schiebern (Start- und Endwert).
    Unterstützt Tastaturnavigation (Pfeiltasten, Tab, 1/2) und Mausbedienung (Klick & Drag).
    """

    DEFAULT_CSS = """
    TwoThumbRangeSlider {
        width: 100%;
        height: 3;
        background: #181825;
        border: solid #45475a;
        padding: 0 1;
    }
    TwoThumbRangeSlider:focus {
        border: solid #89b4fa;
        background: #1e1e2e;
    }
    """

    ALLOW_SELECT = False
    can_focus = True

    class Changed(Message):
        """Wird ausgelöst, wenn sich Start- oder Endwert des Sliders ändern."""

        def __init__(self, start: int, end: int) -> None:
            super().__init__()
            self.start = start
            self.end = end

    def __init__(
        self,
        min_val: int = 1,
        max_val: int = 100,
        start_val: Optional[int] = None,
        end_val: Optional[int] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.min_val = max(1, int(min_val))
        self.max_val = max(self.min_val, int(max_val))
        self.start_val = max(self.min_val, min(self.max_val, int(start_val if start_val is not None else self.min_val)))
        self.end_val = max(self.start_val, min(self.max_val, int(end_val if end_val is not None else self.max_val)))
        self.active_thumb: str = "start"  # "start" oder "end"
        self._is_dragging: bool = False

    def set_bounds(self, min_val: int, max_val: int) -> None:
        """Setzt die minimalen und maximalen Grenzwerte des Sliders."""
        self.min_val = max(1, int(min_val))
        self.max_val = max(self.min_val, int(max_val))
        self.start_val = max(self.min_val, min(self.max_val, self.start_val))
        self.end_val = max(self.start_val, min(self.max_val, self.end_val))
        self.refresh()

    def set_range(self, start: int, end: int, notify: bool = False) -> None:
        """Setzt Start- und Endseite programmatisch."""
        clamped_start = max(self.min_val, min(self.max_val, int(start)))
        clamped_end = max(clamped_start, min(self.max_val, int(end)))
        if clamped_start != self.start_val or clamped_end != self.end_val:
            self.start_val = clamped_start
            self.end_val = clamped_end
            self.refresh()
            if notify:
                self.post_message(self.Changed(self.start_val, self.end_val))

    def _val_to_pos(self, val: int, track_width: int) -> int:
        """Rechnet einen Seitenwert in eine relative Zeichenposition (0 .. track_width - 1) um."""
        if self.max_val <= self.min_val or track_width <= 1:
            return 0
        ratio = (val - self.min_val) / (self.max_val - self.min_val)
        return min(track_width - 1, max(0, int(round(ratio * (track_width - 1)))))

    def _pos_to_val(self, pos: int, track_width: int) -> int:
        """Rechnet eine Zeichenposition auf der Schiene in einen Seitenwert um."""
        if track_width <= 1 or self.max_val <= self.min_val:
            return self.min_val
        ratio = min(1.0, max(0.0, pos / (track_width - 1)))
        return int(round(self.min_val + ratio * (self.max_val - self.min_val)))

    def render(self) -> Text:
        """Rendert die Schiene und Daumen mit Hervorhebung."""
        width = max(20, self.size.width - 2)
        min_str = f"{self.min_val} "
        max_str = f" {self.max_val}"
        track_width = max(10, width - len(min_str) - len(max_str) - 2)

        start_pos = self._val_to_pos(self.start_val, track_width)
        end_pos = self._val_to_pos(self.end_val, track_width)
        if start_pos > end_pos:
            start_pos, end_pos = end_pos, start_pos

        # Zeile 1: Schiene mit Daumen
        line1 = Text()
        line1.append(min_str, style="#a6adc8")
        line1.append("[", style="#6c7086")

        for pos in range(track_width):
            if pos == start_pos and pos == end_pos:
                # Beide Daumen an der gleichen Stelle
                style = "bold #f9e2af on #313244"
                line1.append("◈", style=style)
            elif pos == start_pos:
                style = "bold #a6e3a1" if self.active_thumb == "start" and self.has_focus else "bold #89b4fa"
                line1.append("●", style=style)
            elif pos == end_pos:
                style = "bold #a6e3a1" if self.active_thumb == "end" and self.has_focus else "bold #89b4fa"
                line1.append("●", style=style)
            elif start_pos < pos < end_pos:
                line1.append("═", style="#f9e2af")
            else:
                line1.append("─", style="#45475a")

        line1.append("]", style="#6c7086")
        line1.append(max_str, style="#a6adc8")

        # Zeile 2: Detailanzeige der aktuellen Auswahl
        line2 = Text()
        thumb_hint = "[Tab/1/2: Schieber wechseln | ◀/▶: Verschieben]"
        start_badge = f"Start: {self.start_val}"
        end_badge = f"Ende: {self.end_val}"
        pages_count = (self.end_val - self.start_val + 1)
        pages_badge = f"({pages_count} {'Seite' if pages_count == 1 else 'Seiten'})"

        line2.append(f" {start_badge} ", style="bold #a6e3a1" if self.active_thumb == "start" else "#89b4fa")
        line2.append("➔", style="#cdd6f4")
        line2.append(f" {end_badge} ", style="bold #a6e3a1" if self.active_thumb == "end" else "#89b4fa")
        line2.append(f" {pages_badge}  ", style="#fab387")
        line2.append(thumb_hint, style="#6c7086")

        result = Text()
        result.append_text(line1)
        result.append("\n")
        result.append_text(line2)
        return result

    def _get_track_metrics(self) -> tuple[int, int]:
        """Ermittelt (track_start_x, track_width)."""
        width = max(20, self.size.width - 2)
        min_str = f"{self.min_val} "
        max_str = f" {self.max_val}"
        track_start_x = len(min_str) + 1  # 1 für padding / border
        track_width = max(10, width - len(min_str) - len(max_str) - 2)
        return track_start_x, track_width

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Reagiert auf Mausklicks zur Positionierung der Griffe."""
        self.focus()
        try:
            self.capture_mouse()
        except Exception:
            pass
        try:
            if hasattr(self.screen, "clear_selection"):
                self.screen.clear_selection()
        except Exception:
            pass

        track_start_x, track_width = self._get_track_metrics()
        rel_x = event.x - track_start_x
        val = self._pos_to_val(rel_x, track_width)

        # Welcher Daumen ist näher am Klick?
        dist_start = abs(val - self.start_val)
        dist_end = abs(val - self.end_val)

        if dist_start < dist_end:
            self.active_thumb = "start"
            new_start = min(val, self.end_val)
            self.start_val = max(self.min_val, new_start)
        else:
            self.active_thumb = "end"
            new_end = max(val, self.start_val)
            self.end_val = min(self.max_val, new_end)

        self._is_dragging = True
        self.refresh()
        self.post_message(self.Changed(self.start_val, self.end_val))
        event.stop()
        event.prevent_default()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._is_dragging = False
        try:
            self.release_mouse()
        except Exception:
            pass
        event.stop()
        event.prevent_default()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._is_dragging:
            return
        track_start_x, track_width = self._get_track_metrics()
        rel_x = event.x - track_start_x
        val = self._pos_to_val(rel_x, track_width)

        if self.active_thumb == "start":
            self.start_val = max(self.min_val, min(val, self.end_val))
        else:
            self.end_val = min(self.max_val, max(val, self.start_val))

        self.refresh()
        self.post_message(self.Changed(self.start_val, self.end_val))
        event.stop()
        event.prevent_default()

    def on_key(self, event: events.Key) -> None:
        """Steuerung über Tastatur."""
        key = event.key
        step = 10 if "shift" in event.name else 1

        if key in ("tab", "s", "1"):
            self.active_thumb = "end" if self.active_thumb == "start" and key == "tab" else ("start" if key in ("s", "1") else "end")
            self.refresh()
            event.stop()
            return
        elif key in ("2", "e"):
            self.active_thumb = "end"
            self.refresh()
            event.stop()
            return

        changed = False
        if key in ("left", "down"):
            if self.active_thumb == "start":
                new_val = max(self.min_val, self.start_val - step)
                if new_val != self.start_val:
                    self.start_val = new_val
                    changed = True
            else:
                new_val = max(self.start_val, self.end_val - step)
                if new_val != self.end_val:
                    self.end_val = new_val
                    changed = True
            event.stop()

        elif key in ("right", "up"):
            if self.active_thumb == "start":
                new_val = min(self.end_val, self.start_val + step)
                if new_val != self.start_val:
                    self.start_val = new_val
                    changed = True
            else:
                new_val = min(self.max_val, self.end_val + step)
                if new_val != self.end_val:
                    self.end_val = new_val
                    changed = True
            event.stop()

        elif key == "home":
            if self.active_thumb == "start":
                self.start_val = self.min_val
            else:
                self.end_val = self.start_val
            changed = True
            event.stop()

        elif key == "end":
            if self.active_thumb == "end":
                self.end_val = self.max_val
            else:
                self.start_val = self.end_val
            changed = True
            event.stop()

        if changed:
            self.refresh()
            self.post_message(self.Changed(self.start_val, self.end_val))
