"""
test_skill_auto_sync.py - Tests für das flexible AI-Agent-Skill-Zielverzeichnis
sowie die automatische Skill-Aktualisierung nach App-Updates.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
for _sub in [_SRC_DIR, os.path.join(_SRC_DIR, "core"), os.path.join(_SRC_DIR, "services"), os.path.join(_SRC_DIR, "ui")]:
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

import config
from agent_cli import (
    normalize_argv,
    run_agent_cli,
    sync_skill_to_dir,
    resolve_skill_source_file,
)
from task_manager import TaskManager


class SkillTargetDirConfigTest(unittest.TestCase):
    """Tests für load_skill_target_dir / save_skill_target_dir / is_skill_synced."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app_cfg = os.path.join(self.tmp, "tasks_config.json")
        self.ws_cfg = os.path.join(self.tmp, "config.json")
        self._patches = [
            patch("config.APP_CONFIG_FILE", self.app_cfg),
            patch("config.CONFIG_FILE", self.ws_cfg),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_is_none(self):
        self.assertIsNone(config.load_skill_target_dir())
        self.assertFalse(config.is_skill_synced())

    def test_save_and_load_roundtrip(self):
        target = os.path.join(self.tmp, "agent-skills")
        config.save_skill_target_dir(f"  {target}  ")
        self.assertEqual(config.load_skill_target_dir(), target)
        with open(self.app_cfg, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["skill_target_dir"], target)

    def test_save_writes_existing_workspace_config(self):
        with open(self.ws_cfg, "w", encoding="utf-8") as f:
            json.dump({"theme": "nord"}, f)
        target = os.path.join(self.tmp, "agent-skills")
        config.save_skill_target_dir(target)
        with open(self.ws_cfg, "r", encoding="utf-8") as f:
            ws_data = json.load(f)
        self.assertEqual(ws_data["skill_target_dir"], target)
        self.assertEqual(ws_data["theme"], "nord")

    def test_is_skill_synced_requires_skill_md(self):
        target = os.path.join(self.tmp, "agent-skills")
        os.makedirs(target, exist_ok=True)
        config.save_skill_target_dir(target)
        self.assertFalse(config.is_skill_synced())

        with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Tasks Skill\n")
        self.assertTrue(config.is_skill_synced())

        os.remove(os.path.join(target, "SKILL.md"))
        self.assertFalse(config.is_skill_synced())


class SkillCliSetDirTest(unittest.TestCase):
    """Tests für `tasks skill set-dir`, `sync` mit gespeichertem Ziel und Abbruch."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.app_cfg = os.path.join(self.tmp, "tasks_config.json")
        self.ws_cfg = os.path.join(self.tmp, "config.json")
        self.target = os.path.join(self.tmp, "selected-skill-dir")
        self._patches = [
            patch("config.APP_CONFIG_FILE", self.app_cfg),
            patch("config.CONFIG_FILE", self.ws_cfg),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _configured_dir(self):
        with open(self.app_cfg, "r", encoding="utf-8") as f:
            return json.load(f).get("skill_target_dir")

    def test_set_dir_with_path_argument(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = run_agent_cli(["skill", "set-dir", self.target, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("target_dir"), os.path.abspath(self.target))
        self.assertTrue(os.path.exists(os.path.join(self.target, "SKILL.md")))
        self.assertEqual(self._configured_dir(), os.path.abspath(self.target))
        self.assertTrue(config.is_skill_synced())

    def test_set_dir_alias_via_flag(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = run_agent_cli(["skill", "--set-dir", self.target, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertTrue(data.get("success"))
        self.assertEqual(self._configured_dir(), os.path.abspath(self.target))
        self.assertTrue(os.path.exists(os.path.join(self.target, "SKILL.md")))

    def test_sync_uses_saved_directory_without_prompt(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(run_agent_cli(["skill", "set-dir", self.target]), 0)
        # Simulieren, dass die installierte Datei veraltet ist
        with open(os.path.join(self.target, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("old content")

        with patch("builtins.input") as mock_input, \
             patch("win_dialogs.pick_directory") as mock_pick, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = run_agent_cli(["skill", "sync", "--json"])

        self.assertEqual(code, 0)
        mock_input.assert_not_called()
        mock_pick.assert_not_called()
        data = json.loads(mock_stdout.getvalue())
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("target_dir"), os.path.abspath(self.target))
        source = resolve_skill_source_file()
        with open(source, "r", encoding="utf-8") as f_s, open(os.path.join(self.target, "SKILL.md"), "r", encoding="utf-8") as f_t:
            self.assertEqual(f_s.read(), f_t.read())

    def test_set_dir_cancelled_by_picker_none(self):
        with patch("builtins.input", return_value=""), \
             patch("win_dialogs.pick_directory", return_value=None), \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = run_agent_cli(["skill", "set-dir"])

        self.assertEqual(code, 0)
        self.assertIn("Operation cancelled. No folder selected.", mock_stdout.getvalue())
        self.assertIsNone(config.load_skill_target_dir())
        self.assertFalse(os.path.exists(self.target))

    def test_set_dir_interactive_success(self):
        with patch("builtins.input", return_value=""), \
             patch("win_dialogs.pick_directory", return_value=self.target) as mock_pick, \
             patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = run_agent_cli(["skill", "set-dir"])

        self.assertEqual(code, 0)
        mock_pick.assert_called_once_with(dialog_title="Select Tasks Skill Directory")
        self.assertIn("Press [ENTER] to open the folder picker", mock_stdout.getvalue())
        self.assertEqual(self._configured_dir(), os.path.abspath(self.target))
        self.assertTrue(os.path.exists(os.path.join(self.target, "SKILL.md")))

    def test_sync_first_time_prompts_and_saves(self):
        with patch("builtins.input", return_value=""), \
             patch("win_dialogs.pick_directory", return_value=self.target), \
             patch("sys.stdout", new_callable=io.StringIO):
            code = run_agent_cli(["skill", "sync"])

        self.assertEqual(code, 0)
        self.assertEqual(self._configured_dir(), os.path.abspath(self.target))
        self.assertTrue(config.is_skill_synced())

    def test_status_reports_configured_dir(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            run_agent_cli(["skill", "set-dir", self.target])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = run_agent_cli(["skill", "status", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertEqual(data.get("configured_dir"), os.path.abspath(self.target))
        self.assertTrue(data.get("installed"))
        self.assertTrue(data.get("in_sync"))
        self.assertTrue(data.get("synced"))

    def test_normalize_argv_set_dir_flag(self):
        self.assertEqual(normalize_argv(["--set-dir", "C:\\skills"]), ["skill", "--set-dir", "C:\\skills"])
        self.assertEqual(normalize_argv(["-set-dir"]), ["skill", "--set-dir"])

    def test_sync_skill_to_dir_copies_companion_files(self):
        src_dir = os.path.join(self.tmp, "src-skill")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Skill\n")
        with open(os.path.join(src_dir, "helper.md"), "w", encoding="utf-8") as f:
            f.write("helper\n")
        os.makedirs(os.path.join(src_dir, "assets"))
        with open(os.path.join(src_dir, "assets", "icon.txt"), "w", encoding="utf-8") as f:
            f.write("icon\n")

        dest = os.path.join(self.tmp, "dest-skill")
        ok = sync_skill_to_dir(dest, source_file=os.path.join(src_dir, "SKILL.md"))
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(os.path.join(dest, "SKILL.md")))
        self.assertTrue(os.path.exists(os.path.join(dest, "helper.md")))
        self.assertTrue(os.path.exists(os.path.join(dest, "assets", "icon.txt")))

    def test_sync_skill_to_dir_invalid_source(self):
        self.assertFalse(sync_skill_to_dir(os.path.join(self.tmp, "dest"), source_file=os.path.join(self.tmp, "missing.md")))


class TaskManagerAutoSyncTest(unittest.TestCase):
    """Testet die automatische Skill-Aktualisierung nach einem App-Update."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cache_dir = os.path.join(self.tmp, "cache")
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        # Alte Version simulieren -> is_update == True
        with open(os.path.join(self.cache_dir, "last_version.txt"), "w", encoding="utf-8") as f:
            f.write("0.0.1")
        self.skill_dir = os.path.join(self.tmp, "skill-target")
        os.makedirs(self.skill_dir, exist_ok=True)
        with open(os.path.join(self.skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# old skill\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_persistence(self):
        """Isoliert alle Dateipfade, damit keine echten Benutzerdaten verändert werden."""
        patches = [
            patch("config.CONFIG_DIR", self.cache_dir),
            patch("config.DATA_DIR", self.data_dir),
            patch("config.APP_VERSION", "9.9.9"),
            patch("task_manager.CACHE_FILE", os.path.join(self.cache_dir, "tasks_cache.json")),
            patch("task_manager.CUSTOM_TASKS_FILE", os.path.join(self.data_dir, "custom_tasks.json")),
            patch("task_manager.APP_CUSTOM_TASKS_FILE", os.path.join(self.cache_dir, "tasks_custom_tasks.json")),
            patch("task_manager.DELETED_TASKS_FILE", os.path.join(self.data_dir, "deleted_tasks.json")),
            patch("task_manager.APP_DELETED_TASKS_FILE", os.path.join(self.cache_dir, "tasks_deleted_tasks.json")),
            patch("task_manager.DELETED_MANUAL_TASKS_FILE", os.path.join(self.data_dir, "deleted_manual_tasks.json")),
            patch("task_manager.APP_DELETED_MANUAL_TASKS_FILE", os.path.join(self.cache_dir, "tasks_deleted_manual_tasks.json")),
            patch("task_manager.HIDDEN_TASKS_FILE", os.path.join(self.data_dir, "hidden_tasks.json")),
            patch("task_manager.APP_HIDDEN_TASKS_FILE", os.path.join(self.cache_dir, "tasks_hidden_tasks.json")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_auto_sync_when_update_detected(self):
        self._patch_persistence()
        with patch("config.is_skill_synced", return_value=True), \
             patch("config.load_skill_target_dir", return_value=self.skill_dir), \
             patch("agent_cli.sync_skill_to_dir", return_value=True) as mock_sync, \
             patch("task_manager.logger") as mock_logger:
            TaskManager(autostart_prefetch=False)
            mock_sync.assert_called_once_with(self.skill_dir)
            mock_logger.info.assert_any_call("Tasks skill automatically updated at: %s", self.skill_dir)

    def test_no_auto_sync_when_skill_not_configured(self):
        self._patch_persistence()
        with patch("config.is_skill_synced", return_value=False), \
             patch("agent_cli.sync_skill_to_dir", return_value=True) as mock_sync:
            TaskManager(autostart_prefetch=False)
        mock_sync.assert_not_called()

    def test_real_sync_updates_installed_skill(self):
        """End-to-End: Bei Update wird die SKILL.md im konfigurierten Ordner aktualisiert."""
        self._patch_persistence()
        with patch("config.is_skill_synced", return_value=True), \
             patch("config.load_skill_target_dir", return_value=self.skill_dir):
            TaskManager(autostart_prefetch=False)

        source = resolve_skill_source_file()
        with open(source, "r", encoding="utf-8") as f_s, open(os.path.join(self.skill_dir, "SKILL.md"), "r", encoding="utf-8") as f_t:
            self.assertEqual(f_s.read(), f_t.read())


if __name__ == "__main__":
    unittest.main()
