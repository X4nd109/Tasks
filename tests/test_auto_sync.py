"""
test_auto_sync.py - Tests für das automatische Sync-Intervall.

Deckt Konfiguration, CLI (``tasks tray sync-interval`` / ``tasks tray status``),
das TUI-Einstellungsmodal sowie den Timer in ``TasksApp`` ab.
"""

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
    AUTO_SYNC_INTERVAL_KEY,
    AUTO_SYNC_INTERVALS,
    DEFAULT_AUTO_SYNC_INTERVAL,
    get_auto_sync_interval,
    get_auto_sync_interval_seconds,
    set_auto_sync_interval,
)
import src.core.config as core_config
from agent_cli import run_agent_cli
from src.ui.tui_app import TasksApp, TrayConfigModal


class AutoSyncConfigTest(unittest.TestCase):
    """Tests für Default, Validierung, Normalisierung und Sekunden-Umrechnung."""

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

    def test_config_intervals(self):
        # Default ohne Konfigurationsdatei
        self.assertEqual(get_auto_sync_interval(), DEFAULT_AUTO_SYNC_INTERVAL)
        self.assertEqual(DEFAULT_AUTO_SYNC_INTERVAL, "30min")

        # Alle gültigen Intervalle lassen sich speichern und wieder laden
        for interval in AUTO_SYNC_INTERVALS:
            self.assertTrue(set_auto_sync_interval(interval))
            self.assertEqual(get_auto_sync_interval(), interval)
            expected_seconds = {
                "5min": 300,
                "10min": 600,
                "30min": 1800,
                "1h": 3600,
                "never": 0,
            }[interval]
            self.assertEqual(get_auto_sync_interval_seconds(), expected_seconds)

        # Ungültige Werte werden abgelehnt und nicht gespeichert
        self.assertFalse(set_auto_sync_interval("2min"))
        self.assertFalse(set_auto_sync_interval(""))
        self.assertEqual(get_auto_sync_interval(), "never")

        # Normalisierung von Kurzformen und Synonymen
        aliases = {
            "5m": "5min",
            "10m": "10min",
            "30m": "30min",
            "1hour": "1h",
            "off": "never",
            "disabled": "never",
            "none": "never",
            "0": "never",
            " 10MIN  ": "10min",
        }
        for raw, expected in aliases.items():
            self.assertTrue(set_auto_sync_interval(raw), raw)
            self.assertEqual(get_auto_sync_interval(), expected)

        # Explizite und unbekannte Sekundenwerte
        self.assertEqual(get_auto_sync_interval_seconds("5min"), 300)
        self.assertEqual(get_auto_sync_interval_seconds("1h"), 3600)
        self.assertEqual(get_auto_sync_interval_seconds("never"), 0)
        self.assertEqual(get_auto_sync_interval_seconds("unknown"), 0)

        # Beide Konfigurationsdateien enthalten den Schlüssel
        for path in (self.app_cfg, self.ws_cfg):
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f)[AUTO_SYNC_INTERVAL_KEY], "10min")

    def test_constants_importable_from_both_modules(self):
        self.assertEqual(core_config.AUTO_SYNC_INTERVAL_KEY, AUTO_SYNC_INTERVAL_KEY)
        self.assertEqual(core_config.AUTO_SYNC_INTERVALS, AUTO_SYNC_INTERVALS)
        self.assertEqual(core_config.DEFAULT_AUTO_SYNC_INTERVAL, DEFAULT_AUTO_SYNC_INTERVAL)

        self.assertTrue(core_config.set_auto_sync_interval("10m"))
        self.assertEqual(core_config.get_auto_sync_interval(), "10min")
        self.assertEqual(core_config.get_auto_sync_interval_seconds(), 600)

    def test_invalid_config_value_falls_back_to_default(self):
        with open(self.app_cfg, "w", encoding="utf-8") as f:
            json.dump({AUTO_SYNC_INTERVAL_KEY: "invalid"}, f)
        self.assertEqual(get_auto_sync_interval(), DEFAULT_AUTO_SYNC_INTERVAL)


