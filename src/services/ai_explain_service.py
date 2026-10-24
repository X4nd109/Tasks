"""
ai_explain_service.py - Service für die Generierung von AI-Erklärungsprompts,
Zwischenablage-Kopieren und Browser-Öffnung für Aufgaben.
"""

import os
import sys
import urllib.parse
import webbrowser
from typing import Optional, Tuple

from core.models import Task
from core.config import load_ai_explain_config, AI_EXPLAIN_PRESETS


def build_ai_explain_prompt(task: Task, language: str = "de") -> str:
    """
    Erstellt einen strukturierten, hochwertigen Prompt für KI-Assistenten
    basierend auf den Metadaten und Inhalten einer Aufgabe.
    """
    lang = (language or "de").strip().lower()
    if lang not in ["de", "en"]:
        lang = "de"

    if task.course and task.course_full and task.course.strip() != task.course_full.strip():
        subject = f"{task.course.strip()} ({task.course_full.strip()})"
    else:
        subject = task.course_full or task.course or "Allgemein"
    title = task.title.strip() if task.title else "Aufgabe"
    due_date = task.due_date_str if task.due_date_str else ("Keine Fälligkeit" if lang == "de" else "No due date")
    teacher = task.teacher.strip() if task.teacher else ""
    description = task.description.strip() if task.description else ""

    if not description:
        description = (
            "*(Keine schriftliche Aufgabenbeschreibung im System hinterlegt)*"
            if lang == "de"
            else "*(No written assignment description provided)*"
        )

    # Dateianhänge formatieren
    attachments = getattr(task, "attachments", []) or []
    if attachments:
        att_lines = [f"- {a.name}" for a in attachments if getattr(a, "name", None)]
        attachments_text = "\n".join(att_lines) if att_lines else (
            "- Keine Dateianhänge vorhanden" if lang == "de" else "- No attachments present"
        )
    else:
        attachments_text = "- Keine Dateianhänge vorhanden" if lang == "de" else "- No attachments present"

    if lang == "de":
        teacher_line = f"\n- **Lehrkraft:** {teacher}" if teacher else ""
        prompt = (
            "Bitte erkläre mir die folgende Schulaufgabe verständlich, praxisnah und Schritt für Schritt auf Deutsch. "
            "Gehe dabei auf die Aufgabenstellung ein und erkläre, wie man am besten an die Lösung herangeht.\n\n"
            "### Aufgabe:\n"
            f"- **Fach:** {subject}\n"
            f"- **Titel:** {title}\n"
            f"- **Fälligkeit:** {due_date}"
            f"{teacher_line}\n\n"
            "### Angabe / Beschreibung:\n"
            f"{description}\n\n"
            "### Dazugehörige Dateien / Anhänge:\n"
            f"{attachments_text}\n"
        )
    else:
        teacher_line = f"\n- **Teacher:** {teacher}" if teacher else ""
        prompt = (
            "Please explain the following school assignment clearly, practically, and step-by-step in English. "
            "Focus on the requirements and provide guidance on how to approach and solve the task.\n\n"
            "### Assignment:\n"
            f"- **Subject:** {subject}\n"
            f"- **Title:** {title}\n"
            f"- **Due date:** {due_date}"
            f"{teacher_line}\n\n"
            "### Description / Instructions:\n"
            f"{description}\n\n"
            "### Associated Attachments / Files:\n"
            f"{attachments_text}\n"
        )

    return prompt


def copy_to_clipboard(text: str) -> bool:
    """
    Kopiert den übergebenen Text plattformübergreifend in die System-Zwischenablage.
    Nutzt prioritär pyperclip, mit solidem ctypes/Windows-Fallback.
    """
    if not text:
        return False

    # Stufe 1: pyperclip (falls verfügbar)
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    # Stufe 2: Natives Windows API via ctypes
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            GMEM_MOVEABLE = 0x0002
            CF_UNICODETEXT = 13

            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    encoded = text.encode("utf-16le") + b"\x00\x00"
                    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
                    if h_mem:
                        p_mem = kernel32.GlobalLock(h_mem)
                        if p_mem:
                            ctypes.memmove(p_mem, encoded, len(encoded))
                            kernel32.GlobalUnlock(h_mem)
                            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                            return True
                finally:
                    user32.CloseClipboard()
        except Exception:
            pass

    # Stufe 3: Windows clip.exe / PowerShell Fallback
    if sys.platform == "win32":
        try:
            import subprocess
            proc = subprocess.Popen(
                ["clip"],
                stdin=subprocess.PIPE,
                shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            )
            proc.communicate(text.encode("utf-16le"))
            return proc.returncode == 0
        except Exception:
            pass

    return False


def get_ai_explain_url(prompt: str, config: Optional[dict] = None) -> str:
    """
    Ermittelt die Ziel-URL basierend auf der Konfiguration.
    Ersetzt {prompt} durch den URL-kodierten Prompt, falls vorhanden.
    """
    cfg = config if isinstance(config, dict) else load_ai_explain_config()
    template = cfg.get("url_template", "").strip() or "https://gemini.google.com/app"

    if "{prompt}" in template:
        encoded_prompt = urllib.parse.quote(prompt)
        return template.replace("{prompt}", encoded_prompt)
    return template


def launch_desktop_app(app_path: str) -> bool:
    """Launches a desktop executable application in the background."""
    if not app_path or not os.path.exists(app_path):
        return False
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([app_path], creationflags=flags)
        return True
    except Exception as e:
        logger.warning(f"Failed to launch desktop app '{app_path}': {e}")
        return False


def open_ai_explain(task: Task, config: Optional[dict] = None) -> Tuple[bool, str, str]:
    """
    Generiert den Prompt für die übergebene Aufgabe, kopiert ihn in die
    Zwischenablage und öffnet entweder die Desktop-App (.exe) oder die konfigurierte Web-URL.

    Rückgabe:
        (success, prompt_text, target_url_or_app_path)
    """
    cfg = config if isinstance(config, dict) else load_ai_explain_config()
    lang = cfg.get("language", "de")
    prompt = build_ai_explain_prompt(task, language=lang)
    copied = copy_to_clipboard(prompt)

    provider = cfg.get("provider", "gemini")
    app_path = cfg.get("app_path")

    if provider == "app" and app_path and os.path.exists(app_path):
        launched = launch_desktop_app(app_path)
        return copied or launched, prompt, app_path

    url = get_ai_explain_url(prompt, config=cfg)
    opened = False
    try:
        opened = bool(webbrowser.open(url))
    except Exception:
        pass

    success = copied or opened
    return success, prompt, url
