"""
test_ai_chat_service.py - Unit tests for attachment extraction, task context
building, API dispatching, connection testing, and chat cache persistence.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.models import Task, TaskAttachment
from services import ai_chat_service
from services.ai_chat_service import (
    build_task_ai_context,
    cleanup_ai_chats_cache,
    clear_task_chat_cache,
    extract_attachment_text,
    is_task_ai_explained,
    load_task_chat_cache,
    save_task_chat_cache,
    send_ai_chat_message,
    set_task_ai_explained,
    test_ai_connection,
)


def _make_response(status_code=200, json_data=None, text="", json_error=None):
    """Create a lightweight requests.Response stand-in."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_error is not None:
        response.json.side_effect = json_error
    else:
        response.json.return_value = json_data if json_data is not None else {}
    return response


def _gemini_success(text="Antwort"):
    return _make_response(
        200,
        {
            "candidates": [
                {"content": {"parts": [{"text": text}]}}
            ]
        },
    )


def _openai_success(text="Antwort"):
    return _make_response(
        200,
        {"choices": [{"message": {"role": "assistant", "content": text}}]},
    )


class TestExtractAttachmentText(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, content, encoding="utf-8", binary=False):
        path = os.path.join(self.tmpdir, name)
        if binary:
            with open(path, "wb") as fh:
                fh.write(content)
        else:
            with open(path, "w", encoding=encoding) as fh:
                fh.write(content)
        return path

    def test_reads_utf8_text_file(self):
        path = self._write("notes.txt", "Hausübung: Schleife schreiben\nZeile 2")
        text = extract_attachment_text(path)
        self.assertIn("Hausübung", text)
        self.assertIn("Zeile 2", text)

    def test_reads_source_code_extensions(self):
        for name in ["main.py", "app.java", "index.html", "style.css", "data.json"]:
            path = self._write(name, "content-of-" + name)
            self.assertEqual(extract_attachment_text(path), "content-of-" + name)

    def test_truncates_to_max_chars(self):
        path = self._write("long.txt", "x" * 500)
        text = extract_attachment_text(path, max_chars=100)
        self.assertEqual(len(text), 100)

    def test_missing_file_returns_empty_string(self):
        self.assertEqual(extract_attachment_text(os.path.join(self.tmpdir, "nope.txt")), "")
        self.assertEqual(extract_attachment_text(""), "")

    def test_latin1_fallback(self):
        path = os.path.join(self.tmpdir, "legacy.txt")
        with open(path, "wb") as fh:
            fh.write("Grüße".encode("latin-1"))
        self.assertEqual(extract_attachment_text(path), "Grüße")

    def test_binary_extension_returns_placeholder(self):
        path = self._write("bild.png", b"\x89PNG\r\n\x1a\n\x00\x00", binary=True)
        self.assertEqual(extract_attachment_text(path), "[Binary file: bild.png]")

    def test_archive_returns_placeholder(self):
        path = self._write("bundle.zip", b"PK\x03\x04\x00", binary=True)
        self.assertEqual(extract_attachment_text(path), "[Binary file: bundle.zip]")

    def test_unknown_binary_extension_detected_by_null_bytes(self):
        path = self._write("mystery.dat", b"abc\x00def", binary=True)
        self.assertEqual(extract_attachment_text(path), "[Binary file: mystery.dat]")

    def test_pdf_extraction_uses_fitz(self):
        path = self._write("angabe.pdf", b"%PDF-1.4 fake", binary=True)

        page_one = MagicMock()
        page_one.get_text.return_value = "Kapitel 1\n\n\n  Aufgabenstellung"
        page_two = MagicMock()
        page_two.get_text.return_value = "Seite 2"

        doc = MagicMock()
        doc.page_count = 2
        doc.__getitem__.side_effect = [page_one, page_two]

        fitz = MagicMock()
        fitz.open.return_value = doc

        with patch.object(ai_chat_service, "_load_fitz", return_value=fitz):
            text = extract_attachment_text(path)

        fitz.open.assert_called_once_with(path)
        doc.close.assert_called_once()
        self.assertIn("Kapitel 1", text)
        self.assertIn("Aufgabenstellung", text)
        self.assertIn("Seite 2", text)
        # Excess blank lines are collapsed.
        self.assertNotIn("\n\n\n", text)

    def test_pdf_respects_max_chars(self):
        path = self._write("big.pdf", b"%PDF fake", binary=True)

        page = MagicMock()
        page.get_text.return_value = "A" * 400
        doc = MagicMock()
        doc.page_count = 5
        doc.__getitem__.return_value = page

        fitz = MagicMock()
        fitz.open.return_value = doc

        with patch.object(ai_chat_service, "_load_fitz", return_value=fitz):
            text = extract_attachment_text(path, max_chars=300)

        self.assertLessEqual(len(text), 300)

    def test_pdf_without_fitz_returns_note(self):
        path = self._write("angabe.pdf", b"%PDF fake", binary=True)
        with patch.object(ai_chat_service, "_load_fitz", return_value=None):
            text = extract_attachment_text(path)
        self.assertIn("PyMuPDF", text)

    def test_extraction_exception_is_handled(self):
        path = self._write("broken.txt", "data")
        with patch.object(ai_chat_service, "_read_text_file", side_effect=OSError("boom")):
            text = extract_attachment_text(path)
        self.assertIn("Could not read file", text)
        self.assertIn("broken.txt", text)


