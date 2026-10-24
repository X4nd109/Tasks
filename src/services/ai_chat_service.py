"""
ai_chat_service.py - Service for the interactive AI chat feature.

Responsibilities:
  * Extracting text from task attachments (PDF / plain text / source code).
  * Building the system prompt and task context sent to the AI provider.
  * Dispatching chat messages to Google Gemini or any OpenAI-compatible API.
  * Testing the configured connection.
  * Persisting per-task chat histories and cleaning up stale sessions.
"""

import json
import os
import re
import sys
import time
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from core.models import Task, TaskAttachment
from core.config import (
    CONFIG_DIR,
    WORKSPACE_DIR,
    load_ai_chat_config,
    save_ai_chat_config,
    DEFAULT_AI_CHAT_CONFIG,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The project keeps caches in <workspace>/cache (CONFIG_DIR is exactly that
# folder, with an automatic %LOCALAPPDATA% fallback when the install directory
# is read-only).
CACHE_FILE: str = os.path.join(CONFIG_DIR, "ai_chats.json")
AI_CHATS_CACHE_FILE: str = CACHE_FILE

CACHE_LOCK = threading.RLock()

TEXT_EXTENSIONS: Set[str] = {
    ".txt", ".md", ".py", ".c", ".cpp", ".java",
    ".html", ".css", ".json", ".csv", ".xml",
}

# Extensions that are definitely binary and never worth reading as text.
BINARY_EXTENSIONS: Set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tif", ".tiff",
    # Archives / packages
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".jar", ".war",
    # Office documents (not plain text)
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    # Executables / libraries / databases
    ".exe", ".dll", ".so", ".dylib", ".bin", ".msi", ".pyc", ".class", ".db", ".sqlite",
    # Media
    ".mp3", ".wav", ".mp4", ".avi", ".mkv", ".mov",
}

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

NO_API_KEY_ERROR = (
    "Error: No API key configured. "
    "Please set your API key in Settings -> AI Configuration."
)

FINAL_INSTRUCTION_DE = (
    "Antworte immer präzise, verständlich und schrittweise. "
    "Wenn der Schüler Fragen zur Aufgabe stellt, nutze alle obenstehenden Angaben und Inhalte."
)
FINAL_INSTRUCTION_EN = (
    "Always answer precisely, clearly, and step by step. "
    "When the student asks questions about the assignment, use all of the information and content above."
)


# ---------------------------------------------------------------------------
# Attachment text extraction
# ---------------------------------------------------------------------------

def _load_fitz():
    """Lazily import PyMuPDF so the module also works without it installed."""
    try:
        import fitz  # type: ignore
        return fitz
    except Exception:
        return None


def _basename(file_path: str) -> str:
    return os.path.basename(file_path) if file_path else ""


def _clean_pdf_text(text: str) -> str:
    """Collapse excessive whitespace produced by PDF extraction."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_likely_binary(path: str) -> bool:
    """Heuristic check for NUL bytes in the first few KB of a file."""
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(4096)
        return b"\x00" in chunk
    except Exception:
        return False


def _extract_pdf_text(file_path: str, max_chars: int) -> str:
    fitz = _load_fitz()
    if fitz is None:
        return "[PDF text extraction unavailable: PyMuPDF (fitz) is not installed]"

    doc = None
    try:
        doc = fitz.open(file_path)
        parts: List[str] = []
        total = 0
        for index in range(getattr(doc, "page_count", 0)):
            page = doc[index]
            page_text = _clean_pdf_text(page.get_text() or "")
            if not page_text:
                continue
            parts.append(page_text)
            total += len(page_text) + 2  # account for the joining newlines
            if total >= max_chars:
                break
        text = "\n\n".join(parts)
        return text[:max_chars]
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


def _read_text_file(file_path: str, max_chars: int) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as handle:
            text = handle.read()
    return text[:max_chars]


def extract_attachment_text(file_path: str, max_chars: int = 15000) -> str:
    """
    Extract readable text from an attachment.

    PDFs are read with PyMuPDF, common text/source files with UTF-8
    (latin-1 fallback). Binary files yield a short placeholder. All errors are
    handled gracefully so a missing or broken file never breaks a chat.
    """
    if not file_path or not os.path.exists(file_path):
        return ""

    if max_chars <= 0:
        return ""

    name = _basename(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            return _extract_pdf_text(file_path, max_chars)

        if ext in TEXT_EXTENSIONS:
            return _read_text_file(file_path, max_chars)

        if ext in BINARY_EXTENSIONS:
            return f"[Binary file: {name}]"

        # Unknown extension: try text, fall back to a binary placeholder.
        if _is_likely_binary(file_path):
            return f"[Binary file: {name}]"
        return _read_text_file(file_path, max_chars)
    except Exception as exc:  # pragma: no cover - defensive
        return f"[Could not read file: {name} ({exc})]"


# ---------------------------------------------------------------------------
# System prompt / task context
# ---------------------------------------------------------------------------

def _persona(language: str) -> str:
    if language == "en":
        return (
            "You are an intelligent, helpful AI learning assistant. "
            "You help with homework, projects, and exam preparation. "
            "Explain concepts in a way that is easy to understand and "
            "encourages the student to learn and solve problems independently."
        )
    return (
        "Du bist ein intelligenter, hilfsbereiter KI-Lernassistent für Schüler und Studierende. "
        "Du hilfst bei Hausübungen, Projekten und der Prüfungsvorbereitung. "
        "Erkläre Zusammenhänge verständlich und motiviere dazu, Aufgaben eigenständig zu lösen."
    )


def _format_attachments(task: Task, language: str) -> str:
    attachments: List[TaskAttachment] = list(getattr(task, "attachments", []) or [])
    names = [a.name for a in attachments if getattr(a, "name", None)]
    if not names:
        return "- (No attachments)" if language == "en" else "- (Keine Anhänge)"
    return "\n".join(f"- {name}" for name in names)


def build_task_ai_context(
    task: Task,
    task_files: Optional[List[str]] = None,
    language: str = "de",
) -> str:
    """
    Build the system prompt containing the AI persona plus the full task
    metadata, attachment names, and (optionally) extracted attachment text.
    """
    lang = (language or "de").strip().lower()
    if lang not in ["de", "en"]:
        lang = "de"

    subject = (task.course_full or task.course or "").strip()
    if not subject:
        subject = "Allgemein" if lang == "de" else "General"
    title = (task.title or "").strip() or ("Aufgabe" if lang == "de" else "Assignment")
    due_date = (task.due_date_str or "").strip() or ("Keine Fälligkeit" if lang == "de" else "No due date")
    teacher = (task.teacher or "").strip() or "-"
    status = (task.status_display or "").strip() or "-"
    description = (task.description or "").strip()
    if not description:
        description = (
            "*(Keine schriftliche Aufgabenbeschreibung im System hinterlegt)*"
            if lang == "de"
            else "*(No written assignment description provided)*"
        )

    files = [f for f in (task_files or []) if f]

    if lang == "en":
        lines = [
            _persona(lang),
            "",
            "### Assignment Data",
            f"- Subject / Course: {subject}",
            f"- Assignment Title: {title}",
            f"- Due Date: {due_date}",
            f"- Teacher: {teacher}",
            f"- Status: {status}",
            "",
            "### Description / Instructions",
            description,
            "",
        ]
        if files:
            lines.append("### Attachments and Extracted Content")
            for path in files:
                extracted = extract_attachment_text(path)
                if not extracted:
                    extracted = "[No extractable text content]"
                lines.append(f"--- File: {_basename(path)} ---")
                lines.append(extracted)
                lines.append("")
        else:
            lines.append("### Attachments")
            lines.append(_format_attachments(task, lang))
            lines.append("")
        lines.append(FINAL_INSTRUCTION_EN)
        return "\n".join(lines)

    lines = [
        _persona(lang),
        "",
        "### Aufgabendaten",
        f"- Fach / Kurs: {subject}",
        f"- Titel der Aufgabe: {title}",
        f"- Fälligkeit: {due_date}",
        f"- Lehrkraft: {teacher}",
        f"- Status: {status}",
        "",
        "### Beschreibung / Angabe",
        description,
        "",
    ]
    if files:
        lines.append("### Anhänge und extrahierte Inhalte")
        for path in files:
            extracted = extract_attachment_text(path)
            if not extracted:
                extracted = "[Kein extrahierbarer Textinhalt]"
            lines.append(f"--- Datei: {_basename(path)} ---")
            lines.append(extracted)
            lines.append("")
    else:
        lines.append("### Anhänge")
        lines.append(_format_attachments(task, lang))
        lines.append("")
    lines.append(FINAL_INSTRUCTION_DE)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API communication
# ---------------------------------------------------------------------------

def _error_message(response, payload: Optional[dict] = None) -> str:
    """Extract a human-readable message from an API error response."""
    data = payload
    if data is None:
        try:
            data = response.json()
        except Exception:
            data = None

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        elif isinstance(error, str) and error:
            return error
        if data.get("message"):
            return str(data["message"])

    text = (getattr(response, "text", "") or "").strip()
    return text or f"HTTP {getattr(response, 'status_code', 'unknown')}"


def _post_json(url: str, payload: dict, timeout: int, headers: Optional[dict] = None):
    return requests.post(url, json=payload, timeout=timeout, headers=headers)


def _send_gemini(
    messages: List[Dict[str, str]],
    system_prompt: str,
    config: Dict[str, Any],
    api_key: str,
    timeout: int,
) -> str:
    model = str(config.get("model") or DEFAULT_GEMINI_MODEL).strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )

    contents = []
    for message in messages:
        role = "user" if str(message.get("role", "user")).lower() == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": str(message.get("content", ""))}],
        })

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
    }

    try:
        response = _post_json(url, payload, timeout)
    except requests.exceptions.RequestException as exc:
        return f"Error: Could not reach Gemini: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return f"Error: Unexpected Gemini request failure: {exc}"

    data = None
    try:
        data = response.json()
    except Exception:
        data = None

    if response.status_code == 200:
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return str(text).strip()
        except (KeyError, IndexError, TypeError):
            return "Error: Unexpected response format from Gemini API."

    return f"Error: Gemini API error: {_error_message(response, data)}"


def _send_openai_compatible(
    messages: List[Dict[str, str]],
    system_prompt: str,
    config: Dict[str, Any],
    api_key: str,
    timeout: int,
) -> str:
    base_url = str(config.get("base_url") or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model = str(config.get("model") or DEFAULT_OPENAI_MODEL).strip()
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload_messages = [{"role": "system", "content": system_prompt}]
    for message in messages:
        payload_messages.append({
            "role": str(message.get("role", "user")),
            "content": str(message.get("content", "")),
        })

    payload = {"model": model, "messages": payload_messages}

    try:
        response = _post_json(url, payload, timeout, headers=headers)
    except requests.exceptions.RequestException as exc:
        return f"Error: Could not reach the AI API: {exc}"
    except Exception as exc:  # pragma: no cover - defensive
        return f"Error: Unexpected AI API request failure: {exc}"

    data = None
    try:
        data = response.json()
    except Exception:
        data = None

    if response.status_code == 200:
        try:
            text = data["choices"][0]["message"]["content"]
            return str(text).strip()
        except (KeyError, IndexError, TypeError):
            return "Error: Unexpected response format from the AI API."

    return (
        f"Error: AI API error (HTTP {response.status_code}): "
        f"{_error_message(response, data)}"
    )


def send_ai_chat_message(
    messages: List[Dict[str, str]],
    system_prompt: str,
    config: Optional[Dict[str, Any]] = None,
    timeout: int = 45,
) -> str:
    """
    Send a chat conversation to the configured provider and return the reply
    text. Any failure is reported as a string starting with ``Error:`` so the
    caller never has to deal with exceptions.
    """
    cfg = config if isinstance(config, dict) else load_ai_chat_config()
    api_key = str(cfg.get("api_key", "") or "").strip()
    if not api_key:
        return NO_API_KEY_ERROR

    provider = str(cfg.get("provider", "gemini") or "gemini").strip().lower()

    if provider == "gemini":
        return _send_gemini(messages, system_prompt, cfg, api_key, timeout)

    if provider == "openai_compatible":
        return _send_openai_compatible(messages, system_prompt, cfg, api_key, timeout)

    return f"Error: Unsupported AI provider '{provider}'."


def test_ai_connection(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Send a tiny probe message to verify that the configured endpoint works.

    Returns ``(True, message)`` on success and ``(False, error)`` otherwise.
    """
    try:
        reply = send_ai_chat_message(
            [{"role": "user", "content": "Hi, reply with OK"}],
            "Test",
            config=config,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Error: {exc}"

    if not reply or reply.strip().startswith("Error:"):
        return False, reply or "Error: Empty response from AI provider."

    return True, "Connection successful! Model responded."


def fetch_available_models(api_key: str, provider: Optional[str] = None, base_url: str = "") -> List[Tuple[str, str]]:
    """
    Queries Google Gemini or OpenAI-compatible endpoint to list all available models for the given API key.
    Returns a list of (display_label, model_id) tuples suitable for a Textual Select widget.
    """
    key = (api_key or "").strip()
    default_gemini = [
        ("Gemini 2.0 Flash (Recommended / Fast)", "gemini-2.0-flash"),
        ("Gemini 1.5 Flash (Free Tier)", "gemini-1.5-flash"),
        ("Gemini 1.5 Pro (Complex Reasoning)", "gemini-1.5-pro"),
    ]
    if not key:
        return default_gemini

    # Auto-detect provider if not explicitly given
    if not provider:
        provider = "openai_compatible" if key.startswith("sk-") else "gemini"

    if provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        try:
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                data = res.json()
                raw_models = data.get("models", [])
                out = []
                for m in raw_models:
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        m_id = m.get("name", "").replace("models/", "")
                        d_name = m.get("displayName", m_id)
                        label = f"{d_name} ({m_id})"
                        out.append((label, m_id))
                if out:
                    def _prio(x):
                        mid = x[1].lower()
                        if "2.0-flash" in mid and "thinking" not in mid:
                            return 0
                        if "1.5-flash" in mid:
                            return 1
                        if "pro" in mid:
                            return 2
                        return 10
                    out.sort(key=_prio)
                    return out
        except Exception:
            pass
        return default_gemini
    else:
        url = f"{base_url.rstrip('/')}/models" if base_url else "https://api.openai.com/v1/models"
        headers = {"Authorization": f"Bearer {key}"}
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                raw_models = data.get("data", [])
                out = [(m.get("id"), m.get("id")) for m in raw_models if m.get("id")]
                if out:
                    return out
        except Exception:
            pass
        return [
            ("gpt-4o-mini (Fast & Cheap)", "gpt-4o-mini"),
            ("gpt-4o (High Intelligence)", "gpt-4o"),
        ]


# ---------------------------------------------------------------------------
# Chat cache persistence
# ---------------------------------------------------------------------------

def _ensure_cache_dir() -> None:
    directory = os.path.dirname(CACHE_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _read_cache() -> Dict[str, Any]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(data: Dict[str, Any]) -> None:
    _ensure_cache_dir()
    tmp_path = f"{CACHE_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp_path, CACHE_FILE)


def load_task_chat_cache(task_id: str) -> List[Dict[str, Any]]:
    """Return the persisted chat history for a task (empty list if none)."""
    if not task_id:
        return []
    with CACHE_LOCK:
        data = _read_cache()
    messages = data.get(str(task_id))
    if isinstance(messages, list):
        return [m for m in messages if isinstance(m, dict)]
    return []


def save_task_chat_cache(task_id: str, messages: List[Dict[str, Any]]) -> None:
    """Persist the chat history for a single task."""
    if not task_id:
        return
    with CACHE_LOCK:
        data = _read_cache()
        data[str(task_id)] = list(messages or [])
        try:
            _write_cache(data)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: Could not save AI chat cache: {exc}", file=sys.stderr)


def clear_task_chat_cache(task_id: str) -> None:
    """Remove the persisted chat history of a single task."""
    if not task_id:
        return
    with CACHE_LOCK:
        data = _read_cache()
        if str(task_id) not in data:
            return
        data.pop(str(task_id), None)
        try:
            _write_cache(data)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: Could not clear AI chat cache: {exc}", file=sys.stderr)


def load_last_active_ai_task_id() -> Optional[str]:
    """Return the ID of the task that was last active in the AI assistant."""
    with CACHE_LOCK:
        data = _read_cache()
    val = data.get("_last_active_task_id")
    return str(val) if val else None


def save_last_active_ai_task_id(task_id: Optional[str]) -> None:
    """Save the ID of the task that was last active in the AI assistant (or clear if None/empty)."""
    with CACHE_LOCK:
        data = _read_cache()
        if not task_id:
            data.pop("_last_active_task_id", None)
        else:
            data["_last_active_task_id"] = str(task_id)
        try:
            _write_cache(data)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: Could not save last active task ID: {exc}", file=sys.stderr)


def cleanup_ai_chats_cache(active_open_task_ids: Set[str]) -> int:
    """
    Purge chat histories whose task is no longer open/active.

    Returns the number of removed chat sessions.
    """
    active = {str(tid) for tid in (active_open_task_ids or set())}

    with CACHE_LOCK:
        data = _read_cache()
        if not data:
            return 0

        stale_keys = [key for key in data.keys() if str(key) not in active and not str(key).startswith("_")]
        if not stale_keys:
            return 0

        for key in stale_keys:
            data.pop(key, None)

        try:
            _write_cache(data)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Warning: Could not clean AI chat cache: {exc}", file=sys.stderr)
            return 0

    return len(stale_keys)
