"""
test_tray_service.py - Unit tests for the pystray-based tray integration.

``pystray`` is mocked so no real tray icon is created during the tests. Icon
generation itself uses the real (lightweight) Pillow implementation.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

import src.services.tray_service as tray


class TestTrayImage(unittest.TestCase):
    def test_fallback_image_is_64x64_rgba(self):
        with patch.object(tray, "resolve_icon_path", return_value=None):
            image = tray.create_tray_image()

        self.assertIsInstance(image, Image.Image)
        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.mode, "RGBA")

    def test_fallback_image_custom_size(self):
        image = tray.generate_fallback_image(32)

        self.assertEqual(image.size, (32, 32))
        self.assertEqual(image.mode, "RGBA")

    def test_missing_explicit_icon_falls_back(self):
        missing = os.path.join(tempfile.gettempdir(), "definitely_missing_tasks_icon.png")

        image = tray.create_tray_image(missing)

        self.assertEqual(image.size, (64, 64))

    def test_existing_icon_is_loaded_and_resized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "icon.png")
            Image.new("RGB", (16, 16), (255, 0, 0)).save(path)

            image = tray.create_tray_image(path)

        self.assertEqual(image.size, (64, 64))
        self.assertEqual(image.mode, "RGBA")

    def test_corrupt_icon_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.png")
            with open(path, "wb") as handle:
                handle.write(b"not an image")

            image = tray.create_tray_image(path)

        self.assertEqual(image.size, (64, 64))


class TestTrayService(unittest.TestCase):
    def setUp(self):
        self.pystray = MagicMock()
        self.pystray.Menu.SEPARATOR = "SEPARATOR"

        patcher = patch.object(tray, "pystray", self.pystray)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.on_open = MagicMock()
        self.on_sync = MagicMock()
        self.on_quit = MagicMock()
        self.autostart_checker = MagicMock(return_value=False)
        self.autostart_toggler = MagicMock(return_value=True)

        self.service = tray.TrayService(
            on_open=self.on_open,
            on_sync=self.on_sync,
            on_quit=self.on_quit,
            autostart_checker=self.autostart_checker,
            autostart_toggler=self.autostart_toggler,
        )

    # -- Initialization ------------------------------------------------------

    def test_initial_state(self):
        self.assertIsNone(self.service.icon)
        self.assertIsNone(self.service.image)
        self.assertEqual(self.service.open_count, 0)
        self.assertEqual(self.service.status_text, "Tasks: 0 open")
        self.assertFalse(self.service.is_running)

    def test_initial_open_count_is_clamped(self):
        service = tray.TrayService(open_count=-5)

        self.assertEqual(service.open_count, 0)
        self.assertEqual(service.status_text, "Tasks: 0 open")

    # -- Menu ----------------------------------------------------------------

    def test_menu_setup(self):
        self.service.start()

        self.assertTrue(self.service.start())
        self.pystray.Icon.assert_called_once()
        icon_args = self.pystray.Icon.call_args.args
        self.assertEqual(icon_args[0], "tasks")
        self.assertIsInstance(icon_args[1], Image.Image)
        self.assertEqual(icon_args[2], "Tasks")


        self.pystray.Menu.assert_called_once()
        self.assertEqual(len(self.pystray.Menu.call_args.args), 5)


        texts = [
            call.args[0]
            for call in self.pystray.MenuItem.call_args_list
            if isinstance(call.args[0], str)
        ]
        self.assertEqual(
            texts,
            ["Open Tasks", "Sync Now", "Autostart with Windows", "Quit Tasks"],
        )

        open_call = next(
            call
            for call in self.pystray.MenuItem.call_args_list
            if call.args[0] == "Open Tasks"
        )
        self.assertTrue(open_call.kwargs.get("default"))

        autostart_call = next(
            call
            for call in self.pystray.MenuItem.call_args_list
            if call.args[0] == "Autostart with Windows"
        )
        checked = autostart_call.kwargs.get("checked")
        self.assertTrue(callable(checked))
        self.assertFalse(checked(None))
        self.autostart_checker.assert_called()

    # -- Callbacks -----------------------------------------------------------

    def test_open_callback(self):
        self.service._handle_open()
        self.on_open.assert_called_once()

    def test_sync_callback(self):
        self.service._handle_sync()
        self.on_sync.assert_called_once()

    def test_quit_callback(self):
        self.service._handle_quit()
        self.on_quit.assert_called_once()

    def test_toggle_autostart_enables(self):
        self.autostart_checker.return_value = False

        self.service._handle_autostart_toggle()

        self.autostart_toggler.assert_called_once_with(True)

    def test_toggle_autostart_disables(self):
        self.autostart_checker.return_value = True

        self.service._handle_autostart_toggle()

        self.autostart_toggler.assert_called_once_with(False)

    # -- Lifecycle -----------------------------------------------------------

    def test_start_and_stop(self):
        self.assertTrue(self.service.start())
        icon = self.service.icon
        self.assertIsNotNone(icon)

        self.service.stop()

        icon.stop.assert_called_once()
        self.assertIsNone(self.service.icon)

    def test_start_without_pystray(self):
        with patch.object(tray, "pystray", None):
            self.assertFalse(self.service.start())

    def test_update_status(self):
        self.service.start()
        icon = self.service.icon
        icon.update_menu.reset_mock()

        self.service.update_status(5)

        self.assertEqual(self.service.open_count, 5)
        self.assertEqual(self.service.status_text, "Tasks: 5 open")
        icon.update_menu.assert_called_once()
        self.assertEqual(icon.title, "Tasks")


    def test_update_status_clamps_invalid_values(self):
        self.service.update_status(-3)
        self.assertEqual(self.service.open_count, 0)
        self.assertEqual(self.service.status_text, "Tasks: 0 open")

        self.service.update_status("not a number")
        self.assertEqual(self.service.open_count, 0)

    def test_update_status_before_start(self):
        self.service.update_status(4)

        self.assertEqual(self.service.status_text, "Tasks: 4 open")
        self.assertIsNone(self.service.icon)


class TestRealPystrayMenu(unittest.TestCase):
    @unittest.skipUnless(tray.pystray is not None, "pystray is not installed")
    def test_build_menu_with_real_pystray(self):
        service = tray.TrayService()

        menu = service._build_menu()

        self.assertIsNotNone(menu)


if __name__ == "__main__":
    unittest.main()
