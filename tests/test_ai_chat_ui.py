"""
test_ai_chat_ui.py - Tests for the In-App AI Chat Assistant TUI screen and configuration.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.models import Task, TaskAttachment
from tui_app import AufgabenDetectorApp, AiChatScreen, AiConfigModal, TaskDetailModal


class TestAiChatUI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.sample_task1 = Task(
            id="task_swp_1",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="LinkedList und Generics",
            due_date_str="Montag, 26. Okt., 23:59",
            status="offen",
            status_display="Nicht abgegeben",
            url="https://moodle.spengergasse.at/mod/assign/view.php?id=101",
            teacher="BIM",
            description="Implementiere eine doppelt verkettete Liste in Java.",
            details_loaded=True,
        )
        self.sample_task2 = Task(
            id="task_amec_2",
            platform="moodle",
            course="AMEC",
            course_full="Angewandte Mechatronik",
            title="Schrittmotor A4988",
            due_date_str="Dienstag, 27. Okt., 14:00",
            status="ueberfaellig",
            status_display="Überfällig",
            url="https://moodle.spengergasse.at/mod/assign/view.php?id=102",
            teacher="KRD",
            description="Steuere einen Schrittmotor an.",
            details_loaded=True,
        )
        self.sample_task_done = Task(
            id="task_d_done",
            platform="teams",
            course="D",
            course_full="Deutsch",
            title="Buchrezension",
            due_date_str="Gestern",
            status="abgegeben",
            status_display="Abgegeben",
            url="",
            teacher="WAW",
            description="Erledigte Aufgabe.",
            details_loaded=True,
        )

        self.mock_mgr = MagicMock()
        self.mock_mgr.get_filtered_tasks.return_value = [self.sample_task1, self.sample_task2]
        self.mock_mgr.get_tasks.return_value = [self.sample_task1, self.sample_task2, self.sample_task_done]
        self.mock_mgr.tasks = [self.sample_task1, self.sample_task2, self.sample_task_done]

        AiChatScreen._last_opened_task_id = None
        from services.ai_chat_service import save_last_active_ai_task_id
        save_last_active_ai_task_id("")

    def test_aichat_screen_filters_only_open_and_overdue_tasks(self):
        screen = AiChatScreen(self.mock_mgr)
        screen._load_open_tasks()
        # Only open and overdue tasks should be included in tabs (completed task excluded)
        self.assertEqual(len(screen.open_tasks), 2)
        task_ids = [t.id for t in screen.open_tasks]
        self.assertIn("task_swp_1", task_ids)
        self.assertIn("task_amec_2", task_ids)
        self.assertNotIn("task_d_done", task_ids)

    def test_aichat_screen_tab_expansion_and_selection(self):
        screen = AiChatScreen(self.mock_mgr)
        screen._load_open_tasks()
        screen.select_task(0)
        self.assertEqual(screen.active_task_idx, 0)
        self.assertEqual(screen.active_task.id, "task_swp_1")

        # Select second tab
        screen.select_task(1)
        self.assertEqual(screen.active_task_idx, 1)
        self.assertEqual(screen.active_task.id, "task_amec_2")

    async def test_aichat_screen_compose_and_widgets(self):
        from textual.app import App
        from textual.widgets import Button
        from tui_app import ChatInputArea

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            screen = AiChatScreen(self.mock_mgr)
            await app.push_screen(screen)
            await pilot.pause()

            # Verify input area exists (ChatInputArea, no send button)
            inp = screen.query_one("#ai_chat_input", ChatInputArea)
            self.assertIsNotNone(inp)
            self.assertEqual(len(list(screen.query("#btn_ai_send"))), 0)

            # Verify back button and its bottom-aligned container exist
            btn_box = screen.query_one("#ai_input_btn_box")
            self.assertIsNotNone(btn_box)
            back_btn = screen.query_one("#btn_ai_back", Button)
            self.assertIn("Back", str(back_btn.label))

            # Verify clear button exists directly to the left of back button in btn_box
            clear_btn = screen.query_one("#btn_ai_clear_chat", Button)
            self.assertEqual(str(clear_btn.label).strip(), "🗑️")
            self.assertIn(clear_btn, btn_box.children)
            self.assertIn(back_btn, btn_box.children)

            # Verify input bar borders
            input_bar = screen.query_one("#ai_input_bar")
            self.assertIsNotNone(input_bar.styles.border_top)
            self.assertIsNotNone(input_bar.styles.border_bottom)

            # Verify task tabs were created
            tab_btns = list(screen.query(".ai_tab_btn"))
            self.assertEqual(len(tab_btns), 2)

            # Active tab should have SWP and assignment title
            self.assertIn("SWP", str(tab_btns[0].label))
            self.assertIn("LinkedList", str(tab_btns[0].label))
            # Inactive tab should only have course AMEC without brackets
            self.assertEqual("AMEC", str(tab_btns[1].label).strip())

            # Banner title should only show title without course prefix
            banner_title = screen.query_one("#ai_task_banner_title")
            self.assertEqual(str(banner_title.render()), "LinkedList und Generics")

    async def test_aichat_screen_send_and_clear_action(self):
        from textual.app import App
        from tui_app import ChatInputArea

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            screen = AiChatScreen(self.mock_mgr)
            await app.push_screen(screen)
            await pilot.pause()

            inp = screen.query_one("#ai_chat_input", ChatInputArea)
            inp.value = "Wie fange ich an?"

            with patch("services.ai_chat_service.send_ai_chat_message") as mock_send:
                mock_send.return_value = "Hier ist ein Schritt-für-Schritt Leitfaden..."
                screen.action_send_message()
                self.assertEqual(inp.value, "")  # Cleared after send
                self.assertEqual(inp.styles.height.value, 1)  # Shrunk back to 1 line

            # Test clear action
            screen.action_clear_chat()
            self.assertEqual(screen.chat_history.get("task_swp_1", []), [])

    async def test_assistant_message_renders_markdown_widget(self):
        from textual.app import App
        from textual.widgets import Markdown, Static

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            screen = AiChatScreen(self.mock_mgr)
            await app.push_screen(screen)
            await pilot.pause()

            # Set up chat history with both a user message and assistant message containing markdown code block
            task_id = self.sample_task1.id
            screen.active_task = self.sample_task1
            screen.chat_history[task_id] = [
                {"role": "user", "content": "How do I print hello in bash?"},
                {"role": "assistant", "content": "Here is the command:\n```bash\necho hello\n```"}
            ]
            screen._refresh_chat_display()
            await pilot.pause()

            # Find message containers
            containers = screen.query(".ai_msg_container")
            self.assertEqual(len(containers), 2)

            # First is user (should contain Static)
            user_msg = containers[0].query_one(Static)
            self.assertNotIsInstance(user_msg, Markdown)
            self.assertIn("How do I print hello", str(user_msg.render()))

            # Second is assistant (should contain Markdown)
            assistant_md = containers[1].query_one(Markdown)
            self.assertIsInstance(assistant_md, Markdown)

    async def test_chat_input_area_multiline_and_keys(self):
        from textual.app import App
        from tui_app import ChatInputArea

        class DummyApp(App):
            def compose(self):
                yield ChatInputArea(id="test_inp")

        app = DummyApp()
        async with app.run_test() as pilot:
            inp = app.query_one(ChatInputArea)
            self.assertEqual(inp.styles.height.value, 1)

            # Shift+Enter inserts newline and height becomes 2
            await pilot.press("h", "i")
            await pilot.press("shift+enter")
            await pilot.press("t", "h", "e", "r", "e")
            await pilot.pause()
            self.assertEqual(inp.styles.height.value, 2)
            self.assertIn("\n", inp.text)

            # Another Shift+Enter increases height to 3
            await pilot.press("shift+enter")
            await pilot.press("l", "3")
            await pilot.pause()
            self.assertEqual(inp.styles.height.value, 3)

            # More lines keeps max height at 3 and enables scrollbar
            await pilot.press("shift+enter")
            await pilot.press("l", "4")
            await pilot.pause()
            self.assertEqual(inp.styles.height.value, 3)
            self.assertTrue(inp.show_vertical_scrollbar)

            # Test Windows hardware Shift fallback: enter key when physical shift is pressed
            with patch("tui_app.is_shift_pressed_win32", return_value=True):
                old_lines = inp.document.line_count
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(inp.document.line_count, old_lines + 1)

    def test_app_bindings_and_bottom_bar_contain_ai_button(self):
        mgr = MagicMock()
        mgr.get_filtered_tasks.return_value = []
        app = AufgabenDetectorApp(mgr=mgr)

        binding_keys = [b.key for b in app.BINDINGS]
        self.assertIn("i", binding_keys)

        # Check that action_show_ai_chat is defined
        self.assertTrue(hasattr(app, "action_show_ai_chat"))

    def test_task_detail_modal_ai_explain_redirects_to_ai_chat(self):
        mgr = MagicMock()
        detail_modal = TaskDetailModal(self.sample_task1, mgr)

        app_mock = MagicMock()
        detail_modal._app = app_mock

        with patch.object(detail_modal, "dismiss") as mock_dismiss:
            detail_modal.action_ai_explain()
            mock_dismiss.assert_called_once()
            app_mock.action_show_ai_chat.assert_called_once_with(
                initial_task_id="task_swp_1",
                auto_explain=True
            )

    async def test_ai_config_modal_widgets(self):
        from textual.app import App
        from textual.widgets import Input, Select, Button

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            modal = AiConfigModal()
            await app.push_screen(modal)
            await pilot.pause()

            inp_key = modal.query_one("#inp_ai_key", Input)
            self.assertIsNotNone(inp_key)

            sel_model = modal.query_one("#sel_ai_model", Select)
            self.assertIsNotNone(sel_model)

            btn_test = modal.query_one("#btn_ai_test_conn", Button)
            self.assertIsNotNone(btn_test)

            btn_fetch = modal.query_one("#btn_ai_fetch_models", Button)
            self.assertIsNotNone(btn_fetch)

            # Test that pasting an API key triggers auto-fetch
            with patch.object(modal, "action_fetch_models") as mock_fetch:
                inp_key.value = "AIzaSyD-PasteTestKeyLongEnough12345"
                await pilot.pause()
                mock_fetch.assert_called_once()

    def test_aichat_screen_with_custom_filtered_tasks(self):
        # When filtered tasks from main menu are provided, only those should be loaded
        screen = AiChatScreen(self.mock_mgr, tasks=[self.sample_task2])
        screen._load_open_tasks()
        self.assertEqual(len(screen.open_tasks), 1)
        self.assertEqual(screen.open_tasks[0].id, "task_amec_2")
        self.assertEqual(screen.active_task.id, "task_amec_2")

    def test_aichat_screen_action_passes_current_tasks(self):
        app = AufgabenDetectorApp()
        app.current_tasks = [self.sample_task2]
        with patch.object(app, "push_screen") as mock_push:
            app.action_show_ai_chat()
            mock_push.assert_called_once()
            created_screen = mock_push.call_args[0][0]
            self.assertIsInstance(created_screen, AiChatScreen)
            self.assertEqual(created_screen.tasks_pool, [self.sample_task2])

    async def test_thinking_indicator_animation_and_cleanup(self):
        from textual.app import App
        from textual.widgets import Label

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            screen = AiChatScreen(self.mock_mgr)
            await app.push_screen(screen)
            await pilot.pause()

            # Initially not waiting
            self.assertFalse(screen.is_waiting_for_ai)
            self.assertIsNone(screen._thinking_timer)

            # Set waiting
            screen.active_task = self.sample_task1
            screen.is_waiting_for_ai = True
            screen._refresh_chat_display()
            await pilot.pause()

            lbl = screen.query_one(".ai_thinking_box", Label)
            self.assertEqual(str(lbl.render()), "Thinking.")
            self.assertEqual(screen._thinking_step, 1)
            self.assertIsNotNone(screen._thinking_timer)

            # Step 1 -> Step 2
            screen._step_thinking_indicator()
            self.assertEqual(screen._thinking_step, 2)
            self.assertEqual(str(lbl.render()), "Thinking..")

            # Step 2 -> Step 3
            screen._step_thinking_indicator()
            self.assertEqual(screen._thinking_step, 3)
            self.assertEqual(str(lbl.render()), "Thinking...")

            # Step 3 -> Step 1 (Loop back)
            screen._step_thinking_indicator()
            self.assertEqual(screen._thinking_step, 1)
            self.assertEqual(str(lbl.render()), "Thinking.")

            # Turn off waiting: timer is stopped and cleaned up
            screen.is_waiting_for_ai = False
            screen._step_thinking_indicator()
            self.assertIsNone(screen._thinking_timer)

            # Test cleanup on dismiss
            screen._thinking_timer = MagicMock()
            screen.action_dismiss_screen()
            self.assertIsNone(screen._thinking_timer)

    def test_aichat_screen_theme_css_variables(self):
        from textual.app import App
        css = AiChatScreen.DEFAULT_CSS
        # Semantic variables present for multi-theme compatibility
        self.assertIn("$background", css)
        self.assertIn("$surface", css)
        self.assertIn("$panel", css)
        self.assertIn("$primary", css)
        self.assertIn("$border", css)
        self.assertIn("$text", css)
        self.assertIn("$warning", css)
        self.assertIn("$success", css)
        # Saturated red used for the trash button
        self.assertIn("#e03131", css)

        # Ensure CSS parses completely without any syntax errors
        app = App()
        app.stylesheet.add_source(css)

    def test_last_opened_task_restoration_and_fallback(self):
        AiChatScreen._last_opened_task_id = None

        # 1. No previous task: defaults to first task (index 0)
        screen1 = AiChatScreen(self.mock_mgr)
        screen1._load_open_tasks()
        self.assertEqual(screen1.active_task_idx, 0)
        self.assertEqual(screen1.active_task.id, "task_swp_1")

        # 2. Select task at index 1 ("task_amec_2")
        screen1.select_task(1)
        self.assertEqual(AiChatScreen._last_opened_task_id, "task_amec_2")

        # 3. New screen should automatically restore "task_amec_2"
        screen2 = AiChatScreen(self.mock_mgr)
        screen2._load_open_tasks()
        self.assertEqual(screen2.active_task_idx, 1)
        self.assertEqual(screen2.active_task.id, "task_amec_2")

        # 4. If last opened task is no longer in open tasks, fall back to index 0
        screen3 = AiChatScreen(self.mock_mgr, tasks=[self.sample_task1])
        screen3._load_open_tasks()
        self.assertEqual(screen3.active_task_idx, 0)
        self.assertEqual(screen3.active_task.id, "task_swp_1")

    async def test_assistant_response_scrolls_to_top_of_bubble(self):
        from textual.app import App
        from textual.containers import Vertical

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            screen = AiChatScreen(self.mock_mgr)
            await app.push_screen(screen)
            await pilot.pause()

            screen.active_task = self.sample_task1
            screen.chat_history[self.sample_task1.id] = [
                {"role": "user", "content": "Tell me a long story."},
                {"role": "assistant", "content": "Line 1\n" * 50}
            ]

            # Refresh with scroll_to_assistant_top=True
            with patch.object(screen, "call_after_refresh") as mock_after_refresh:
                screen._refresh_chat_display(scroll_to_assistant_top=True)
                mock_after_refresh.assert_called_once()
                # Verify that the callback executes scroll_visible(top=True, animate=False)
                cb = mock_after_refresh.call_args[0][0]
                assistant_bubble = screen.query(".ai_msg_assistant").last()
                with patch.object(assistant_bubble, "scroll_visible") as mock_scroll_visible:
                    cb()
                    mock_scroll_visible.assert_called_once_with(top=True, animate=False)


if __name__ == "__main__":
    unittest.main()
