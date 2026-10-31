"""
test_notifications.py - Comprehensive unit tests for Windows Toast Notifications,
deep-linking protocol dispatch, NotificationEngine, and NotificationConfigModal.
"""

import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
for _sub in [_SRC_DIR, os.path.join(_SRC_DIR, "core"), os.path.join(_SRC_DIR, "services"), os.path.join(_SRC_DIR, "ui")]:
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

import config
from config import (
    DEFAULT_NOTIFICATION_SETTINGS,
    NOTIFICATIONS_CONFIG_KEY,
    get_notification_settings,
    get_task_due_window_seconds,
    set_notification_settings,
)
from models import Task, UntisExam
from notification_engine import NotificationEngine
from notification_service import NotificationService
from main import _parse_protocol_uri, _handle_protocol_uri
from src.ui.tui_app import NotificationConfigModal, SettingsModal, TasksApp


def make_task(
    id="t_1",
    title="Task 1",
    course="AMEC",
    due_date_str="04.11.2026",
    due_timestamp=None,
    is_completed=False,
):
    t = Task(
        id=id,
        platform="moodle",
        course=course,
        course_full=course,
        title=title,
        due_date_str=due_date_str,
        status="done" if is_completed else "open",
        status_display="Erledigt" if is_completed else "Offen",
        url="http://example.com",
        due_timestamp=due_timestamp,
    )
    if is_completed:
        t.completed = True
    return t


