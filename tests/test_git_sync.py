import os
import sys
import unittest

# Projekt-Pfade einbinden
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "core")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "services")))

from git_sync_service import (
    mask_git_url,
    build_authenticated_url,
    merge_custom_tasks,
    merge_custom_exams,
    merge_exam_notes,
    merge_deleted_tasks,
    merge_config_files,
)


class TestGitSyncService(unittest.TestCase):

    def test_mask_git_url(self):
        url1 = "https://ghp_secretToken123@github.com/user/repo.git"
        masked1 = mask_git_url(url1)
        self.assertNotIn("ghp_secretToken123", masked1)
        self.assertEqual(masked1, "https://***@github.com/user/repo.git")

        url2 = "https://user:password123@gitlab.com/group/repo.git"
        masked2 = mask_git_url(url2)
        self.assertNotIn("password123", masked2)
        self.assertEqual(masked2, "https://***@gitlab.com/group/repo.git")

        url3 = "https://github.com/user/repo.git"
        self.assertEqual(mask_git_url(url3), url3)

    def test_build_authenticated_url(self):
        repo_url = "https://github.com/user/my-repo.git"
        token = "ghp_1234567890abcdef"
        auth_url = build_authenticated_url(repo_url, token)
        self.assertEqual(auth_url, "https://ghp_1234567890abcdef@github.com/user/my-repo.git")

        # Wenn Token bereits enthalten ist, wird es ersetzt
        old_auth_url = "https://old_token@github.com/user/my-repo.git"
        new_auth_url = build_authenticated_url(old_auth_url, "new_token")
        self.assertEqual(new_auth_url, "https://new_token@github.com/user/my-repo.git")

        # Ohne Token bleibt die URL unverändert
        self.assertEqual(build_authenticated_url(repo_url, ""), repo_url)

    def test_merge_custom_tasks(self):
        local_tasks = [
            {
                "id": "task_1",
                "title": "Lokale Aufgabe 1",
                "status": "offen",
                "due_timestamp": 1000.0,
            },
            {
                "id": "task_conflict",
                "title": "Aufgabe in beiden",
                "status": "offen",
                "due_timestamp": 2000.0,
            },
        ]
        remote_tasks = [
            {
                "id": "task_2",
                "title": "Remote Aufgabe 2",
                "status": "offen",
                "due_timestamp": 1500.0,
            },
            {
                "id": "task_conflict",
                "title": "Aufgabe in beiden (auf Laptop erledigt)",
                "status": "erledigt",
                "due_timestamp": 2000.0,
            },
        ]

        merged = merge_custom_tasks(local_tasks, remote_tasks)
        ids = [t["id"] for t in merged]
        self.assertIn("task_1", ids)
        self.assertIn("task_2", ids)
        self.assertIn("task_conflict", ids)
        self.assertEqual(len(merged), 3)

        # Konfliktprüfung: Remote 'erledigt' muss gegenüber lokal 'offen' bevorzugt werden
        conflict_task = next(t for t in merged if t["id"] == "task_conflict")
        self.assertEqual(conflict_task["status"], "erledigt")

    def test_merge_custom_exams(self):
        local_exams = [
            {"id": "exam_1", "subject": "AMEC", "custom_topics": "Kapitel 1"},
            {"id": "exam_conflict", "subject": "E", "custom_topics": "Kurz"},
        ]
        remote_exams = [
            {"id": "exam_2", "subject": "POS", "custom_topics": "Python"},
            {"id": "exam_conflict", "subject": "E", "custom_topics": "Sehr ausführlicher Lernstoff"},
        ]

        merged = merge_custom_exams(local_exams, remote_exams)
        self.assertEqual(len(merged), 3)
        conflict_exam = next(e for e in merged if e["id"] == "exam_conflict")
        self.assertEqual(conflict_exam["custom_topics"], "Sehr ausführlicher Lernstoff")

    def test_merge_exam_notes(self):
        local_notes = {
            "exam_1": "Notiz 1",
            "exam_2": "",
        }
        remote_notes = {
            "exam_2": "Wichtige Notiz von Laptop",
            "exam_3": "Notiz 3",
        }
        merged = merge_exam_notes(local_notes, remote_notes)
        self.assertEqual(merged["exam_1"], "Notiz 1")
        self.assertEqual(merged["exam_2"], "Wichtige Notiz von Laptop")
        self.assertEqual(merged["exam_3"], "Notiz 3")

    def test_merge_deleted_tasks(self):
        local_del = ["task_a", "task_b"]
        remote_del = ["task_b", "task_c"]
        merged = merge_deleted_tasks(local_del, remote_del)
        self.assertEqual(sorted(merged), ["task_a", "task_b", "task_c"])

    def test_merge_config_files(self):
        local_cfg = {
            "theme": "nord",
            "untis_group": "3ahwii-old",
            "untis_school": "spengergasse-old",
            "student_name": "Old Name",
            "student_class": "2AHWII",
            "favorite_themes": ["nord", "dracula"],
            "excuse_profile": {
                "student_name": "Max",
                "student_class": "1AHIT",
                "school_address": "Spengergasse 20",
            },
        }
        remote_cfg = {
            "theme": "catppuccin",
            "untis_school": "spengergasse",
            "untis_group": "3ahwii",
            "student_name": "Alexander New",
            "student_class": "3AHWII",
            "favorite_themes": ["nord", "gruvbox"],
            "excuse_profile": {
                "student_name": "Alexander New",
                "teacher_name": "Prof. Erika",
                "school_district": "1050 Wien",
            },
        }
        merged = merge_config_files(local_cfg, remote_cfg)
        self.assertEqual(merged["theme"], "catppuccin")  # Remote Theme synchronisiert
        self.assertEqual(merged["untis_school"], "spengergasse")  # Remote Schulname synchronisiert
        self.assertEqual(merged["untis_group"], "3ahwii")  # Remote Klasse synchronisiert
        self.assertEqual(merged["student_name"], "Alexander New")  # Remote Schülername synchronisiert
        self.assertEqual(merged["student_class"], "3AHWII")
        self.assertEqual(merged["favorite_themes"], ["nord", "dracula", "gruvbox"])  # Favoriten gemerged
        self.assertEqual(merged["excuse_profile"]["student_name"], "Alexander New")
        self.assertEqual(merged["excuse_profile"]["teacher_name"], "Prof. Erika")
        self.assertEqual(merged["excuse_profile"]["school_address"], "Spengergasse 20")
        self.assertEqual(merged["excuse_profile"]["school_district"], "1050 Wien")

    def test_login_choice_modal_has_git(self):
        from tui_app import LoginChoiceModal
        modal = LoginChoiceModal()
        binding_keys = [b.key for b in modal.BINDINGS]
        self.assertIn("4", binding_keys)
        self.assertIn("g", binding_keys)

    def test_git_setup_modal_structure(self):
        from tui_app import GitSetupModal
        modal = GitSetupModal()
        self.assertTrue(hasattr(modal, "compose"))
        self.assertTrue(hasattr(modal, "_save_and_sync"))
        self.assertTrue(hasattr(modal, "_disconnect_git"))
        self.assertIn("#git_setup_guide_link", modal.DEFAULT_CSS)

    def test_theme_select_modal(self):
        from tui_app import ThemeSelectModal
        modal = ThemeSelectModal(current_theme="catppuccin-mocha")
        self.assertTrue(hasattr(modal, "compose"))
        binding_keys = [b.key for b in modal.BINDINGS]
        for num in ["1", "2", "3", "4", "5", "escape"]:
            self.assertIn(num, binding_keys)

        dismissed = []
        modal.dismiss = lambda res=None: dismissed.append(res)
        modal.action_choose_dracula()
        self.assertEqual(dismissed[-1], "dracula")
        modal.action_choose_tokyo_night()
        self.assertEqual(dismissed[-1], "tokyo-night")
        modal.action_cancel()
        self.assertIsNone(dismissed[-1])

    def test_theme_change_triggers_git_push(self):
        from unittest.mock import patch
        from config import save_saved_theme, load_saved_theme
        from git_sync_service import GitSyncService

        # Setze Ausgangszustand
        save_saved_theme("nord")
        self.assertEqual(load_saved_theme(), "nord")

        # Mit Mock prüfen, ob GitSyncService.async_push aufgerufen wird
        with patch.object(GitSyncService, "async_push") as mock_push:
            with patch("git_sync_service.is_git_configured", return_value=True):
                # Wechsle auf 'dracula'
                save_saved_theme("dracula")
                self.assertEqual(load_saved_theme(), "dracula")
                mock_push.assert_called_with("Update theme: dracula")

                mock_push.reset_mock()
                # Erneutes Setzen des gleichen Themes darf keinen Push auslösen
                save_saved_theme("dracula")
                mock_push.assert_not_called()

                # Wechsle zurück auf 'catppuccin-mocha'
                save_saved_theme("catppuccin-mocha")
                self.assertEqual(load_saved_theme(), "catppuccin-mocha")
                mock_push.assert_called_with("Update theme: catppuccin-mocha")

    def test_favorite_themes_change_triggers_git_push(self):
        from unittest.mock import patch
        from config import save_favorite_themes, load_favorite_themes
        from git_sync_service import GitSyncService

        save_favorite_themes(["nord"])
        with patch.object(GitSyncService, "async_push") as mock_push:
            with patch("git_sync_service.is_git_configured", return_value=True):
                # Favoriten ändern
                save_favorite_themes(["nord", "gruvbox"])
                mock_push.assert_called_with("Update favorite themes")

                # Gleiche Favoriten erneut speichern darf keinen Push auslösen
                mock_push.reset_mock()
                save_favorite_themes(["nord", "gruvbox"])
                mock_push.assert_not_called()

    def test_school_and_student_config_triggers_git_push(self):
        from unittest.mock import patch
        from config import save_full_school_config, load_full_school_config
        from git_sync_service import GitSyncService

        sample_profile = {
            "student_name": "Test Student",
            "student_class": "3AHWII",
            "untis_group": "X",
            "untis_school": "spengergasse",
            "teacher_name": "Prof. Test",
            "school_address": "Spengergasse 20",
            "school_district": "1050 Wien",
        }

        with patch.object(GitSyncService, "async_push") as mock_push:
            with patch("git_sync_service.is_git_configured", return_value=True):
                save_full_school_config(sample_profile)
                mock_push.assert_called_with("Update student & school config")
                
                loaded = load_full_school_config()
                self.assertEqual(loaded["student_name"], "Test Student")
                self.assertEqual(loaded["student_class"], "3AHWII")
                self.assertEqual(loaded["untis_school"], "spengergasse")

    def test_pull_and_sync_does_not_push(self):
        from unittest.mock import patch
        from git_sync_service import GitSyncService

        mock_config = {
            "enabled": True,
            "repo_url": "https://github.com/test/repo.git",
            "token": "tok123",
            "branch": "main",
        }

        with patch("git_sync_service.get_git_sync_config", return_value=mock_config):
            with patch("git_sync_service.is_valid_git_repo", return_value=True):
                with patch("git_sync_service.GitSyncService.push_changes"):
                    with patch("git_sync_service.GitSyncService.async_push"):
                        with patch("git_sync_service._run_git_cmd") as mock_git:
                            # Mock successful git fetch, merge abort, reset --hard, clean
                            mock_git.return_value = (True, "", "")
                            with patch("os.path.exists", return_value=False):
                                with patch("git_sync_service.save_git_sync_config"):
                                    ok, msg, has_updates = GitSyncService.pull_and_sync()

                    self.assertTrue(ok)
                    # Überprüfe, dass git push NIEMALS in pull_and_sync aufgerufen wird
                    called_cmds = [call[0][0] for call in mock_git.call_args_list]
                    for cmd in called_cmds:
                        self.assertNotIn("push", cmd, f"Git push was unexpectedly called during pull_and_sync: {cmd}")
                        self.assertNotIn("commit", cmd, f"Git commit was unexpectedly called during pull_and_sync: {cmd}")

    def test_push_changes_commits_and_pushes(self):
        from unittest.mock import patch
        from git_sync_service import GitSyncService

        mock_config = {
            "enabled": True,
            "repo_url": "https://github.com/test/repo.git",
            "token": "tok123",
            "branch": "main",
        }

        with patch("git_sync_service.get_git_sync_config", return_value=mock_config):
            with patch("git_sync_service.is_valid_git_repo", return_value=True):
                with patch("git_sync_service._run_git_cmd") as mock_git:
                    # Side effect für _run_git_cmd: status meldet Änderung 'M config.json'
                    def git_side_effect(cmd, **kwargs):
                        if "status" in cmd:
                            return (True, "M config.json", "")
                        if "rev-list" in cmd:
                            return (True, "1", "")
                        return (True, "", "")

                    mock_git.side_effect = git_side_effect
                    with patch("git_sync_service.save_git_sync_config"):
                        ok, msg = GitSyncService.push_changes("Test Commit")

                    self.assertTrue(ok)
                    called_cmds = [call[0][0] for call in mock_git.call_args_list]
                    has_commit = any("commit" in cmd for cmd in called_cmds)
                    has_push = any("push" in cmd for cmd in called_cmds)
                    self.assertTrue(has_commit, "Git commit should be called in push_changes")
                    self.assertTrue(has_push, "Git push should be called in push_changes")

    def test_setup_repository_completes_without_deadlock(self):
        from unittest.mock import patch
        from git_sync_service import GitSyncService

        with patch("git_sync_service.is_git_available", return_value=True):
            with patch.object(GitSyncService, "test_connection", return_value=(True, "OK")):
                with patch("git_sync_service.is_valid_git_repo", return_value=False):
                    with patch("git_sync_service._run_git_cmd") as mock_git:
                        # ls-remote returns a branch
                        mock_git.return_value = (True, "hash refs/heads/main", "")
                        with patch("git_sync_service._safe_rmtree"):
                            with patch("os.makedirs"):
                                with patch("os.path.exists", return_value=True):
                                    with patch("os.rename"):
                                        with patch("git_sync_service.save_git_sync_config"):
                                            with patch.object(GitSyncService, "pull_and_sync", return_value=(True, "Pulled", False)) as mock_pull:
                                                with patch.object(GitSyncService, "push_changes", return_value=(True, "Pushed")) as mock_push:
                                                    ok, msg = GitSyncService.setup_repository(
                                                        repo_url="https://github.com/user/repo.git",
                                                        token="test_token",
                                                        branch="main",
                                                    )
                                                    self.assertTrue(ok)
                                                    self.assertIn("successfully", msg.lower())
                                                    mock_pull.assert_called_once()
                                                    mock_push.assert_called_once()

    def test_merge_custom_tasks_respects_deleted_ids(self):
        local_tasks = [
            {"id": "t1", "title": "Aufgabe 1", "status": "offen"},
            {"id": "t_del", "title": "Geloeschte Aufgabe", "status": "offen"},
        ]
        remote_tasks = [
            {"id": "t2", "title": "Aufgabe 2", "status": "offen"},
            {"id": "t_del", "title": "Geloeschte Aufgabe", "status": "offen"},
        ]
        merged = merge_custom_tasks(local_tasks, remote_tasks, deleted_ids={"t_del"})
        ids = [t["id"] for t in merged]
        self.assertIn("t1", ids)
        self.assertIn("t2", ids)
        self.assertNotIn("t_del", ids)

    def test_manual_task_deletion_records_tombstone(self):
        from unittest.mock import patch
        from git_sync_service import GitSyncService
        from task_manager import TaskManager, Task
        mgr = TaskManager(autostart_prefetch=False)
        test_task = Task(
            id="manual_test_del_123",
            platform="manual",
            course="TEST",
            course_full="Test Course",
            title="Test Del",
            due_date_str="Morgen",
            status="offen",
            status_display="Open",
            url="",
        )
        mgr.tasks.append(test_task)
        
        # Loeschen der manuellen Aufgabe
        with patch.object(GitSyncService, "async_push"):
            mgr.delete_task("manual_test_del_123")
        
        self.assertIn("manual_test_del_123", mgr.deleted_ids)
        self.assertNotIn("manual_test_del_123", [t.id for t in mgr.tasks])

    def test_cleanup_legacy_sync_repo_files(self):
        """Prüft die automatische Migration und Bereinigung veralteter aufgaben_detector_*.json Dateien im Sync-Repo."""
        import tempfile
        from unittest.mock import patch
        import git_sync_service
        from git_sync_service import cleanup_legacy_sync_repo_files

        with tempfile.TemporaryDirectory() as tmp_repo:
            repo_data = os.path.join(tmp_repo, "data")
            os.makedirs(repo_data, exist_ok=True)

            # Erzeuge veraltete Dateien
            old_cfg = os.path.join(tmp_repo, "aufgaben_detector_config.json")
            with open(old_cfg, "w") as f:
                f.write('{"test_key": "val"}')

            old_tasks = os.path.join(repo_data, "aufgaben_detector_custom_tasks.json")
            with open(old_tasks, "w") as f:
                f.write('[{"id": "task_1"}]')

            # Mock git rm Befehl
            with patch.object(git_sync_service, "_run_git_cmd") as mock_git:
                mock_git.return_value = (True, "", "")
                changed = cleanup_legacy_sync_repo_files(tmp_repo)

            self.assertTrue(changed)
            # Alte Dateien müssen physisch gelöscht worden sein
            self.assertFalse(os.path.exists(old_cfg))
            self.assertFalse(os.path.exists(old_tasks))
            # Neue Standarddateien müssen existieren
            new_cfg = os.path.join(tmp_repo, "config.json")
            self.assertTrue(os.path.exists(new_cfg))
            new_tasks = os.path.join(repo_data, "custom_tasks.json")
            self.assertTrue(os.path.exists(new_tasks))


if __name__ == "__main__":
    unittest.main()


