"""
test_terminal_profile.py - Unit tests for Windows Terminal profile auto-repair service.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.services.terminal_profile_service import (
    TASKS_PROFILE_GUID,
    TASKS_PROFILE_NAME,
    find_windows_terminal_settings_file,
    get_default_tasks_executable,
    get_default_icon_path,
    ensure_windows_terminal_profile,
    remove_windows_terminal_profile,
    get_windows_terminal_profile_status,
)


class TestTerminalProfileService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_settings = os.path.join(self.temp_dir.name, "settings.json")
        self.mock_app_dir = os.path.join(self.temp_dir.name, "TasksApp")
        os.makedirs(self.mock_app_dir, exist_ok=True)
        os.makedirs(os.path.join(self.mock_app_dir, "assets"), exist_ok=True)

        # Create dummy Tasks.exe and icon
        self.mock_exe = os.path.join(self.mock_app_dir, "Tasks.exe")
        with open(self.mock_exe, "w") as f:
            f.write("mock")
        self.mock_icon = os.path.join(self.mock_app_dir, "assets", "app_icon.png")
        with open(self.mock_icon, "w") as f:
            f.write("mock")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_default_tasks_executable(self):
        exe = get_default_tasks_executable(self.mock_app_dir)
        self.assertEqual(os.path.abspath(exe), os.path.abspath(self.mock_exe))

    def test_get_default_icon_path(self):
        icon = get_default_icon_path(self.mock_app_dir)
        self.assertEqual(os.path.abspath(icon), os.path.abspath(self.mock_icon))

    @patch("src.services.terminal_profile_service.find_windows_terminal_settings_file")
    def test_ensure_profile_modern_schema(self, mock_find):
        mock_find.return_value = self.mock_settings
        initial_data = {
            "$schema": "https://aka.ms/terminal-profiles-schema",
            "profiles": {
                "defaults": {},
                "list": [
                    {"guid": "{powershell-guid}", "name": "PowerShell"}
                ]
            }
        }
        with open(self.mock_settings, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        ok = ensure_windows_terminal_profile(app_dir=self.mock_app_dir)
        self.assertTrue(ok)

        with open(self.mock_settings, "r", encoding="utf-8") as f:
            data = json.load(f)

        profiles = data["profiles"]["list"]
        self.assertEqual(len(profiles), 2)
        tasks_p = next((p for p in profiles if p.get("guid") == TASKS_PROFILE_GUID), None)
        self.assertIsNotNone(tasks_p)
        self.assertEqual(tasks_p["name"], TASKS_PROFILE_NAME)
        self.assertEqual(tasks_p["commandline"], self.mock_exe)
        self.assertEqual(tasks_p["startingDirectory"], os.path.abspath(self.mock_app_dir))
        self.assertEqual(tasks_p["icon"], self.mock_icon)

    @patch("src.services.terminal_profile_service.find_windows_terminal_settings_file")
    def test_migrate_legacy_run_bat_commandline(self, mock_find):
        mock_find.return_value = self.mock_settings
        legacy_data = {
            "profiles": {
                "list": [
                    {
                        "guid": TASKS_PROFILE_GUID,
                        "name": "Tasks",
                        "commandline": r'cmd.exe /c "C:\Old\run.bat"',
                        "startingDirectory": r"C:\Old",
                        "icon": r"C:\Old\app_icon.png"
                    }
                ]
            }
        }
        with open(self.mock_settings, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        ok = ensure_windows_terminal_profile(app_dir=self.mock_app_dir)
        self.assertTrue(ok)

        with open(self.mock_settings, "r", encoding="utf-8") as f:
            data = json.load(f)

        profiles = data["profiles"]["list"]
        self.assertEqual(len(profiles), 1)
        tasks_p = profiles[0]
        self.assertEqual(tasks_p["commandline"], self.mock_exe)
        self.assertEqual(tasks_p["startingDirectory"], os.path.abspath(self.mock_app_dir))

    @patch("src.services.terminal_profile_service.find_windows_terminal_settings_file")
    def test_migrate_legacy_aufgaben_detector_name(self, mock_find):
        mock_find.return_value = self.mock_settings
        legacy_data = {
            "profiles": [
                {
                    "guid": "{old-guid}",
                    "name": "Aufgaben-Detector",
                    "commandline": r"cmd.exe /c run.bat",
                }
            ]
        }
        with open(self.mock_settings, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        ok = ensure_windows_terminal_profile(app_dir=self.mock_app_dir)
        self.assertTrue(ok)

        with open(self.mock_settings, "r", encoding="utf-8") as f:
            data = json.load(f)

        profiles = data["profiles"]
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["name"], TASKS_PROFILE_NAME)
        self.assertEqual(profiles[0]["guid"], TASKS_PROFILE_GUID)
        self.assertEqual(profiles[0]["commandline"], self.mock_exe)

    @patch("src.services.terminal_profile_service.find_windows_terminal_settings_file")
    def test_idempotency_does_not_duplicate(self, mock_find):
        mock_find.return_value = self.mock_settings
        with open(self.mock_settings, "w", encoding="utf-8") as f:
            json.dump({"profiles": {"list": []}}, f)

        ensure_windows_terminal_profile(app_dir=self.mock_app_dir)
        ensure_windows_terminal_profile(app_dir=self.mock_app_dir)
        ensure_windows_terminal_profile(app_dir=self.mock_app_dir)

        with open(self.mock_settings, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(len(data["profiles"]["list"]), 1)

    @patch("src.services.terminal_profile_service.find_windows_terminal_settings_file")
    def test_remove_profile(self, mock_find):
        mock_find.return_value = self.mock_settings
        with open(self.mock_settings, "w", encoding="utf-8") as f:
            json.dump({
                "profiles": {
                    "list": [
                        {"guid": TASKS_PROFILE_GUID, "name": "Tasks"},
                        {"guid": "{other}", "name": "cmd"}
                    ]
                }
            }, f)

        ok = remove_windows_terminal_profile()
        self.assertTrue(ok)

        with open(self.mock_settings, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(len(data["profiles"]["list"]), 1)
        self.assertEqual(data["profiles"]["list"][0]["name"], "cmd")

    @patch("src.services.terminal_profile_service.find_windows_terminal_settings_file")
    def test_get_status(self, mock_find):
        mock_find.return_value = self.mock_settings
        with open(self.mock_settings, "w", encoding="utf-8") as f:
            json.dump({
                "profiles": {
                    "list": [
                        {
                            "guid": TASKS_PROFILE_GUID,
                            "name": "Tasks",
                            "commandline": "Tasks.exe",
                            "startingDirectory": "C:\\Tasks",
                            "icon": "icon.png"
                        }
                    ]
                }
            }, f)

        status = get_windows_terminal_profile_status()
        self.assertTrue(status["installed"])
        self.assertTrue(status["configured"])
        self.assertEqual(status["commandline"], "Tasks.exe")


if __name__ == "__main__":
    unittest.main()
