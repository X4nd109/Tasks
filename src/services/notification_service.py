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


def _workspace_root() -> str:
    """Returns the project root folder (three levels above this file, or dev root if frozen in dev repo)."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        cur = exe_dir
        for _ in range(3):
            if os.path.isdir(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _python_executable_without_console() -> str:
    """Prefers ``pythonw.exe`` next to the running interpreter (no console flash)."""
    py_exe = sys.executable or "python.exe"
    try:
        directory = os.path.dirname(py_exe)
        basename = os.path.basename(py_exe).lower()
        if basename == "python.exe":
            pythonw = os.path.join(directory, "pythonw.exe")
            if os.path.exists(pythonw):
                return pythonw
    except Exception:
        pass
    return py_exe


def get_default_icon_path() -> str:
    """Returns the absolute path to the default Tasks app icon (app_icon.png)."""
    assets_dir = os.path.join(_workspace_root(), "assets")
    png_path = os.path.join(assets_dir, "app_icon.png")
    if os.path.isfile(png_path):
        return os.path.abspath(png_path)
    ico_path = os.path.join(assets_dir, "app_icon.ico")
    if os.path.isfile(ico_path):
        return os.path.abspath(ico_path)
    return ""


def _format_icon_uri(icon_path: str) -> str:
    """Converts a local icon path to a valid file:/// URI for Windows Toast XML."""
    if not icon_path:
        return ""
    try:
        p = os.path.abspath(icon_path)
        if os.path.isfile(p):
            from pathlib import Path

            return Path(p).as_uri()
    except Exception:
        pass
    return icon_path


if Notification is not None:
    def _modern_show(self) -> None:
        """Sends a modern ToastGeneric notification with placement='appLogoOverride'."""
        if not _is_windows():
            return
        import subprocess

        actions_str = "\n".join(self.actions) if getattr(self, "actions", None) else ""
        audio_str = '<audio silent="true" />'

        launch_str = ""
        launch_val = getattr(self, "launch", "")
        if launch_val:
            launch_str = f'activationType="protocol" launch="{launch_val}"'

        icon_val = getattr(self, "icon", "")
        image_element = ""
        if icon_val:
            icon_uri = _format_icon_uri(icon_val)
            if icon_uri:
                image_element = f'<image placement="appLogoOverride" src="{icon_uri}" />'

        title_str = getattr(self, "title", "")
        msg_str = getattr(self, "msg", "")
        duration_str = getattr(self, "duration", "short") or "short"
        tag_str = getattr(self, "tag", title_str) or title_str
        group_str = (
            getattr(self, "group", getattr(self, "app_id", DEFAULT_APP_ID))
            or DEFAULT_APP_ID
        )

        script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null

$Template = @"
<toast {launch_str} duration="{duration_str}">
    <visual>
        <binding template="ToastGeneric">
            {image_element}
            <text id="1"><![CDATA[{title_str}]]></text>
            <text id="2"><![CDATA[{msg_str}]]></text>
        </binding>
    </visual>
    <actions>
        {actions_str}
    </actions>
    {audio_str}
</toast>
"@

$SerializedXml = New-Object Windows.Data.Xml.Dom.XmlDocument
$SerializedXml.LoadXml($Template)

$Toast = [Windows.UI.Notifications.ToastNotification]::new($SerializedXml)
$Toast.Tag = "{tag_str[:16]}"
$Toast.Group = "{group_str}"

$Notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{getattr(self, 'app_id', DEFAULT_APP_ID)}")
$Notifier.Show($Toast);
"""
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-Command", script]
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=si,
        )

    Notification.show = _modern_show


def ensure_tasks_protocol_registered() -> bool:
    """Registers the ``tasks://`` URL protocol for the current Windows user.

    Creates ``HKCU\\Software\\Classes\\tasks`` with the URL protocol marker and
    an ``shell\\open\\command`` value that forwards the URI to
    ``main.py --uri "%1"``. Uses ``pythonw.exe`` when available so opening a
    toast does not flash a console window. Never raises.
    """
    if not _is_windows():
        return False

    try:
        import winreg  # type: ignore[import-not-found]

        root = _workspace_root()
        main_py = os.path.join(root, "main.py")
        command = f'"{_python_executable_without_console()}" "{main_py}" --uri "%1"'
        png_icon = os.path.join(root, "assets", "app_icon.png")
        ico_icon = os.path.join(root, "assets", "app_icon.ico")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\tasks") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Tasks Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        if os.path.isfile(ico_icon):
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, r"Software\Classes\tasks\DefaultIcon"
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, os.path.abspath(ico_icon))

        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Classes\tasks\shell\open\command"
        ) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

        # Register AppUserModelId so Windows Action Center & Toast header display the app icon
        icon_for_aumid = png_icon if os.path.isfile(png_icon) else ico_icon
        if os.path.isfile(icon_for_aumid):
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, r"Software\Classes\AppUserModelId\Tasks"
            ) as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DEFAULT_APP_ID)
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, os.path.abspath(icon_for_aumid))

        return True
    except Exception:
        return False


class NotificationService:
    """Small wrapper around ``winotify`` for Windows toast notifications."""

    def __init__(
        self,
        app_id: str = DEFAULT_APP_ID,
        default_icon: Optional[str] = None,
    ) -> None:
        self.app_id = app_id or DEFAULT_APP_ID
        if default_icon is not None:
            self.default_icon = default_icon
        else:
            self.default_icon = get_default_icon_path()

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
            chosen_icon = icon_path if icon_path is not None else self.default_icon
            resolved_icon = ""
            if chosen_icon:
                try:
                    resolved_icon = os.path.abspath(chosen_icon)
                except (OSError, ValueError):  # pragma: no cover - defensive
                    resolved_icon = str(chosen_icon)

            toast = Notification(
                app_id=self.app_id,
                title=title,
                msg=msg,
                icon=resolved_icon,
            )
            toast.icon = resolved_icon

            if launch_url_or_action:
                toast.launch = launch_url_or_action

            toast.show()
            return True
        except Exception:
            return False

    def notify_new_tasks(self, new_tasks: list) -> bool:
        """Notifies about one or more newly discovered assignments."""
        try:
            count = len(new_tasks)
        except TypeError:
            return False

        if count == 0:
            return False

        if count == 1:
            task = new_tasks[0]
            title = f"New Assignment: {getattr(task, 'subject', '') or getattr(task, 'course', '')}"
            msg = f"{getattr(task, 'title', '')}\nDue: {getattr(task, 'due_date_str', '')}"
            launch = f"tasks://task/{getattr(task, 'id', '')}"
        else:
            title = "Tasks: New Assignments"
            msg = f"{count} new assignments found."
            launch = "tasks://main"

        return self.send_notification(title=title, msg=msg, launch_url_or_action=launch)

    def notify_task_due(self, task, time_remaining_str: str) -> bool:
        """Reminds the user that an assignment is due soon."""
        subject = getattr(task, "subject", "") or getattr(task, "course", "")
        title = f"Assignment Due Soon: {subject}"
        msg = (
            f"{getattr(task, 'title', '')}\n"
            f"Due: {getattr(task, 'due_date_str', '')} ({time_remaining_str})"
        )
        launch = f"tasks://task/{getattr(task, 'id', '')}"
        return self.send_notification(title=title, msg=msg, launch_url_or_action=launch)

    def notify_exam_reminder(self, exam, days_until: int) -> bool:
        """Reminds the user about an upcoming exam or test."""
        exam_type_display = getattr(exam, "exam_type_display", "") or "Exam"
        subject = getattr(exam, "subject", "")
        title = f"Upcoming {exam_type_display}: {subject}"

        if days_until > 1:
            countdown = f"in {days_until}d"
        elif days_until == 1:
            countdown = "Tomorrow"
        else:
            countdown = "Today"

        text = (
            getattr(exam, "name", "")
            or getattr(exam, "text", "")
            or subject
        )
        msg = (
            f"{text}\n"
            f"Date: {getattr(exam, 'date_display', '')} ({countdown})\n"
            "Time to study!"
        )
        launch = f"tasks://exam/{getattr(exam, 'id', '')}"
        return self.send_notification(title=title, msg=msg, launch_url_or_action=launch)

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
