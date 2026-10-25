"""
agent_cli.py - Token-effiziente, blitzschnelle Befehlszeilen-Schnittstelle
speziell für autonome KI-Agenten und Terminal-Skripte.

Unterstützt sowohl Subcommands (`tasks list`) als auch Flags (`tasks -list` / `tasks --list`).
Liest standardmäßig sofort den lokalen Cache (< 0.1s) und minimiert Token-Verbrauch.
"""

import argparse
import datetime
import json
import os
import sys
import time
import re
import webbrowser
from typing import List, Optional, Tuple

from config import CONFIG_DIR, extract_teacher, normalize_subject_name, load_all_course_links
from models import Task
from task_manager import TaskManager, parse_deadline_for_sorting

LAST_CLI_TASKS_FILE = os.path.join(CONFIG_DIR, ".last_cli_tasks.json")


def _score_course_match(course: dict, q: str) -> float:
    """Berechnet einen Relevanz-Score für einen Kurs basierend auf der Suchanfrage."""
    subj = (course.get("subject") or "").lower().strip()
    title = (course.get("display_title") or course.get("fullname") or "").lower().strip()
    badge = (course.get("display_badge") or "").lower().strip()
    full_text = f"{badge} {subj} {title}"

    # 1. Exakter Match auf Fachkürzel (z.B. "sesd" == "sesd")
    if subj == q:
        return 100.0

    # 2. Fachkürzel startet mit Query (z.B. "ses" in "sesd" oder "am" in "amec")
    if subj.startswith(q):
        return 85.0

    # 3. Query im Fachkürzel enthalten
    if q in subj:
        return 75.0

    # 4. Exaktes Wort im Titel (z.B. "security" in "Security Software Development")
    if re.search(rf"\b{re.escape(q)}\b", title):
        return 65.0

    # 5. Titel startet mit Query
    if title.startswith(q):
        return 60.0

    # 6. Query als Teilstring im Titel
    if q in title:
        return 50.0

    # 7. Query im Volltext (z.B. Plattformname wie "teams" oder "moodle")
    if q in full_text:
        return 40.0

    # 8. Fuzzy Match: Alle Zeichen der Query kommen der Reihe nach im Titel/Kürzel vor
    pos = 0
    matched_chars = 0
    for char in q:
        idx = full_text.find(char, pos)
        if idx != -1:
            matched_chars += 1
            pos = idx + 1
        else:
            break
    if matched_chars == len(q) and len(q) >= 2:
        return 20.0 + (len(q) / max(len(full_text), 1)) * 10.0

    return 0.0


def _load_raw_moodle_courses() -> List[dict]:
    """Lädt ungefilterte Moodle-Kurse aus dem Cache als Fallback."""
    from config import MOODLE_BASE_URL, ASSETS_DIR
    cache_path = os.path.join(CONFIG_DIR, "moodle_courses_cache.json")
    if not os.path.exists(cache_path):
        fallback_p = os.path.join(ASSETS_DIR, "default_courses.json")
        if os.path.exists(fallback_p):
            cache_path = fallback_p
        else:
            return []
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                res = []
                for mc in data:
                    cid = str(mc.get("id", ""))
                    if not cid:
                        continue
                    res.append({
                        "platform": "moodle",
                        "display_badge": "[Moodle]",
                        "subject": mc.get("subject", ""),
                        "display_title": mc.get("fullname", f"Moodle Kurs #{cid}"),
                        "url": mc.get("url") or f"{MOODLE_BASE_URL}/course/view.php?id={cid}",
                        "is_current_class": False,
                    })
                return res
    except Exception:
        pass
    return []


def find_best_course_match(query: str) -> Tuple[Optional[dict], List[dict]]:
    """
    Sucht den passendsten Kurs für die gegebene Suchanfrage (Fachkürzel, Name oder Stichwort).
    Priorisiert Treffer wie die TUI-Befehlspalette.
    Gibt (bester_treffer, alle_treffer_sortiert) zurück.
    """
    q = query.strip().lower()
    if not q:
        return None, []

    courses = load_all_course_links()
    scored_matches: List[Tuple[float, dict]] = []

    for c in courses:
        score = _score_course_match(c, q)
        if score > 0:
            scored_matches.append((score, c))

    # Fallback: Falls in den gefilterten Kursen kein starker Treffer (Score >= 50) gefunden wurde,
    # im Moodle-Rohcache nach exakten oder besseren Treffern suchen
    has_strong_match = any(score >= 50.0 for score, _ in scored_matches)
    if not has_strong_match:
        raw_moodle = _load_raw_moodle_courses()
        seen_urls = {item[1].get("url") for item in scored_matches}
        for c in raw_moodle:
            if c.get("url") in seen_urls:
                continue
            score = _score_course_match(c, q)
            if score > 0:
                scored_matches.append((score, c))

    scored_matches.sort(key=lambda x: x[0], reverse=True)
    sorted_courses = [item[1] for item in scored_matches]
    best = sorted_courses[0] if sorted_courses else None
    return best, sorted_courses


def format_courses_list_text(courses: List[dict]) -> str:
    """Kompakte, token-effiziente Kursliste."""
    if not courses:
        return "No courses found."
    lines = []
    lines.append(f"{'#':<4} {'PLATFORM':<11} {'SUBJECT':<10} {'COURSE NAME'}")
    lines.append("-" * 75)
    for i, c in enumerate(courses, 1):
        p = c.get("platform", "moodle").capitalize()
        s = (c.get("subject") or "-")[:9]
        title = (c.get("display_title") or c.get("fullname") or "").replace("\n", " ").strip()
        if len(title) > 48:
            title = title[:46] + "…"
        lines.append(f"{i:<4} {p:<11} {s:<10} {title}")
    lines.append("-" * 75)
    lines.append(f"Total: {len(courses)} course(s). Open any course with: tasks open <fach>")
    return "\n".join(lines)


def format_courses_list_json(courses: List[dict]) -> str:
    """Kompakte JSON-Ausgabe der Kursliste."""
    data = []
    for i, c in enumerate(courses, 1):
        data.append({
            "index": i,
            "platform": c.get("platform", "moodle"),
            "subject": c.get("subject", ""),
            "title": c.get("display_title") or c.get("fullname") or "",
            "url": c.get("url", ""),
        })
    return json.dumps(data, ensure_ascii=False, indent=2)


