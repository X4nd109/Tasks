"""
test_agent_cli.py - Unit-Tests für die Agent-CLI Schnittstelle.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
for _sub in [_SRC_DIR, os.path.join(_SRC_DIR, "core"), os.path.join(_SRC_DIR, "services"), os.path.join(_SRC_DIR, "ui")]:
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from agent_cli import (
    normalize_argv,
    is_agent_cli_command,
    run_agent_cli,
    resolve_task,
    format_task_list_text,
    format_task_list_json,
    format_task_detail_text,
    format_guide_text,
    save_last_cli_task_ids,
    load_last_cli_task_ids,
)
from models import Task
from task_manager import TaskManager


class TestAgentCLI(unittest.TestCase):
    def setUp(self):
        self.sample_task1 = Task(
            id="test_task_1",
            platform="moodle",
            course="AM",
            course_full="Angewandte Mathematik",
            title="Mathe Übungsblatt 1",
            due_date_str="Morgen 23:59",
            status="offen",
            status_display="Open",
            url="https://moodle.test/1",
            details_loaded=True,
            teacher="BIM"
        )
        self.sample_task2 = Task(
            id="test_task_2",
            platform="teams",
            course="SEW",
            course_full="Softwareentwicklung",
            title="Python Programmieren",
            due_date_str="15.10. 12:00",
            status="completed",
            status_display="Completed",
            url="https://teams.test/2",
            details_loaded=True,
            teacher="EIJ"
        )

    def test_normalize_argv(self):
        """Testet die Normalisierung verschiedener Schreibweisen und Flags."""
        self.assertEqual(normalize_argv(["-list"]), ["list"])
        self.assertEqual(normalize_argv(["--list"]), ["list"])
        self.assertEqual(normalize_argv(["-show", "1"]), ["show", "1"])
        self.assertEqual(normalize_argv(["--show", "test_id"]), ["show", "test_id"])
        self.assertEqual(normalize_argv(["-download", "1"]), ["download", "1"])
        self.assertEqual(normalize_argv(["--download", "2"]), ["download", "2"])
        self.assertEqual(normalize_argv(["-add", "--title", "A", "--subject", "B"]), ["add", "--title", "A", "--subject", "B"])
        self.assertEqual(normalize_argv(["-done", "1"]), ["done", "1"])
        self.assertEqual(normalize_argv(["--complete", "1"]), ["done", "1"])
        self.assertEqual(normalize_argv(["-delete", "1"]), ["delete", "1"])
        self.assertEqual(normalize_argv(["-restore", "1"]), ["restore", "1"])
        self.assertEqual(normalize_argv(["-sync"]), ["sync"])
        self.assertEqual(normalize_argv(["--guide"]), ["guide"])
        self.assertEqual(normalize_argv(["-h"]), ["guide"])
        self.assertEqual(normalize_argv(["--help"]), ["guide"])
        self.assertEqual(normalize_argv(["-skill"]), ["skill"])
        self.assertEqual(normalize_argv(["--skill"]), ["skill"])
        self.assertEqual(normalize_argv(["--json"]), ["list", "--json"])
        self.assertEqual(normalize_argv(["-json"]), ["list", "--json"])

    def test_is_agent_cli_command(self):
        """Testet die Erkennung von CLI-Befehlen."""
        self.assertTrue(is_agent_cli_command(["list"]))
        self.assertTrue(is_agent_cli_command(["-list"]))
        self.assertTrue(is_agent_cli_command(["--list"]))
        self.assertTrue(is_agent_cli_command(["show", "1"]))
        self.assertTrue(is_agent_cli_command(["-show", "1"]))
        self.assertTrue(is_agent_cli_command(["download", "1"]))
        self.assertTrue(is_agent_cli_command(["add"]))
        self.assertTrue(is_agent_cli_command(["done", "1"]))
        self.assertTrue(is_agent_cli_command(["delete", "1"]))
        self.assertTrue(is_agent_cli_command(["restore", "1"]))
        self.assertTrue(is_agent_cli_command(["sync"]))
        self.assertTrue(is_agent_cli_command(["guide"]))
        self.assertTrue(is_agent_cli_command(["--help"]))
        self.assertTrue(is_agent_cli_command(["-h"]))
        self.assertTrue(is_agent_cli_command(["skill"]))
        self.assertTrue(is_agent_cli_command(["-skill"]))
        self.assertTrue(is_agent_cli_command(["--skill"]))
        self.assertTrue(is_agent_cli_command(["--json"]))

        self.assertFalse(is_agent_cli_command([]))
        self.assertFalse(is_agent_cli_command(["--teams-login"]))
        self.assertFalse(is_agent_cli_command(["--moodle-login"]))
        self.assertFalse(is_agent_cli_command(["--untis-sync"]))

    def test_format_task_list_text(self):
        """Testet die kompakte Textausgabe der Aufgabenliste."""
        output = format_task_list_text([self.sample_task1], total_count=1, status_filter="open")
        self.assertIn("test_task_1", output)
        self.assertIn("AM", output)
        self.assertIn("Mathe Übungsblatt 1", output)
        self.assertIn("Listed 1 task(s)", output)

    def test_format_task_list_json(self):
        """Testet die strukturierte JSON-Ausgabe der Aufgabenliste."""
        output_str = format_task_list_json([self.sample_task1, self.sample_task2])
        data = json.loads(output_str)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], "test_task_1")
        self.assertEqual(data[0]["course"], "AM")
        self.assertEqual(data[1]["id"], "test_task_2")
        self.assertEqual(data[1]["status"], "completed")

    def test_format_task_detail_text(self):
        """Testet die Detailansicht als Text."""
        mock_mgr = MagicMock()
        output = format_task_detail_text(self.sample_task1, mock_mgr)
        self.assertIn("Title:       Mathe Übungsblatt 1", output)
        self.assertIn("ID:          test_task_1", output)
        self.assertIn("Subject:     AM (Angewandte Mathematik)", output)
        self.assertIn("Teacher:     BIM", output)

    def test_format_guide_text(self):
        """Testet, dass der Agent-Guide wichtige Befehle enthält."""
        guide = format_guide_text()
        self.assertIn("tasks list", guide)
        self.assertIn("tasks show", guide)
        self.assertIn("tasks download", guide)
        self.assertIn("tasks add", guide)
        self.assertIn("tasks done", guide)
        self.assertIn("tasks delete", guide)
        self.assertIn("tasks sync", guide)

    def test_last_cli_task_ids_cache(self):
        """Testet das Speichern und Laden der zuletzt aufgelisteten IDs."""
        test_ids = ["task_alpha", "task_beta", "task_gamma"]
        save_last_cli_task_ids(test_ids)
        loaded = load_last_cli_task_ids()
        self.assertEqual(loaded, test_ids)

    def test_resolve_task_by_id_and_index(self):
        """Testet das Auflösen einer Aufgabe per ID und per Index."""
        mock_mgr = MagicMock()
        mock_mgr.tasks = [self.sample_task1, self.sample_task2]
        mock_mgr.get_deleted_tasks.return_value = []
        mock_mgr.get_filtered_tasks.return_value = [self.sample_task1, self.sample_task2]

        save_last_cli_task_ids(["test_task_1", "test_task_2"])

        # 1. Per Index 1
        resolved_1 = resolve_task(mock_mgr, "1")
        self.assertIsNotNone(resolved_1)
        self.assertEqual(resolved_1.id, "test_task_1")

        # 2. Per Index 2
        resolved_2 = resolve_task(mock_mgr, "2")
        self.assertIsNotNone(resolved_2)
        self.assertEqual(resolved_2.id, "test_task_2")

        # 3. Per exakter ID
        resolved_id = resolve_task(mock_mgr, "test_task_1")
        self.assertEqual(resolved_id.id, "test_task_1")

        # 4. Per Präfix
        resolved_pre = resolve_task(mock_mgr, "test_task_2")
        self.assertEqual(resolved_pre.id, "test_task_2")

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_run_agent_cli_guide(self, mock_stdout):
        """Testet das Ausführen von `tasks guide`."""
        exit_code = run_agent_cli(["guide"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Agent CLI Reference", mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_run_agent_cli_add_and_validation(self, mock_stdout):
        """Testet das Hinzufügen einer Aufgabe und Validierung."""
        # Ohne Parameter -> Fehler
        exit_code_err = run_agent_cli(["add"])
        self.assertEqual(exit_code_err, 1)
        self.assertIn("Error: --title and --subject are required", mock_stdout.getvalue())

    def test_find_best_course_match(self):
        """Testet das Auffinden von Kursen per Fachkürzel und Name."""
        from agent_cli import find_best_course_match
        best, all_m = find_best_course_match("sesd")
        self.assertIsNotNone(best)
        self.assertEqual(best["subject"], "SESD")
        self.assertIn("11856", best["url"])

        # Unbekannter Kurs
        none_match, _ = find_best_course_match("unbekanntesfachxyz123")
        self.assertIsNone(none_match)

    @patch("config.load_full_school_config", return_value={"student_class": "3AHWII"})
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_run_agent_cli_courses(self, mock_stdout, mock_cfg):
        """Testet den `tasks courses` Befehl."""
        exit_code = run_agent_cli(["courses"])
        self.assertEqual(exit_code, 0)
        output = mock_stdout.getvalue()
        self.assertIn("PLATFORM", output)
        self.assertIn("SESD", output)

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_run_agent_cli_open_json(self, mock_stdout):
        """Testet `tasks open sesd --json --no-browse`."""
        exit_code = run_agent_cli(["open", "sesd", "--json", "--no-browse"])
        self.assertEqual(exit_code, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("subject"), "SESD")
        self.assertIn("moodle", data.get("platform"))
        self.assertIn("11856", data.get("url"))

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_run_agent_cli_open_flag_syntax(self, mock_stdout):
        """Testet die Flag-Syntax `-open sesd`."""
        exit_code = run_agent_cli(["-open", "sesd", "--no-browse"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Opening [Moodle]", mock_stdout.getvalue())
        self.assertIn("SESD", mock_stdout.getvalue())


    def test_run_agent_cli_skill_sync_and_status(self):
        """Testet 'tasks skill sync' und 'tasks skill status'."""
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Status vor der Installation (nicht installiert)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = run_agent_cli(["skill", "status", "--target", tmpdir, "--json"])
                self.assertEqual(exit_code, 0)
                data = json.loads(mock_stdout.getvalue())
                self.assertFalse(data.get("installed"))

            # 2. Installation / Sync
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = run_agent_cli(["skill", "sync", "--target", tmpdir, "--json"])
                self.assertEqual(exit_code, 0)
                data = json.loads(mock_stdout.getvalue())
                self.assertTrue(data.get("success"))
                self.assertTrue(os.path.exists(os.path.join(tmpdir, "SKILL.md")))

            # 3. Status nach Installation (installiert und in sync)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = run_agent_cli(["skill", "status", "--target", tmpdir, "--json"])
                self.assertEqual(exit_code, 0)
                data = json.loads(mock_stdout.getvalue())
                self.assertTrue(data.get("installed"))
                self.assertTrue(data.get("in_sync"))


    def test_is_agent_cli_command_update(self):
        """Testet die Erkennung von 'tasks update' und 'tasks reinstall'."""
        self.assertTrue(is_agent_cli_command(["update"]))
        self.assertTrue(is_agent_cli_command(["reinstall"]))
        self.assertTrue(is_agent_cli_command(["--update"]))
        self.assertTrue(is_agent_cli_command(["-reinstall"]))

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_run_agent_cli_update_help(self, mock_stdout):
        """Testet 'tasks update --help'."""
        code = run_agent_cli(["update", "--help"])
        self.assertEqual(code, 0)
        out = mock_stdout.getvalue()
        self.assertIn("Usage: tasks update", out)
        self.assertIn("--force", out)
        self.assertIn("--json", out)

    @patch("sys.stdout", new_callable=io.StringIO)
    @patch("src.services.update_service.check_for_updates")
    def test_run_agent_cli_update_up_to_date_json(self, mock_check, mock_stdout):
        """Testet 'tasks update --json' wenn kein Update vorliegt."""
        mock_check.return_value = None
        code = run_agent_cli(["update", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(mock_stdout.getvalue())
        self.assertFalse(data.get("update_available"))
        self.assertIn("already up to date", data.get("message", ""))

    @patch("sys.stdout", new_callable=io.StringIO)
    @patch("src.services.update_service.launch_update_and_restart")
    @patch("src.services.update_service.download_update_installer")
    @patch("src.services.update_service.check_for_updates")
    def test_run_agent_cli_update_force_flow(self, mock_check, mock_dl, mock_launch, mock_stdout):
        """Testet den vollen Durchlauf von 'tasks update --force'."""
        mock_check.return_value = {
            "current_version": "2.3.5",
            "latest_version": "2.3.5",
            "installer_url": "https://example.com/Tasks_Setup.exe",
            "installer_name": "Tasks_Setup.exe",
            "installer_size": 10485760,
        }
        mock_dl.return_value = True
        mock_launch.return_value = True

        code = run_agent_cli(["update", "--force"])
        self.assertEqual(code, 0)
        out = mock_stdout.getvalue()
        self.assertIn("Reinstalling v2.3.5", out)
        self.assertIn("Launching Tasks Update Manager", out)
        mock_dl.assert_called_once()
        mock_launch.assert_called_once()



    def test_normalize_skill_target_dir(self):
        """Verifies that normalize_skill_target_dir preserves paths containing 'tasks'
        and appends 'tasks' only when missing."""
        from agent_cli import normalize_skill_target_dir

        # Path lacking tasks
        p1 = normalize_skill_target_dir("C:/my/skills")
        self.assertTrue(p1.endswith("tasks"))

        # Paths containing tasks in various forms
        p2 = normalize_skill_target_dir("C:/my/Tasks App")
        self.assertTrue(p2.endswith("Tasks App"))

        p3 = normalize_skill_target_dir("C:/my/app_tasks")
        self.assertTrue(p3.endswith("app_tasks"))

        p4 = normalize_skill_target_dir("C:/my/TASKS - App")
        self.assertTrue(p4.endswith("TASKS - App"))

    def test_unlink_skill_and_cli_remove(self):
        """Tests unlinking/removing a configured skill both via function and CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, "tasks")
            os.makedirs(skill_dir, exist_ok=True)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write("# Tasks Skill")

            with patch("config.load_skill_target_dir", return_value=skill_dir),                  patch("config.clear_skill_target_dir") as mock_clear:
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    code = run_agent_cli(["skill", "remove", "--json"])
                    self.assertEqual(code, 0)
                    data = json.loads(mock_stdout.getvalue())
                    self.assertTrue(data.get("success"))
                    mock_clear.assert_called_once()
                    self.assertFalse(os.path.exists(skill_file))

    def test_move_skill_target_dir_and_cli_move(self):
        """Tests moving an installed skill to a new directory via CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = os.path.join(tmpdir, "old_tasks")
            new_dir = os.path.join(tmpdir, "new_location", "tasks")
            os.makedirs(old_dir, exist_ok=True)
            old_file = os.path.join(old_dir, "SKILL.md")
            with open(old_file, "w", encoding="utf-8") as f:
                f.write("# Old Skill")

            with patch("config.load_skill_target_dir", return_value=old_dir),                  patch("config.save_skill_target_dir") as mock_save,                  patch("agent_cli.sync_skill_to_dir", return_value=True):
                with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                    code = run_agent_cli(["skill", "move", new_dir, "--json"])
                    self.assertEqual(code, 0)
                    data = json.loads(mock_stdout.getvalue())
                    self.assertTrue(data.get("success"))
                    mock_save.assert_called_once_with(os.path.normpath(os.path.abspath(new_dir)))
                    # Old file removed
                    self.assertFalse(os.path.exists(old_file))


if __name__ == "__main__":
    unittest.main()
