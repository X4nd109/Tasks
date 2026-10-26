import unittest
from textual.app import App
from textual.widgets import Input, TextArea
from src.ui.tui_app import (
    ChatInputArea,
    AddTaskModal,
    AddExamModal,
    SettingsModal,
    MoodleLoginModal,
    TeamsSetupModal,
    GitSetupModal,
    UntisSetupModal,
    Digi4SchoolDownloadModal,
    SchoolbookUrlModal,
)


class TestChatInputAreaBehavior(unittest.TestCase):
    def test_input_instancecheck_compatibility(self):
        area = ChatInputArea(placeholder="Test")
        self.assertIsInstance(area, Input)
        self.assertIsInstance(area, TextArea)

    def test_thin_border_style(self):
        area = ChatInputArea()
        self.assertEqual(area.styles.height.value, 5)
        # Verify border styling is solid thin line
        self.assertIn("border: solid", area.DEFAULT_CSS)

    def test_value_property(self):
        area = ChatInputArea(value="Initial")
        self.assertEqual(area.value, "Initial")
        area.value = "Updated"
        self.assertEqual(area.value, "Updated")
        self.assertEqual(area.text, "Updated")

    def test_dynamic_padding_progression(self):
        area = ChatInputArea(value="")
        area._update_line_layout()
        self.assertEqual(area.styles.height.value, 5)
        self.assertEqual(area.styles.padding, (1, 1, 1, 1))
        self.assertFalse(area.show_vertical_scrollbar)

        # 1 line
        area.text = "Single line text"
        area._update_line_layout()
        self.assertEqual(area.styles.height.value, 5)
        self.assertEqual(area.styles.padding, (1, 1, 1, 1))
        self.assertFalse(area.show_vertical_scrollbar)

        # 2 lines
        area.text = "Line 1\nLine 2"
        area._update_line_layout()
        self.assertEqual(area.styles.height.value, 5)
        self.assertEqual(area.styles.padding, (0, 1, 1, 1))
        self.assertFalse(area.show_vertical_scrollbar)

        # 3 lines
        area.text = "Line 1\nLine 2\nLine 3"
        area._update_line_layout()
        self.assertEqual(area.styles.height.value, 5)
        self.assertEqual(area.styles.padding, (0, 1, 0, 1))
        self.assertFalse(area.show_vertical_scrollbar)

        # 4 lines (overflow)
        area.text = "Line 1\nLine 2\nLine 3\nLine 4"
        area._update_line_layout()
        self.assertEqual(area.styles.height.value, 5)
        self.assertEqual(area.styles.padding, (0, 1, 0, 1))
        self.assertTrue(area.show_vertical_scrollbar)


class TestChatInputAreaKeyHandling(unittest.IsolatedAsyncioTestCase):
    async def test_enter_submits_message(self):
        class InputApp(App):
            def __init__(self):
                super().__init__()
                self.submitted_vals = []

            def compose(self):
                yield ChatInputArea(id="test_chat_input")

            def on_input_submitted(self, event: Input.Submitted):
                self.submitted_vals.append(event.value)

        app = InputApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#test_chat_input", ChatInputArea)
            inp.value = "Hello World"
            await pilot.press("enter")
            self.assertIn("Hello World", app.submitted_vals)

    async def test_shift_enter_inserts_newline(self):
        class InputApp(App):
            def compose(self):
                yield ChatInputArea(id="test_chat_input")

        app = InputApp()
        async with app.run_test() as pilot:
            inp = app.query_one("#test_chat_input", ChatInputArea)
            inp.value = "First"
            inp.cursor_location = (0, 5)
            await pilot.press("shift+enter")
            self.assertIn("\n", inp.text)
            self.assertEqual(inp.styles.padding, (0, 1, 1, 1))
            self.assertFalse(inp.show_vertical_scrollbar)