class TestNotificationConfig(unittest.TestCase):
    """Tests for notification settings loading, saving, and due-window seconds conversion."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app_cfg = os.path.join(self.tmp, "tasks_config.json")
        self.ws_cfg = os.path.join(self.tmp, "config.json")
        self._patches = [
            patch("config.APP_CONFIG_FILE", self.app_cfg),
            patch("config.CONFIG_FILE", self.ws_cfg),
            patch("src.core.config.APP_CONFIG_FILE", self.app_cfg),
            patch("src.core.config.CONFIG_FILE", self.ws_cfg),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_notification_settings(self):
        settings = get_notification_settings()
        self.assertTrue(settings["new_tasks_enabled"])
        self.assertEqual(settings["task_due_window"], "2h")
        self.assertTrue(settings["exam_reminders_enabled"])
        self.assertEqual(settings["exam_reminder_time"], "20:00")
        self.assertEqual(settings["exam_days_ahead"]["TE"], 4)
        self.assertEqual(settings["exam_days_ahead"]["SA"], 7)
        self.assertEqual(settings["exam_days_ahead"]["WDH"], 3)
        self.assertEqual(settings["exam_days_ahead"]["PR"], 3)

    def test_save_and_load_notification_settings(self):
        new_settings = {
            "new_tasks_enabled": False,
            "task_due_window": "5h",
            "exam_reminders_enabled": True,
            "exam_reminder_time": "18:30",
            "exam_days_ahead": {"TE": 2, "SA": 5, "WDH": 1, "PR": 0},
        }
        self.assertTrue(set_notification_settings(new_settings))
        loaded = get_notification_settings()
        self.assertFalse(loaded["new_tasks_enabled"])
        self.assertEqual(loaded["task_due_window"], "5h")
        self.assertEqual(loaded["exam_reminder_time"], "18:30")
        self.assertEqual(loaded["exam_days_ahead"]["TE"], 2)
        self.assertEqual(loaded["exam_days_ahead"]["SA"], 5)
        self.assertEqual(loaded["exam_days_ahead"]["WDH"], 1)
        self.assertEqual(loaded["exam_days_ahead"]["PR"], 0)

    def test_get_task_due_window_seconds(self):
        self.assertEqual(get_task_due_window_seconds("1h"), 3600)
        self.assertEqual(get_task_due_window_seconds("2h"), 7200)
        self.assertEqual(get_task_due_window_seconds("3h"), 10800)
        self.assertEqual(get_task_due_window_seconds("5h"), 18000)
        self.assertEqual(get_task_due_window_seconds("1d"), 86400)
        self.assertEqual(get_task_due_window_seconds("never"), 0)
        # Default fallback
        self.assertEqual(get_task_due_window_seconds("invalid"), 7200)


class TestNotificationServiceMessages(unittest.TestCase):
    """Tests that notification formatting matches the required English format and launch URIs."""

    def setUp(self):
        self.svc = NotificationService()

    @patch.object(NotificationService, "send_notification", return_value=True)
    def test_notify_new_tasks_single(self, mock_send):
        task = make_task(id="t_1", title="Rotary Encoder", course="AMEC", due_date_str="04.11.2026")
        self.assertTrue(self.svc.notify_new_tasks([task]))
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertIn("New Assignment: AMEC", kwargs["title"])
        self.assertIn("Rotary Encoder", kwargs["msg"])
        self.assertEqual(kwargs["launch_url_or_action"], "tasks://task/t_1")

    @patch.object(NotificationService, "send_notification", return_value=True)
    def test_notify_new_tasks_multiple(self, mock_send):
        t1 = make_task(id="t_1", title="Task 1", course="AMEC")
        t2 = make_task(id="t_2", title="Task 2", course="SWP")
        self.assertTrue(self.svc.notify_new_tasks([t1, t2]))
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["title"], "Tasks: New Assignments")
        self.assertIn("2 new assignments found.", kwargs["msg"])
        self.assertEqual(kwargs["launch_url_or_action"], "tasks://main")

    @patch.object(NotificationService, "send_notification", return_value=True)
    def test_notify_task_due(self, mock_send):
        task = make_task(id="t_due_1", title="PLF Preparation", course="BET", due_date_str="Today 23:59")
        self.assertTrue(self.svc.notify_task_due(task, "in 1h 45m"))
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertIn("Assignment Due Soon: BET", kwargs["title"])
        self.assertIn("in 1h 45m", kwargs["msg"])
        self.assertEqual(kwargs["launch_url_or_action"], "tasks://task/t_due_1")

    @patch.object(NotificationService, "send_notification", return_value=True)
    def test_notify_exam_reminder(self, mock_send):
        exam = UntisExam(
            id="e_1",
            exam_type="TE",
            exam_type_display="Test",
            subject="SWP",
            name="OOP Basics",
            text="1. Test",
            date="2026-11-04",
            date_display="04.11.2026",
            start_time="10:00",
            end_time="10:50",
            days_until=4,
        )
        self.assertTrue(self.svc.notify_exam_reminder(exam, 4))
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertIn("Upcoming Test: SWP", kwargs["title"])
        self.assertIn("Time to study!", kwargs["msg"])
        self.assertIn("in 4d", kwargs["msg"])
        self.assertEqual(kwargs["launch_url_or_action"], "tasks://exam/e_1")

    @patch.object(NotificationService, "send_notification", return_value=True)
    def test_notify_update_available(self, mock_send):
        info = {
            "current_version": "1.0.2",
            "latest_version": "2.4.0",
            "tag_name": "v2.4.0",
        }
        self.assertTrue(self.svc.notify_update_available(info))
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertIn("Tasks Update verfügbar (v2.4.0)", kwargs["title"])
        self.assertIn("Eine neue Version steht bereit", kwargs["msg"])
        self.assertEqual(kwargs["launch_url_or_action"], "tasks://update")

    def test_default_icon_path(self):
        self.assertTrue(self.svc.default_icon)
        self.assertTrue(os.path.isfile(self.svc.default_icon))
        self.assertTrue(
            self.svc.default_icon.endswith("app_icon.png")
            or self.svc.default_icon.endswith("app_icon.ico")
        )

    @patch("notification_service.Notification")
    @patch("notification_service._is_windows", return_value=True)
    def test_send_notification_uses_default_icon(self, _mock_win, mock_notif):
        mock_instance = MagicMock()
        mock_notif.return_value = mock_instance

        self.svc.send_notification("Test Title", "Test Message")
        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs.get("icon"), self.svc.default_icon)
        mock_instance.show.assert_called_once()


class TestNotificationEngine(unittest.TestCase):
    """Tests state persistence, deduplication, and conditional triggers in NotificationEngine."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmp, "notification_state.json")
        self.engine = NotificationEngine(self.state_file)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch.object(NotificationService, "notify_new_tasks")
    def test_check_new_tasks_initial_run_does_not_spam(self, mock_notify):
        t1 = make_task(id="t_1", title="Task 1", course="AMEC")
        t2 = make_task(id="t_2", title="Task 2", course="SWP")
        res = self.engine.check_new_tasks([t1, t2])
        # First run initializes state without sending toasts
        self.assertEqual(res, [])
        mock_notify.assert_not_called()
        self.assertEqual(set(self.engine.known_task_ids), {"t_1", "t_2"})

    @patch.object(NotificationService, "notify_new_tasks")
    def test_check_new_tasks_subsequent_run_notifies(self, mock_notify):
        t1 = make_task(id="t_1", title="Task 1", course="AMEC")
        self.engine.check_new_tasks([t1])

        t3 = make_task(id="t_3", title="New Task", course="BET")
        res = self.engine.check_new_tasks([t1, t3])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, "t_3")
        mock_notify.assert_called_once()

    @patch.object(NotificationService, "notify_task_due")
    def test_check_task_due_reminders(self, mock_notify):
        now = time.time()
        # Task due in 1 hour (3600s), within default 2h (7200s) window
        t_due = make_task(id="due_1", title="Due Soon", course="AMEC", due_timestamp=now + 3600)
        # Task due in 5 hours, outside 2h window
        t_far = make_task(id="far_1", title="Far Away", course="SWP", due_timestamp=now + 18000)
        # Task already completed
        t_done = make_task(id="done_1", title="Completed", course="BET", due_timestamp=now + 1800, is_completed=True)

        with patch("notification_engine.get_notification_settings", return_value={"task_due_window": "2h"}):
            notified = self.engine.check_task_due_reminders([t_due, t_far, t_done])
            self.assertEqual(len(notified), 1)
            self.assertEqual(notified[0].id, "due_1")
            mock_notify.assert_called_once()

            # Second call for the same task does not notify again
            mock_notify.reset_mock()
            notified_again = self.engine.check_task_due_reminders([t_due, t_far])
            self.assertEqual(notified_again, [])
            mock_notify.assert_not_called()

    @patch.object(NotificationService, "notify_exam_reminder")
    def test_check_exam_reminders(self, mock_notify):
        exam_te = UntisExam(
            id="e_te", exam_type="TE", exam_type_display="Test", subject="SWP",
            name="OOP", text="", date="2026-11-04", date_display="04.11.",
            start_time="10:00", end_time="10:50", days_until=4
        )
        exam_sa = UntisExam(
            id="e_sa", exam_type="SA", exam_type_display="Schularbeit", subject="AMEC",
            name="Hardware", text="", date="2026-11-10", date_display="10.11.",
            start_time="08:00", end_time="09:40", days_until=10  # outside 7 days
        )

        settings = {
            "exam_reminders_enabled": True,
            "exam_reminder_time": "19:00",
            "exam_days_ahead": {"TE": 4, "SA": 7, "WDH": 3, "PR": 3},
        }

        with patch("notification_engine.get_notification_settings", return_value=settings), patch(
            "notification_engine.datetime"
        ) as mock_dt:
            # Fake current time: 20:00 (after 19:00 reminder time)
            mock_dt.datetime.now.return_value = datetime.datetime(2026, 10, 31, 20, 0, 0)
            mock_dt.date.today.return_value = datetime.date(2026, 10, 31)

            notified = self.engine.check_exam_reminders([exam_te, exam_sa])
            self.assertEqual(len(notified), 1)
            self.assertEqual(notified[0].id, "e_te")
            mock_notify.assert_called_once()

            # Calling again today will not notify again
            mock_notify.reset_mock()
            notified_again = self.engine.check_exam_reminders([exam_te, exam_sa])
            self.assertEqual(notified_again, [])
            mock_notify.assert_not_called()

    @patch.object(NotificationService, "notify_update_available", return_value=True)
    def test_check_update_notification_throttling(self, mock_notify):
        info = {"latest_version": "2.4.0", "tag_name": "v2.4.0"}
        # Initial notification
        sent = self.engine.check_update_notification(update_info=info)
        self.assertTrue(sent)
        mock_notify.assert_called_once_with(info)
        self.assertEqual(self.engine.last_update_notified_tag, "v2.4.0")

        # Second notification within 6h cooldown is suppressed (even with normalized tag variant '2.4.0')
        mock_notify.reset_mock()
        info_normalized = {"latest_version": "2.4.0", "tag_name": "2.4.0"}
        sent_again = self.engine.check_update_notification(update_info=info_normalized)
        self.assertFalse(sent_again)
        mock_notify.assert_not_called()

        # Force bypasses throttling
        sent_forced = self.engine.check_update_notification(update_info=info, force=True)
        self.assertTrue(sent_forced)
        mock_notify.assert_called_once_with(info)

        # A newer release tag (e.g. v2.5.0) notifies immediately
        mock_notify.reset_mock()
        info_new = {"latest_version": "2.5.0", "tag_name": "v2.5.0"}
        sent_new = self.engine.check_update_notification(update_info=info_new)
        self.assertTrue(sent_new)
        mock_notify.assert_called_once_with(info_new)
        self.assertEqual(self.engine.last_update_notified_tag, "v2.5.0")

        # Persistence check
        new_engine = NotificationEngine(self.state_file)
        self.assertEqual(new_engine.last_update_notified_tag, "v2.5.0")
        self.assertTrue(new_engine.last_update_notified_time > 0)