def save_last_cli_task_ids(task_ids: List[str]) -> None:
    """Speichert die zuletzt aufgelisteten Task-IDs für stabile 1-basierte Indexierung."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(LAST_CLI_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(task_ids, f)
    except Exception:
        pass


def load_last_cli_task_ids() -> List[str]:
    """Lädt die zuletzt aufgelisteten Task-IDs."""
    if os.path.exists(LAST_CLI_TASKS_FILE):
        try:
            with open(LAST_CLI_TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(x) for x in data]
        except Exception:
            pass
    return []


def resolve_task(mgr: TaskManager, target: str) -> Optional[Task]:
    """
    Löst eine Aufgaben-Referenz auf:
    1. Numerischer 1-basierter Index aus der letzten `tasks list` Abfrage
    2. Exakte Task-ID
    3. Prefix- / Teilstring-Treffer auf Task-ID
    """
    target = target.strip()
    if not target:
        return None

    # 1. Numerischer Index
    if target.isdigit():
        idx = int(target)
        last_ids = load_last_cli_task_ids()
        if last_ids and 1 <= idx <= len(last_ids):
            target_id = last_ids[idx - 1]
            task = next((t for t in mgr.tasks if t.id == target_id), None)
            if task:
                return task
            deleted_task = next((t for t in mgr.get_deleted_tasks() if t.id == target_id), None)
            if deleted_task:
                return deleted_task

        # Fallback wenn keine last_cli_tasks existieren
        active = mgr.get_filtered_tasks(status_filter="all", timeframe_filter="all")
        if 1 <= idx <= len(active):
            return active[idx - 1]

    # 2. Exakte ID in aktiven Aufgaben
    for t in mgr.tasks:
        if t.id == target:
            return t

    # 3. Exakte ID in gelöschten Aufgaben
    for t in mgr.get_deleted_tasks():
        if t.id == target:
            return t

    # 4. Präfix-Suche in aktiven Aufgaben
    target_lower = target.lower()
    for t in mgr.tasks:
        if t.id.lower().startswith(target_lower):
            return t

    # 5. Präfix-Suche in gelöschten Aufgaben
    for t in mgr.get_deleted_tasks():
        if t.id.lower().startswith(target_lower):
            return t

    # 6. Fallback: Substring-Suche
    for t in mgr.tasks:
        if target_lower in t.id.lower():
            return t

    return None


def format_task_list_text(tasks: List[Task], total_count: int, status_filter: str) -> str:
    """Token-effiziente, schnörkellose Text-Tabelle."""
    if not tasks:
        return f"No tasks found matching filter (status='{status_filter}', total in cache={total_count})."

    # Tabellenkopf
    lines = []
    lines.append(f"{'#':<4} {'ID':<24} {'SUBJECT':<8} {'DUE DATE':<18} {'STATUS':<11} {'TITLE'}")
    lines.append("-" * 86)

    for i, t in enumerate(tasks, 1):
        # Kompakter Status
        if t.is_completed:
            st = "Done"
        elif t.is_overdue:
            st = "Overdue"
        elif t.is_due_soon:
            st = "Soon"
        else:
            st = "Open"

        # Frist kürzen falls zu lang
        due = t.due_date_str
        if len(due) > 16:
            due = due[:15] + "…"

        course = t.course[:7] if t.course else "-"
        t_id = t.id[:23] if len(t.id) > 23 else t.id
        title = t.title.replace("\n", " ").strip()
        if len(title) > 60:
            title = title[:58] + "…"

        lines.append(f"{i:<4} {t_id:<24} {course:<8} {due:<18} {st:<11} {title}")

    lines.append("-" * 86)
    open_count = len([t for t in tasks if not t.is_completed and not t.is_overdue])
    overdue_count = len([t for t in tasks if t.is_overdue])
    done_count = len([t for t in tasks if t.is_completed])
    lines.append(f"Listed {len(tasks)} task(s) | Open: {open_count} | Overdue: {overdue_count} | Done: {done_count} | Total cached: {total_count}")
    return "\n".join(lines)


def format_task_list_json(tasks: List[Task]) -> str:
    """Kompaktes JSON für Aufgabenliste."""
    data = []
    for i, t in enumerate(tasks, 1):
        data.append({
            "index": i,
            "id": t.id,
            "platform": t.platform,
            "course": t.course,
            "course_full": t.course_full,
            "title": t.title,
            "due": t.due_date_str,
            "due_timestamp": t.due_timestamp,
            "status": "completed" if t.is_completed else ("overdue" if t.is_overdue else "open"),
            "status_display": t.status_display,
            "teacher": t.teacher,
            "url": t.url,
            "attachments_count": len(t.attachments) if t.attachments else 0,
        })
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_task_detail_text(task: Task, mgr: TaskManager) -> str:
    """Detaillierte, token-effiziente Textausgabe."""
    lines = []
    lines.append(f"Title:       {task.title}")
    lines.append(f"ID:          {task.id}")
    lines.append(f"Subject:     {task.course} ({task.course_full})")
    lines.append(f"Teacher:     {task.teacher or '-'}")
    lines.append(f"Platform:    {task.platform}")
    
    status_label = "Completed" if task.is_completed else ("Overdue" if task.is_overdue else "Open")
    lines.append(f"Status:      {status_label} ({task.status_display})")
    lines.append(f"Due Date:    {task.due_date_str}")
    if task.url:
        lines.append(f"URL:         {task.url}")
    if task.download_dir:
        lines.append(f"Folder:      {task.download_dir}")

    # Attachments
    if task.attachments:
        lines.append("Attachments:")
        for att in task.attachments:
            size_info = f" ({att.size})" if att.size else ""
            lines.append(f"  - {att.name}{size_info}: {att.url}")
    else:
        lines.append("Attachments: None")

    # Beschreibung
    lines.append("\nDescription:")
    desc = (task.description or "").strip()
    if desc:
        lines.append(desc)
    else:
        lines.append("(No description provided)")

    return "\n".join(lines)


def format_guide_text() -> str:
    """Kompakter Agent-Leitfaden mit minimalem Token-Footprint."""
    return """# Tasks - Agent CLI Reference

Fast (<0.1s offline cache) & token-efficient CLI designed for AI agents.

