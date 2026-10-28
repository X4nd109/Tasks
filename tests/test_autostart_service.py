"""
test_autostart_service.py - Unit tests for the Windows Registry autostart manager.

The Windows registry is fully mocked, so these tests never touch the real
``HKCU\\...\\Run`` key.
"""

import os
import sys
import unittest
from unittest.mock import ANY, MagicMock, patch

import src.services.autostart_service as autostart


class TestAutostartService(unittest.TestCase):
    def setUp(self):
        self.winreg = MagicMock()
        self.winreg.HKEY_CURRENT_USER = "HKCU"
        self.winreg.KEY_READ = 0x20019
        self.winreg.KEY_SET_VALUE = 0x0002
        self.winreg.REG_SZ = 1

        patches = [
            patch.object(autostart, "winreg", self.winreg),
            patch.object(autostart, "is_windows", return_value=True),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    # -- is_autostart_enabled ------------------------------------------------

    def test_is_autostart_enabled_true(self):
        self.winreg.QueryValueEx.return_value = ("cmd", 1)

        self.assertTrue(autostart.is_autostart_enabled())
        self.winreg.OpenKey.assert_called_with(
            "HKCU", autostart.RUN_KEY_PATH, 0, self.winreg.KEY_READ
        )
        self.winreg.QueryValueEx.assert_called_with(ANY, "Tasks")

    def test_is_autostart_enabled_missing_value(self):
        self.winreg.QueryValueEx.side_effect = FileNotFoundError("not found")

        self.assertFalse(autostart.is_autostart_enabled())

    def test_is_autostart_enabled_permission_error(self):
        self.winreg.OpenKey.side_effect = PermissionError("denied")

        self.assertFalse(autostart.is_autostart_enabled())

    def test_is_autostart_enabled_non_windows(self):
        with patch.object(autostart, "is_windows", return_value=False):
            self.assertFalse(autostart.is_autostart_enabled())

    # -- set_autostart -------------------------------------------------------

    def test_set_autostart_true(self):
        self.assertTrue(autostart.set_autostart(True))

        self.winreg.SetValueEx.assert_called_once()
        args = self.winreg.SetValueEx.call_args.args
        self.assertEqual(args[1], "Tasks")
        self.assertEqual(args[2], 0)
        self.assertEqual(args[3], self.winreg.REG_SZ)
        self.assertIn("--tray", args[4])
        self.winreg.DeleteValue.assert_not_called()

    def test_set_autostart_false(self):
        self.assertTrue(autostart.set_autostart(False))

        self.winreg.DeleteValue.assert_called_once_with(ANY, "Tasks")
        self.winreg.SetValueEx.assert_not_called()

    def test_set_autostart_false_when_already_missing(self):
        self.winreg.DeleteValue.side_effect = FileNotFoundError("missing")

        self.assertTrue(autostart.set_autostart(False))

    def test_set_autostart_permission_error(self):
        self.winreg.SetValueEx.side_effect = PermissionError("denied")

        self.assertFalse(autostart.set_autostart(True))

    def test_set_autostart_non_windows(self):
        with patch.object(autostart, "is_windows", return_value=False):
            self.assertFalse(autostart.set_autostart(True))
            self.assertFalse(autostart.set_autostart(False))

    # -- get_autostart_command ----------------------------------------------

    def test_get_autostart_command_registered_value(self):
        self.winreg.QueryValueEx.return_value = ('"C:\\Python\\pythonw.exe" "main.py" --tray', 1)

        command = autostart.get_autostart_command()

        self.assertEqual(command, '"C:\\Python\\pythonw.exe" "main.py" --tray')

    def test_get_autostart_command_default_when_missing(self):
        self.winreg.QueryValueEx.side_effect = FileNotFoundError("missing")

        command = autostart.get_autostart_command()

        self.assertEqual(command, autostart.get_default_autostart_command())
        self.assertIn("--tray", command)
        self.assertIn("main.py", command)

    def test_get_autostart_command_ignores_empty_value(self):
        self.winreg.QueryValueEx.return_value = ("", 1)

        command = autostart.get_autostart_command()

        self.assertEqual(command, autostart.get_default_autostart_command())

    # -- Command line construction ------------------------------------------

    def test_default_command_uses_pythonw_when_available(self):
        fake_python = os.path.join("C:\\Python310", "python.exe")
        fake_pythonw = os.path.join("C:\\Python310", "pythonw.exe")

        with patch.object(sys, "executable", fake_python), patch.object(
            autostart.os.path, "exists", return_value=True
        ):
            command = autostart.get_default_autostart_command()

        self.assertTrue(command.startswith(f'"{fake_pythonw}"'))
        self.assertIn("--tray", command)

    def test_default_command_falls_back_to_interpreter(self):
        fake_python = os.path.join("C:\\Python310", "python.exe")

        with patch.object(sys, "executable", fake_python), patch.object(
            autostart.os.path, "exists", return_value=False
        ):
            command = autostart.get_default_autostart_command()

        self.assertTrue(command.startswith(f'"{fake_python}"'))
        self.assertIn("--tray", command)

    def test_default_command_for_frozen_executable(self):
        fake_exe = os.path.join("C:\\Program Files\\Tasks", "Tasks.exe")

        with patch.object(sys, "executable", fake_exe), patch.object(
            sys, "frozen", True, create=True
        ):
            command = autostart.get_default_autostart_command()

        self.assertEqual(command, f'"{fake_exe}" --tray')

    def test_toggle_autostart(self):
        with patch.object(autostart, "is_autostart_enabled", return_value=False), patch.object(
            autostart, "set_autostart", return_value=True
        ) as mock_set:
            self.assertTrue(autostart.toggle_autostart())

        mock_set.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
