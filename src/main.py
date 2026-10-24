"""
main.py - Hauptprogramm des Aufgaben-Detectors für Moodle und Microsoft Teams.
Konsolidierte Aufgabenverwaltung.
"""

import argparse
import json
import os
import sys
import time
import warnings

# Suppress PyMuPDF legacy fitz module deprecation warning
warnings.filterwarnings("ignore", category=FutureWarning, module="fitz")

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _sub in [_ROOT_DIR, _SRC_DIR, os.path.join(_SRC_DIR, "core"), os.path.join(_SRC_DIR, "services"), os.path.join(_SRC_DIR, "ui")]:
    if _sub not in sys.path:
        sys.path.insert(0, _sub)

# Enable Per-Monitor DPI Awareness v2 early for Windows processes
if sys.platform == "win32":
    try:
        from win_dialogs import enable_high_dpi_awareness
        enable_high_dpi_awareness()
    except Exception:
        pass

from rich.console import Console
from rich.prompt import Prompt

from config import clean_browser_profile_caches, AUTO_CLEAN_BROWSER_CACHE
from models import Task
from task_manager import TaskManager
import ui

console = Console()


def handle_detail_view(task: Task, mgr: TaskManager, is_deleted: bool = False):
    """Interaktive Schleife für die Aufgaben-Detailansicht."""
    # Lade Details, falls nötig
    if not task.details_loaded:
        with console.status(f"[bold cyan]Loading details & attachments for '{task.title}'...[/bold cyan]", spinner="dots"):
            mgr.load_task_details(task)

    while True:
        ui.render_task_detail(task, is_deleted=is_deleted)
        valid_choices = ["o", "d", "w", "z", ""] if is_deleted else ["o", "d", "l", "z", ""]
        action = Prompt.ask("\nSelect action", choices=valid_choices, default="z").strip().lower()

        if action == "o":
            ui.open_task_in_browser(task)
            time.sleep(1)
        elif action == "d":
            with console.status(f"[bold green]Downloading files for '{task.title}' to Downloads...[/bold green]", spinner="dots"):
                files = mgr.download_task_files(task)
            if files:
                console.print(f"\n[bold green]✓ {len(files)} file(s) successfully saved in:[/bold green]")
                console.print(f"[cyan]{task.download_dir}[/cyan]\n")
                try:
                    os.startfile(task.download_dir)
                except Exception:
                    pass
            else:
                console.print("\n[yellow]No downloadable attachments found. (angabe.md created)[/yellow]\n")
            Prompt.ask("Press [ENTER] to continue")
        elif action == "l" and not is_deleted:
            mgr.delete_task(task.id)
            console.print(f"\n[bold green]✓ Assignment '{task.title}' was hidden / deleted![/bold green]")
            console.print("[dim]It will no longer appear in your active task list.[/dim]")
            console.print("[dim]You can restore it anytime via [G] in the main menu.[/dim]\n")
            Prompt.ask("Press [ENTER] to return to menu")
            break
        elif action == "w" and is_deleted:
            mgr.restore_task(task.id)
            console.print(f"\n[bold green]✓ Assignment '{task.title}' restored to active list![/bold green]\n")
            Prompt.ask("Press [ENTER] to continue")
            break
        elif action in ["z", ""]:
            break


def handle_deleted_tasks_menu(mgr: TaskManager):
    """Menü zur Anzeige und Wiederherstellung gelöschter Aufgaben."""
    while True:
        deleted_tasks = mgr.get_deleted_tasks()
        ui.render_deleted_tasks_table(deleted_tasks)

        if not deleted_tasks:
            Prompt.ask("Press [ENTER] to return to main menu")
            break

        console.print("─" * 78)
        console.print(
            "[bold white]Commands:[/bold white] "
            "[bold cyan][1-N][/bold cyan] Details / Restore  |  "
            "[bold green][W][/bold green] Restore all  |  "
            "[bold yellow][Z][/bold yellow] Back to main menu"
        )
        try:
            choice = Prompt.ask("\nEnter choice").strip()
        except (KeyboardInterrupt, EOFError):
            break

        choice_lower = choice.lower()
        if choice_lower in ["z", "q", ""]:
            break
        elif choice_lower == "w":
            for t in list(deleted_tasks):
                mgr.restore_task(t.id)
            console.print("\n[bold green]✓ All hidden assignments successfully restored![/bold green]\n")
            time.sleep(1.2)
            break
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(deleted_tasks):
                selected = deleted_tasks[idx - 1]
                handle_detail_view(selected, mgr, is_deleted=True)
            else:
                console.print(f"[red]Invalid number: {idx}.[/red]")
                time.sleep(1.2)