## Commands
  tasks list [-s open|all|completed|overdue] [-f SUBJECT] [-p moodle|teams|manual] [--json]
    List assignments from local cache.
    Flags:
      -s, --status    Filter: open (default), all, completed, overdue
      -f, --subject   Filter by subject abbreviation (e.g. AM, SEW, D)
      -p, --platform  Filter platform: all, moodle, teams, manual
      --sync          Force live sync before listing
      --json          Output structured JSON

  tasks show <id|index> [--json]
    Show full description, links, and attachments for a task.
    Supports either Task ID (e.g. 'moodle_10421') or 1-based index (e.g. '1').

  tasks download <id|index> [--auto-dir] [--dir PATH] [--json]
    Download attachments & assignment markdown for the task.
    Use --auto-dir (-a) to automatically detect linked course folder and create a subfolder.
    Returns the absolute paths of all saved files for immediate reading.

  tasks explain <id|index> [--lang de|en] [--copy-only] [--no-browser] [--json]
    Generate a structured AI prompt for an assignment, copy to clipboard, and open in AI browser.

  tasks add --title "..." --subject "..." [--due "..."] [--teacher "..."] [--desc "..."] [--json]
    Create a manual homework task directly from CLI.

  tasks open <fach> [--json]
    Open a Moodle or Teams course in the browser (e.g. 'tasks open sesd' or 'tasks open mathe').
    Picks the top matching course (just like Backspace search in the TUI).

  tasks courses [--json]
    List all available Moodle and Teams courses with abbreviations.

  tasks done <id|index> [--json]
    Toggle completed/open state of an assignment.

  tasks delete <id|index> [--json]
    Hide or delete an assignment from active list.

  tasks restore <id|index> [--json]
    Restore a hidden/deleted assignment.

  tasks books [list|open|add|remove|download] [--json]
    Manage and open schoolbooks (PDF, Web, Digi4School).
    Subcommands:
      list                       List all linked schoolbooks
      open <id|index>            Open schoolbook in default viewer or browser
      add <path|url> [--title]   Link a local PDF or online schoolbook
      remove <id|index>          Remove linked schoolbook
      download <code>            Download Digi4School book with OCR

  tasks dirs [list|open|add|remove] [--json]
    Manage and open linked local directories in file explorer.
    Subcommands:
      list                       List all linked directories
      open <id|index|name>       Open directory in system file explorer
      add <path> [--title]       Link a local folder path (auto-titled from folder)
      remove <id|index|name>     Remove linked directory

  tasks skill [sync|status] [--target PATH] [--json]
    Manage global Antigravity / Agent skill.
    Subcommands:
      sync (default)             Install/sync skill to ~/.gemini/config/skills/tasks/
      status                     Check installation status and sync state

  tasks sync [--deep] [--json]
    Perform live network sync with Moodle & Teams in background/terminal.

  tasks guide
    Print this reference guide.

## Shorthand Flags
  All commands can also be called as flags:
  `tasks -list`, `tasks --list`, `tasks -open sesd`, `tasks -courses`, `tasks -show 1`, `tasks -sync`, `tasks -dirs`, `tasks -skill`