class TestProtocolUriAndIpc(unittest.TestCase):
    """Tests parsing and dispatch of tasks:// protocol URIs."""

    def test_parse_protocol_uri(self):
        cmd, target = _parse_protocol_uri("tasks://task/moodle_1234")
        self.assertEqual(cmd, "OPEN_TASK:moodle_1234")
        self.assertEqual(target, "moodle_1234")

        cmd, target = _parse_protocol_uri("tasks://exam/20261104_1000_BET")
        self.assertEqual(cmd, "OPEN_EXAM:20261104_1000_BET")
        self.assertEqual(target, "20261104_1000_BET")

        cmd, target = _parse_protocol_uri("tasks://main")
        self.assertEqual(cmd, "SHOW")
        self.assertIsNone(target)

    def test_parse_protocol_uri_update(self):
        cmd, target = _parse_protocol_uri("tasks://update")
        self.assertEqual(cmd, "OPEN_UPDATE")
        self.assertIsNone(target)

        cmd, target = _parse_protocol_uri("tasks://update/")
        self.assertEqual(cmd, "OPEN_UPDATE")
        self.assertIsNone(target)

    @patch("main._send_instance_command", return_value="OK:OPEN_TASK")
    def test_handle_protocol_uri_dispatches_to_running_instance(self, mock_send):
        with patch("sys.stdout", new_callable=io.StringIO):
            res = _handle_protocol_uri("tasks://task/task_42")
        self.assertTrue(res)
        mock_send.assert_called_once_with("OPEN_TASK:task_42")

    @patch("main._send_instance_command", return_value="OK:OPEN_UPDATE")
    def test_handle_protocol_uri_update_dispatches_to_running_instance(self, mock_send):
        with patch("sys.stdout", new_callable=io.StringIO):
            res = _handle_protocol_uri("tasks://update")
        self.assertTrue(res)
        mock_send.assert_called_once_with("OPEN_UPDATE")


