"""
task_manager.py - Zentrale Verwaltung für Moodle- und Teams-Aufgaben.
Übernimmt Zusammenführung, Sortierung, Caching und Filterung.
"""

import datetime
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple


from config import CACHE_FILE, DELETED_TASKS_FILE, APP_DELETED_TASKS_FILE, DELETED_MANUAL_TASKS_FILE, APP_DELETED_MANUAL_TASKS_FILE, HIDDEN_TASKS_FILE, APP_HIDDEN_TASKS_FILE, CUSTOM_TASKS_FILE, APP_CUSTOM_TASKS_FILE, extract_teacher, is_platform_enabled
from models import Task
import moodle_service
import teams_service


def parse_deadline_for_sorting(due_str: str) -> float:
    """Berechnet einen Näherungs-Timestamp für die chronologische Sortierung."""
    if not due_str or any(kw in due_str.lower() for kw in ["keine", "none", "no deadline", "no due"]):
        return datetime.datetime.now().timestamp() + 365 * 86400  # Weit in der Zukunft

    now = datetime.datetime.now()
    lower = due_str.lower().strip()

    # Überfällig / Gestern / Vor X Tagen / Overdue / Yesterday
    if any(kw in lower for kw in ["überfällig", "ueberfaellig", "overdue", "gestern", "yesterday", "vor "]):
        return now.timestamp() - 86400

    # Heute / Today
    if "heute" in lower or "today" in lower:
        m_time = re_search_time(lower)
        if m_time:
            h, m = m_time
            return now.replace(hour=h, minute=m, second=0).timestamp()
        return now.timestamp()

    # Morgen / Tomorrow
    if "morgen" in lower or "tomorrow" in lower:
        tomorrow = now + datetime.timedelta(days=1)
        m_time = re_search_time(lower)
        if m_time:
            h, m = m_time
            return tomorrow.replace(hour=h, minute=m, second=0).timestamp()
        return tomorrow.timestamp()

    # Datumsparser für Datumsangaben (z.B. "15.10. 23:59", "15.10.2026 23:59", "Dienstag, 29. September, 00:00" oder "12. Okt., 23:59")
    months = {
        "jan": 1, "jän": 1, "feb": 2, "mär": 3, "mar": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12
    }

    import re
    # 1. Numerisches europäisches Format: DD.MM. oder DD.MM.YYYY
    m_num = re.search(r"(\d{1,2})\.(\d{1,2})\.?(?:\s*(\d{4}))?", due_str)
    if m_num and not re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)", due_str):
        day = int(m_num.group(1))
        mon = int(m_num.group(2))
        year = int(m_num.group(3)) if m_num.group(3) else now.year
        if mon < now.month - 2 and not m_num.group(3):
            year += 1
        h, min_ = 23, 59
        m_time = re_search_time(lower)
        if m_time:
            h, min_ = m_time
        try:
            target_dt = datetime.datetime(year, mon, day, h, min_, 0)
            return target_dt.timestamp()
        except ValueError:
            pass

    # 2. Textuelles Monatsformat
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)", due_str)
    if m:
        day = int(m.group(1))
        mon_str = m.group(2).lower()[:3]
        mon = months.get(mon_str, now.month)
        year = now.year
        m_yr = re.search(r"\b(20\d\d)\b", due_str)
        if m_yr:
            year = int(m_yr.group(1))
        elif mon < now.month - 2:
            year += 1

        h, min_ = 23, 59
        m_time = re_search_time(lower)
        if m_time:
            h, min_ = m_time

        try:
            target_dt = datetime.datetime(year, mon, day, h, min_, 0)
            return target_dt.timestamp()
        except ValueError:
            pass

    return now.timestamp() + 30 * 86400


def re_search_time(text: str) -> Optional[Tuple[int, int]]:
    import re
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except ValueError:
            pass
    return None


def task_sort_key(t: Task):
    is_done = 1 if t.is_completed else 0
    is_welcome = 0 if t.id == "manual_welcome_setup_guide" else 1
    is_over = 0 if t.is_overdue else 1
    ts = t.due_timestamp or (time.time() + 9999999)
    return (is_done, is_welcome, is_over, ts)