"""


def normalize_argv(argv: List[str]) -> List[str]:
    """
    Normalisiert gemischte Eingabesyntax:
    `tasks -list` -> `tasks list`
    `tasks --list` -> `tasks list`
    `tasks -open sesd` -> `tasks open sesd`
    `tasks -courses` -> `tasks courses`
    `tasks -show 1` -> `tasks show 1`
    `tasks --show 1` -> `tasks show 1`
    `tasks -sync` -> `tasks sync`
    `tasks --sync` -> `tasks sync`
    `tasks -download 1` -> `tasks download 1`
    `tasks --download 1` -> `tasks download 1`
    `tasks -add ...` -> `tasks add ...`
    `tasks -done 1` -> `tasks done 1`
    `tasks -delete 1` -> `tasks delete 1`
    `tasks -restore 1` -> `tasks restore 1`
    `tasks -guide` -> `tasks guide`
    `tasks -json` -> `tasks list --json`
    """
    if not argv:
        return []

    norm = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        lower = arg.lower()

        # Sonderfall: Reines `--json` ohne Command -> `list --json`
        if lower in ["--json", "-json"] and i == 0:
            norm.append("list")
            norm.append("--json")
            i += 1
            continue

        # Flag-Präfixe zu Subcommands konvertieren
        flag_to_cmd = {
            "--list": "list", "-list": "list",
            "--show": "show", "-show": "show",
            "--get": "show", "-get": "show",
            "--view": "show", "-view": "show",
            "--download": "download", "-download": "download",
            "--dl": "download", "-dl": "download",
            "--add": "add", "-add": "add",
            "--done": "done", "-done": "done",
            "--complete": "done", "-complete": "done",
            "--toggle": "done", "-toggle": "done",
            "--delete": "delete", "-delete": "delete",
            "--remove": "delete", "-remove": "delete",
            "--restore": "restore", "-restore": "restore",
            "--sync": "sync", "-sync": "sync",
            "--guide": "guide", "-guide": "guide",
            "--help": "guide", "-help": "guide", "-h": "guide",
            "--open": "open", "-open": "open",
            "--course": "open", "-course": "open",
            "--courses": "courses", "-courses": "courses",
            "--skill": "skill", "-skill": "skill",
            "--skills": "skill", "-skills": "skill",
        }

        if i == 0 and lower in flag_to_cmd:
            norm.append(flag_to_cmd[lower])
        else:
            norm.append(arg)
        i += 1

    return norm


def is_agent_cli_command(argv: List[str]) -> bool:
    """Ermittelt, ob der Programmaufruf ein Agent-CLI-Befehl ist."""
    if not argv:
        return False

    first = argv[0].lower()
    known_commands = {
        "list", "ls", "show", "get", "view", "info",
        "download", "dl", "fetch",
        "explain", "ai-explain", "ask-ai",
                "add", "new", "create",
        "done", "complete", "toggle",
        "delete", "del", "remove", "rm", "hide",
        "restore", "unhide", "undelete",
        "sync", "guide", "agent-guide", "help",
        "open", "course", "courses", "courselist",
        "books", "book", "schulbuch", "schulbücher",
        "dirs", "dir", "directories", "folder", "folders", "ordner",
        "skill", "skills"
    }

    if first in known_commands:
        return True

    # Flag-Versionen
    flag_prefixes = [
        "-list", "--list", "-show", "--show", "-get", "--get",
        "-download", "--download", "-dl", "--dl",
        "-explain", "--explain",
                "-add", "--add", "-done", "--done", "-toggle", "--toggle",
        "-delete", "--delete", "-restore", "--restore",
        "-sync", "--sync", "-guide", "--guide", "--json", "-json",
        "-help", "--help", "-h",
        "-open", "--open", "-courses", "--courses", "-course", "--course",
        "-books", "--books", "-book", "--book",
        "-dirs", "--dirs", "-dir", "--dir", "-folder", "--folder",
        "-skill", "--skill", "-skills", "--skills"
    ]
    return any(first.startswith(p) for p in flag_prefixes)


def run_agent_cli(argv: List[str]) -> int:
    """Haupt-Dispatcher für alle Agent-CLI-Befehle."""
    norm_argv = normalize_argv(argv)
    if not norm_argv:
        print(format_guide_text())
        return 0

    command = norm_argv[0].lower()
    sub_args = norm_argv[1:]

    # ─────────────────────────────────────────────────────────────────
    # 1. GUIDE / HELP
    # ─────────────────────────────────────────────────────────────────
    if command in ["guide", "agent-guide", "help"]:
        print(format_guide_text())
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 2. SYNC
    # ─────────────────────────────────────────────────────────────────
    if command == "sync":
        parser = argparse.ArgumentParser(prog="tasks sync", add_help=False)
        parser.add_argument("--deep", action="store_true", help="Perform deep course scan")
        parser.add_argument("--json", action="store_true", help="JSON output")
        args, _ = parser.parse_known_args(sub_args)

        mgr = TaskManager(autostart_prefetch=False)
        if not args.json:
            print("Syncing live from Moodle and Teams...")
        m_cnt, t_cnt = mgr.sync(deep_scan=args.deep, start_prefetch=False)

        if args.json:
            print(json.dumps({
                "success": True,
                "moodle_tasks": m_cnt,
                "teams_tasks": t_cnt,
                "total_cached": len(mgr.tasks),
                "timestamp": time.time()
            }, ensure_ascii=False))
        else:
            print(f"✓ Synced successfully: {m_cnt} Moodle tasks, {t_cnt} Teams tasks (Total: {len(mgr.tasks)}).")
        return 0

    # ─────────────────────────────────────────────────────────────────
    # COURSES (List all courses)
    # ─────────────────────────────────────────────────────────────────
    if command in ["courses", "courselist"]:
        parser = argparse.ArgumentParser(prog="tasks courses", add_help=False)
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, _ = parser.parse_known_args(sub_args)

        courses = load_all_course_links()
        if args.json:
            print(format_courses_list_json(courses))
        else:
            print(format_courses_list_text(courses))
        return 0

    # ─────────────────────────────────────────────────────────────────
    # OPEN (Open course in browser)
    # ─────────────────────────────────────────────────────────────────
    if command in ["open", "course", "launch"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Course abbreviation or name (e.g. 'sesd')")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--no-browse", action="store_true", help="Do not open browser (print URL only)")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            # Fallback: Keine Argumente -> Liste aller Kurse anzeigen
            courses = load_all_course_links()
            if args.json:
                print(format_courses_list_json(courses))
            else:
                print(format_courses_list_text(courses))
            return 0

        best_course, all_matches = find_best_course_match(target)
        if not best_course:
            msg = f"Error: No course found matching '{target}'. Use 'tasks courses' to list available courses."
            if args.json:
                print(json.dumps({"error": msg, "query": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        url = best_course.get("url", "")
        title = best_course.get("display_title") or best_course.get("fullname") or target
        badge = best_course.get("display_badge") or f"[{best_course.get('platform', 'course').capitalize()}]"

        if not args.no_browse and url:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass

        if args.json:
            print(json.dumps({
                "success": True,
                "platform": best_course.get("platform", "moodle"),
                "subject": best_course.get("subject", ""),
                "title": title,
                "url": url,
            }, ensure_ascii=False, indent=2))
        else:
            print(f"✓ Opening {badge} '{title}' in browser...")
            print(f"URL: {url}")
        return 0

    # TaskManager ohne Hintergrund-Prefetch initialisieren für sofortige Rückgabe
    mgr = TaskManager(autostart_prefetch=False)

    # ─────────────────────────────────────────────────────────────────
    # 3. LIST
    # ─────────────────────────────────────────────────────────────────
    if command in ["list", "ls"]:
        parser = argparse.ArgumentParser(prog="tasks list", add_help=False)
        parser.add_argument("-s", "--status", default="open", choices=["open", "all", "completed", "overdue"], help="Status filter")
        parser.add_argument("-f", "--subject", default=None, help="Subject filter")
        parser.add_argument("-p", "--platform", default="all", choices=["all", "moodle", "teams", "manual"], help="Platform filter")
        parser.add_argument("-t", "--timeframe", default="all", help="Timeframe (all, 1_week, 2_weeks, 4_weeks)")
        parser.add_argument("-q", "--search", default=None, help="Search keyword")
        parser.add_argument("--include-deleted", action="store_true", help="Include hidden tasks")
        parser.add_argument("--sync", action="store_true", help="Live sync before listing")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, _ = parser.parse_known_args(sub_args)

        if args.sync:
            mgr.sync(deep_scan=False, start_prefetch=False)

        # Mapping status filter
        status_map = {
            "open": "open_only",
            "all": "all",
            "completed": "completed",
            "overdue": "overdue",
        }
        internal_status = status_map.get(args.status, "open_only")

        filtered_tasks = mgr.get_filtered_tasks(
            platform_filter=args.platform,
            status_filter=internal_status,
            subject_filter=args.subject,
            search_query=args.search,
            include_deleted=args.include_deleted,
            timeframe_filter=args.timeframe
        )

        # Zuletzt aufgelistete IDs speichern für stabile Indexierung
        save_last_cli_task_ids([t.id for t in filtered_tasks])

        if args.json:
            print(format_task_list_json(filtered_tasks))
        else:
            print(format_task_list_text(filtered_tasks, len(mgr.tasks), args.status))
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 4. SHOW / GET / VIEW
    # ─────────────────────────────────────────────────────────────────
    if command in ["show", "get", "view", "info"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Task ID or 1-based index")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        parser.add_argument("--sync", action="store_true", help="Fetch remote details live if missing")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            msg = "Error: Please provide a Task ID or list index. Example: 'tasks show 1' or 'tasks show moodle_12345'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        task = resolve_task(mgr, target)
        if not task:
            msg = f"Error: Task '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        # Details nachladen falls noch nicht vorhanden
        if not task.details_loaded or args.sync:
            try:
                mgr.load_task_details(task)
            except Exception as e:
                pass

        if args.json:
            print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(format_task_detail_text(task, mgr))
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 5. DOWNLOAD
    # ─────────────────────────────────────────────────────────────────
    if command in ["download", "dl", "fetch"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Task ID or 1-based index")
        parser.add_argument("--auto-dir", "-a", action="store_true", help="Automatically detect linked course directory and create subfolder")
        parser.add_argument("--dir", default=None, help="Destination folder")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            msg = "Error: Please provide a Task ID or list index to download. Example: 'tasks download 1'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        task = resolve_task(mgr, target)
        if not task:
            msg = f"Error: Task '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        target_dir = args.dir
        if args.auto_dir:
            try:
                from directory_service import DirectoryService
            except ImportError:
                from services.directory_service import DirectoryService
            try:
                from config import sanitize_filename
            except ImportError:
                from core.config import sanitize_filename

            matched = DirectoryService.find_matching_directory_for_course(task.course, task.course_full)
            if not matched:
                msg = f"Error: No linked directory found matching course '{task.course or task.course_full}'. Link one first with 'tasks dirs add <path>'."
                if args.json:
                    print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
                else:
                    print(msg)
                return 1
            safe_title = sanitize_filename(task.title)
            target_dir = os.path.join(matched.get("path", ""), safe_title)
            os.makedirs(target_dir, exist_ok=True)

        try:
            files = mgr.download_task_files(task, dest_dir=target_dir)
        except Exception as e:
            msg = f"Error during download: {e}"
            if args.json:
                print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        if args.json:
            print(json.dumps({
                "success": True,
                "id": task.id,
                "title": task.title,
                "folder": task.download_dir or target_dir or args.dir,
                "files": files
            }, ensure_ascii=False, indent=2))
        else:
            print(f"✓ Downloaded {len(files)} file(s) for '{task.title}':")
            for f in files:
                print(f"  - {f}")
            folder = task.download_dir or target_dir or args.dir or "-"
            print(f"Folder: {folder}")
        return 0

    # ─────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────
    # EXPLAIN (AI Explain prompt generation, clipboard copy & browser launch)
    # ─────────────────────────────────────────────────────────────────
    if command in ["explain", "ai-explain", "ask-ai"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Task ID or 1-based index")
        parser.add_argument("--lang", choices=["de", "en"], default=None, help="Prompt language ('de' or 'en')")
        parser.add_argument("--no-browser", action="store_true", help="Do not open browser")
        parser.add_argument("--copy-only", action="store_true", help="Only copy prompt to clipboard")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            msg = "Error: Please provide a Task ID or list index. Example: 'tasks explain 1'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        task = resolve_task(mgr, target)
        if not task:
            msg = f"Error: Task '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        if not task.details_loaded:
            try:
                mgr.load_task_details(task)
            except Exception:
                pass

        from services.ai_explain_service import build_ai_explain_prompt, copy_to_clipboard, get_ai_explain_url
        from config import load_ai_explain_config, load_ai_chat_config
        from services.ai_chat_service import build_task_ai_context, send_ai_chat_message

        cfg = load_ai_explain_config()
        chat_cfg = load_ai_chat_config()
        lang = args.lang or chat_cfg.get("language") or cfg.get("language", "de")
        cfg["language"] = lang
        chat_cfg["language"] = lang

        prompt = build_ai_explain_prompt(task, language=lang)
        copied = copy_to_clipboard(prompt)
        url = get_ai_explain_url(prompt, config=cfg)

        ai_response = None
        if chat_cfg.get("api_key") and not args.copy_only:
            try:
                system_prompt = build_task_ai_context(task, language=lang)
                user_msg = (
                    "Bitte erkläre mir diese Aufgabe verständlich, praxisnah und Schritt für Schritt."
                    if lang == "de" else
                    "Please explain this assignment clearly, practically, and step-by-step."
                )
                ai_response = send_ai_chat_message(
                    [{"role": "user", "content": user_msg}],
                    system_prompt=system_prompt,
                    config=chat_cfg
                )
            except Exception as e:
                ai_response = f"AI request failed: {e}"

        opened = False
        if not args.no_browser and not args.copy_only and not ai_response:
            try:
                import webbrowser
                opened = bool(webbrowser.open(url))
            except Exception:
                pass

        if args.json:
            out_dict = {
                "success": True,
                "task_id": task.id,
                "task_title": task.title,
                "language": lang,
                "copied_to_clipboard": copied,
                "prompt": prompt
            }
            if ai_response:
                out_dict["ai_response"] = ai_response
                out_dict["model"] = chat_cfg.get("model", "unknown")
            else:
                out_dict["browser_opened"] = opened
                out_dict["url"] = url
            print(json.dumps(out_dict, ensure_ascii=False, indent=2))
        else:
            if ai_response:
                print(f"🤖 AI Explanation for '{task.title}' [{chat_cfg.get('model', 'AI')}]:")
                print("-" * 60)
                print(ai_response)
                print("-" * 60)
            else:
                print(f"✓ AI prompt generated for '{task.title}' [{lang.upper()}]:")
                print("-" * 50)
                print(prompt)
                print("-" * 50)
            status_parts = []
            if copied:
                status_parts.append("Copied to clipboard")
            if opened:
                status_parts.append(f"Opened in browser ({url})")
            elif not args.no_browser and not args.copy_only and not ai_response:
                status_parts.append(f"URL: {url}")
            print(f"Status: {', '.join(status_parts) if status_parts else 'Ready'}")
        return 0

    # ─────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────
    # 6. ADD
    # ─────────────────────────────────────────────────────────────────
    if command in ["add", "new", "create"]:
        parser = argparse.ArgumentParser(prog="tasks add", add_help=False)
        parser.add_argument("--title", "-t", required=False, help="Assignment title")
        parser.add_argument("--subject", "-s", required=False, help="Subject (e.g. AM, SEW, D)")
        parser.add_argument("--due", "-d", default="No deadline", help="Due date (e.g. '15.10. 23:59')")
        parser.add_argument("--teacher", default="", help="Teacher abbreviation (e.g. BIM)")
        parser.add_argument("--desc", "--description", default="", help="Optional description")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, _ = parser.parse_known_args(sub_args)

        if not args.title or not args.subject:
            msg = "Error: --title and --subject are required. Example: tasks add --title \"Mathe HÜ\" --subject \"AM\" --due \"15.10. 23:59\""
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        clean_sub = normalize_subject_name(args.subject)
        teacher = args.teacher
        if not teacher:
            teacher = extract_teacher("", clean_sub, args.title, args.desc)
            if teacher == "-":
                teacher = ""

        new_task = Task(
            id=f"manual_{int(time.time() * 1000)}",
            platform="manual",
            course=clean_sub,
            course_full=args.subject,
            title=args.title,
            due_date_str=args.due or "No deadline",
            status="open",
            status_display="Open",
            url="",
            teacher=teacher,
            description=args.desc,
            details_loaded=True,
            due_timestamp=parse_deadline_for_sorting(args.due),
        )
        mgr.add_task(new_task)

        if args.json:
            print(json.dumps({
                "success": True,
                "task": new_task.to_dict()
            }, ensure_ascii=False, indent=2))
        else:
            print(f"✓ Added assignment '{new_task.title}' (ID: {new_task.id}, Subject: {new_task.course}, Due: {new_task.due_date_str})")
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 7. DONE / COMPLETE / TOGGLE
    # ─────────────────────────────────────────────────────────────────
    if command in ["done", "complete", "toggle"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Task ID or 1-based index")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            msg = f"Error: Please provide a Task ID or index to mark as done. Example: 'tasks done 1'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        task = resolve_task(mgr, target)
        if not task:
            msg = f"Error: Task '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        updated = mgr.toggle_task_status(task.id)
        if not updated:
            msg = f"Error: Could not update task '{task.id}'."
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        state = "Completed" if updated.is_completed else "Open"
        if args.json:
            print(json.dumps({
                "success": True,
                "id": updated.id,
                "title": updated.title,
                "completed": updated.is_completed,
                "status": updated.status,
                "status_display": updated.status_display
            }, ensure_ascii=False))
        else:
            print(f"✓ Task '{updated.title}' ({updated.id}) is now marked as: {state}")
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 8. DELETE / REMOVE / HIDE
    # ─────────────────────────────────────────────────────────────────
    if command in ["delete", "del", "remove", "rm", "hide"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Task ID or 1-based index")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            msg = f"Error: Please provide a Task ID or index to delete/hide. Example: 'tasks delete 1'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        task = resolve_task(mgr, target)
        if not task:
            msg = f"Error: Task '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg, "target": target}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        mgr.delete_task(task.id)

        if args.json:
            print(json.dumps({
                "success": True,
                "id": task.id,
                "title": task.title,
                "deleted": True
            }, ensure_ascii=False))
        else:
            print(f"✓ Task '{task.title}' ({task.id}) hidden/deleted. (Restore with: tasks restore {task.id})")
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 9. RESTORE / UNHIDE
    # ─────────────────────────────────────────────────────────────────
    if command in ["restore", "unhide", "undelete"]:
        parser = argparse.ArgumentParser(prog=f"tasks {command}", add_help=False)
        parser.add_argument("target", nargs="?", default="", help="Task ID or 1-based index")
        parser.add_argument("--json", action="store_true", help="Output as JSON")
        args, remaining = parser.parse_known_args(sub_args)

        target = args.target or (remaining[0] if remaining else "")
        if not target:
            msg = f"Error: Please provide a Task ID or index to restore. Example: 'tasks restore moodle_12345'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        task = resolve_task(mgr, target)
        task_id = task.id if task else target

        restored = mgr.restore_task(task_id)
        if args.json:
            print(json.dumps({
                "success": restored,
                "id": task_id,
                "restored": restored
            }, ensure_ascii=False))
        else:
            if restored:
                print(f"✓ Task '{task_id}' restored to active list.")
            else:
                print(f"Notice: Task '{task_id}' was not in hidden/deleted list.")
        return 0

    # ─────────────────────────────────────────────────────────────────
    # 10. SCHOOLBOOKS (PDF & Web)
    # ─────────────────────────────────────────────────────────────────
    if command in ["books", "book", "schulbuch", "schulbücher"]:
        return handle_books_command(sub_args)

    # ─────────────────────────────────────────────────────────────────
    # 11. DIRECTORIES (Local Folders)
    # ─────────────────────────────────────────────────────────────────
    if command in ["dirs", "dir", "directories", "folder", "folders", "ordner"]:
        return handle_dirs_command(sub_args)

    # ─────────────────────────────────────────────────────────────────
    # 12. SKILL (Sync/Status of Agent Skill)
    # ─────────────────────────────────────────────────────────────────
    if command in ["skill", "skills"]:
        return handle_skill_command(sub_args)

    # Unbekannter Befehl
    print(f"Unknown command: '{command}'. Use 'tasks guide' or 'tasks --help' for available commands.")
    return 1


def handle_books_command(sub_args: List[str]) -> int:
    """Manages and opens schoolbooks via CLI."""
    parser = argparse.ArgumentParser(prog="tasks books", add_help=False)
    parser.add_argument("action", nargs="?", default="list", help="list, open, add, remove, download")
    parser.add_argument("target", nargs="?", default="", help="Book title, ID, index, file path, web URL, or access code")
    parser.add_argument("--title", "-t", default="", help="Title for the book (optional for PDF)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args, remaining = parser.parse_known_args(sub_args)

    try:
        from schoolbook_service import SchoolbookService
    except ImportError:
        from src.services.schoolbook_service import SchoolbookService

    action = (args.action or "list").lower()
    target = args.target or (remaining[0] if remaining else "")

    # If first parameter is not an action, but a search query or index to open:
    if action not in ["list", "ls", "open", "add", "remove", "rm", "delete", "download", "grab", "d4s", "digi", "digi4school"]:
        target = args.action
        action = "open"

    books = SchoolbookService.load_books()

    if action in ["list", "ls"]:
        if args.json:
            print(json.dumps({"books": books, "count": len(books)}, ensure_ascii=False, indent=2))
        else:
            if not books:
                print("No schoolbooks linked. Link one with: tasks books add <path|url>")
            else:
                print(f"=== Schoolbooks ({len(books)} linked) ===")
                for idx, b in enumerate(books, 1):
                    badge = "[PDF]" if b.get("type") == "pdf" else "[WEB]"
                    print(f"[{idx}] {badge} {b.get('title')}")
                    print(f"    Path/URL: {b.get('path')}")
        return 0

    if action == "open":
        if not target:
            msg = "Error: Please specify a book title, ID, or index. Example: 'tasks books open 1'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        selected_book = None
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(books):
                selected_book = books[idx]

        if not selected_book:
            selected_book = SchoolbookService.find_book(target)

        if not selected_book:
            msg = f"Error: Schoolbook '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        ok, msg = SchoolbookService.open_book(selected_book)
        if args.json:
            print(json.dumps({"success": ok, "message": msg, "book": selected_book}, ensure_ascii=False))
        else:
            print(f"{'✓' if ok else '✗'} {msg}")
        return 0 if ok else 1

    if action == "add":
        if not target:
            msg = "Error: Please provide a path to a PDF file or a URL. Example: 'tasks books add C:\\book.pdf'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        is_url = target.startswith("http://") or target.startswith("https://")
        if is_url:
            book = SchoolbookService.add_web_book(target, title=args.title)
        else:
            if not os.path.exists(target):
                msg = f"Error: File '{target}' does not exist."
                if args.json:
                    print(json.dumps({"error": msg}, ensure_ascii=False))
                else:
                    print(msg)
                return 1
            book = SchoolbookService.add_pdf_book(target, title=args.title)

        if args.json:
            print(json.dumps({"success": True, "book": book}, ensure_ascii=False))
        else:
            print(f"✓ Schoolbook '{book.get('title')}' successfully linked.")
        return 0

    if action in ["remove", "rm", "delete"]:
        if not target:
            msg = "Error: Please specify a book to remove."
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        target_id = target
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(books):
                target_id = books[idx].get("id", target)

        ok = SchoolbookService.remove_book(target_id)
        if args.json:
            print(json.dumps({"success": ok, "target": target}, ensure_ascii=False))
        else:
            if ok:
                print(f"✓ Schoolbook '{target}' removed.")
            else:
                print(f"Error: Schoolbook '{target}' not found.")
        return 0 if ok else 1

    if action in ["download", "grab", "d4s", "digi", "digi4school"]:
        if not target:
            msg = "Error: Please specify a 12-digit access code. Example: 'tasks books download 26s7dbu5qxvw'"
            if args.json:
                print(json.dumps({"error": msg, "success": False}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        parser_d4s = argparse.ArgumentParser(prog="tasks books download", add_help=False)
        parser_d4s.add_argument("--email", default="", help="Digi4School Email")
        parser_d4s.add_argument("--password", default="", help="Digi4School Password")
        parser_d4s.add_argument("--output", "-o", default="", help="Target file path")
        parser_d4s.add_argument("--pages", "-p", default="", help="Page range (e.g. '1-50')")
        parser_d4s.add_argument("--scale", type=float, default=4.0, help="Device scale factor (e.g. 4.0 for Ultra-HD, 2.0 for standard)")
        parser_d4s.add_argument("--quality", choices=["standard", "high", "ultra"], default=None, help="Render quality preset: standard (2.0), high (3.0), ultra (4.0)")
        parser_d4s.add_argument("--dpi", type=int, default=None, help="Custom DPI resolution (default: auto from scale, e.g. 600 at 4.0)")
        parser_d4s.add_argument("--psm", type=int, default=3, help="Tesseract Page Segmentation Mode")
        parser_d4s.add_argument("--lang", "-l", default="deu+eng", help="OCR language(s)")
        parser_d4s.add_argument("--no-ocr", action="store_true", help="Skip OCR and generate image-only PDF")
        parser_d4s.add_argument("--no-toc", action="store_true", help="Skip table of contents and bookmarks")
        parser_d4s.add_argument("--page-offset", default="auto", help="Offset for page numbering ('auto' or integer)")
        parser_d4s.add_argument("--visible", action="store_true", help="Show browser window during download")
        parser_d4s.add_argument("--tesseract-cmd", default=None, help="Custom path to tesseract executable")
        parser_d4s.add_argument("--timeout", type=int, default=45, help="Timeout per page in seconds")
        parser_d4s.add_argument("--retries", type=int, default=3, help="Max retry attempts per page")
        d4s_args, _ = parser_d4s.parse_known_args(sub_args)

        email = d4s_args.email
        password = d4s_args.password

        if not email:
            if sys.stdin.isatty():
                email = input("Digi4School Email: ").strip()
            else:
                msg = "Error: No email provided (--email required)."
                if args.json:
                    print(json.dumps({"error": msg, "success": False}, ensure_ascii=False))
                else:
                    print(msg)
                return 1

        if not password:
            if sys.stdin.isatty():
                import getpass
                password = getpass.getpass("Digi4School Password: ")
            else:
                msg = "Error: No password provided (--password required)."
                if args.json:
                    print(json.dumps({"error": msg, "success": False}, ensure_ascii=False))
                else:
                    print(msg)
                return 1

        try:
            from digi4school_service import Digi4SchoolService
        except ImportError:
            from src.services.digi4school_service import Digi4SchoolService

        import asyncio
        import time

        t0 = time.time()
        phase_start = [t0]
        curr_phase = [""]

        def cli_progress(phase, cur, tot, msg_txt):
            if not args.json:
                now = time.time()
                if phase != curr_phase[0]:
                    curr_phase[0] = phase
                    phase_start[0] = now
                eta_str = ""
                if phase in ("pages", "ocr") and cur > 0 and tot > 0:
                    el = now - phase_start[0]
                    rate = cur / max(0.001, el)
                    rem = (tot - cur) / max(0.001, rate)
                    m, s = divmod(int(rem), 60)
                    eta_str = f" [ETA: {m:02d}:{s:02d}]"
                sys.stdout.write(f"\r[{phase}] {msg_txt}{eta_str}            ")
                sys.stdout.flush()

        try:
            res = asyncio.run(
                Digi4SchoolService.download_book(
                    email=email,
                    password=password,
                    code=target,
                    output_path=d4s_args.output or None,
                    pages=d4s_args.pages or None,
                    scale=d4s_args.scale,
                    quality=d4s_args.quality,
                    dpi=d4s_args.dpi,
                    psm=d4s_args.psm,
                    lang=d4s_args.lang,
                    timeout=d4s_args.timeout,
                    retries=d4s_args.retries,
                    no_ocr=d4s_args.no_ocr,
                    no_toc=d4s_args.no_toc,
                    page_offset=d4s_args.page_offset,
                    visible=d4s_args.visible,
                    tesseract_cmd=d4s_args.tesseract_cmd,
                    progress_cb=cli_progress,
                )
            )
            if not args.json:
                sys.stdout.write("\n")
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"✓ Schoolbook '{res.get('title')}' successfully downloaded:")
                print(f"  Path:       {res.get('path')}")
                print(f"  Pages:      {res.get('pages')}")
                print(f"  Size:       {res.get('size_mb')} MB")
                print(f"  Resolution: Scale {res.get('scale', 4.0):g}x ({res.get('dpi', 600)} DPI)")
                print(f"  OCR:        {'Yes' if res.get('ocr') else 'No'}")
                print(f"  TOC / Links:{'Yes' if res.get('toc') else 'No'}")
            return 0
        except Exception as e:
            if not args.json:
                sys.stdout.write("\n")
            msg = f"Error during download: {e}"
            if args.json:
                print(json.dumps({"error": msg, "success": False}, ensure_ascii=False))
            else:
                print(msg)
            return 1

    return 0


def handle_dirs_command(sub_args: List[str]) -> int:
    """Manages and opens linked directories via CLI."""
    parser = argparse.ArgumentParser(prog="tasks dirs", add_help=False)
    parser.add_argument("action", nargs="?", default="list", help="list, open, add, remove")
    parser.add_argument("target", nargs="?", default="", help="Directory title, ID, index, or folder path")
    parser.add_argument("--title", "-t", default="", help="Title for the directory (optional)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args, remaining = parser.parse_known_args(sub_args)

    try:
        from directory_service import DirectoryService
    except ImportError:
        from src.services.directory_service import DirectoryService

    action = (args.action or "list").lower()
    target = args.target or (remaining[0] if remaining else "")

    if action not in ["list", "ls", "open", "add", "remove", "rm", "delete"]:
        target = args.action
        action = "open"

    dirs = DirectoryService.load_directories()

    if action in ["list", "ls"]:
        if args.json:
            print(json.dumps({"directories": dirs, "count": len(dirs)}, ensure_ascii=False, indent=2))
        else:
            if not dirs:
                print("No directories linked. Link one with: tasks dirs add <path>")
            else:
                print(f"=== Linked Directories ({len(dirs)} linked) ===")
                for idx, d in enumerate(dirs, 1):
                    print(f"[{idx}] 📁 {d.get('title')}")
                    print(f"    Path: {d.get('path')}")
        return 0

    if action == "open":
        if not target:
            msg = "Error: Please specify a directory title, ID, or index. Example: 'tasks dirs open 1'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        selected_dir = None
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(dirs):
                selected_dir = dirs[idx]

        if not selected_dir:
            selected_dir = DirectoryService.find_directory(target)

        if not selected_dir:
            msg = f"Error: Directory '{target}' not found."
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        ok, msg = DirectoryService.open_directory(selected_dir)
        if args.json:
            print(json.dumps({"success": ok, "message": msg, "directory": selected_dir}, ensure_ascii=False))
        else:
            print(f"{'✓' if ok else 'Error:'} {msg}")
        return 0 if ok else 1

    if action == "add":
        if not target:
            msg = "Error: Please provide a folder path. Example: 'tasks dirs add C:\\path\\to\\BET'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        clean_path = target.strip().strip('"').strip("'")
        if not os.path.exists(clean_path):
            msg = f"Error: Directory path does not exist on disk: '{clean_path}'"
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        entry = DirectoryService.add_directory(clean_path, title=args.title)
        if args.json:
            print(json.dumps({"success": True, "directory": entry}, ensure_ascii=False))
        else:
            print(f"✓ Linked directory '{entry.get('title')}' -> {entry.get('path')}")
        return 0

    if action in ["remove", "rm", "delete"]:
        if not target:
            msg = "Error: Please specify a directory title, ID, or index to remove."
            if args.json:
                print(json.dumps({"error": msg}, ensure_ascii=False))
            else:
                print(msg)
            return 1

        target_id = target
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(dirs):
                target_id = dirs[idx].get("id", target)

        ok = DirectoryService.remove_directory(target_id)
        if args.json:
            print(json.dumps({"success": ok, "removed": target_id}, ensure_ascii=False))
        else:
            if ok:
                print(f"✓ Removed directory link '{target}'")
            else:
                print(f"Notice: Directory '{target}' was not found in linked list.")
        return 0 if ok else 1

    print(f"Unknown action: '{action}'. Available: list, open, add, remove")
    return 1


def handle_skill_command(sub_args: List[str]) -> int:
    """Manages syncing and status of the global Antigravity/Agent skill."""
    parser = argparse.ArgumentParser(prog="tasks skill", add_help=False)
    parser.add_argument("action", nargs="?", default="sync", help="sync, install, update, status, check")
    parser.add_argument("--target", default="", help="Custom target directory for the skill (defaults to ~/.gemini/config/skills/tasks)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args, _ = parser.parse_known_args(sub_args)

    action = (args.action or "sync").lower()
    if action not in ["sync", "install", "update", "status", "check", "info"]:
        action = "sync"

    # Ermittle Quell-Skillverzeichnis
    try:
        from config import WORKSPACE_DIR
    except ImportError:
        WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    source_skill_file = os.path.join(WORKSPACE_DIR, "skills", "tasks", "SKILL.md")
    if not os.path.exists(source_skill_file):
        # Fallback relative zu dieser Datei
        source_skill_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "skills", "tasks", "SKILL.md"))

    # Zielverzeichnis: Standardmäßig ~/.gemini/config/skills/tasks
    if args.target:
        target_dir = os.path.abspath(args.target)
    else:
        user_home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        target_dir = os.path.join(user_home, ".gemini", "config", "skills", "tasks")

    target_skill_file = os.path.join(target_dir, "SKILL.md")

    if action in ["status", "check", "info"]:
        exists = os.path.exists(target_skill_file)
        in_sync = False
        source_exists = os.path.exists(source_skill_file)
        if exists and source_exists:
            try:
                with open(source_skill_file, "r", encoding="utf-8") as f_s, open(target_skill_file, "r", encoding="utf-8") as f_t:
                    in_sync = (f_s.read() == f_t.read())
            except Exception:
                in_sync = False

        if args.json:
            print(json.dumps({
                "installed": exists,
                "in_sync": in_sync,
                "source_file": source_skill_file if source_exists else None,
                "target_file": target_skill_file,
                "target_dir": target_dir
            }, ensure_ascii=False, indent=2))
        else:
            if not source_exists:
                print(f"Warning: Source skill not found at '{source_skill_file}'.")
            if exists:
                status_str = "in sync with repo" if in_sync else "outdated / differs from repo"
                print(f"✓ tasks skill is installed at: {target_skill_file} ({status_str})")
            else:
                print(f"Notice: tasks skill is not installed yet. Run 'tasks skill sync' to install.")
        return 0

    # action in ["sync", "install", "update"]
    if not os.path.exists(source_skill_file):
        msg = f"Error: Source skill file not found at: '{source_skill_file}'"
        if args.json:
            print(json.dumps({"error": msg, "success": False}, ensure_ascii=False))
        else:
            print(msg)
        return 1

    try:
        os.makedirs(target_dir, exist_ok=True)
        import shutil
        shutil.copy2(source_skill_file, target_skill_file)

        # Zusätzliche Dateien/Ordner aus dem Quellverzeichnis synchronisieren
        source_dir = os.path.dirname(source_skill_file)
        for item in os.listdir(source_dir):
            if item == "SKILL.md":
                continue
            s_item = os.path.join(source_dir, item)
            t_item = os.path.join(target_dir, item)
            if os.path.isdir(s_item):
                if os.path.exists(t_item):
                    shutil.rmtree(t_item, ignore_errors=True)
                shutil.copytree(s_item, t_item)
            elif os.path.isfile(s_item):
                shutil.copy2(s_item, t_item)

        if args.json:
            print(json.dumps({
                "success": True,
                "action": "synced",
                "source_file": source_skill_file,
                "target_file": target_skill_file,
                "target_dir": target_dir
            }, ensure_ascii=False, indent=2))
        else:
            print(f"✓ Successfully synced tasks skill to:")
            print(f"  {target_skill_file}")
            print(f"  Slash command: /tasks")
        return 0
    except Exception as e:
        msg = f"Error syncing skill: {e}"
        if args.json:
            print(json.dumps({"error": msg, "success": False}, ensure_ascii=False))
        else:
            print(msg)
        return 1