class TestModalInputsBehavior(unittest.IsolatedAsyncioTestCase):
    async def test_modals_use_chat_input_area_for_text_fields(self):
        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            # AddTaskModal: Only inp_add_desc is ChatInputArea, others are standard Input
            task_modal = AddTaskModal()
            await app.push_screen(task_modal)
            self.assertNotIsInstance(task_modal.query_one("#inp_add_subject"), ChatInputArea)
            self.assertIsInstance(task_modal.query_one("#inp_add_subject"), Input)
            self.assertNotIsInstance(task_modal.query_one("#inp_add_title"), ChatInputArea)
            self.assertIsInstance(task_modal.query_one("#inp_add_title"), Input)
            self.assertNotIsInstance(task_modal.query_one("#inp_add_due"), ChatInputArea)
            self.assertIsInstance(task_modal.query_one("#inp_add_due"), Input)
            self.assertNotIsInstance(task_modal.query_one("#inp_add_time"), ChatInputArea)
            self.assertIsInstance(task_modal.query_one("#inp_add_time"), Input)
            self.assertNotIsInstance(task_modal.query_one("#inp_add_teacher"), ChatInputArea)
            self.assertIsInstance(task_modal.query_one("#inp_add_teacher"), Input)
            self.assertIsInstance(task_modal.query_one("#inp_add_desc"), ChatInputArea)
            app.pop_screen()

            # AddExamModal: Only inp_add_exam_topics is ChatInputArea, others are standard Input
            exam_modal = AddExamModal()
            await app.push_screen(exam_modal)
            self.assertNotIsInstance(exam_modal.query_one("#inp_add_exam_subject"), ChatInputArea)
            self.assertIsInstance(exam_modal.query_one("#inp_add_exam_subject"), Input)
            self.assertNotIsInstance(exam_modal.query_one("#inp_add_exam_date"), ChatInputArea)
            self.assertIsInstance(exam_modal.query_one("#inp_add_exam_date"), Input)
            self.assertNotIsInstance(exam_modal.query_one("#inp_add_exam_time"), ChatInputArea)
            self.assertIsInstance(exam_modal.query_one("#inp_add_exam_time"), Input)
            self.assertNotIsInstance(exam_modal.query_one("#inp_add_exam_teacher"), ChatInputArea)
            self.assertIsInstance(exam_modal.query_one("#inp_add_exam_teacher"), Input)
            self.assertNotIsInstance(exam_modal.query_one("#inp_add_exam_room"), ChatInputArea)
            self.assertIsInstance(exam_modal.query_one("#inp_add_exam_room"), Input)
            self.assertIsInstance(exam_modal.query_one("#inp_add_exam_topics"), ChatInputArea)
            app.pop_screen()

            # MoodleLoginModal
            moodle_modal = MoodleLoginModal()
            await app.push_screen(moodle_modal)
            self.assertNotIsInstance(moodle_modal.query_one("#inp_m_url"), ChatInputArea)
            self.assertIsInstance(moodle_modal.query_one("#inp_m_url"), Input)
            self.assertNotIsInstance(moodle_modal.query_one("#inp_m_user"), ChatInputArea)
            self.assertIsInstance(moodle_modal.query_one("#inp_m_user"), Input)
            pass_input = moodle_modal.query_one("#inp_m_pass", Input)
            self.assertNotIsInstance(pass_input, ChatInputArea)
            self.assertTrue(pass_input.password)
            app.pop_screen()

            # TeamsSetupModal
            teams_modal = TeamsSetupModal()
            await app.push_screen(teams_modal)
            self.assertNotIsInstance(teams_modal.query_one("#inp_t_email"), ChatInputArea)
            self.assertIsInstance(teams_modal.query_one("#inp_t_email"), Input)
            teams_pass = teams_modal.query_one("#inp_t_pass", Input)
            self.assertNotIsInstance(teams_pass, ChatInputArea)
            self.assertTrue(teams_pass.password)
            app.pop_screen()

            # Digi4School
            digi_modal = Digi4SchoolDownloadModal()
            await app.push_screen(digi_modal)
            self.assertNotIsInstance(digi_modal.query_one("#digi_input_email"), ChatInputArea)
            self.assertIsInstance(digi_modal.query_one("#digi_input_email"), Input)
            digi_pass = digi_modal.query_one("#digi_input_password", Input)
            self.assertNotIsInstance(digi_pass, ChatInputArea)
            self.assertTrue(digi_pass.password)
            app.pop_screen()

            # GitSetupModal
            git_modal = GitSetupModal()
            await app.push_screen(git_modal)
            self.assertNotIsInstance(git_modal.query_one("#inp_git_url"), ChatInputArea)
            self.assertIsInstance(git_modal.query_one("#inp_git_url"), Input)
            self.assertNotIsInstance(git_modal.query_one("#inp_git_branch"), ChatInputArea)
            self.assertIsInstance(git_modal.query_one("#inp_git_branch"), Input)
            git_token = git_modal.query_one("#inp_git_token", Input)
            self.assertNotIsInstance(git_token, ChatInputArea)
            self.assertTrue(git_token.password)
            app.pop_screen()


if __name__ == "__main__":
    unittest.main()
