"""
notification_engine.py - Background engine that decides when to show toasts.

The engine keeps a small JSON state file (``cache/notification_state.json``)
so that the same assignment or exam is never announced twice:

* ``known_task_ids``       - every assignment ID seen so far
* ``due_notified_task_ids``- assignment ID -> notification timestamp
* ``exam_notified_dates``  - exam ID -> ``YYYY-MM-DD`` of the last reminder

All state writes are atomic and every public method is defensive: errors are
swallowed so a broken cache can never crash the TUI or the tray process.
"""

from __future__ import annotations

import datetime
import json
import os
import time
from typing import List, Optional

try:
    from config import (
        CONFIG_DIR,
        get_notification_settings,
        get_task_due_window_seconds,
    )
except ImportError:  # pragma: no cover - package-relative import
    from src.core.config import (  # type: ignore[no-redef]
        CONFIG_DIR,
        get_notification_settings,
        get_task_due_window_seconds,
    )

try:
    from notification_service import NotificationService
except ImportError:  # pragma: no cover - package-relative import
    from src.services.notification_service import NotificationService  # type: ignore[no-redef]


DEFAULT_STATE_FILE = os.path.join(CONFIG_DIR, "notification_state.json")


def _as_list(items) -> list:
    """Converts any iterable to a list without ever raising."""
    if items is None:
        return []
    try:
        return list(items)
    except TypeError:
        return []


def _task_id(task) -> str:
    raw = getattr(task, "id", None)
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, (str, int)):
        return str(raw).strip()
    return ""


def _is_completed(task) -> bool:
    completed = getattr(task, "completed", None)
    if isinstance(completed, bool):
        return completed
    try:
        return bool(getattr(task, "is_completed", False))
    except Exception:
        return False