def interactive_loop():
    """Haupt-CLI-Schleife."""
    mgr = TaskManager()

    # Falls noch gar keine Aufgaben im Cache sind, einmalig synchronisieren
    if not mgr.tasks:
        console.clear()
        console.print("[bold cyan]First start: Syncing current assignments from Moodle and Teams...[/bold cyan]\n")
        with console.status("[bold green]Loading Moodle & Teams data...[/bold green]", spinner="dots") as status:
            mgr.sync(
                deep_scan=False,
                on_progress=lambda msg: status.update(f"[bold green]{msg}[/bold green]")
            )

    platform_filter = "all"
    status_filter = "open_only"
    subject_filter = "all"

    try:
        while True:
            console.clear()

            # Statistiken
            moodle_count = len([t for t in mgr.tasks if t.platform == "moodle"])
            teams_count = len([t for t in mgr.tasks if t.platform == "teams"])
            deleted_count = len(mgr.get_deleted_tasks())
            ui.render_header(moodle_count, teams_count, mgr.last_sync, deleted_count=deleted_count)

            # Aktuell gefilterte Aufgaben
            current_tasks = mgr.get_filtered_tasks(
                platform_filter=platform_filter,
                status_filter=status_filter,
                subject_filter=None if subject_filter == "all" else subject_filter
            )

            ui.render_task_table(
                current_tasks,
                current_filter_platform=platform_filter,
                current_filter_status=status_filter,
                current_subject_filter=subject_filter
            )

            # Befehlszeile
            g_badge = "[bold magenta][G][/bold magenta] Trash"
            console.print("\n" + "─" * 78)
            console.print(
                "[bold white]Commands:[/bold white] "
                "[bold cyan][1-N][/bold cyan] Details  |  "
                "[bold green][A][/bold green] Add  |  "
                "[bold yellow][R][/bold yellow] Sync  |  "
                "[bold yellow][F][/bold yellow] Subject  |  "
                "[bold yellow][S][/bold yellow] Status  |  "
                "[bold yellow][P][/bold yellow] Platform  |  "
                f"{g_badge}  |  "
                "[bold blue][T][/bold blue] Teams  |  "
                "[bold orange3][M][/bold orange3] Moodle  |  "
                "[bold red][Q][/bold red] Quit"
            )

            try:
                choice = Prompt.ask("\nEnter choice").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Program terminated.[/dim]")
                break

            if not choice:
                continue

            choice_lower = choice.lower()

            # 1. Beenden
            if choice_lower in ["q", "exit", "quit"]:
                console.print("\n[bold green]Goodbye and good luck with your schoolwork![/bold green]")
                break

            # 2. Hinzufügen (Add)
            elif choice_lower == "a":
                console.print("\n[bold cyan]Add Homework / Assignment:[/bold cyan]")
                sub = Prompt.ask("Subject").strip()
                tit = Prompt.ask("Assignment title").strip()
                due = Prompt.ask("Due date (e.g. 15.10. 23:59)", default="No deadline").strip()
                tch = Prompt.ask("Teacher (e.g. BIM/EIJ, WAW)", default="").strip()
                dsc = Prompt.ask("Description (optional)", default="").strip()

                if sub and tit:
                    from config import normalize_subject_name, extract_teacher
                    from task_manager import parse_deadline_for_sorting
                    clean_sub = normalize_subject_name(sub)
                    if not tch:
                        tch = extract_teacher("", clean_sub, tit, dsc)
                        if tch == "-":
                            tch = ""
                    new_task = Task(
                        id=f"manual_{int(time.time() * 1000)}",
                        platform="manual",
                        course=clean_sub,
                        course_full=sub,
                        title=tit,
                        due_date_str=due or "No deadline",
                        status="open",
                        status_display="Open",
                        url="",
                        teacher=tch,
                        description=dsc,
                        details_loaded=True,
                        due_timestamp=parse_deadline_for_sorting(due),
                    )
                    mgr.add_task(new_task)
                    console.print(f"[bold green]✓ Assignment '{tit}' added successfully![/bold green]")
                else:
                    console.print("[yellow]Subject and title are required. Assignment not added.[/yellow]")
                time.sleep(1.2)

            # 3. Synchronisieren
            elif choice_lower == "r":
                console.print("\n[cyan]Syncing Moodle and Teams live...[/cyan]")
                with console.status("[bold green]Syncing Moodle and Teams in parallel...[/bold green]", spinner="dots") as status:
                    m_cnt, t_cnt = mgr.sync(
                        deep_scan=False,
                        on_progress=lambda msg: status.update(f"[bold green]{msg}[/bold green]")
                    )
                console.print(f"[bold green]✓ Synced: {m_cnt} Moodle tasks, {t_cnt} Teams tasks.[/bold green]")
                time.sleep(1.2)

            # 4. Status-Filter auswählen
            elif choice_lower == "s":
                console.print("\n[bold]Select Status Filter:[/bold]")
                console.print("  [bold cyan][1][/bold cyan] Open only")
                console.print("  [bold cyan][2][/bold cyan] Overdue only")
                console.print("  [bold cyan][3][/bold cyan] Completed only")
                console.print("  [bold cyan][4][/bold cyan] All")
                curr_choice = {"open_only": "1", "overdue": "2", "completed": "3", "all": "4"}.get(status_filter, "1")
                s_in = Prompt.ask("\nChoice [1-4]", default=curr_choice).strip().lower()
                if s_in in ["1", "o", "open", "offen"]:
                    status_filter = "open_only"
                elif s_in in ["2", "u", "overdue", "ueberfaellig", "überfällig"]:
                    status_filter = "overdue"
                elif s_in in ["3", "c", "completed", "erledigt", "abgegeben"]:
                    status_filter = "completed"
                elif s_in in ["4", "a", "all", "alle"]:
                    status_filter = "all"
                elif s_in in ["q", "z", "back", "zurueck"]:
                    pass
                else:
                    console.print("[yellow]Invalid input. Filter remains unchanged.[/yellow]")
                    time.sleep(1.0)

            # 5. Plattform-Filter auswählen
            elif choice_lower == "p":
                console.print("\n[bold]Select Platform Filter:[/bold]")
                console.print("  [bold cyan][1][/bold cyan] All platforms")
                console.print("  [bold cyan][2][/bold cyan] Moodle")
                console.print("  [bold cyan][3][/bold cyan] Teams")
                console.print("  [bold cyan][4][/bold cyan] Manual")
                curr_choice = {"all": "1", "moodle": "2", "teams": "3", "manual": "4"}.get(platform_filter, "1")
                p_in = Prompt.ask("\nChoice [1-4]", default=curr_choice).strip().lower()
                if p_in in ["1", "a", "all", "alle"]:
                    platform_filter = "all"
                elif p_in in ["2", "m", "moodle"]:
                    platform_filter = "moodle"
                elif p_in in ["3", "t", "teams"]:
                    platform_filter = "teams"
                elif p_in in ["4", "c", "manual", "custom"]:
                    platform_filter = "manual"
                elif p_in in ["q", "z", "back", "zurueck"]:
                    pass
                else:
                    console.print("[yellow]Invalid input. Filter remains unchanged.[/yellow]")
                    time.sleep(1.0)

            # 6. Fach-Filter
            elif choice_lower == "f":
                available_subjects = sorted(list(set(t.course for t in mgr.tasks)))
                console.print(f"\n[bold]Available subjects:[/bold] {', '.join(available_subjects)}")
                f_in = Prompt.ask("Filter by which subject? ('all' for all)").strip()
                if f_in:
                    subject_filter = f_in

            # 7. Gelöschte / Ausgeblendete Aufgaben anzeigen & verwalten
            elif choice_lower == "g":
                handle_deleted_tasks_menu(mgr)

            # 8. Teams Setup / Login
            elif choice_lower == "t":
                from auth import setup_teams_interactive
                success = setup_teams_interactive(console)
                if success:
                    with console.status("[bold green]Updating Teams assignments...[/bold green]", spinner="dots") as status:
                        mgr.sync(
                            deep_scan=False,
                            on_progress=lambda msg: status.update(f"[bold green]{msg}[/bold green]")
                        )
                else:
                    time.sleep(1.5)

            # 9. Moodle Setup / Login
            elif choice_lower == "m":
                from auth import setup_moodle_interactive
                success = setup_moodle_interactive(console)
                if success:
                    with console.status("[bold green]Updating Moodle assignments...[/bold green]", spinner="dots") as status:
                        mgr.sync(
                            deep_scan=False,
                            on_progress=lambda msg: status.update(f"[bold green]{msg}[/bold green]")
                        )
                else:
                    time.sleep(1.5)

            # 10. Nummernauswahl (Aufgabe öffnen)
            elif choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(current_tasks):
                    selected_task = current_tasks[idx - 1]
                    handle_detail_view(selected_task, mgr)
                else:
                    console.print(f"[red]Invalid number: {idx}. Please choose a number between 1 and {len(current_tasks)}.[/red]")
                    time.sleep(1.2)
    finally:
        mgr.stop_background_prefetch()


