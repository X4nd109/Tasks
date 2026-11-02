"""
test_agent_skill_modal.py - Tests for AgentSkillSetupModal and the 🤖 Agent button
in AiChatScreen.
"""

import asyncio
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
for p in [_ROOT, _SRC, os.path.join(_SRC, "core"), os.path.join(_SRC, "services"), os.path.join(_SRC, "ui")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Label
from tui_app import AgentSkillSetupModal, AiChatScreen, ConfirmSkillRemovalModal, AgentSkillStatusModal, AgentHubModal
import config


class AgentSkillModalTest(unittest.TestCase):
    """Tests for the step-by-step universal AgentSkillSetupModal."""

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

    def test_modal_initial_state(self):
        modal = AgentSkillSetupModal()
        self.assertEqual(modal.current_step, 1)
        self.assertTrue(bool(modal.target_dir))

    def test_modal_folder_picker(self):
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillSetupModal()

        # Folder without 'tasks' -> should immediately append 'tasks' upon selection
        skills_root = os.path.join(self.tmp, "my_custom_skills")
        os.makedirs(skills_root, exist_ok=True)

        # Folder with 'tasks' in name -> should keep name as is
        tasks_app_dir = os.path.join(self.tmp, "Tasks App")
        os.makedirs(tasks_app_dir, exist_ok=True)

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillSetupModal)

                # 1. Picking folder without 'tasks'
                with patch("win_dialogs.pick_directory", return_value=skills_root):
                    modal._browse_directory()
                expected_skills_target = os.path.normpath(os.path.join(skills_root, "tasks"))
                self.assertEqual(os.path.normpath(modal.target_dir), expected_skills_target)
                self.assertEqual(os.path.normpath(modal.query_one("#skill_path_input", Input).value), expected_skills_target)

                # 2. Picking folder with 'tasks' in name (e.g. 'Tasks App', 'tasks_app', 'App Tasks')
                with patch("win_dialogs.pick_directory", return_value=tasks_app_dir):
                    modal._browse_directory()
                self.assertEqual(os.path.normpath(modal.target_dir), os.path.normpath(tasks_app_dir))
                self.assertEqual(os.path.normpath(modal.query_one("#skill_path_input", Input).value), os.path.normpath(tasks_app_dir))

        asyncio.run(_test())

    def test_modal_step_transitions(self):
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillSetupModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillSetupModal)
                self.assertEqual(modal.current_step, 1)

                # Next to Step 2
                modal.query_one("#btn_step1_next", Button).press()
                await pilot.pause()
                self.assertEqual(modal.current_step, 2)

                # Back button in Step 2 returns to Step 1
                modal.query_one("#btn_step2_back", Button).press()
                await pilot.pause()
                self.assertEqual(modal.current_step, 1)

                # Forward again
                modal.query_one("#btn_step1_next", Button).press()
                await pilot.pause()
                self.assertEqual(modal.current_step, 2)

                # Download button transitions Step 2 to Step 3
                with patch("agent_cli.sync_skill_to_dir", return_value=True):
                    modal.query_one("#btn_do_download", Button).press()
                    await pilot.pause(0.2)
                self.assertEqual(modal.current_step, 3)

                # Finish button exists in Step 3
                finish_btn = modal.query_one("#btn_step3_finish", Button)
                self.assertIsNotNone(finish_btn)
                self.assertIn("Finish", str(finish_btn.label))

        asyncio.run(_test())

    def test_modal_download_success(self):
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillSetupModal()

        app = TestApp()
        custom_dir = os.path.join(self.tmp, "test_download_dir", "tasks")
        os.makedirs(custom_dir, exist_ok=True)

        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillSetupModal)
                modal.target_dir = custom_dir

                with patch("agent_cli.sync_skill_to_dir", return_value=True):
                    modal._execute_download()
                    await pilot.pause(0.2)

                self.assertEqual(modal.current_step, 3)
                self.assertEqual(config.load_skill_target_dir(), os.path.abspath(custom_dir))

        asyncio.run(_test())

    def test_modal_auto_appends_tasks_folder_silently(self):
        """Verifies that exiting Step 1 automatically appends a 'tasks' subfolder
        if not already present, without extra popups, and displays it in Step 2 Target."""
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillSetupModal()

        parent_skills_dir = os.path.join(self.tmp, "custom_skills_root")
        os.makedirs(parent_skills_dir, exist_ok=True)

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillSetupModal)
                # User set parent dir without 'tasks'
                modal.target_dir = parent_skills_dir
                modal.query_one("#skill_path_input", Input).value = parent_skills_dir

                # Click Next (finishing Step 1)
                modal.query_one("#btn_step1_next", Button).press()
                await pilot.pause()

                # Step 2 reached
                self.assertEqual(modal.current_step, 2)
                expected_dir = os.path.normpath(os.path.join(parent_skills_dir, "tasks"))
                self.assertEqual(os.path.normpath(modal.target_dir), expected_dir)

                target_lbl_text = str(modal.query_one("#step2_target_lbl", Label).content)
                self.assertIn(os.path.join("custom_skills_root", "tasks", "SKILL.md"), target_lbl_text)

                # Now go back to Step 1
                modal.query_one("#btn_step2_back", Button).press()
                await pilot.pause()
                self.assertEqual(modal.current_step, 1)

                # Input in Step 1 now holds the normalized path
                inp_val = os.path.normpath(modal.query_one("#skill_path_input", Input).value)
                self.assertEqual(inp_val, expected_dir)

                # Clicking Next again should NOT append another tasks (no tasks/tasks)
                modal.query_one("#btn_step1_next", Button).press()
                await pilot.pause()
                self.assertEqual(os.path.normpath(modal.target_dir), expected_dir)

        asyncio.run(_test())

    def test_modal_abort_step2_does_not_set_flag(self):
        """Verifies that aborting/cancelling in Step 2 does NOT set the configured flag,
        and that the flag is only persisted when arriving at Step 3."""
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillSetupModal()

        custom_target = os.path.join(self.tmp, "fresh_agent_env", "tasks")
        os.makedirs(custom_target, exist_ok=True)

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillSetupModal)
                modal.target_dir = custom_target

                # Go to Step 2
                modal.query_one("#btn_step1_next", Button).press()
                await pilot.pause()
                self.assertEqual(modal.current_step, 2)

                # Abort/Cancel in Step 2: flag must NOT be set
                with patch.object(modal, "dismiss") as mock_dismiss:
                    modal.action_cancel()
                    mock_dismiss.assert_called_once_with(False)
                await pilot.pause()
                self.assertIsNone(config.load_skill_target_dir())

        asyncio.run(_test())