class TestNotificationConfigModal(unittest.IsolatedAsyncioTestCase):
    """Integration test for NotificationConfigModal."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app_cfg = os.path.join(self.tmp, "tasks_config.json")
        self.ws_cfg = os.path.join(self.tmp, "config.json")
        self._patches = [
            patch("config.APP_CONFIG_FILE", self.app_cfg),
            patch("config.CONFIG_FILE", self.ws_cfg),
            patch("src.core.config.APP_CONFIG_FILE", self.app_cfg),
            patch("src.core.config.CONFIG_FILE", self.ws_cfg),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_modal_compose_and_save(self):
        app = TasksApp(MagicMock(), sync_on_startup=False)
        async with app.run_test(size=(120, 45)) as pilot:
            modal = NotificationConfigModal()
            app.push_screen(modal)
            await pilot.pause()

            # Verify widgets exist
            btn_new = app.screen.query_one("#btn_notif_new_toggle")
            btn_exam = app.screen.query_one("#btn_notif_exam_toggle")
            sel_due = app.screen.query_one("#sel_notif_due_window")
            inp_time = app.screen.query_one("#inp_notif_exam_time")
            sel_te = app.screen.query_one("#sel_days_te")
            sel_sa = app.screen.query_one("#sel_days_sa")

            self.assertIsNotNone(btn_new)
            self.assertIsNotNone(btn_exam)
            self.assertEqual(sel_due.value, "2h")
            self.assertEqual(inp_time.value, "20:00")
            self.assertEqual(sel_te.value, 4)
            self.assertEqual(sel_sa.value, 7)

            # Change settings
            modal.new_enabled = False
            inp_time.value = "19:30"
            sel_due.value = "3h"
            sel_te.value = 5

            # Save
            modal._save()
            await pilot.pause()

        saved = get_notification_settings()
        self.assertFalse(saved["new_tasks_enabled"])
        self.assertEqual(saved["task_due_window"], "3h")
        self.assertEqual(saved["exam_reminder_time"], "19:30")
        self.assertEqual(saved["exam_days_ahead"]["TE"], 5)


if __name__ == "__main__":
    unittest.main()
