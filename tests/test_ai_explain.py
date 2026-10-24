"""
test_ai_explain.py - Unit tests for AI Explain prompt generation, configuration,
clipboard helpers, and CLI/TUI integration.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.models import Task, TaskAttachment
from core.config import (
    load_ai_explain_config,
    save_ai_explain_config,
    AI_EXPLAIN_PRESETS,
    DEFAULT_AI_EXPLAIN_CONFIG,
)
from services.ai_explain_service import (
    build_ai_explain_prompt,
    copy_to_clipboard,
    get_ai_explain_url,
    open_ai_explain,
)
from core.agent_cli import run_agent_cli, is_agent_cli_command


class TestAiExplain(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.sample_task = Task(
            id="test_task_1",
            platform="moodle",
            course="AMEC",
            course_full="Angewandte Mechatronik",
            title="Aufgabe 03: Schrittmotor ansteuern",
            due_date_str="Freitag, 24. Okt., 23:59",
            status="offen",
            status_display="Noch offen",
            url="https://moodle.spengergasse.at/mod/assign/view.php?id=12345",
            teacher="KRD",
            description="Entwickle einen Arduino-Sketch zur Schrittmotor-Ansteuerung via A4988 Treiber.",
            attachments=[
                TaskAttachment(name="schaltplan.pdf", url="https://moodle.spengergasse.at/file1"),
                TaskAttachment(name="datenblatt_a4988.pdf", url="https://moodle.spengergasse.at/file2"),
            ],
            details_loaded=True,
        )

    def test_build_prompt_de(self):
        prompt = build_ai_explain_prompt(self.sample_task, language="de")
        self.assertIn("Bitte erkläre mir die folgende Schulaufgabe verständlich", prompt)
        self.assertIn("AMEC (Angewandte Mechatronik)", prompt)
        self.assertIn("Aufgabe 03: Schrittmotor ansteuern", prompt)
        self.assertIn("Freitag, 24. Okt., 23:59", prompt)
        self.assertIn("KRD", prompt)
        self.assertIn("Arduino-Sketch", prompt)
        self.assertIn("- schaltplan.pdf", prompt)
        self.assertIn("- datenblatt_a4988.pdf", prompt)

    def test_build_prompt_en(self):
        prompt = build_ai_explain_prompt(self.sample_task, language="en")
        self.assertIn("Please explain the following school assignment clearly", prompt)
        self.assertIn("AMEC (Angewandte Mechatronik)", prompt)
        self.assertIn("Aufgabe 03: Schrittmotor ansteuern", prompt)
        self.assertIn("**Teacher:** KRD", prompt)
        self.assertIn("- schaltplan.pdf", prompt)
        self.assertIn("- datenblatt_a4988.pdf", prompt)

    def test_build_prompt_no_attachments(self):
        empty_task = Task(
            id="test_task_2",
            platform="manual",
            course="D",
            course_full="Deutsch",
            title="Erörterung schreiben",
            due_date_str="Morgen",
            status="offen",
            status_display="Open",
            url="",
            teacher="",
            description="",
            attachments=[],
        )
        prompt_de = build_ai_explain_prompt(empty_task, language="de")
        self.assertIn("Keine Dateianhänge vorhanden", prompt_de)
        self.assertIn("(Keine schriftliche Aufgabenbeschreibung im System hinterlegt)", prompt_de)

        prompt_en = build_ai_explain_prompt(empty_task, language="en")
        self.assertIn("No attachments present", prompt_en)
        self.assertIn("(No written assignment description provided)", prompt_en)

    def test_get_ai_explain_url(self):
        # Gemini: Static URL
        cfg_gemini = {"url_template": "https://gemini.google.com/app"}
        url_gemini = get_ai_explain_url("Hello World", config=cfg_gemini)
        self.assertEqual(url_gemini, "https://gemini.google.com/app")

        # ChatGPT: {prompt} replacement with URL encoding
        cfg_chatgpt = {"url_template": "https://chatgpt.com/?q={prompt}"}
        url_chatgpt = get_ai_explain_url("Erklär mir das: 1 + 1", config=cfg_chatgpt)
        self.assertTrue(url_chatgpt.startswith("https://chatgpt.com/?q="))
        self.assertIn("Erkl%C3%A4r", url_chatgpt)
        self.assertNotIn("{prompt}", url_chatgpt)

    def test_config_persistence(self):
        original = load_ai_explain_config()
        test_cfg = {
            "provider": "app",
            "url_template": "https://chatgpt.com/?q={prompt}",
            "app_path": r"C:\Tools\Gemini.exe",
            "language": "en",
        }
        try:
            save_ai_explain_config(test_cfg, auto_push=False)
            loaded = load_ai_explain_config()
            self.assertEqual(loaded.get("provider"), "app")
            self.assertEqual(loaded.get("url_template"), "https://chatgpt.com/?q={prompt}")
            self.assertEqual(loaded.get("app_path"), r"C:\Tools\Gemini.exe")
            self.assertEqual(loaded.get("language"), "en")
        finally:
            save_ai_explain_config(original, auto_push=False)

    def test_copy_to_clipboard(self):
        # Test that copy_to_clipboard doesn't crash and returns boolean
        result = copy_to_clipboard("Test AI prompt text")
        self.assertIsInstance(result, bool)

    @patch("webbrowser.open")
    def test_open_ai_explain(self, mock_browser):
        mock_browser.return_value = True
        success, prompt, url = open_ai_explain(self.sample_task)
        self.assertTrue(success)
        self.assertTrue(len(prompt) > 0)
        self.assertTrue(url.startswith("http"))

    @patch("os.path.exists")
    @patch("services.ai_explain_service.launch_desktop_app")
    def test_open_ai_explain_desktop_app(self, mock_launch, mock_exists):
        mock_exists.return_value = True
        mock_launch.return_value = True
        cfg = {
            "provider": "app",
            "url_template": "",
            "app_path": r"C:\Program Files\Gemini\Gemini.exe",
            "language": "en",
        }
        success, prompt, target = open_ai_explain(self.sample_task, config=cfg)
        self.assertTrue(success)
        mock_launch.assert_called_once_with(r"C:\Program Files\Gemini\Gemini.exe")
        self.assertEqual(target, r"C:\Program Files\Gemini\Gemini.exe")

    def test_is_agent_cli_command(self):
        self.assertTrue(is_agent_cli_command(["explain", "1"]))
        self.assertTrue(is_agent_cli_command(["ai-explain", "moodle_1"]))
        self.assertTrue(is_agent_cli_command(["--explain", "1"]))

    @patch("webbrowser.open")
    def test_cli_explain_command(self, mock_browser):
        # Test CLI explain output
        mock_browser.return_value = True
        import io
        from contextlib import redirect_stdout

        out = io.StringIO()
        with redirect_stdout(out):
            ret = run_agent_cli(["explain", "1", "--copy-only", "--json"])
        self.assertEqual(ret, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data.get("success"))
        self.assertIn("prompt", data)
        self.assertIn("copied_to_clipboard", data)

    def test_task_detail_modal_contains_ai_explain_button(self):
        from tui_app import TaskDetailModal
        mgr = MagicMock()
        modal = TaskDetailModal(self.sample_task, mgr)
        binding_keys = [b.key for b in modal.BINDINGS]
        self.assertIn("a", binding_keys)

    def test_ai_explain_modal_compose_and_actions(self):
        from tui_app import AiExplainModal
        modal = AiExplainModal()
        modal._select_preset("chatgpt")
        self.assertEqual(modal.current_provider, "chatgpt")

        # Test selecting desktop app preset
        modal._select_preset("app")
        self.assertEqual(modal.current_provider, "app")

        # Test language toggle
        initial_lang = modal.current_language
        modal.action_toggle_language()
        self.assertNotEqual(modal.current_language, initial_lang)
        modal.action_toggle_language()
        self.assertEqual(modal.current_language, initial_lang)

    async def test_ai_explain_modal_save_and_back_buttons(self):
        from textual.app import App
        from textual.widgets import Button
        from tui_app import AiExplainModal

        class DummyApp(App):
            pass

        app = DummyApp()
        async with app.run_test() as pilot:
            modal = AiExplainModal()
            await app.push_screen(modal)
            await pilot.pause()
            save_btn = modal.query_one("#btn_ai_save", Button)
            back_btn = modal.query_one("#btn_ai_cancel", Button)
            self.assertIn("Save", str(save_btn.label))
            self.assertIn("Back", str(back_btn.label))


if __name__ == "__main__":
    unittest.main()
