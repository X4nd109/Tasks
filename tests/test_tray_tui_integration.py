"""
test_tray_tui_integration.py - Integration tests for TrayConfigModal, TasksApp tray methods, and CLI dispatch.
"""

import unittest
from unittest.mock import MagicMock, PropertyMock, patch
from src.ui.tui_app import SettingsModal, TrayConfigModal, TasksApp
from src.core.config import (
    is_minimize_to_tray_enabled,
    set_minimize_to_tray_enabled,
)


class TestTrayTuiIntegration(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        set_minimize_to_tray_enabled(True)

    def tearDown(self):
        set_minimize_to_tray_enabled(True)

    async def test_settings_modal_has_tray_button(self):
        app = TasksApp(MagicMock(), sync_on_startup=False)
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            btn = app.screen.query_one("#btn_set_tray")
            self.assertIsNotNone(btn)
            self.assertIn("System Tray", str(btn.label))
            await pilot.click("#btn_set_cancel")

    async def test_tray_config_modal_compose_and_save(self):
        app = TasksApp(MagicMock(), sync_on_startup=False)
        async with app.run_test(size=(120, 35)) as pilot:
            app.push_screen(TrayConfigModal())
            await pilot.pause()
            btn_tray = app.screen.query_one("#btn_tray_toggle")
            btn_auto = app.screen.query_one("#btn_auto_toggle")
            self.assertIsNotNone(btn_tray)
            self.assertIsNotNone(btn_auto)
            self.assertIn("Minimize to System Tray", str(btn_tray.label))

            # Verify description labels are present, styled and filled
            desc_labels = list(app.screen.query(".tray_cfg_desc"))
            self.assertEqual(len(desc_labels), 3)
            for desc_lbl in desc_labels:
                rendered_text = str(desc_lbl.render())
                self.assertTrue(len(rendered_text.strip()) > 20)
                self.assertGreaterEqual(desc_lbl.size.width, 50)

            # Test toggling
            await pilot.click("#btn_tray_toggle")
            await pilot.pause()
            self.assertEqual(btn_tray.variant, "default")
            await pilot.click("#btn_tray_cfg_back")

    def test_ipc_command_handler(self):
        mgr = MagicMock()
        mgr.tasks = []
        app = TasksApp(mgr=mgr, sync_on_startup=False)

        with patch.object(app, "restore_from_tray") as mock_restore, patch.object(app, "call_from_thread") as mock_cft:
            res_show = app._handle_ipc_command("SHOW")
            self.assertEqual(res_show, "RESTORED")
            mock_restore.assert_called_once()

            res_quit = app._handle_ipc_command("QUIT")
            self.assertEqual(res_quit, "OK:QUITTING")
            mock_cft.assert_called_with(app.action_real_quit)

            res_status = app._handle_ipc_command("STATUS")
            self.assertEqual(res_status, "OK:TASKS=0")

            res_unknown = app._handle_ipc_command("INVALID")
            self.assertEqual(res_unknown, "ERROR:UNKNOWN")

    async def test_btn_main_quit_hides_to_tray(self):
        set_minimize_to_tray_enabled(True)
        app = TasksApp(MagicMock(), sync_on_startup=False)
        async with app.run_test(size=(120, 35)) as pilot:
            with patch.object(app, "hide_to_tray") as mock_hide:
                app._tray_service = MagicMock()
                await pilot.click("#btn_main_quit")
                await pilot.pause()
                mock_hide.assert_called_once()

    def test_console_ctrl_close_event_stops_services_without_spawn(self):
        """Clicking the console [X] stops pipe and tray, then lets Windows close the console."""
        set_minimize_to_tray_enabled(True)
        app = TasksApp(MagicMock(), sync_on_startup=False)
        server = MagicMock()
        tray = MagicMock()
        app._single_instance_server = server
        app._tray_service = tray
        try:
            with patch("subprocess.Popen") as mock_popen:
                app._install_console_close_handler()
                self.assertTrue(hasattr(app, "_console_ctrl_cb"))
                res = app._console_ctrl_cb(2)  # CTRL_CLOSE_EVENT
                self.assertFalse(res)
                server.stop.assert_called_once()
                tray.stop.assert_called_once()
                mock_popen.assert_not_called()
        finally:
            app._uninstall_console_close_handler()
            app._stop_mouse_listener.set()

    def test_console_ctrl_c_event_triggers_real_quit(self):
        """CTRL_C_EVENT hands over to action_real_quit on the Textual thread and is swallowed."""
        app = TasksApp(MagicMock(), sync_on_startup=False)
        try:
            with patch.object(app, "call_from_thread") as mock_cft:
                app._install_console_close_handler()
                self.assertTrue(app._console_ctrl_cb(0))
                mock_cft.assert_called_once_with(app.action_real_quit)
        finally:
            app._uninstall_console_close_handler()
            app._stop_mouse_listener.set()

    def test_console_ctrl_close_event_ignored_without_tray(self):
        set_minimize_to_tray_enabled(False)
        app = TasksApp(MagicMock(), sync_on_startup=False)
        try:
            with patch("subprocess.Popen") as mock_popen:
                app._install_console_close_handler()
                self.assertFalse(app._console_ctrl_cb(2))
                mock_popen.assert_not_called()
        finally:
            app._uninstall_console_close_handler()
            app._stop_mouse_listener.set()
            set_minimize_to_tray_enabled(True)

    def test_action_quit_app_force_false_hides_to_tray(self):
        """Q / Exit button keeps the app resident in the tray when minimize_to_tray is enabled."""
        set_minimize_to_tray_enabled(True)
        app = TasksApp(MagicMock(), sync_on_startup=False)
        app._tray_service = MagicMock()
        with patch.object(TasksApp, "focused", new_callable=PropertyMock, return_value=None), patch.object(
            app, "hide_to_tray"
        ) as mock_hide, patch.object(app, "exit") as mock_exit:
            app.action_quit_app(force=False)
            mock_hide.assert_called_once()
            mock_exit.assert_not_called()

    def test_action_real_quit_stops_services_and_exits(self):
        """Ctrl+C / tray Quit fully terminates: pipe and tray stopped, Textual exit called."""
        set_minimize_to_tray_enabled(True)
        app = TasksApp(MagicMock(), sync_on_startup=False)
        app._single_instance_server = MagicMock()
        app._tray_service = MagicMock()
        with patch.object(app, "hide_to_tray") as mock_hide, patch.object(app, "exit") as mock_exit:
            app.action_real_quit()
            app._single_instance_server.stop.assert_called_once()
            app._tray_service.stop.assert_called_once()
            mock_hide.assert_not_called()
            mock_exit.assert_called_once()

    def test_mouse_back_listener_has_no_low_level_hook(self):
        """The global WH_MOUSE_LL hook (which froze the whole OS mouse) must stay removed."""
        import inspect
        source = inspect.getsource(TasksApp._run_mouse_back_listener)
        self.assertNotIn("SetWindowsHookEx", source)
        self.assertNotIn("UnhookWindowsHookEx", source)
        self.assertNotIn("PeekMessageW", source)
        self.assertNotIn("MSLLHOOKSTRUCT", source)
        self.assertIn("GetAsyncKeyState", source)

    def test_tray_cli_commands(self):
        from src.core.agent_cli import run_agent_cli
        # Test tray enable
        ret = run_agent_cli(["tray", "enable", "--json"])
        self.assertEqual(ret, 0)
        self.assertTrue(is_minimize_to_tray_enabled())

        # Test tray disable
        ret = run_agent_cli(["tray", "disable", "--json"])
        self.assertEqual(ret, 0)
        self.assertFalse(is_minimize_to_tray_enabled())

        # Reset
        set_minimize_to_tray_enabled(True)

        # Test autostart status
        ret = run_agent_cli(["autostart", "status", "--json"])
        self.assertEqual(ret, 0)


if __name__ == "__main__":
    unittest.main()
