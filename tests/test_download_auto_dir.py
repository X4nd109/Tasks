"""
test_download_auto_dir.py - Unit tests for smart download auto-directory matching,
DownloadLocationModal (with English labels & hotkeys 1, 2, 3), and CLI --auto-dir flag.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
for _sub in [_SRC_DIR, os.path.join(_SRC_DIR, "core"), os.path.join(_SRC_DIR, "services"), os.path.join(_SRC_DIR, "ui")]:
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

from models import Task, TaskAttachment
import directory_service
from directory_service import DirectoryService
sys.modules['services.directory_service'] = directory_service
from agent_cli import run_agent_cli, is_agent_cli_command
from tui_app import DownloadLocationModal, TaskDetailModal


class TestDownloadAutoDir(unittest.TestCase):

    def setUp(self):
        self.sample_task = Task(
            id="test_task_bet_1",
            platform="moodle",
            course="BET",
            course_full="Biomedizinische Technik",
            title="Laborbericht 01: EKG Sensorik",
            due_date_str="Montag, 27. Okt., 23:59",
            status="offen",
            status_display="Noch offen",
            url="https://moodle.spengergasse.at/mod/assign/view.php?id=9999",
            teacher="KRD",
            description="Messung der Herzströme mit AD8232.",
            attachments=[
                TaskAttachment(name="schaltplan.pdf", url="https://moodle.spengergasse.at/pdf1"),
            ],
            details_loaded=True,
        )

    def test_directory_service_matching(self):
        fake_dirs = [
            {"id": "dir_1", "title": "BET", "path": r"C:\School\3. Klasse\BET"},
            {"id": "dir_2", "title": "Softwareentwicklung", "path": r"C:\School\3. Klasse\SWP"},
            {"id": "dir_3", "title": "Netzwerktechnik", "path": r"C:\School\3. Klasse\NWES"},
        ]

        with patch.object(DirectoryService, "load_directories", return_value=fake_dirs):
            # 1. Exact match on title ("BET")
            m1 = DirectoryService.find_matching_directory_for_course("BET", "Biomedizinische Technik")
            self.assertIsNotNone(m1)
            self.assertEqual(m1["title"], "BET")

            # 2. Match on course code in path basename ("SWP")
            m2 = DirectoryService.find_matching_directory_for_course("SWP", "Softwareentwicklung")
            self.assertIsNotNone(m2)
            self.assertEqual(m2["title"], "Softwareentwicklung")

            # 3. Match on full title
            m3 = DirectoryService.find_matching_directory_for_course("SEW", "Softwareentwicklung")
            self.assertIsNotNone(m3)
            self.assertEqual(m3["title"], "Softwareentwicklung")

            # 4. No match for unknown course
            m4 = DirectoryService.find_matching_directory_for_course("CH", "Chemie")
            self.assertIsNone(m4)

            # 5. Empty inputs
            self.assertIsNone(DirectoryService.find_matching_directory_for_course(None, None))
            self.assertIsNone(DirectoryService.find_matching_directory_for_course("", ""))

    def test_download_location_modal_with_match(self):
        fake_dirs = [
            {"id": "dir_1", "title": "BET", "path": r"C:\School\3. Klasse\BET"},
        ]
        with patch.object(DirectoryService, "load_directories", return_value=fake_dirs):
            modal = DownloadLocationModal(self.sample_task)
            self.assertIsNotNone(modal.matched_dir)
            self.assertEqual(modal.matched_dir["title"], "BET")

            # Check bindings: 1, 2, 3, escape
            binding_keys = [b.key for b in modal.BINDINGS]
            self.assertIn("1", binding_keys)
            self.assertIn("2", binding_keys)
            self.assertIn("3", binding_keys)
            self.assertIn("escape", binding_keys)

            # Test dismiss actions
            modal.dismiss = MagicMock()
            modal.action_choose_auto()
            modal.dismiss.assert_called_with("auto")

            modal.action_choose_manual()
            modal.dismiss.assert_called_with("manual")

            modal.action_choose_downloads()
            modal.dismiss.assert_called_with("downloads")

            modal.action_cancel()
            modal.dismiss.assert_called_with(None)

    def test_download_location_modal_without_match(self):
        with patch.object(DirectoryService, "load_directories", return_value=[]):
            modal = DownloadLocationModal(self.sample_task)
            self.assertIsNone(modal.matched_dir)

            modal.dismiss = MagicMock()
            # If no matched dir, action_choose_auto must not dismiss
            modal.action_choose_auto()
            modal.dismiss.assert_not_called()

            # Manual and downloads still work
            modal.action_choose_manual()
            modal.dismiss.assert_called_with("manual")

    def test_task_detail_modal_no_agent_button(self):
        mgr = MagicMock()
        modal = TaskDetailModal(self.sample_task, mgr)
        binding_keys = [b.key for b in modal.BINDINGS]
        # Agent key 'g' should no longer be present
        self.assertNotIn("g", binding_keys)
        # Download key 'd' must be present
        self.assertIn("d", binding_keys)

    def test_agent_command_removed_from_cli(self):
        self.assertFalse(is_agent_cli_command(["agent", "1"]))
        self.assertFalse(is_agent_cli_command(["ai-agent", "1"]))
        self.assertFalse(is_agent_cli_command(["--agent", "1"]))

    @patch("task_manager.TaskManager.download_task_files")
    @patch("agent_cli.resolve_task")
    def test_cli_download_auto_dir_success(self, mock_resolve, mock_dl):
        mock_resolve.return_value = self.sample_task
        mock_dl.return_value = ["schaltplan.pdf"]
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_dirs = [
                {"id": "dir_bet", "title": "BET", "path": tmpdir},
            ]
            with patch.object(DirectoryService, "load_directories", return_value=fake_dirs):
                out = io.StringIO()
                with redirect_stdout(out):
                    ret = run_agent_cli(["download", "1", "--auto-dir", "--json"])
                self.assertEqual(ret, 0)
                data = json.loads(out.getvalue())
                self.assertTrue(data.get("success"))
                self.assertIn("folder", data)
                self.assertTrue(data["folder"].startswith(tmpdir))

    @patch("agent_cli.resolve_task")
    def test_cli_download_auto_dir_no_match(self, mock_resolve):
        mock_resolve.return_value = self.sample_task
        with patch.object(DirectoryService, "load_directories", return_value=[]):
            out = io.StringIO()
            with redirect_stdout(out):
                ret = run_agent_cli(["download", "1", "--auto-dir", "--json"])
            self.assertEqual(ret, 1)
            data = json.loads(out.getvalue())
            self.assertIn("error", data)
            self.assertIn("No linked directory found", data["error"])


if __name__ == "__main__":
    unittest.main()
