import io
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock, PropertyMock

import config
import task_manager
import teams_service
from models import Task


class TestTeamsShutdown(unittest.TestCase):
    def setUp(self):
        # Reset shutdown state before each test
        config._IS_SHUTTING_DOWN = False

    def tearDown(self):
        config._IS_SHUTTING_DOWN = False

    def test_shutdown_flag_lifecycle(self):
        self.assertFalse(config.is_shutting_down())
        config.set_shutting_down()
        self.assertTrue(config.is_shutting_down())

    def test_close_all_active_browser_contexts_sets_shutdown(self):
        mock_ctx = MagicMock()
        config.register_active_browser_context(mock_ctx)
        config.close_all_active_browser_contexts()
        self.assertTrue(config.is_shutting_down())
        mock_ctx.close.assert_called_once()

    def test_fetch_teams_tasks_suppresses_target_closed_error(self):
        stderr_capture = io.StringIO()
        class TargetClosedError(Exception):
            pass

        with patch("teams_service.check_teams_session", return_value=True), \
             patch("teams_service.sync_playwright", side_effect=TargetClosedError("Target page, context or browser has been closed")), \
             patch("sys.stderr", stderr_capture):
            tasks = teams_service.fetch_teams_tasks()
            self.assertEqual(tasks, [])
            # Assert nothing was printed to stderr
            self.assertEqual(stderr_capture.getvalue(), "")

    def test_fetch_teams_tasks_suppresses_any_error_when_shutting_down(self):
        config.set_shutting_down()
        stderr_capture = io.StringIO()

        with patch("teams_service.check_teams_session", return_value=True), \
             patch("teams_service.sync_playwright", side_effect=RuntimeError("Some network glitch during shutdown")), \
             patch("sys.stderr", stderr_capture):
            tasks = teams_service.fetch_teams_tasks()
            self.assertEqual(tasks, [])
            self.assertEqual(stderr_capture.getvalue(), "")

    def test_fetch_teams_task_details_suppresses_target_closed_error(self):
        stderr_capture = io.StringIO()
        class TargetClosedError(Exception):
            pass

        t = Task(
            id="teams_1",
            platform="teams",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Test Task",
            due_date_str="Morgen",
            status="offen",
            status_display="Zugewiesen",
            url="https://teams.microsoft.com",
            details_loaded=False,
        )
        with patch("os.path.exists", return_value=True), \
             patch("teams_service.sync_playwright", side_effect=TargetClosedError("Target page, context or browser has been closed")), \
             patch("sys.stderr", stderr_capture):
            res = teams_service.fetch_teams_task_details(t)
            self.assertEqual(res.id, "teams_1")
            self.assertEqual(stderr_capture.getvalue(), "")

    def test_task_manager_sync_suppresses_teams_error_when_shutting_down(self):
        config.set_shutting_down()
        stderr_capture = io.StringIO()

        mgr = task_manager.TaskManager(autostart_prefetch=False)
        mgr._is_shutting_down = True

        with patch("task_manager.is_platform_enabled", side_effect=lambda p: p == "teams"), \
             patch("teams_service.fetch_teams_tasks", side_effect=Exception("Target page, context or browser has been closed")), \
             patch("sys.stderr", stderr_capture):
            m_cnt, t_cnt = mgr.sync(deep_scan=False, start_prefetch=False)
            self.assertEqual(t_cnt, 0)
            self.assertEqual(stderr_capture.getvalue(), "")

    def test_sync_worker_aborted_prints_sync_not_complete(self):
        """Stellt sicher, dass ein abgebrochener Sync (Strg+C) 'Sync not Complete' ausgibt,
        ohne dass eine Exception (z.B. RuntimeError: App is not running) nach außen entweicht."""
        from tui_app import TasksApp

        mgr = task_manager.TaskManager(autostart_prefetch=False)

        # --- Fall 1: call_from_thread wirft RuntimeError("App is not running") ---
        app = TasksApp(mgr, sync_on_startup=False)
        app._is_syncing = False

        stdout_capture = io.StringIO()
        with patch("git_sync_service.is_git_configured", return_value=False), \
             patch.object(mgr, "sync", return_value=(0, 0)), \
             patch.object(TasksApp, "is_running", new_callable=PropertyMock, return_value=True), \
             patch.object(app, "call_from_thread", side_effect=RuntimeError("App is not running")), \
             redirect_stdout(stdout_capture):
            # Darf keine Exception nach außen werfen
            app.action_sync_tasks()
            if app._sync_thread is not None:
                app._sync_thread.join(timeout=5.0)

        self.assertIn("Sync not Complete", stdout_capture.getvalue())
        self.assertFalse(app._is_syncing)
        self.assertTrue(app._sync_not_complete_printed)

        # --- Fall 2: App wird während des Syncs beendet (is_running == False / Shutdown) ---
        app2 = TasksApp(mgr, sync_on_startup=False)
        app2._is_syncing = False

        stdout_capture2 = io.StringIO()
        with patch("git_sync_service.is_git_configured", return_value=False), \
             patch.object(mgr, "sync", return_value=(0, 0)), \
             patch.object(TasksApp, "is_running", new_callable=PropertyMock, return_value=False), \
             patch.object(app2, "call_from_thread") as mock_cft, \
             redirect_stdout(stdout_capture2):
            app2.action_sync_tasks()
            if app2._sync_thread is not None:
                app2._sync_thread.join(timeout=5.0)

        self.assertIn("Sync not Complete", stdout_capture2.getvalue())
        self.assertFalse(app2._is_syncing)
        # Bei nicht laufender App darf kein UI-Update mehr versucht werden
        mock_cft.assert_not_called()

        # --- Fall 3: Kein doppeltes Ausgeben (Flag-Guard) ---
        stdout_capture3 = io.StringIO()
        with patch("git_sync_service.is_git_configured", return_value=False), \
             patch.object(mgr, "sync", return_value=(0, 0)), \
             patch.object(TasksApp, "is_running", new_callable=PropertyMock, return_value=False), \
             redirect_stdout(stdout_capture3):
            app2.action_sync_tasks()
            if app2._sync_thread is not None:
                app2._sync_thread.join(timeout=5.0)

        self.assertEqual(stdout_capture3.getvalue().count("Sync not Complete"), 1)


if __name__ == "__main__":
    unittest.main()
