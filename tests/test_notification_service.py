"""
test_notification_service.py - Unit tests for the winotify toast wrapper.

``winotify`` is fully mocked; no real toast is ever displayed.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import src.services.notification_service as notification_service


class TestNotificationService(unittest.TestCase):
    def setUp(self):
        self.toast = MagicMock()
        self.notification_cls = MagicMock(return_value=self.toast)

        patches = [
            patch.object(notification_service, "Notification", self.notification_cls),
            patch.object(notification_service, "_is_windows", return_value=True),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        self.service = notification_service.NotificationService()

    # -- Availability --------------------------------------------------------

    def test_is_available(self):
        self.assertTrue(self.service.is_available())

    def test_is_available_without_winotify(self):
        with patch.object(notification_service, "Notification", None):
            self.assertFalse(self.service.is_available())

    def test_is_available_non_windows(self):
        with patch.object(notification_service, "_is_windows", return_value=False):
            self.assertFalse(self.service.is_available())

    # -- send_notification ---------------------------------------------------

    def test_send_notification(self):
        result = self.service.send_notification("Title", "Message")

        self.assertTrue(result)
        self.notification_cls.assert_called_once_with(
            app_id="Tasks", title="Title", msg="Message"
        )
        self.toast.show.assert_called_once()

    def test_send_notification_with_icon_and_launch(self):
        result = self.service.send_notification(
            "Title",
            "Message",
            icon_path="assets/app_icon.png",
            launch_url_or_action="https://example.com",
        )

        self.assertTrue(result)
        self.assertEqual(self.toast.icon, os.path.abspath("assets/app_icon.png"))
        self.assertEqual(self.toast.launch, "https://example.com")
        self.toast.show.assert_called_once()

    def test_send_notification_handles_exceptions(self):
        self.toast.show.side_effect = RuntimeError("toast failed")

        self.assertFalse(self.service.send_notification("Title", "Message"))

    def test_send_notification_unavailable(self):
        with patch.object(notification_service, "Notification", None):
            self.assertFalse(self.service.send_notification("Title", "Message"))

        self.toast.show.assert_not_called()

    def test_custom_app_id(self):
        custom = notification_service.NotificationService(app_id="CustomTasks")
        custom.send_notification("Title", "Message")

        self.notification_cls.assert_called_with(
            app_id="CustomTasks", title="Title", msg="Message"
        )

    # -- Helpers -------------------------------------------------------------

    def test_notify_task(self):
        with patch.object(self.service, "send_notification", return_value=True) as mock_send:
            result = self.service.notify_task(
                "Math homework", "2026-11-02 08:00", subject="MATH"
            )

        self.assertTrue(result)
        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertIn("Math homework", kwargs["title"])
        self.assertIn("2026-11-02 08:00", kwargs["msg"])
        self.assertIn("MATH", kwargs["msg"])

    def test_notify_task_without_subject(self):
        with patch.object(self.service, "send_notification", return_value=True) as mock_send:
            self.service.notify_task("Essay", "Tomorrow")

        kwargs = mock_send.call_args.kwargs
        self.assertIn("Tomorrow", kwargs["msg"])
        self.assertNotIn("Subject:", kwargs["msg"])

    def test_notify_sync_summary_singular(self):
        with patch.object(self.service, "send_notification", return_value=True) as mock_send:
            self.assertTrue(self.service.notify_sync_summary(1))

        self.assertIn("1 new task", mock_send.call_args.kwargs["msg"])

    def test_notify_sync_summary_plural(self):
        with patch.object(self.service, "send_notification", return_value=True) as mock_send:
            self.assertTrue(self.service.notify_sync_summary(5))

        self.assertIn("5 new tasks", mock_send.call_args.kwargs["msg"])

    def test_notify_sync_summary_zero(self):
        with patch.object(self.service, "send_notification", return_value=True) as mock_send:
            self.assertTrue(self.service.notify_sync_summary(0))

        self.assertIn("No new tasks", mock_send.call_args.kwargs["msg"])


if __name__ == "__main__":
    unittest.main()