def main():
    # ── Blitzschnelle Agent-CLI Dispatch ────────────────────────────────────
    from agent_cli import is_agent_cli_command, run_agent_cli
    if len(sys.argv) > 1 and is_agent_cli_command(sys.argv[1:]):
        sys.exit(run_agent_cli(sys.argv[1:]))
    # ────────────────────────────────────────────────────────────────────────

    if AUTO_CLEAN_BROWSER_CACHE:
        try:
            clean_browser_profile_caches()
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="School Assignment Hub for Moodle & Microsoft Teams")
    parser.add_argument("--sync", action="store_true", help="Sync all assignments from Moodle and Teams")
    parser.add_argument("--teams-login", action="store_true", help="Perform interactive Microsoft Teams login")
    parser.add_argument("--moodle-login", action="store_true", help="Perform Moodle login")
    parser.add_argument("--untis-login", action="store_true", help="Perform interactive WebUntis login in browser")
    parser.add_argument("--untis-sync", action="store_true", help="Sync WebUntis absences and timetable")
    parser.add_argument("--json", action="store_true", help="Output tasks as structured JSON")
    parser.add_argument("--deep", action="store_true", help="Perform Moodle deep scan across all courses")
    parser.add_argument("--cli", action="store_true", help="Start classic text CLI instead of modern TUI")

    args = parser.parse_args()

    if not args.json:
        from dependency_checker import ensure_dependencies
        ensure_dependencies()

    if args.teams_login:
        from auth import setup_teams_interactive
        setup_teams_interactive(console)
        return

    if args.moodle_login:
        from auth import setup_moodle_interactive
        setup_moodle_interactive(console)
        return

    if args.untis_login:
        from untis_service import open_untis_login_window
        open_untis_login_window()
        return

    if args.untis_sync:
        from untis_service import sync_untis_data
        ok, msg, summaries = sync_untis_data(headless=True)
        print(msg)
        for s in summaries:
            print(f"- {s.subject}: {s.total_hours} hour(s) missed (Last: {s.last_date})")
        return

    if args.sync or args.json:
        mgr = TaskManager(autostart_prefetch=False)
        mgr.sync(deep_scan=args.deep, start_prefetch=False)
        if args.json:
            print(json.dumps([t.to_dict() for t in mgr.tasks], ensure_ascii=False, indent=2))
        else:
            moodle_count = len([t for t in mgr.tasks if t.platform == "moodle"])
            teams_count = len([t for t in mgr.tasks if t.platform == "teams"])
            ui.render_header(moodle_count, teams_count, mgr.last_sync)
            ui.render_task_table(mgr.tasks, current_filter_status="all")
        return

    # Standard: Modern TUI with mouse buttons (or explicit CLI via --cli)
    if args.cli:
        ui.adjust_console_window(120, 32)
        interactive_loop()
    else:
        try:
            from tui_app import run_tui
            code = run_tui()
            sys.exit(code or 0)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as e:
            console.print(f"[bold red]Error running application:[/bold red] {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
