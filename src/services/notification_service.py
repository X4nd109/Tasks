"""
notification_service.py - Native Windows toast notifications for Tasks.

Uses the optional ``winotify`` package. All notification attempts are fully
guarded: if the package is missing, the platform is unsupported, or Windows
refuses to display the toast, the methods simply return ``False``.
"""

from __future__ import annotations

import os
import sys
from typing import Optional

try:
    from winotify import Notification  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    Notification = None  # type: ignore[assignment]


DEFAULT_APP_ID = "Tasks"


def _is_windows() -> bool:
    """Returns ``True`` when running on Windows."""
    return os.name == "nt" or sys.platform.startswith("win")


class NotificationService:
    """Small wrapper around ``winotify`` for Windows toast notifications."""

    def __init__(self, app_id: str = DEFAULT_APP_ID) -> None:
        self.app_id = app_id or DEFAULT_APP_ID

    def is_available(self) -> bool:
        """Checks whether toast notifications can be displayed on this system."""
        return Notification is not None and _is_windows()

    def send_notification(
        self,
        title: str,
        msg: str,
        icon_path: Optional[str] = None,
        launch_url_or_action: Optional[str] = None,
    ) -> bool:
        """
        Shows a toast notification.

        Returns ``True`` when the notification was handed to Windows
        successfully, ``False`` otherwise. Never raises.
        """
        if not self.is_available():
            return False

        try:
            toast = Notification(app_id=self.app_id, title=title, msg=msg)

            if icon_path:
                try:
                    toast.icon = os.path.abspath(icon_path)
                except (OSError, ValueError):  # pragma: no cover - defensive
                    toast.icon = icon_path

            if launch_url_or_action:
                toast.launch = launch_url_or_action

            toast.show()
            return True
        except Exception:
            return False

    def notify_task(
        self,
        title: str,
        due_date: str,
        subject: Optional[str] = None,
    ) -> bool:
        """Sends a reminder for an upcoming task."""
        message_parts = [f"Due: {due_date}"]
        if subject:
            message_parts.append(f"Subject: {subject}")

        return self.send_notification(
            title=f"Upcoming task: {title}",
            msg="\n".join(message_parts),
        )

    def notify_sync_summary(self, new_count: int) -> bool:
        """Sends a short summary after a synchronisation run."""
        try:
            count = int(new_count)
        except (TypeError, ValueError):
            count = 0

        if count <= 0:
            return self.send_notification(
                title="Tasks sync complete",
                msg="No new tasks found.",
            )

        noun = "task" if count == 1 else "tasks"
        return self.send_notification(
            title="Tasks sync complete",
            msg=f"{count} new {noun} found.",
        )