class TaskManager:
    def __init__(self, autostart_prefetch: bool = True):
        self.autostart_prefetch = autostart_prefetch
        self.tasks: List[Task] = []
        self.hidden_ids: set = set()
        self.deleted_manual_ids: set = set()
        self.last_sync: Optional[float] = None
        self._cache_lock = threading.RLock()
        self._playwright_lock = threading.Lock()
        self._prefetch_thread: Optional[threading.Thread] = None
        self._stop_prefetch = False
        self._is_shutting_down = False

        self.load_deleted_tasks()
        loaded = self.load_cache()
        custom = self.load_custom_tasks()
        if custom:
            with self._cache_lock:
                existing_ids = {t.id for t in self.tasks}
                for ct in custom:
                    if ct.id not in existing_ids:
                        self.tasks.append(ct)
                        existing_ids.add(ct.id)
                self.tasks.sort(key=task_sort_key)

        # Sicherstellen: Beim allerersten Start (egal ob schon Aufgaben existieren oder nicht)
        # wird die Getting-Started-Aufgabe immer garantiert geladen und angezeigt!
        self._ensure_welcome_task_on_first_run()

        # Nach einem Versions-Update: Welcome-Aufgabe garantieren (ent-löschen & auf Open zurücksetzen)
        self._check_and_apply_version_update()

        if (loaded or custom) and self.autostart_prefetch:
            self.start_background_prefetch()

    @staticmethod
    def create_welcome_task() -> Task:
        now_ts = datetime.datetime.now().timestamp()
        return Task(
            id="manual_welcome_setup_guide",
            platform="manual",
            course="SETUP",
            course_full="Getting Started",
            title="Welcome to Aufgaben Detector! Complete your setup",
            due_date_str="Action required",
            status="open",
            status_display="Open",
            url="",
            teacher="INFO",
            description=(
                "Welcome to Aufgaben Detector!\n\n"
                "Please complete your initial setup:\n"
                "1. Student Profile: Click '⚙️ Settings' in the bottom bar, then '⚙️ School & Student Config' (set your name, class, and school details for excuse PDFs).\n"
                "2. School Platform Logins: Click '⚙️ Settings', then '🔑 Login':\n"
                "   - '👥 Teams Login' to sign in to Microsoft Teams\n"
                "   - '🎓 Moodle Login' to sign in to Moodle\n"
                "   - '📅 WebUntis Login' to sign in to WebUntis\n"
                "3. In-App AI Assistant: Click '⚙️ Settings' -> '🤖 AI Configuration' (enter your free Google Gemini API key or OpenAI key).\n"
                "   - Press 'I' or click '🤖 Ai' in the bottom bar anytime to chat with the AI assistant about any assignment with automatic PDF & code extraction!\n"
                "   - In any task's details, click '🤖 Ai Explain' [A] for an instant step-by-step walkthrough.\n"
                "4. Git Cloud-Sync (sync tasks & exams across PC and Laptop):\n"
                "   - Create a private repository on GitHub (e.g. 'aufgaben-backup')\n"
                "   - In the app, click '⚙️ Settings' -> '🔑 Login' -> '🐙 Git Cloud-Sync', and enter your Repo URL & Token\n"
                "5. Synchronize: Click '🔄 Sync' [R] in the bottom bar to fetch and detect all your assignments!\n\n"
                "Tip: Click '✓ Mark as Completed' below to finish this guide, or '🗑️ Delete' to remove it."
            ),
            details_loaded=True,
            due_timestamp=now_ts + 86400 * 2,
        )

    def _check_and_apply_version_update(self) -> None:
        """Prüft, ob die Anwendung aktualisiert wurde (neue APP_VERSION oder Update-Flag).
        Falls ja, wird die Getting-Started-Aufgabe ent-löscht, aktualisiert und als Open an den Anfang gesetzt.
        """
        import tempfile
        from config import APP_VERSION, CONFIG_DIR, DATA_DIR
        version_files = [
            os.path.join(DATA_DIR, "last_version.txt"),
            os.path.join(CONFIG_DIR, "last_version.txt"),
        ]
        last_version = None
        for vf in version_files:
            if os.path.exists(vf):
                try:
                    with open(vf, "r", encoding="utf-8") as f:
                        last_version = f.read().strip()
                        if last_version:
                            break
                except Exception:
                    pass

        # Update-Flag aus In-App Update Runner prüfen
        update_flag = os.path.join(tempfile.gettempdir(), "AufgabenDetector_Update", "update_just_applied.txt")
        has_update_flag = os.path.exists(update_flag)
        if has_update_flag:
            try:
                os.remove(update_flag)
            except Exception:
                pass

        markers = [
            os.path.join(CONFIG_DIR, ".first_run_completed"),
            os.path.join(DATA_DIR, ".first_run_completed"),
        ]
        has_first_run_marker = any(os.path.exists(m) for m in markers)

        is_update = has_update_flag or (last_version is not None and last_version != APP_VERSION) or (last_version is None and has_first_run_marker)

        # Version persistieren
        for vf in version_files:
            try:
                os.makedirs(os.path.dirname(vf), exist_ok=True)
                with open(vf, "w", encoding="utf-8") as f:
                    f.write(APP_VERSION)
            except Exception:
                pass

        if is_update:
            welcome_id = "manual_welcome_setup_guide"
            welcome_task = self.create_welcome_task()
            with self._cache_lock:
                # 1. Aus gelöschten Listen austragen
                if welcome_id in self.deleted_manual_ids:
                    self.deleted_manual_ids.discard(welcome_id)
                    self.save_deleted_manual_tasks(auto_push=False)
                if welcome_id in self.hidden_ids:
                    self.hidden_ids.discard(welcome_id)
                    self.save_hidden_tasks(auto_push=False)

                # 2. In den Aufgaben wiederherstellen / auf Open setzen
                existing = next((t for t in self.tasks if t.id == welcome_id), None)
                if existing:
                    existing.status = "open"
                    existing.status_display = "Open"
                    existing.title = welcome_task.title
                    existing.description = welcome_task.description
                    existing.course_full = welcome_task.course_full
                    existing.due_date_str = welcome_task.due_date_str
                    existing.due_timestamp = welcome_task.due_timestamp
                else:
                    self.tasks.insert(0, welcome_task)

                self.tasks.sort(key=task_sort_key)
                self.save_custom_tasks(auto_push=False)

    def _ensure_welcome_task_on_first_run(self) -> None:
        """Stellt sicher, dass beim allerersten Start einer Installation immer die Welcome-Aufgabe existiert."""
        from config import CONFIG_DIR, WORKSPACE_DIR
        markers = [
            os.path.join(CONFIG_DIR, ".first_run_completed"),
            os.path.join(WORKSPACE_DIR, ".first_run_completed"),
        ]
        is_first_run = not any(os.path.exists(m) for m in markers)
        welcome_id = "manual_welcome_setup_guide"
        if is_first_run:
            with self._cache_lock:
                if welcome_id not in [t.id for t in self.tasks] and welcome_id not in self.deleted_ids:
                    welcome_task = self.create_welcome_task()
                    self.tasks.insert(0, welcome_task)
                    self.tasks.sort(key=task_sort_key)
                    self.save_custom_tasks(auto_push=False)
            for m in markers:
                try:
                    os.makedirs(os.path.dirname(m), exist_ok=True)
                    with open(m, "w", encoding="utf-8") as f:
                        f.write(f"first_run={datetime.datetime.now().isoformat()}\n")
                    break
                except Exception:
                    pass

    def load_custom_tasks(self) -> List[Task]:
        """Loads manually created tasks from disk.
        If no custom tasks file exists (clean install), provides a welcome setup guide task in English.
        """
        custom_tasks: List[Task] = []
        seen_ids = set()
        file_found = False
        for path in [CUSTOM_TASKS_FILE, APP_CUSTOM_TASKS_FILE]:
            if os.path.exists(path):
                file_found = True
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    t = Task.from_dict(item)
                                    if t.id not in seen_ids and t.id not in self.deleted_ids:
                                        custom_tasks.append(t)
                                        seen_ids.add(t.id)
                except Exception as e:
                    print(f"Warning: Could not load manual tasks from {path}: {e}", file=sys.stderr)

        # Fallback for clean install: No custom tasks file exists yet and task wasn't previously deleted
        if not file_found and not custom_tasks and "manual_welcome_setup_guide" not in self.deleted_ids:
            custom_tasks.append(self.create_welcome_task())

        return custom_tasks

    def reload_custom_tasks(self) -> None:
        """Lädt gelöschte und manuelle Aufgaben nach externen Änderungen (z.B. Git-Sync) neu ein."""
        self.load_deleted_tasks()
        custom = self.load_custom_tasks()
        with self._cache_lock:
            # Bestehende manuelle Tasks entfernen
            self.tasks = [t for t in self.tasks if t.platform not in ["manual", "custom"]]
            existing_ids = {t.id for t in self.tasks}
            for ct in custom:
                if ct.id not in self.deleted_ids and ct.id not in existing_ids:
                    self.tasks.append(ct)
                    existing_ids.add(ct.id)
            self.tasks.sort(key=task_sort_key)


    def save_custom_tasks(self, auto_push: bool = True):
        """Saves manually created tasks permanently."""
        with self._cache_lock:
            seen = set()
            custom_tasks = []
            for t in self.tasks:
                if t.platform in ["manual", "custom"] and t.id not in seen and t.id not in self.deleted_ids:
                    seen.add(t.id)
                    custom_tasks.append(t)
            for path in [CUSTOM_TASKS_FILE, APP_CUSTOM_TASKS_FILE]:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump([t.to_dict() for t in custom_tasks], f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Warning: Could not save manual tasks to {path}: {e}", file=sys.stderr)
        if auto_push:
            try:
                from git_sync_service import is_git_configured, GitSyncService
                if is_git_configured():
                    GitSyncService.async_push("Update custom tasks")
            except Exception:
                pass

    def add_task(self, task: Task):
        """Fügt eine manuell erstellte Aufgabe hinzu und speichert sie ab."""
        with self._cache_lock:
            existing_idx = next((i for i, t in enumerate(self.tasks) if t.id == task.id), None)
            if existing_idx is not None:
                self.tasks[existing_idx] = task
            else:
                self.tasks.append(task)

            def sort_key(t: Task):
                is_done = 1 if t.is_completed else 0
                is_over = 0 if t.is_overdue else 1
                ts = t.due_timestamp or (time.time() + 9999999)
                return (is_done, is_over, ts)

            self.tasks.sort(key=sort_key)
            self.save_custom_tasks()
            self.save_cache()

    def toggle_task_status(self, task_id: str) -> Optional[Task]:
        """Schaltet den Erledigt-Status einer Aufgabe um (erledigt <-> offen)."""
        with self._cache_lock:
            task = next((t for t in self.tasks if t.id == task_id), None)
            if not task:
                return None
            if task.is_completed:
                task.status = "open"
                task.status_display = "Open"
            else:
                task.status = "completed"
                task.status_display = "Completed"

            def sort_key(t: Task):
                is_done = 1 if t.is_completed else 0
                is_over = 0 if t.is_overdue else 1
                ts = t.due_timestamp or (time.time() + 9999999)
                return (is_done, is_over, ts)

            self.tasks.sort(key=sort_key)
            if task.platform in ["manual", "custom"]:
                self.save_custom_tasks()
            self.save_cache()
            return task

    @property
    def deleted_ids(self) -> set:
        """Kombinierte Menge aller ausgeblendeten (Moodle/Teams) und gelöschten (manuellen) Aufgaben-IDs."""
        return self.hidden_ids | self.deleted_manual_ids

    @deleted_ids.setter
    def deleted_ids(self, val):
        self.hidden_ids = {str(x).strip() for x in val if not str(x).strip().startswith("manual_")}
        self.deleted_manual_ids = {str(x).strip() for x in val if str(x).strip().startswith("manual_")}

    def load_deleted_tasks(self):
        """Lädt getrennt: ausgeblendete Plattform-Aufgaben (hidden_tasks.json) und gelöschte manuelle Aufgaben (deleted_manual_tasks.json)."""
        # 1. Ausgeblendete Moodle/Teams-Aufgaben laden
        for path in [HIDDEN_TASKS_FILE, APP_HIDDEN_TASKS_FILE]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.hidden_ids.update(str(x).strip() for x in data if str(x).strip())
                except Exception as e:
                    print(f"Warning: Could not load hidden tasks from {path}: {e}", file=sys.stderr)

        # 2. Gelöschte manuelle Aufgaben laden
        for path in [DELETED_MANUAL_TASKS_FILE, APP_DELETED_MANUAL_TASKS_FILE]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            self.deleted_manual_ids.update(str(x).strip() for x in data if str(x).strip())
                except Exception as e:
                    print(f"Warning: Could not load deleted manual tasks from {path}: {e}", file=sys.stderr)

        # 3. Automatische Migration aus Legacy deleted_tasks.json (falls vorhanden)
        migrated = False
        for path in [DELETED_TASKS_FILE, APP_DELETED_TASKS_FILE]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                s = str(item).strip()
                                if not s:
                                    continue
                                if s.startswith("manual_"):
                                    self.deleted_manual_ids.add(s)
                                else:
                                    self.hidden_ids.add(s)
                            migrated = True
                    os.remove(path)
                except Exception:
                    pass

        if migrated:
            self.save_hidden_tasks(auto_push=False)
            self.save_deleted_manual_tasks(auto_push=False)

    def save_hidden_tasks(self, auto_push: bool = True):
        """Speichert ausgeblendete Moodle- und Teams-Aufgaben in hidden_tasks.json."""
        with self._cache_lock:
            for path in [HIDDEN_TASKS_FILE, APP_HIDDEN_TASKS_FILE]:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(sorted(list(self.hidden_ids)), f, indent=2)
                except Exception as e:
                    print(f"Warning: Could not save hidden tasks to {path}: {e}", file=sys.stderr)
        if auto_push:
            try:
                from git_sync_service import is_git_configured, GitSyncService
                if is_git_configured():
                    GitSyncService.async_push("Update hidden tasks")
            except Exception:
                pass

    def save_deleted_manual_tasks(self, auto_push: bool = True):
        """Speichert gelöschte manuelle Aufgaben-IDs (Tombstones) in deleted_manual_tasks.json."""
        with self._cache_lock:
            for path in [DELETED_MANUAL_TASKS_FILE, APP_DELETED_MANUAL_TASKS_FILE]:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(sorted(list(self.deleted_manual_ids)), f, indent=2)
                except Exception as e:
                    print(f"Warning: Could not save deleted manual tasks to {path}: {e}", file=sys.stderr)
        if auto_push:
            try:
                from git_sync_service import is_git_configured, GitSyncService
                if is_git_configured():
                    GitSyncService.async_push("Update deleted manual tasks")
            except Exception:
                pass

    def save_deleted_tasks(self, auto_push: bool = True):
        """Kompatibilitätsmethode: Speichert sowohl hidden_tasks als auch deleted_manual_tasks ab."""
        self.save_hidden_tasks(auto_push=auto_push)
        self.save_deleted_manual_tasks(auto_push=auto_push)

    def delete_custom_task(self, task_id: str, auto_push: bool = True) -> bool:
        """Löscht eine manuell erstellte Aufgabe aus dem Speicher und den Dateien und vermerkt ein Tombstone in deleted_manual_tasks.json."""
        tid = str(task_id).strip()
        with self._cache_lock:
            initial_len = len(self.tasks)
            self.tasks = [t for t in self.tasks if str(t.id).strip() != tid]
            self.deleted_manual_ids.add(tid)
            self.save_deleted_manual_tasks(auto_push=auto_push)
            if len(self.tasks) != initial_len:
                self.save_custom_tasks(auto_push=auto_push)
                self.save_cache()
                return True
            return False

    def delete_task(self, task_id: str):
        """Markiert eine Plattform-Aufgabe als hidden bzw. löscht eine manuelle Aufgabe."""
        tid = str(task_id).strip()
        with self._cache_lock:
            task = next((t for t in self.tasks if str(t.id).strip() == tid), None)
            if task and task.platform in ["manual", "custom"]:
                self.delete_custom_task(tid, auto_push=True)
                return
        self.hidden_ids.add(tid)
        self.save_hidden_tasks(auto_push=True)

    def clear_platform_tasks(self, platform: str) -> int:
        """Entfernt alle gecachten Aufgaben einer bestimmten Plattform und speichert den Cache."""
        plat_lower = platform.strip().lower()
        removed_count = 0
        with self._cache_lock:
            initial_count = len(self.tasks)
            self.tasks = [t for t in self.tasks if getattr(t, "platform", "").lower() != plat_lower]
            removed_count = initial_count - len(self.tasks)
        if removed_count > 0:
            self.save_cache()
        return removed_count

    def restore_task(self, task_id: str):
        """Stellt eine zuvor ausgeblendete oder gelöschte Aufgabe wieder her."""
        tid = str(task_id).strip()
        changed = False
        if tid in self.hidden_ids:
            self.hidden_ids.remove(tid)
            self.save_hidden_tasks()
            changed = True
        if tid in self.deleted_manual_ids:
            self.deleted_manual_ids.remove(tid)
            self.save_deleted_manual_tasks()
            changed = True
        return changed

    def is_deleted(self, task_id: str) -> bool:
        tid = str(task_id).strip()
        return tid in self.deleted_ids

    def get_deleted_tasks(self) -> List[Task]:
        """Gibt alle Aufgaben zurück, die als gelöscht markiert sind."""
        with self._cache_lock:
            return [t for t in self.tasks if str(t.id).strip() in self.deleted_ids]

    def load_cache(self) -> bool:
        """Lädt zwischengespeicherte Aufgaben für blitzschnellen Start."""
        with self._cache_lock:
            if os.path.exists(CACHE_FILE):
                try:
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.last_sync = data.get("last_sync")
                        raw_tasks = data.get("tasks", [])
                        self.tasks = [Task.from_dict(t) for t in raw_tasks]
                        for t in self.tasks:
                            if t.status_display and ("nichts abgegeben" in t.status_display.lower() or "für diese aufgabe" in t.status_display.lower()):
                                t.status_display = "noch offen"
                            if not t.teacher or t.teacher in ["-", "GRO", "AIC"] or t.course == "UFW":
                                t.teacher = extract_teacher(t.course_full, t.course, t.title, t.description)
                        # Auch manuelle Aufgaben hinzufügen
                        custom_tasks = self.load_custom_tasks()
                        existing_ids = {t.id for t in self.tasks}
                        for ct in custom_tasks:
                            if ct.id not in existing_ids:
                                self.tasks.append(ct)
                                existing_ids.add(ct.id)
                        return True
                except Exception as e:
                    print(f"Warning: Could not load cache: {e}", file=sys.stderr)
            return False

    def save_cache(self):
        """Saves current task cache to disk with minimal lock holding time."""
        try:
            self.save_custom_tasks(auto_push=False)
            with self._cache_lock:
                data = {
                    "last_sync": self.last_sync or time.time(),
                    "tasks": [t.to_dict() for t in self.tasks]
                }
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}", file=sys.stderr)

    def start_background_prefetch(self):
        """Startet den Hintergrund-Thread zum schrittweisen Vorabladen aller Aufgaben-Details."""
        self._stop_prefetch = False
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=1.0)
            if self._prefetch_thread.is_alive():
                return
        self._prefetch_thread = threading.Thread(
            target=self._prefetch_worker,
            daemon=True,
            name="PrefetchWorker"
        )
        self._prefetch_thread.start()


    def stop_background_prefetch(self):
        """Stoppt den Vorabladen-Hintergrund-Thread."""
        self._stop_prefetch = True
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=1.0)

    def shutdown(self):
        """Beendet Hintergrund-Aktivitäten sauber beim Beenden der Anwendung."""
        self._is_shutting_down = True
        self.stop_background_prefetch()

    def _prefetch_worker(self):
        """Prefetch-Worker für schnellen, ressourcenschonenden HTTP-Hintergrundabruf von Moodle-Details."""
        # Kurze Pause für UI-Start (unterbrechbar)
        for _ in range(10):
            if self._stop_prefetch or getattr(self, "_is_shutting_down", False):
                return
            time.sleep(0.1)

        attempted_ids = set()
        batch_counter = 0

        while not self._stop_prefetch and not getattr(self, "_is_shutting_down", False):
            target_task = None
            with self._cache_lock:
                candidates = [
                    t for t in self.tasks
                    if t.platform == "moodle" and not t.details_loaded and t.id not in self.deleted_ids and t.id not in attempted_ids
                ]
                if not candidates:
                    break

                # Priorisiere offene Aufgaben (nach Frist)
                def prefetch_priority(t: Task):
                    is_done = 1 if t.is_completed else 0
                    is_over = 0 if t.is_overdue else 1
                    ts = t.due_timestamp or 9999999999
                    return (is_done, is_over, ts)

                candidates.sort(key=prefetch_priority)
                target_task = candidates[0]
                attempted_ids.add(target_task.id)

            if not target_task:
                break

            try:
                # WICHTIG: Nur reines, leichtgewichtiges HTTP (kein Playwright/Chromium im Hintergrund-Prefetch),
                # um Menü-Lags und EPIPE-Crashes bei App-Exit vollständig zu verhindern.
                moodle_service.fetch_moodle_task_details_http(target_task)

                with self._cache_lock:
                    target_task.due_timestamp = parse_deadline_for_sorting(target_task.due_date_str)
                    if not target_task.teacher or target_task.teacher in ["-", "GRO", "AIC"] or target_task.course == "UFW":
                        target_task.teacher = extract_teacher(target_task.course_full, target_task.course, target_task.title, target_task.description)

                # Disk I/O bündeln (alle 5 Aufgaben), um den UI-Thread nicht mit ständigen Schreibvorgängen zu belasten
                batch_counter += 1
                if batch_counter >= 5:
                    self.save_cache()
                    batch_counter = 0
            except Exception:
                pass

            for _ in range(5):
                if self._stop_prefetch or getattr(self, "_is_shutting_down", False):
                    break
                time.sleep(0.1)

        # Letzter Cache-Flush am Ende des Prefetch-Durchlaufs
        if batch_counter > 0 and not getattr(self, "_is_shutting_down", False):
            try:
                self.save_cache()
            except Exception:
                pass

    def _merge_platform_tasks(self, new_tasks: List[Task], platform: str):
        """Führt Aufgaben einer einzelnen Plattform sofort in den Bestand ein und speichert den Cache."""
        with self._cache_lock:
            existing_map = {t.id: t for t in self.tasks}
            other_tasks = [t for t in self.tasks if t.platform != platform]

            merged: List[Task] = []
            seen_ids = set()
            for t in new_tasks:
                if t.id in seen_ids:
                    continue
                seen_ids.add(t.id)
                if t.id in existing_map:
                    cached = existing_map[t.id]
                    if cached.details_loaded:
                        t.description = cached.description
                        t.attachments = cached.attachments
                        t.details_loaded = cached.details_loaded
                    if cached.download_dir:
                        t.download_dir = cached.download_dir
                    if (not t.due_date_str or "keine" in t.due_date_str.lower()) and cached.due_date_str and "keine" not in cached.due_date_str.lower():
                        t.due_date_str = cached.due_date_str

                t.due_timestamp = parse_deadline_for_sorting(t.due_date_str)
                if not t.teacher or t.teacher in ["-", "GRO"]:
                    t.teacher = extract_teacher(t.course_full, t.course, t.title, t.description)
                merged.append(t)

            combined = other_tasks + merged
            def sort_key(t: Task):
                is_done = 1 if t.is_completed else 0
                is_over = 0 if t.is_overdue else 1
                ts = t.due_timestamp or (time.time() + 9999999)
                return (is_done, is_over, ts)

            combined.sort(key=sort_key)
            self.tasks = combined
            self.last_sync = time.time()
            self.save_custom_tasks(auto_push=False)
            self.save_cache()

    def sync(self, deep_scan: bool = False, on_progress=None, start_prefetch: bool = True, on_batch_complete=None) -> Tuple[int, int]:
        """
        Synchronisiert Aufgaben von Moodle und Teams live und parallel.
        Gibt (Anzahl Moodle, Anzahl Teams) zurück.
        on_batch_complete wird sofort aufgerufen, sobald eine Plattform fertig ist (z.B. Moodle nach 3s).
        """
        self.stop_background_prefetch()

        # Parallele Ausführung von Moodle- und Teams-Sync
        if on_progress:
            on_progress("Syncing Moodle and Teams in parallel...")

        m_tasks: List[Task] = []
        t_tasks: List[Task] = []
        moodle_ok = False
        teams_ok = False

        def fetch_moodle():
            if not is_platform_enabled("moodle"):
                return []
            nonlocal moodle_ok, m_tasks
            try:
                if on_progress:
                    on_progress("Syncing Moodle assignments...")
                res = moodle_service.fetch_moodle_tasks(deep_scan=deep_scan)
                moodle_ok = True
                m_tasks = res
                self._merge_platform_tasks(res, "moodle")
                if on_batch_complete:
                    try:
                        on_batch_complete()
                    except Exception:
                        pass
                if on_progress:
                    on_progress(f"Moodle completed ({len(res)} assignments).")
                return res
            except Exception as e:
                print(f"Moodle sync error: {e}", file=sys.stderr)
                moodle_ok = False
                return []

        def fetch_teams():
            if not is_platform_enabled("teams"):
                return []
            nonlocal teams_ok, t_tasks
            try:
                if on_progress:
                    on_progress("Syncing Microsoft Teams assignments...")
                res = teams_service.fetch_teams_tasks()
                teams_ok = True
                t_tasks = res
                self._merge_platform_tasks(res, "teams")
                if on_batch_complete:
                    try:
                        on_batch_complete()
                    except Exception:
                        pass
                if on_progress:
                    on_progress(f"Teams completed ({len(res)} assignments).")
                return res
            except Exception as e:
                print(f"Teams sync error: {e}", file=sys.stderr)
                teams_ok = False
                return []

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_moodle = executor.submit(fetch_moodle)
            future_teams = executor.submit(fetch_teams)
            future_moodle.result()
            future_teams.result()

        moodle_count = len(m_tasks) if moodle_ok else 0
        teams_count = len(t_tasks) if teams_ok else 0

        if start_prefetch:
            self.start_background_prefetch()
        return moodle_count, teams_count

    def get_filtered_tasks(
        self,
        platform_filter: str = "all",  # "all", "moodle", "teams", "manual"
        status_filter: str = "open_only",  # "all", "open_only", "overdue", "completed"
        subject_filter: Optional[str] = None,
        search_query: Optional[str] = None,
        include_deleted: bool = False,
        timeframe_filter: str = "2_weeks",  # "1_week", "2_weeks", "4_weeks", "8_weeks", "all"
    ) -> List[Task]:
        """Gibt gefilterte Aufgabenliste zurück (Standard: ohne gelöschte Aufgaben)."""
        with self._cache_lock:
            if not include_deleted:
                results = [t for t in self.tasks if str(t.id).strip() not in self.deleted_ids and not self.is_deleted(t.id)]
            else:
                results = list(self.tasks)

        # Plattform-Filter
        if platform_filter != "all":
            if platform_filter in ["manual", "custom"]:
                results = [t for t in results if t.platform in ["manual", "custom"]]
            else:
                results = [t for t in results if t.platform == platform_filter]

        # Status-Filter
        if status_filter in ["open_only", "open", "offen", "todo", "to_do"]:
            results = [t for t in results if not t.is_completed and not t.is_overdue]
        elif status_filter in ["overdue", "ueberfaellig", "überfällig"]:
            results = [t for t in results if t.is_overdue]
        elif status_filter in ["completed", "abgegeben", "erledigt", "done"]:
            results = [t for t in results if t.is_completed]

        # Fach-Filter
        if subject_filter and subject_filter != "all":
            s_lower = subject_filter.lower()
            results = [t for t in results if s_lower in t.course.lower() or s_lower in t.course_full.lower()]

        # Fälligkeits-/Zeitrahmen-Filter (1 Woche, 2 Wochen, 4 Wochen, 8 Wochen, Alles)
        if timeframe_filter and timeframe_filter.lower() not in ["all", "alles"]:
            tf_clean = timeframe_filter.lower().strip()
            days = None
            if "1" in tf_clean and "w" in tf_clean:
                days = 7
            elif "2" in tf_clean and "w" in tf_clean:
                days = 14
            elif "4" in tf_clean and "w" in tf_clean:
                days = 28
            elif "8" in tf_clean and "w" in tf_clean:
                days = 56

            if days is not None:
                now = datetime.datetime.now()
                cutoff_dt = (now + datetime.timedelta(days=days)).replace(hour=23, minute=59, second=59)
                cutoff_ts = cutoff_dt.timestamp()

                filtered = []
                for t in results:
                    if t.id == "manual_welcome_setup_guide":
                        filtered.append(t)
                        continue
                    ts = t.due_timestamp
                    if ts is None and t.due_date_str:
                        ts = parse_deadline_for_sorting(t.due_date_str)
                    if ts is not None and ts <= cutoff_ts:
                        filtered.append(t)
                results = filtered

        # Suchbegriff
        if search_query:
            q_lower = search_query.lower()
            results = [
                t for t in results
                if q_lower in t.title.lower() or q_lower in t.course.lower() or q_lower in t.description.lower()
            ]

        return results

    def load_task_details(self, task: Task, on_progress=None) -> Task:
        """Loads details for a specific task if not loaded yet."""
        if task.details_loaded:
            return task

        if on_progress:
            on_progress(f"Loading assignment details for '{task.title}'...")

        if task.platform == "moodle":
            success = moodle_service.fetch_moodle_task_details_http(task)
            if not success:
                with self._playwright_lock:
                    if not task.details_loaded:
                        moodle_service.fetch_moodle_task_details(task)
        elif task.platform == "teams":
            with self._playwright_lock:
                if not task.details_loaded:
                    teams_service.fetch_teams_task_details(task)

        with self._cache_lock:
            task.due_timestamp = parse_deadline_for_sorting(task.due_date_str)
            if not task.teacher or task.teacher in ["-", "GRO", "AIC"] or task.course == "UFW":
                task.teacher = extract_teacher(task.course_full, task.course, task.title, task.description)
            self.save_cache()

        return task

    def download_task_files(self, task: Task, dest_dir: Optional[str] = None, on_progress=None) -> List[str]:
        """Downloads all attachments and assignment details to folder."""
        self.load_task_details(task, on_progress=on_progress)

        if on_progress:
            on_progress(f"Downloading attachments for '{task.title}'...")

        if task.platform == "moodle":
            files = moodle_service.download_moodle_attachments(task, dest_dir=dest_dir)
        elif task.platform == "teams":
            files = teams_service.download_teams_attachments(task, dest_dir=dest_dir)
        else:
            files = []

        with self._cache_lock:
            self.save_cache()
        return files