class AutoSyncCliTest(unittest.TestCase):
    """Tests für ``tasks tray sync-interval`` und die Statusausgabe."""

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

    def test_cli_sync_interval(self):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval", "10min"])
        self.assertEqual(ret, 0)
        self.assertIn("Auto-sync interval set to: 10min", out.getvalue())
        self.assertEqual(get_auto_sync_interval(), "10min")

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval", "off"])
        self.assertEqual(ret, 0)
        self.assertIn("Auto-sync interval set to: never", out.getvalue())
        self.assertEqual(get_auto_sync_interval(), "never")

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval", "2min"])
        self.assertEqual(ret, 1)
        self.assertIn("Invalid interval", out.getvalue())
        self.assertEqual(get_auto_sync_interval(), "never")

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval", "1h", "--json"])
        self.assertEqual(ret, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(payload["auto_sync_interval"], "1h")
        self.assertEqual(payload["seconds"], 3600)
        self.assertTrue(payload["success"])

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval", "bad", "--json"])
        self.assertEqual(ret, 1)
        payload = json.loads(out.getvalue().strip())
        self.assertIn("error", payload)

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval"])
        self.assertEqual(ret, 0)
        self.assertIn("Current auto-sync interval: 1h", out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            ret = run_agent_cli(["tray", "sync-interval", "--json"])
        self.assertEqual(ret, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(payload["auto_sync_interval"], "1h")
        self.assertEqual(payload["seconds"], 3600)

    def test_cli_tray_status(self):
        set_auto_sync_interval("10min")
        with patch("single_instance.send_instance_command", return_value=None), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            ret = run_agent_cli(["tray", "status"])
        self.assertEqual(ret, 0)
        self.assertIn("Auto-Sync Interval: 10min", out.getvalue())

        with patch("single_instance.send_instance_command", return_value=None), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            ret = run_agent_cli(["tray", "status", "--json"])
        self.assertEqual(ret, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertEqual(payload["auto_sync_interval"], "10min")
        self.assertEqual(payload["auto_sync_interval_seconds"], 600)


class AutoSyncTrayModalTest(unittest.IsolatedAsyncioTestCase):
    """Prüft das Select-Widget im ``TrayConfigModal`` inklusive Speichern."""

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

    async def test_tray_modal_select(self):
        set_auto_sync_interval("10min")
        app = TasksApp(MagicMock(), sync_on_startup=False)
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(TrayConfigModal())
            await pilot.pause()

            select = app.screen.query_one("#sel_auto_sync")
            self.assertEqual(select.value, "10min")
            self.assertEqual(select.id, "sel_auto_sync")

            # Auswahl ändern und speichern
            select.value = "1h"
            await pilot.pause()
            with patch("autostart_service.set_autostart"), patch(
                "src.services.autostart_service.set_autostart"
            ):
                await pilot.click("#btn_tray_cfg_save")
                await pilot.pause()

        self.assertEqual(get_auto_sync_interval(), "1h")


class AutoSyncAppTimerTest(unittest.TestCase):
    """Prüft ``TasksApp._check_auto_sync``."""

    def _app(self):
        app = TasksApp(MagicMock(), sync_on_startup=False)
        app._is_syncing = False
        return app

    def test_app_check_auto_sync(self):
        app = self._app()

        with patch("config.get_auto_sync_interval_seconds", return_value=300), patch(
            "config.is_shutting_down", return_value=False
        ), patch.object(app, "action_sync_tasks") as mock_sync:
            app._last_auto_sync_time = time.time() - 301
            app._check_auto_sync()
            mock_sync.assert_called_once()

        with patch("config.get_auto_sync_interval_seconds", return_value=300), patch(
            "config.is_shutting_down", return_value=False
        ), patch.object(app, "action_sync_tasks") as mock_sync:
            app._last_auto_sync_time = time.time() - 100
            app._check_auto_sync()
            mock_sync.assert_not_called()

        with patch("config.get_auto_sync_interval_seconds", return_value=0), patch(
            "config.is_shutting_down", return_value=False
        ), patch.object(app, "action_sync_tasks") as mock_sync:
            app._last_auto_sync_time = time.time() - 100000
            app._check_auto_sync()
            mock_sync.assert_not_called()

        app._is_syncing = True
        with patch("config.get_auto_sync_interval_seconds", return_value=300), patch(
            "config.is_shutting_down", return_value=False
        ), patch.object(app, "action_sync_tasks") as mock_sync:
            app._last_auto_sync_time = time.time() - 100000
            app._check_auto_sync()
            mock_sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