class AiChatScreenAgentButtonTest(unittest.TestCase):
    """Verifies that AiChatScreen renders the 1-line Clear, 1-line Agent, and 3-line Back buttons."""

    def test_ai_chat_screen_contains_agent_button(self):
        mgr_mock = MagicMock()
        mgr_mock.get_all_tasks.return_value = []

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AiChatScreen(mgr=mgr_mock)

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                screen = app.query_one(AiChatScreen)

                clear_btn = screen.query_one("#btn_ai_clear_chat", Button)
                self.assertIsNotNone(clear_btn)
                self.assertEqual(clear_btn.styles.height.value, 1)

                agent_btn = screen.query_one("#btn_ai_agent_skill", Button)
                self.assertIsNotNone(agent_btn)
                self.assertIn("Agent", str(agent_btn.label))
                self.assertEqual(agent_btn.styles.height.value, 1)

                back_btn = screen.query_one("#btn_ai_back", Button)
                self.assertIsNotNone(back_btn)
                self.assertEqual(back_btn.styles.height.value, 3)

        asyncio.run(_test())



class ConfirmSkillRemovalModalTest(unittest.TestCase):
    """Tests for ConfirmSkillRemovalModal."""

    def test_confirm_modal_buttons(self):
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield ConfirmSkillRemovalModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(ConfirmSkillRemovalModal)
                self.assertIsNotNone(modal.query_one("#btn_confirm_remove", Button))
                self.assertIsNotNone(modal.query_one("#btn_cancel_remove", Button))

                with patch.object(modal, "dismiss") as mock_dismiss:
                    modal.query_one("#btn_confirm_remove", Button).press()
                    await pilot.pause()
                    mock_dismiss.assert_called_with(True)

                with patch.object(modal, "dismiss") as mock_dismiss:
                    modal.query_one("#btn_cancel_remove", Button).press()
                    await pilot.pause()
                    mock_dismiss.assert_called_with(False)

        asyncio.run(_test())