def _format_remaining(seconds: float) -> str:
    """Formats a positive number of seconds as ``in 1h 45m`` / ``in 45m``."""
    total_minutes = max(1, int(seconds // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"in {hours}h {minutes}m"
    if hours:
        return f"in {hours}h"
    return f"in {minutes}m"


class NotificationEngine:
    """Checks assignments and exams and sends toast notifications."""

    def __init__(self, state_file: Optional[str] = None) -> None:
        self.state_file = state_file or DEFAULT_STATE_FILE
        self.known_task_ids: List[str] = []
        self.due_notified_task_ids: dict = {}
        self.exam_notified_dates: dict = {}
        self.last_update_check: float = 0.0
        self.last_update_notified_tag: str = ""
        self.last_update_notified_time: float = 0.0
        self.load_state()

    # -- State persistence ---------------------------------------------------

    def load_state(self) -> dict:
        """Loads the notification state from disk (tolerates missing/corrupt files)."""
        state = {}
        try:
            if self.state_file and os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    state = loaded
        except Exception:
            state = {}

        known = state.get("known_task_ids", [])
        self.known_task_ids = [str(i) for i in known] if isinstance(known, list) else []

        due = state.get("due_notified_task_ids", {})
        self.due_notified_task_ids = {
            str(k): v for k, v in due.items()
        } if isinstance(due, dict) else {}

        exams = state.get("exam_notified_dates", {})
        self.exam_notified_dates = {
            str(k): str(v) for k, v in exams.items()
        } if isinstance(exams, dict) else {}

        try:
            self.last_update_check = float(state.get("last_update_check", 0.0) or 0.0)
        except (TypeError, ValueError):
            self.last_update_check = 0.0

        self.last_update_notified_tag = str(state.get("last_update_notified_tag", "") or "")

        try:
            self.last_update_notified_time = float(state.get("last_update_notified_time", 0.0) or 0.0)
        except (TypeError, ValueError):
            self.last_update_notified_time = 0.0

        return {
            "known_task_ids": list(self.known_task_ids),
            "due_notified_task_ids": dict(self.due_notified_task_ids),
            "exam_notified_dates": dict(self.exam_notified_dates),
            "last_update_check": self.last_update_check,
            "last_update_notified_tag": self.last_update_notified_tag,
            "last_update_notified_time": self.last_update_notified_time,
        }

    def save_state(self) -> bool:
        """Writes the notification state atomically. Returns ``True`` on success."""
        payload = {
            "known_task_ids": list(self.known_task_ids),
            "due_notified_task_ids": dict(self.due_notified_task_ids),
            "exam_notified_dates": dict(self.exam_notified_dates),
            "last_update_check": self.last_update_check,
            "last_update_notified_tag": self.last_update_notified_tag,
            "last_update_notified_time": self.last_update_notified_time,
        }
        try:
            directory = os.path.dirname(self.state_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp_path = f"{self.state_file}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.state_file)
            return True
        except Exception:
            return False

    # -- New assignments -----------------------------------------------------

    def check_new_tasks(self, current_tasks: list) -> list:
        """Detects newly discovered assignments and announces them once."""
        tasks = _as_list(current_tasks)

        try:
            settings = get_notification_settings()
        except Exception:
            settings = {}

        current_ids = [_task_id(t) for t in tasks if _task_id(t)]
        known = set(self.known_task_ids)

        # First run ever: remember everything, but never spam the user.
        if not known:
            self.known_task_ids = list(dict.fromkeys(current_ids))
            self.save_state()
            return []

        new_tasks = [t for t in tasks if _task_id(t) not in known]

        if not settings.get("new_tasks_enabled", True):
            # Keep tracking IDs while notifications are disabled.
            self.known_task_ids = list(dict.fromkeys(self.known_task_ids + current_ids))
            self.save_state()
            return []

        if not new_tasks:
            return []

        try:
            NotificationService().notify_new_tasks(new_tasks)
        except Exception:
            pass

        self.known_task_ids = list(dict.fromkeys(self.known_task_ids + current_ids))
        self.save_state()
        return new_tasks

    # -- Assignment due reminders -------------------------------------------

    def check_task_due_reminders(self, current_tasks: list) -> list:
        """Sends a reminder for each assignment entering the due window."""
        tasks = _as_list(current_tasks)

        try:
            settings = get_notification_settings()
        except Exception:
            settings = {}

        try:
            window_sec = get_task_due_window_seconds(settings.get("task_due_window"))
        except Exception:
            window_sec = 7200

        if window_sec <= 0:
            return []

        now = time.time()
        notified = []
        due_map = self.due_notified_task_ids
        if not isinstance(due_map, dict):
            due_map = {}

        task_by_id = {}
        for task in tasks:
            tid = _task_id(task)
            if tid:
                task_by_id[tid] = task

            if getattr(task, "deleted", False) or _is_completed(task):
                continue

            try:
                due_ts = float(getattr(task, "due_timestamp", None) or 0)
            except (TypeError, ValueError):
                due_ts = 0.0

            if not due_ts:
                continue

            diff = due_ts - now
            if not (0 < diff <= window_sec):
                continue

            if tid in due_map:
                # Already announced for this (still running) deadline.
                continue

            remaining = _format_remaining(diff)
            try:
                NotificationService().notify_task_due(task, remaining)
            except Exception:
                pass

            due_map[tid] = now
            notified.append(task)

        # Drop entries whose deadline already passed (or that vanished).
        for tid in list(due_map.keys()):
            task = task_by_id.get(tid)
            if task is None:
                due_map.pop(tid, None)
                continue
            try:
                due_ts = float(getattr(task, "due_timestamp", None) or 0)
            except (TypeError, ValueError):
                due_ts = 0.0
            if not due_ts or due_ts <= now:
                due_map.pop(tid, None)

        self.due_notified_task_ids = due_map
        self.save_state()
        return notified

    # -- Exam reminders ------------------------------------------------------

    def check_exam_reminders(self, exams: list) -> list:
        """Sends one reminder per exam day, respecting the per-type lead time."""
        exam_list = _as_list(exams)

        try:
            settings = get_notification_settings()
        except Exception:
            settings = {}

        if not settings.get("exam_reminders_enabled", True):
            return []

        reminder_time = str(settings.get("exam_reminder_time", "20:00") or "20:00").strip()
        try:
            hour_str, minute_str = reminder_time.split(":", 1)
            reminder_hour = int(hour_str)
            reminder_minute = int(minute_str)
            if not (0 <= reminder_hour <= 23 and 0 <= reminder_minute <= 59):
                raise ValueError
        except Exception:
            reminder_hour, reminder_minute = 20, 0

        try:
            now = datetime.datetime.now()
            today_str = datetime.date.today().isoformat()
        except Exception:  # pragma: no cover - extremely defensive
            return []

        if (now.hour, now.minute) < (reminder_hour, reminder_minute):
            return []

        days_ahead = settings.get("exam_days_ahead", {})
        if not isinstance(days_ahead, dict):
            days_ahead = {}

        notified = []
        for exam in exam_list:
            if getattr(exam, "is_past", False):
                continue

            try:
                days_until = int(getattr(exam, "days_until", 0) or 0)
            except (TypeError, ValueError):
                continue

            if days_until <= 0:
                continue

            exam_type = str(getattr(exam, "exam_type", "") or "")
            allowed_days = days_ahead.get(exam_type, 0)
            if allowed_days is None:
                continue
            try:
                allowed_days = int(allowed_days)
            except (TypeError, ValueError):
                continue
            if allowed_days <= 0:
                continue

            if days_until > allowed_days:
                continue

            exam_id = str(getattr(exam, "id", "") or "")
            if self.exam_notified_dates.get(exam_id) == today_str:
                continue

            try:
                NotificationService().notify_exam_reminder(exam, days_until)
            except Exception:
                pass

            self.exam_notified_dates[exam_id] = today_str
            notified.append(exam)

        self.save_state()
        return notified

    # -- Update notifications ------------------------------------------------

    def check_update_notification(
        self,
        update_info: Optional[dict] = None,
        force: bool = False,
        cooldown_seconds: float = 21600.0,
    ) -> bool:
        """
        Checks for an available application update and displays a toast notification.
        Throttled to at most once every ``cooldown_seconds`` (default 6h) per release tag.
        Returns ``True`` if a notification was sent, ``False`` otherwise.
        """
        now = time.time()
        info = update_info
        if info is None:
            # Throttle the network call to GitHub (30m between checks, 5m retry on offline/error)
            check_cooldown = 1800.0
            if not force and (now - self.last_update_check < check_cooldown):
                return False
            try:
                try:
                    from update_service import check_for_updates
                except ImportError:
                    from src.services.update_service import check_for_updates
                info = check_for_updates()
            except Exception:
                info = None

            if info:
                self.last_update_check = now
            else:
                # If offline or no update, allow retry after 5 minutes instead of locking out for hours
                self.last_update_check = max(0.0, now - (check_cooldown - 300.0))
            self.save_state()

        if not info or not isinstance(info, dict):
            return False

        tag = str(info.get("tag_name") or info.get("latest_version") or "").strip()
        if not tag:
            return False

        tag_norm = tag.lstrip("vV")
        last_norm = self.last_update_notified_tag.lstrip("vV")

        if not force:
            if tag_norm and tag_norm == last_norm and (now - self.last_update_notified_time < cooldown_seconds):
                return False

        try:
            sent = NotificationService().notify_update_available(info)
        except Exception:
            sent = False

        if sent:
            self.last_update_notified_tag = tag
            self.last_update_notified_time = now
            self.save_state()
        return sent