class TestBuildTaskAiContext(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name
        self.task = Task(
            id="task-1",
            platform="moodle",
            course="AMEC",
            course_full="Angewandte Mechatronik",
            title="Aufgabe 03: Schrittmotor ansteuern",
            due_date_str="Freitag, 24. Okt., 23:59",
            status="offen",
            status_display="Noch offen",
            url="https://moodle.spengergasse.at/mod/assign/view.php?id=1",
            teacher="KRD",
            description="Entwickle einen Arduino-Sketch für den A4988 Treiber.",
            attachments=[
                TaskAttachment(name="schaltplan.pdf", url="https://example.com/1"),
                TaskAttachment(name="datenblatt.pdf", url="https://example.com/2"),
            ],
            details_loaded=True,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_german_context_contains_persona_and_metadata(self):
        context = build_task_ai_context(self.task, language="de")
        self.assertIn(
            "Du bist ein intelligenter, hilfsbereiter KI-Lernassistent für Schüler und Studierende",
            context,
        )
        self.assertIn("Angewandte Mechatronik", context)
        self.assertIn("Aufgabe 03: Schrittmotor ansteuern", context)
        self.assertIn("Freitag, 24. Okt., 23:59", context)
        self.assertIn("KRD", context)
        self.assertIn("Noch offen", context)
        self.assertIn("Entwickle einen Arduino-Sketch", context)
        self.assertIn("- schaltplan.pdf", context)
        self.assertIn("- datenblatt.pdf", context)
        self.assertIn("Antworte immer präzise, verständlich und schrittweise", context)

    def test_english_context_contains_persona_and_metadata(self):
        context = build_task_ai_context(self.task, language="en")
        self.assertIn("intelligent, helpful AI learning assistant", context)
        self.assertIn("Subject / Course: Angewandte Mechatronik", context)
        self.assertIn("Assignment Title: Aufgabe 03: Schrittmotor ansteuern", context)
        self.assertIn("Due Date: Freitag, 24. Okt., 23:59", context)
        self.assertIn("Teacher: KRD", context)
        self.assertIn("Status: Noch offen", context)
        self.assertIn("- schaltplan.pdf", context)
        self.assertIn("Always answer precisely, clearly, and step by step", context)

    def test_invalid_language_falls_back_to_german(self):
        context = build_task_ai_context(self.task, language="fr")
        self.assertIn("Du bist ein intelligenter", context)

    def test_local_files_are_extracted_and_appended(self):
        file_path = os.path.join(self.tmpdir, "angabe.txt")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write("Wichtiger Aufgabentext 123")

        context = build_task_ai_context(self.task, task_files=[file_path], language="de")
        self.assertIn("--- Datei: angabe.txt ---", context)
        self.assertIn("Wichtiger Aufgabentext 123", context)
        # Local files take precedence over the plain attachment list.
        self.assertNotIn("- schaltplan.pdf", context)

    def test_local_files_english_header(self):
        file_path = os.path.join(self.tmpdir, "spec.md")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write("# Specification")

        context = build_task_ai_context(self.task, task_files=[file_path], language="en")
        self.assertIn("--- File: spec.md ---", context)
        self.assertIn("# Specification", context)
        self.assertNotIn("- schaltplan.pdf", context)

    def test_empty_local_file_gets_placeholder(self):
        file_path = os.path.join(self.tmpdir, "empty.txt")
        open(file_path, "w", encoding="utf-8").close()

        context = build_task_ai_context(self.task, task_files=[file_path], language="de")
        self.assertIn("--- Datei: empty.txt ---", context)
        self.assertIn("Kein extrahierbarer Textinhalt", context)

    def test_no_attachments_message(self):
        task = Task(
            id="task-2",
            platform="manual",
            course="D",
            course_full="Deutsch",
            title="Erörterung",
            due_date_str="Morgen",
            status="offen",
            status_display="Open",
            url="",
            teacher="",
            description="",
            attachments=[],
        )
        context = build_task_ai_context(task, language="de")
        self.assertIn("Keine Anhänge", context)
        self.assertIn("Keine schriftliche Aufgabenbeschreibung", context)
        self.assertIn("Lehrkraft: -", context)


class TestSendAiChatMessageGemini(unittest.TestCase):
    MESSAGES = [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Erkläre die Aufgabe"},
    ]

    def _config(self, **overrides):
        cfg = {
            "provider": "gemini",
            "api_key": "test-key",
            "model": "gemini-2.0-flash",
            "base_url": "https://api.openai.com/v1",
            "language": "de",
        }
        cfg.update(overrides)
        return cfg

    @patch("services.ai_chat_service.requests.post")
    def test_success_builds_payload_and_returns_text(self, mock_post):
        mock_post.return_value = _gemini_success("  Die Lösung lautet 42.  ")

        result = send_ai_chat_message(
            self.MESSAGES, "SYSTEM PROMPT", config=self._config()
        )

        self.assertEqual(result, "Die Lösung lautet 42.")
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        url = args[0] if args else kwargs.get("url")
        self.assertIn("generativelanguage.googleapis.com", url)
        self.assertIn("gemini-2.0-flash:generateContent", url)
        self.assertIn("key=test-key", url)
        self.assertEqual(kwargs["timeout"], 45)

        payload = kwargs["json"]
        self.assertEqual(
            payload["system_instruction"]["parts"][0]["text"], "SYSTEM PROMPT"
        )
        self.assertEqual(
            [m["role"] for m in payload["contents"]], ["user", "model", "user"]
        )
        self.assertEqual(payload["contents"][1]["parts"][0]["text"], "Hi")

    @patch("services.ai_chat_service.requests.post")
    def test_custom_model_and_timeout(self, mock_post):
        mock_post.return_value = _gemini_success("ok")

        send_ai_chat_message(
            [{"role": "user", "content": "x"}],
            "s",
            config=self._config(model="gemini-2.5-pro"),
            timeout=7,
        )

        args, kwargs = mock_post.call_args
        self.assertIn("gemini-2.5-pro:generateContent", args[0])
        self.assertEqual(kwargs["timeout"], 7)

    @patch("services.ai_chat_service.requests.post")
    def test_api_error_returns_clean_message(self, mock_post):
        mock_post.return_value = _make_response(
            400,
            {"error": {"message": "API key not valid. Please pass a valid API key."}},
            text='{"error": ...}',
        )

        result = send_ai_chat_message(
            self.MESSAGES, "system", config=self._config()
        )

        self.assertTrue(result.startswith("Error:"))
        self.assertIn("API key not valid", result)
        self.assertNotIn("Traceback", result)

    @patch("services.ai_chat_service.requests.post")
    def test_rate_limit_error_is_surfaced(self, mock_post):
        mock_post.return_value = _make_response(
            429, {"error": {"message": "Resource has been exhausted (e.g. check quota)."}}
        )

        result = send_ai_chat_message(
            self.MESSAGES, "system", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("exhausted", result)

    @patch("services.ai_chat_service.requests.post")
    def test_error_without_json_uses_response_text(self, mock_post):
        mock_post.return_value = _make_response(
            500, None, text="Internal Server Error", json_error=ValueError("no json")
        )

        result = send_ai_chat_message(
            self.MESSAGES, "system", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Internal Server Error", result)

    @patch("services.ai_chat_service.requests.post")
    def test_unexpected_success_payload_is_handled(self, mock_post):
        mock_post.return_value = _make_response(200, {"candidates": []})

        result = send_ai_chat_message(
            self.MESSAGES, "system", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Unexpected response format", result)

    @patch("services.ai_chat_service.requests.post")
    def test_network_exception_is_handled(self, mock_post):
        mock_post.side_effect = ai_chat_service.requests.exceptions.ConnectionError(
            "no route to host"
        )

        result = send_ai_chat_message(
            self.MESSAGES, "system", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Could not reach Gemini", result)


class TestSendAiChatMessageOpenAI(unittest.TestCase):
    def _config(self, **overrides):
        cfg = {
            "provider": "openai_compatible",
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
            "base_url": "https://api.example.com/v1/",
            "language": "en",
        }
        cfg.update(overrides)
        return cfg

    @patch("services.ai_chat_service.requests.post")
    def test_success_builds_payload_and_returns_text(self, mock_post):
        mock_post.return_value = _openai_success("  Here is the answer.  ")

        result = send_ai_chat_message(
            [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Previous"},
                {"role": "user", "content": "Follow-up"},
            ],
            "SYSTEM",
            config=self._config(),
        )

        self.assertEqual(result, "Here is the answer.")
        args, kwargs = mock_post.call_args
        # Trailing slash of the base URL must be stripped.
        self.assertEqual(args[0], "https://api.example.com/v1/chat/completions")
        self.assertEqual(kwargs["timeout"], 45)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")

        payload = kwargs["json"]
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "SYSTEM"})
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "Question"})
        self.assertEqual(payload["messages"][2]["role"], "assistant")
        self.assertEqual(len(payload["messages"]), 4)

    @patch("services.ai_chat_service.requests.post")
    def test_defaults_are_used(self, mock_post):
        mock_post.return_value = _openai_success("ok")

        send_ai_chat_message(
            [{"role": "user", "content": "x"}],
            "s",
            config={"provider": "openai_compatible", "api_key": "k"},
        )

        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "gpt-4o-mini")

    @patch("services.ai_chat_service.requests.post")
    def test_api_error_returns_clean_message(self, mock_post):
        mock_post.return_value = _make_response(
            401,
            {"error": {"message": "Incorrect API key provided."}},
        )

        result = send_ai_chat_message(
            [{"role": "user", "content": "x"}], "s", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Incorrect API key provided", result)
        self.assertIn("401", result)

    @patch("services.ai_chat_service.requests.post")
    def test_error_without_json_uses_response_text(self, mock_post):
        mock_post.return_value = _make_response(
            503, None, text="Service Unavailable", json_error=ValueError("no json")
        )

        result = send_ai_chat_message(
            [{"role": "user", "content": "x"}], "s", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Service Unavailable", result)

    @patch("services.ai_chat_service.requests.post")
    def test_network_exception_is_handled(self, mock_post):
        mock_post.side_effect = ai_chat_service.requests.exceptions.Timeout("timed out")

        result = send_ai_chat_message(
            [{"role": "user", "content": "x"}], "s", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Could not reach the AI API", result)

    @patch("services.ai_chat_service.requests.post")
    def test_unexpected_success_payload_is_handled(self, mock_post):
        mock_post.return_value = _make_response(200, {"choices": []})

        result = send_ai_chat_message(
            [{"role": "user", "content": "x"}], "s", config=self._config()
        )

        self.assertIn("Error:", result)
        self.assertIn("Unexpected response format", result)


class TestSendAiChatMessageCommon(unittest.TestCase):
    def test_missing_api_key_returns_exact_error(self):
        result = send_ai_chat_message(
            [{"role": "user", "content": "Hallo"}],
            "system",
            config={"provider": "gemini", "api_key": "   "},
        )
        self.assertEqual(
            result,
            "Error: No API key configured. "
            "Please set your API key in Settings -> AI Configuration.",
        )

    @patch("services.ai_chat_service.requests.post")
    def test_config_is_loaded_when_none(self, mock_post):
        mock_post.return_value = _gemini_success("ok")
        with patch.object(
            ai_chat_service,
            "load_ai_chat_config",
            return_value={"provider": "gemini", "api_key": "k", "model": "m"},
        ) as mock_load:
            result = send_ai_chat_message(
                [{"role": "user", "content": "x"}], "s"
            )
        mock_load.assert_called_once()
        self.assertEqual(result, "ok")

    def test_unsupported_provider(self):
        result = send_ai_chat_message(
            [{"role": "user", "content": "x"}],
            "s",
            config={"provider": "unknown", "api_key": "k"},
        )
        self.assertIn("Error:", result)
        self.assertIn("Unsupported AI provider", result)


class TestAiConnection(unittest.TestCase):
    @patch("services.ai_chat_service.requests.post")
    def test_connection_success(self, mock_post):
        mock_post.return_value = _gemini_success("OK")

        ok, message = test_ai_connection(
            {"provider": "gemini", "api_key": "k", "model": "gemini-2.0-flash"}
        )

        self.assertTrue(ok)
        self.assertEqual(message, "Connection successful! Model responded.")
        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["system_instruction"]["parts"][0]["text"], "Test")
        self.assertEqual(payload["contents"][0]["parts"][0]["text"], "Hi, reply with OK")

    @patch("services.ai_chat_service.requests.post")
    def test_connection_failure_from_api(self, mock_post):
        mock_post.return_value = _make_response(
            403, {"error": {"message": "Permission denied"}}
        )

        ok, message = test_ai_connection(
            {"provider": "gemini", "api_key": "bad"}
        )

        self.assertFalse(ok)
        self.assertIn("Error:", message)
        self.assertIn("Permission denied", message)

    def test_connection_failure_without_api_key(self):
        ok, message = test_ai_connection({"provider": "gemini", "api_key": ""})
        self.assertFalse(ok)
        self.assertIn("No API key configured", message)

    @patch("services.ai_chat_service.requests.post")
    def test_connection_success_openai(self, mock_post):
        mock_post.return_value = _openai_success("OK")

        ok, message = test_ai_connection(
            {"provider": "openai_compatible", "api_key": "k"}
        )

        self.assertTrue(ok)
        self.assertEqual(message, "Connection successful! Model responded.")


class TestChatCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name
        self.cache_path = os.path.join(self.tmpdir, "cache", "ai_chats.json")
        self._patcher = patch.object(ai_chat_service, "CACHE_FILE", self.cache_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def _read_raw(self):
        with open(self.cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_load_missing_cache_returns_empty_list(self):
        self.assertEqual(load_task_chat_cache("unknown"), [])

    def test_save_and_load_roundtrip(self):
        messages = [
            {"role": "user", "content": "Hallo", "timestamp": 123456789},
            {"role": "assistant", "content": "Hi!", "timestamp": 123456799},
        ]
        save_task_chat_cache("task-1", messages)

        self.assertTrue(os.path.exists(self.cache_path))
        self.assertEqual(load_task_chat_cache("task-1"), messages)
        self.assertEqual(self._read_raw()["task-1"], messages)

    def test_save_preserves_other_tasks(self):
        save_task_chat_cache("task-1", [{"role": "user", "content": "A"}])
        save_task_chat_cache("task-2", [{"role": "user", "content": "B"}])

        raw = self._read_raw()
        self.assertIn("task-1", raw)
        self.assertIn("task-2", raw)
        self.assertEqual(load_task_chat_cache("task-1")[0]["content"], "A")

    def test_save_overwrites_existing_history(self):
        save_task_chat_cache("task-1", [{"role": "user", "content": "old"}])
        save_task_chat_cache("task-1", [{"role": "user", "content": "new"}])

        self.assertEqual(load_task_chat_cache("task-1")[0]["content"], "new")

    def test_clear_removes_only_requested_task(self):
        save_task_chat_cache("task-1", [{"role": "user", "content": "A"}])
        save_task_chat_cache("task-2", [{"role": "user", "content": "B"}])

        clear_task_chat_cache("task-1")

        self.assertEqual(load_task_chat_cache("task-1"), [])
        self.assertEqual(load_task_chat_cache("task-2")[0]["content"], "B")
        self.assertNotIn("task-1", self._read_raw())

    def test_clear_missing_task_is_noop(self):
        save_task_chat_cache("task-1", [{"role": "user", "content": "A"}])
        clear_task_chat_cache("does-not-exist")
        self.assertIn("task-1", self._read_raw())

    def test_cleanup_purges_only_inactive_tasks(self):
        save_task_chat_cache("open-1", [{"role": "user", "content": "A"}])
        save_task_chat_cache("open-2", [{"role": "user", "content": "B"}])
        save_task_chat_cache("closed-1", [{"role": "user", "content": "C"}])
        save_task_chat_cache("closed-2", [{"role": "user", "content": "D"}])

        removed = cleanup_ai_chats_cache({"open-1", "open-2"})

        self.assertEqual(removed, 2)
        raw = self._read_raw()
        self.assertEqual(set(raw.keys()), {"open-1", "open-2"})
        self.assertEqual(load_task_chat_cache("closed-1"), [])

    def test_cleanup_with_all_active_returns_zero(self):
        save_task_chat_cache("open-1", [{"role": "user", "content": "A"}])
        self.assertEqual(cleanup_ai_chats_cache({"open-1"}), 0)

    def test_cleanup_with_no_cache_returns_zero(self):
        self.assertEqual(cleanup_ai_chats_cache({"open-1"}), 0)

    def test_cleanup_with_empty_active_set_purges_everything(self):
        save_task_chat_cache("task-1", [{"role": "user", "content": "A"}])
        save_task_chat_cache("task-2", [{"role": "user", "content": "B"}])

        self.assertEqual(cleanup_ai_chats_cache(set()), 2)
        self.assertEqual(self._read_raw(), {})

    def test_corrupted_cache_is_tolerated(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            fh.write("{ not valid json")

        self.assertEqual(load_task_chat_cache("task-1"), [])

        # Saving afterwards repairs the file instead of crashing.
        save_task_chat_cache("task-1", [{"role": "user", "content": "A"}])
        self.assertEqual(self._read_raw()["task-1"][0]["content"], "A")


EXPLAIN_PROMPT_DE = (
    "Bitte erkläre mir diese Aufgabe verständlich, praxisnah und Schritt für Schritt."
)
EXPLAIN_PROMPT_EN = (
    "Please explain this assignment clearly, practically, and step-by-step."
)


class TestAiExplainedState(unittest.TestCase):
    """Tests for the persisted single-execution ``Ai Explain`` marker."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name
        self.cache_path = os.path.join(self.tmpdir, "cache", "ai_chats.json")
        self._patcher = patch.object(ai_chat_service, "CACHE_FILE", self.cache_path)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def _write_raw(self, data):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def _read_raw(self):
        with open(self.cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # -- is_task_ai_explained -------------------------------------------
    def test_empty_task_id_is_not_explained(self):
        self.assertFalse(is_task_ai_explained(""))
        self.assertFalse(is_task_ai_explained(None))

    def test_unknown_task_is_not_explained(self):
        self.assertFalse(is_task_ai_explained("unknown"))

    def test_task_without_messages_is_not_explained(self):
        self._write_raw({"task-1": []})
        self.assertFalse(is_task_ai_explained("task-1"))

    def test_marker_marks_task_as_explained(self):
        save_task_chat_cache("task-1", [{"role": "user", "content": "Hallo"}])
        set_task_ai_explained("task-1", True)
        self.assertTrue(is_task_ai_explained("task-1"))

    def test_marker_without_messages_is_not_explained(self):
        # A marker alone (no persisted messages) does not count.
        self._write_raw({"_explained_task_ids": ["task-1"]})
        self.assertFalse(is_task_ai_explained("task-1"))

    def test_retroactive_detection_german_prompt(self):
        save_task_chat_cache(
            "task-1",
            [
                {"role": "user", "content": EXPLAIN_PROMPT_DE},
                {"role": "assistant", "content": "Hier ist die Erklärung..."},
            ],
        )
        self.assertTrue(is_task_ai_explained("task-1"))

    def test_retroactive_detection_english_prompt(self):
        save_task_chat_cache(
            "task-1",
            [
                {"role": "user", "content": EXPLAIN_PROMPT_EN},
                {"role": "assistant", "content": "Here is the explanation..."},
            ],
        )
        self.assertTrue(is_task_ai_explained("task-1"))

    def test_retroactive_detection_via_is_explain_flag(self):
        save_task_chat_cache(
            "task-1",
            [
                {"role": "user", "content": "Something custom", "is_explain": True},
                {"role": "assistant", "content": "Answer"},
            ],
        )
        self.assertTrue(is_task_ai_explained("task-1"))

    def test_error_reply_is_not_counted_as_explained(self):
        for error_text in (
            "Error: Could not reach Gemini: boom",
            "AI request failed: timeout",
            "Error: No API key configured.",
        ):
            with self.subTest(error=error_text):
                save_task_chat_cache(
                    "task-1",
                    [
                        {"role": "user", "content": EXPLAIN_PROMPT_DE, "is_explain": True},
                        {"role": "assistant", "content": error_text},
                    ],
                )
                self.assertFalse(is_task_ai_explained("task-1"))

    def test_normal_conversation_is_not_explained(self):
        save_task_chat_cache(
            "task-1",
            [
                {"role": "user", "content": "Wie fange ich an?"},
                {"role": "assistant", "content": "Fang mit der Theorie an."},
            ],
        )
        self.assertFalse(is_task_ai_explained("task-1"))

    def test_explain_prompt_without_assistant_reply_is_not_explained(self):
        save_task_chat_cache(
            "task-1",
            [{"role": "user", "content": EXPLAIN_PROMPT_DE, "is_explain": True}],
        )
        self.assertFalse(is_task_ai_explained("task-1"))

    # -- set_task_ai_explained ------------------------------------------
    def test_set_marker_creates_list_and_deduplicates(self):
        set_task_ai_explained("task-1", True)
        set_task_ai_explained("task-1", True)
        set_task_ai_explained("task-2", True)

        raw = self._read_raw()
        self.assertEqual(raw["_explained_task_ids"], ["task-1", "task-2"])

    def test_set_marker_false_removes_all_occurrences(self):
        self._write_raw(
            {
                "task-1": [{"role": "user", "content": "x"}],
                "_explained_task_ids": ["task-1", "task-2", "task-1"],
            }
        )
        set_task_ai_explained("task-1", False)

        self.assertEqual(self._read_raw()["_explained_task_ids"], ["task-2"])
        self.assertFalse(is_task_ai_explained("task-1"))

    def test_set_marker_with_empty_task_id_is_noop(self):
        set_task_ai_explained("", True)
        set_task_ai_explained(None, True)
        self.assertFalse(os.path.exists(self.cache_path))

    def test_set_marker_repairs_invalid_marker_type(self):
        self._write_raw({
            "task-1": [{"role": "user", "content": "x"}],
            "_explained_task_ids": "broken",
        })
        set_task_ai_explained("task-1", True)
        self.assertEqual(self._read_raw()["_explained_task_ids"], ["task-1"])

    # -- clear_task_chat_cache ------------------------------------------
    def test_clear_resets_explained_state(self):
        save_task_chat_cache(
            "task-1",
            [
                {"role": "user", "content": EXPLAIN_PROMPT_DE, "is_explain": True},
                {"role": "assistant", "content": "Erklärung"},
            ],
        )
        set_task_ai_explained("task-1", True)
        self.assertTrue(is_task_ai_explained("task-1"))

        clear_task_chat_cache("task-1")

        self.assertFalse(is_task_ai_explained("task-1"))
        raw = self._read_raw()
        self.assertNotIn("task-1", raw)
        self.assertNotIn("task-1", raw.get("_explained_task_ids", []))

    def test_clear_only_removes_own_marker(self):
        set_task_ai_explained("task-1", True)
        set_task_ai_explained("task-2", True)

        clear_task_chat_cache("task-1")

        self.assertEqual(self._read_raw()["_explained_task_ids"], ["task-2"])

    # -- cleanup_ai_chats_cache -----------------------------------------
    def test_cleanup_purges_inactive_explained_ids(self):
        for task_id in ("open-1", "closed-1"):
            save_task_chat_cache(
                task_id,
                [
                    {"role": "user", "content": EXPLAIN_PROMPT_DE, "is_explain": True},
                    {"role": "assistant", "content": "Erklärung"},
                ],
            )
            set_task_ai_explained(task_id, True)

        removed = cleanup_ai_chats_cache({"open-1"})

        self.assertEqual(removed, 1)
        raw = self._read_raw()
        self.assertIn("open-1", raw)
        self.assertNotIn("closed-1", raw)
        self.assertEqual(raw["_explained_task_ids"], ["open-1"])
        self.assertTrue(is_task_ai_explained("open-1"))

    def test_cleanup_keeps_active_explained_ids(self):
        save_task_chat_cache("open-1", [{"role": "user", "content": "x"}])
        set_task_ai_explained("open-1", True)

        self.assertEqual(cleanup_ai_chats_cache({"open-1"}), 0)
        self.assertEqual(self._read_raw()["_explained_task_ids"], ["open-1"])

    def test_cleanup_purges_explained_ids_without_chat_history(self):
        # A dangling marker (no chat entry) is removed as well.
        self._write_raw({"_explained_task_ids": ["closed-1"]})

        self.assertEqual(cleanup_ai_chats_cache({"open-1"}), 0)
        self.assertEqual(self._read_raw()["_explained_task_ids"], [])

    def test_cleanup_preserves_other_underscore_keys(self):
        self._write_raw({
            "_last_active_task_id": "task-1",
            "_explained_task_ids": ["task-1"],
        })

        self.assertEqual(cleanup_ai_chats_cache({str("task-1")}), 0)
        raw = self._read_raw()
        self.assertEqual(raw["_last_active_task_id"], "task-1")
        self.assertEqual(raw["_explained_task_ids"], ["task-1"])


if __name__ == "__main__":
    unittest.main()