class AgentSkillStatusModalTest(unittest.TestCase):
    """Tests for AgentSkillStatusModal (display, move, remove)."""

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

    def test_status_display_with_configured_skill(self):
        skill_dir = os.path.join(self.tmp, "active_skills", "tasks")
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Skill")
        config.save_skill_target_dir(skill_dir)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillStatusModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillStatusModal)
                dir_text = str(modal.query_one("#status_dir_value", Label).content)
                self.assertIn("active_skills", dir_text)
                auto_text = str(modal.query_one("#status_autoupdate_value", Label).content)
                self.assertIn("ENABLED", auto_text)
                file_text = str(modal.query_one("#status_file_value", Label).content)
                self.assertIn("Installed", file_text)

        asyncio.run(_test())

    def test_status_move_button(self):
        old_dir = os.path.join(self.tmp, "old_skills", "tasks")
        new_dir = os.path.join(self.tmp, "new_skills", "tasks")
        os.makedirs(old_dir, exist_ok=True)
        with open(os.path.join(old_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Skill")
        config.save_skill_target_dir(old_dir)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentSkillStatusModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                modal = app.query_one(AgentSkillStatusModal)
                with patch("win_dialogs.pick_directory", return_value=new_dir),                      patch("agent_cli.sync_skill_to_dir", return_value=True):
                    modal._handle_move()
                    await pilot.pause()
                self.assertEqual(config.load_skill_target_dir(), os.path.abspath(new_dir))
                dir_text = str(modal.query_one("#status_dir_value", Label).content)
                self.assertIn("new_skills", dir_text)

        asyncio.run(_test())


class AgentHubModalTest(unittest.TestCase):
    """Tests for AgentHubModal: greyed-out State button when unconfigured,
    enabled when configured, and dynamic update after removal."""

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

    def test_hub_state_button_disabled_when_no_skill_configured(self):
        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentHubModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                hub = app.query_one(AgentHubModal)
                state_btn = hub.query_one("#btn_hub_state", Button)
                # No skill configured -> button MUST be disabled / greyed out
                self.assertTrue(state_btn.disabled)

        asyncio.run(_test())

    def test_hub_state_button_enabled_when_skill_configured(self):
        skill_dir = os.path.join(self.tmp, "my_agent", "tasks")
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Tasks Skill")
        config.save_skill_target_dir(skill_dir)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentHubModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                hub = app.query_one(AgentHubModal)
                state_btn = hub.query_one("#btn_hub_state", Button)
                # Skill is configured -> button MUST be enabled
                self.assertFalse(state_btn.disabled)

        asyncio.run(_test())

    def test_hub_state_button_greys_out_after_removal(self):
        skill_dir = os.path.join(self.tmp, "my_agent", "tasks")
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# Tasks Skill")
        skill_file = os.path.join(skill_dir, "SKILL.md")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write("# Skill")
        config.save_skill_target_dir(skill_dir)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentHubModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                hub = app.query_one(AgentHubModal)
                state_btn = hub.query_one("#btn_hub_state", Button)
                self.assertFalse(state_btn.disabled)

                # Simulate removal from status modal
                from agent_cli import unlink_skill
                unlink_skill(delete_files=True)
                hub._refresh_state()
                await pilot.pause()

                # State button should now be disabled/greyed out
                self.assertTrue(state_btn.disabled)

        asyncio.run(_test())



    def test_hub_detects_and_notifies_when_skill_folder_manually_deleted(self):
        """When skill directory was manually deleted on disk, AgentHubModal._refresh_state
        disables the State button, clears config, and notifies the user."""
        skill_dir = os.path.join(self.tmp, "deleted_agent", "tasks")
        # Configure without creating directory on disk
        config.save_skill_target_dir(skill_dir)
        self.assertEqual(config.load_skill_target_dir(), skill_dir)

        class TestApp(App):
            def compose(self) -> ComposeResult:
                yield AgentHubModal()

        app = TestApp()
        async def _test():
            async with app.run_test() as pilot:
                hub = app.query_one(AgentHubModal)
                state_btn = hub.query_one("#btn_hub_state", Button)
                self.assertTrue(state_btn.disabled)
                # Config must be cleared
                self.assertIsNone(config.load_skill_target_dir())

        asyncio.run(_test())


class TasksAppStartupSkillIntegrityTest(unittest.TestCase):
    """Tests for TasksApp startup integrity check when skill is unexpectedly removed."""

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

    def test_startup_detects_deleted_skill_and_notifies(self):
        from tui_app import TasksApp
        skill_dir = os.path.join(self.tmp, "gone_folder", "tasks")
        config.save_skill_target_dir(skill_dir)

        mgr_mock = MagicMock()
        mgr_mock.get_all_tasks.return_value = []
        mgr_mock.active_filter = "all"
        mgr_mock.active_subject_filter = None

        app = TasksApp(mgr=mgr_mock, sync_on_startup=False)

        async def _test():
            async with app.run_test() as pilot:
                # Target dir should be unlinked
                self.assertIsNone(config.load_skill_target_dir())

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
