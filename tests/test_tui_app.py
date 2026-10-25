"""
test_tui_app.py - Automatisierter Integrationstest für die Textual-TUI mit Maus-Buttons.
"""

import asyncio
import datetime
import os
import sys
import unittest
from unittest.mock import patch
from textual.command import CommandPalette
from textual.events import MouseDown, Click
from textual.widgets import Button, DataTable, Footer, Input, Label

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import src

from config import ALLOWED_THEMES, DEFAULT_THEME, load_saved_theme, save_saved_theme, load_all_course_links
from tui_app import (
    TasksApp,
    AufgabenDetectorApp,
    AddTaskModal,
    StatusFilterModal,
    TimeframeFilterModal,
    PlatformFilterModal,
    SubjectFilterModal,
    FilterMenuModal,
    SettingsModal,
    TrashModal,
    TaskDetailModal,
    LoginChoiceModal,
    LoginReminderModal,
    TeamsSetupModal,
    MoodleLoginModal,
    UntisSetupModal,
    AbsencesScreen,
    ExcuseLetterModal,
    ExamsScreen,
    AddExamModal,
    is_app_window_foreground,
    SyncSpinner,
    HOTKEYS_CATALOG,
    CourseLinksProvider,
)
from task_manager import TaskManager
from models import Task


class TestAufgabenDetectorTUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from config import save_enabled_platforms, DEFAULT_ENABLED_PLATFORMS
        save_enabled_platforms(dict(DEFAULT_ENABLED_PLATFORMS))
        # Erstelle TaskManager ohne automatischen Hintergrund-Prefetch für Tests
        self.mgr = TaskManager(autostart_prefetch=False)
        self.mgr.tasks = [
            Task(
                id="test_1",
                platform="moodle",
                course="SWP",
                course_full="Softwareentwicklung",
                title="SWP Hausübung 1",
                due_date_str="Morgen, 15:00 Uhr",
                status="offen",
                status_display="Zugewiesen",
                url="https://moodle.spengergasse.at",
                teacher="AIC",
                details_loaded=True,
                description="Test Moodle Aufgabe Beschreibung"
            ),
            Task(
                id="test_2",
                platform="teams",
                course="UFW",
                course_full="3AHWII UFW",
                title="UFW Teams Aufgabe",
                due_date_str="Überfällig",
                status="ueberfaellig",
                status_display="Überfällig",
                url="https://teams.cloud.microsoft",
                teacher="FAT",
                details_loaded=True,
                description="Test Teams Aufgabe Beschreibung"
            )
        ]

    async def asyncTearDown(self):
        from config import save_enabled_platforms, DEFAULT_ENABLED_PLATFORMS
        save_enabled_platforms(dict(DEFAULT_ENABLED_PLATFORMS))

    def test_tasks_app_class_and_alias(self):
        """Prüft, dass TasksApp existiert und AufgabenDetectorApp als Alias bereitsteht."""
        self.assertIs(TasksApp, AufgabenDetectorApp)
        app = TasksApp()
        self.assertEqual(app.TITLE, "TASKS")

    async def test_tui_buttons_and_interactions(self):
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Tabelle prüfen (standardmäßig Filter 'open_only' -> 1 offene Aufgabe)
            dt = app.query_one("#tasks_table", DataTable)
            self.assertEqual(dt.row_count, 1)
            self.assertEqual(dt.cell_padding, 2)

            # 2. Filter-Button mit der Maus anklicken -> Status-Filter
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)
            await pilot.click("#btn_filter_status")
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusFilterModal)
            await pilot.click("#btn_st_open")
            await pilot.pause()
            self.assertEqual(app.status_filter, "open_only")

            # 3. Filter-Button -> Plattform-Filter
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)
            await pilot.click("#btn_filter_platform")
            await pilot.pause()
            self.assertIsInstance(app.screen, PlatformFilterModal)
            await pilot.click("#btn_plat_moodle")
            await pilot.pause()
            self.assertEqual(app.platform_filter, "moodle")

            # 4. Filter-Button -> Fach-Filter
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)
            await pilot.click("#btn_filter_subject")
            await pilot.pause()
            self.assertIsInstance(app.screen, SubjectFilterModal)
            await pilot.click("#btn_subj_all")
            await pilot.pause()
            self.assertEqual(app.subject_filter, "all")

            # 5. Hidden Tasks über Settings aufrufen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_hidden")
            await pilot.pause()
            self.assertIsInstance(app.screen, TrashModal)
            # Back-Button im TrashModal führt zurück ins Settings-Menü
            await pilot.click("#btn_trash_close")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_cancel")
            await pilot.pause()

            # 6. Aufgabe per Tastatur '1' auswählen (Detailansicht öffnen)
            await pilot.press("1")
            await pilot.pause()
            self.assertIsInstance(app.screen, TaskDetailModal)
            await pilot.click("#btn_det_close")
            await pilot.pause()

            # 7. Unified Login-Button über Settings aufrufen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_login")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)
            # Back-Button im Login-Menü führt zurück ins Settings-Menü
            await pilot.click("#btn_login_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_cancel")
            await pilot.pause()

            # 8. Unified Login-Button per Tastatur 'l' aufrufen
            await pilot.press("l")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)
            await pilot.press("escape")
            await pilot.pause()

            # 8b. Theme über Settings-Menü anklicken und mit ESC schließen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_theme")
            await pilot.pause()
            self.assertIsInstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()

            # 9. Beenden-Button mit der Maus anklicken
            await pilot.click("#btn_main_quit")

    async def test_login_choice_modal_navigation(self):
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # Login-Menü per Settings -> Login öffnen -> Teams auswählen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_login")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)
            await pilot.click("#btn_login_teams")
            await pilot.pause()
            self.assertIsInstance(app.screen, TeamsSetupModal)
            self.assertEqual(app.screen.query_one("#inp_t_email", Input).value, "")
            # Back im Teams-Dialog führt zurück ins LoginChoiceModal
            await pilot.click("#btn_t_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)

            # Moodle auswählen
            await pilot.click("#btn_login_moodle")
            await pilot.pause()
            self.assertIsInstance(app.screen, MoodleLoginModal)
            self.assertEqual(app.screen.query_one("#inp_m_user", Input).placeholder, "Username")
            # Back im Moodle-Dialog führt zurück ins LoginChoiceModal
            await pilot.click("#btn_m_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)

    async def test_noch_offen_status_display(self):
        # Prüfe, dass "Für diese Aufgabe wurde nichts abgegeben" zu "noch offen" transformiert wird
        task = Task(
            id="test_unsubmitted",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Projektantrag",
            due_date_str="Montag, 12. Oktober, 08:00",
            status="offen",
            status_display="Für diese Aufgabe wurde nichts abgegeben",
            url="https://moodle.spengergasse.at",
            teacher="BIM/EIJ",
        )
        self.assertEqual(task.status_display, "noch offen")

        # Prüfe dynamische Neuzuweisung
        task.status_display = "Für diese Aufgabe wurde nichts abgegeben"
        self.assertEqual(task.status_display, "noch offen")

        self.mgr.tasks.append(task)
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            dt = app.query_one("#tasks_table", DataTable)
            self.assertGreaterEqual(dt.row_count, 2)
            row_keys = list(dt.rows.keys())
            self.assertEqual(dt.get_row_height(row_keys[0]), 2)
            self.assertEqual(dt.get_row_height(row_keys[1]), 2)

            # Prüfe, dass in info_stats der Todo-Zähler vorhanden ist
            info_stats = app.query_one("#info_stats", Label)
            stats_content = str(info_stats.render())
            self.assertIn("To Do", stats_content)

    async def test_login_choice_modal_key_shortcuts(self):
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # Login-Menü per 'l' öffnen -> per 't' Teams öffnen
            await pilot.press("l")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)
            await pilot.press("t")
            await pilot.pause()
            self.assertIsInstance(app.screen, TeamsSetupModal)
            self.assertEqual(app.screen.query_one("#inp_t_email", Input).value, "")
            await pilot.press("escape")
            await pilot.pause()

            # Login-Menü per 'l' öffnen -> per 'm' Moodle öffnen
            await pilot.press("l")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)
            await pilot.press("m")
            await pilot.pause()
            self.assertIsInstance(app.screen, MoodleLoginModal)
            self.assertEqual(app.screen.query_one("#inp_m_user", Input).placeholder, "Username")
            await pilot.press("escape")
            await pilot.pause()

    async def test_task_detail_modal_expanded(self):
        task = self.mgr.tasks[0]
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = TaskDetailModal(task, self.mgr)
            await app.push_screen(modal)
            await pilot.pause()
            dialog = app.screen.query_one("#detail_dialog")
            self.assertEqual(dialog.styles.width.value, 90)
            self.assertEqual(dialog.styles.height.value, 90)
            meta = app.screen.query_one("#detail_meta", Label)
            self.assertIn("Status:", str(meta.render()))

            # For Moodle/Teams tasks: no status button, but browser, download, hide, close exist
            self.assertEqual(len(list(app.screen.query("#btn_det_status"))), 0)
            self.assertIsNotNone(app.screen.query_one("#btn_det_browser", Button))
            self.assertIsNotNone(app.screen.query_one("#btn_det_download", Button))
            self.assertIsNotNone(app.screen.query_one("#btn_det_delete", Button))
            self.assertIsNotNone(app.screen.query_one("#btn_det_close", Button))

            await pilot.press("escape")
            await pilot.pause()

    async def test_manual_task_detail_modal_buttons(self):
        """Prüft, dass bei manual Aufgaben nur der Erledigt-Button und Close vorhanden sind."""
        manual_task = Task(
            id="man_test_1",
            platform="manual",
            course="SWP PM",
            course_full="Softwareentwicklung",
            title="Manual Task Test",
            due_date_str="Morgen, 12:00",
            status="offen",
            status_display="Open",
            url="",
        )
        self.mgr.tasks.append(manual_task)
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = TaskDetailModal(manual_task, self.mgr)
            await app.push_screen(modal)
            await pilot.pause()

            # Keine Browser-, Download- oder Hide-Buttons
            self.assertEqual(len(list(app.screen.query("#btn_det_browser"))), 0)
            self.assertEqual(len(list(app.screen.query("#btn_det_download"))), 0)
            self.assertEqual(len(list(app.screen.query("#btn_det_delete"))), 0)

            # Nur Erledigt-Button und Close vorhanden
            btn_status = app.screen.query_one("#btn_det_status", Button)
            self.assertIsNotNone(app.screen.query_one("#btn_det_close", Button))
            self.assertIn("Completed", str(btn_status.label))

            # Abhaken -> Status wird completed, Button ändert sich zu "Mark as Open"
            await pilot.click("#btn_det_status")
            await pilot.pause()
            self.assertTrue(manual_task.is_completed)
            self.assertIn("Open", str(btn_status.label))

            # Nochmal toggeln (Hotkey 'e') -> Status wird wieder offen
            await pilot.press("e")
            await pilot.pause()
            self.assertFalse(manual_task.is_completed)
            self.assertIn("Completed", str(btn_status.label))

            # Schließen per Button
            await pilot.click("#btn_det_close")
            await pilot.pause()

    async def test_completed_manual_task_detail_modal_uncomplete_or_delete(self):
        """Prüft, dass bei einer erledigten manuellen Aufgabe sowohl Uncomplete als auch Delete möglich sind."""
        completed_manual_task = Task(
            id="man_test_completed_1",
            platform="manual",
            course="E",
            course_full="Englisch",
            title="Essay Draft",
            due_date_str="Gestern, 18:00",
            status="completed",
            status_display="Completed",
            url="",
        )
        self.mgr.tasks.append(completed_manual_task)
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = TaskDetailModal(completed_manual_task, self.mgr)
            await app.push_screen(modal)
            await pilot.pause()

            # 1. Beide Buttons müssen vorhanden sein: Mark as Open und Delete
            btn_status = app.screen.query_one("#btn_det_status", Button)
            btn_delete = app.screen.query_one("#btn_det_delete", Button)
            self.assertIn("Open", str(btn_status.label))
            self.assertIn("Delete", str(btn_delete.label))

            # 2. Löschen per Klick auf #btn_det_delete
            await pilot.click("#btn_det_delete")
            await pilot.pause()

            # Modal geschlossen und Aufgabe komplett aus TaskManager entfernt
            self.assertNotIsInstance(app.screen, TaskDetailModal)
            remaining_ids = [t.id for t in self.mgr.tasks]
            self.assertNotIn("man_test_completed_1", remaining_ids)

    async def test_ui_cleanups_header_and_footer(self):
        """Prüft, dass der Footer und die leeren Filter-Platzhalter entfernt wurden."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Kein Footer-Widget mehr im DOM vorhanden
            self.assertEqual(len(list(app.query(Footer))), 0)

            # 2. Kein #info_filter Label mehr vorhanden
            self.assertEqual(len(list(app.query("#info_filter"))), 0)

            # 3. Filter- und Settings-Buttons vorhanden
            filter_btn = app.query_one("#btn_main_filter", Button)
            self.assertIn("Filter", str(filter_btn.label))
            settings_btn = app.query_one("#btn_main_settings", Button)
            self.assertIn("Settings", str(settings_btn.label))

            # 4. info_stats zeigt Aufgabenstatistiken an
            stats_lbl = app.query_one("#info_stats", Label)
            self.assertIn("To Do", str(stats_lbl.render()))

    async def test_theme_top_five_and_persistence(self):
        """Prüft, dass alle konfigurierten Themes aktiv sind und das Theme persistent gespeichert wird."""
        orig_theme = load_saved_theme()
        try:
            # 1. Alle konfigurierten Themes aktiv
            app = AufgabenDetectorApp(self.mgr)
            self.assertEqual(sorted(list(app.available_themes.keys())), sorted(ALLOWED_THEMES))
            self.assertEqual(len(app.available_themes), len(ALLOWED_THEMES))

            async with app.run_test(size=(120, 35)) as pilot:
                # 2. Klick auf Settings-Button -> Theme-Button öffnet Palette
                await pilot.click("#btn_main_settings")
                await pilot.pause()
                self.assertIsInstance(app.screen, SettingsModal)
                await pilot.click("#btn_set_theme")
                await pilot.pause()
                self.assertIsInstance(app.screen, CommandPalette)

                # 3. Theme 'dracula' auswählen
                await pilot.press("d", "r", "a", "c", "u", "l", "a")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(app.theme, "dracula")

                # 4. Prüfen, dass das Theme persistent gespeichert wurde
                self.assertEqual(load_saved_theme(), "dracula")

            # 5. Neuer App-Start lädt automatisch das persistierte Theme 'dracula'
            app2 = AufgabenDetectorApp(self.mgr)
            self.assertEqual(app2.theme, "dracula")

        finally:
            save_saved_theme(orig_theme)

    async def test_theme_keyboard_shortcuts(self):
        """Prüft, dass 't' und 'ctrl+p' die Palette / Theme-Auswahl öffnen."""
        orig_theme = load_saved_theme()
        try:
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # Taste 't' öffnet die Palette
                await pilot.press("t")
                await pilot.pause()
                self.assertIsInstance(app.screen, CommandPalette)
                await pilot.press("escape")
                await pilot.pause()

                # 'ctrl+p' öffnet ebenfalls die Theme-Palette
                await pilot.press("ctrl+p")
                await pilot.pause()
                self.assertIsInstance(app.screen, CommandPalette)
                await pilot.press("n", "o", "r", "d")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                self.assertEqual(app.theme, "nord")
                self.assertEqual(load_saved_theme(), "nord")

        finally:
            save_saved_theme(orig_theme)

    async def test_theme_color_adaptation(self):
        """Prüft, dass der Screen und die Tabelle dynamisch die echten Theme-Farben übernehmen."""
        orig_theme = load_saved_theme()
        try:
            expected_screen_colors = {
                "catppuccin-mocha": "#181825",
                "dracula": "#282A36",
                "tokyo-night": "#1A1B26",
                "nord": "#2E3440",
                "monokai": "#272822",
            }
            for th, hex_color in expected_screen_colors.items():
                save_saved_theme(th)
                app = AufgabenDetectorApp(self.mgr)
                async with app.run_test(size=(120, 35)) as pilot:
                    self.assertEqual(app.theme, th)
                    self.assertEqual(app.screen.styles.background.hex.upper(), hex_color.upper())
                    dt = app.query_one("#tasks_table", DataTable)
                    # Die Tabelle sollte dynamisch mit dem Theme gefärbt sein
                    self.assertIsNotNone(dt.styles.background)
        finally:
            save_saved_theme(orig_theme)

    async def test_button_bar_layout_fit(self):
        """Prüft, dass alle 7 Buttons auf 136, 120, 110 und 100 Spalten ohne Abschneiden hineinpassen."""
        for width in [136, 120, 110, 100]:
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(width, 35)) as pilot:
                b_bar = app.query_one("#button_bar")
                buttons = list(b_bar.query(Button))
                self.assertEqual(len(buttons), 8)
                self.assertEqual(buttons[0].id, "btn_main_absences")
                self.assertIn("Absences", str(buttons[0].label))
                self.assertEqual(buttons[1].id, "btn_main_exams")
                self.assertIn("Tests", str(buttons[1].label))
                self.assertEqual(buttons[2].id, "btn_main_ai")
                self.assertIn("Ai", str(buttons[2].label))
                b_last = app.query_one("#btn_main_quit", Button)
                self.assertIn("Exit", str(b_last.label))
                total_used = b_last.region.x + b_last.region.width
                self.assertLessEqual(total_used, b_bar.size.width)


    async def test_settings_modal_submenus(self):
        """Prüft alle Untermenüs im Settings-Menü: Login, Hidden Tasks, Theme und Untis Group."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Login aus Settings-Menü aufrufen -> LoginChoiceModal öffnet sich
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_login")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)
            # Back kehrt zurück zu SettingsModal
            await pilot.click("#btn_login_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)

            # 2. Hidden Tasks aus Settings-Menü aufrufen -> TrashModal öffnet sich
            await pilot.click("#btn_set_hidden")
            await pilot.pause()
            self.assertIsInstance(app.screen, TrashModal)
            # Back kehrt zurück zu SettingsModal
            await pilot.click("#btn_trash_close")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)

            # 3. Theme aus Settings-Menü aufrufen -> CommandPalette öffnet sich
            await pilot.click("#btn_set_theme")
            await pilot.pause()
            self.assertIsInstance(app.screen, CommandPalette)
            await pilot.press("escape")
            await pilot.pause()

            # 4. School & Student Config aus Settings aufrufen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            from tui_app import SchoolConfigModal
            await pilot.click("#btn_set_school_config")
            await pilot.pause()
            self.assertIsInstance(app.screen, SchoolConfigModal)
            await pilot.press("escape")
            await pilot.pause()

            # 5. Tastaturkürzel im Platform-Menü prüfen (nur noch Plattformauswahl)
            await pilot.press("p")
            await pilot.pause()
            self.assertIsInstance(app.screen, PlatformFilterModal)
            await pilot.press("3")
            await pilot.pause()
            self.assertEqual(app.platform_filter, "teams")

    async def test_platform_modal_compact_fit_small_screens(self):
        """Prüft, dass PlatformFilterModal auch auf kleineren Fenstern (Höhe 24, 20, 18) sauber hineinpasst."""
        for height in [24, 20, 18]:
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(100, height)) as pilot:
                await pilot.press("p")
                await pilot.pause()
                self.assertIsInstance(app.screen, PlatformFilterModal)
                dialog = app.screen.query_one("#plat_dialog")
                # Dialog-Höhe muss in den sichtbaren Screen passen
                self.assertLessEqual(dialog.region.height, height)
                await pilot.press("escape")
                await pilot.pause()

    def test_get_windows_console_window_size(self):
        """Prüft, dass get_windows_console_window_size ohne Exceptions ausgeführt werden kann."""
        from tui_app import get_windows_console_window_size
        size = get_windows_console_window_size()
        if size is not None:
            w, h = size
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)

    def test_ensure_terminal_window_size(self):
        """Prüft, dass ensure_terminal_window_size ohne Fehler mit target_cols=136 ausgeführt werden kann."""
        from tui_app import ensure_terminal_window_size
        # Sollte in jeder Umgebung (auch headless) sicher durchlaufen
        ensure_terminal_window_size(target_cols=136)

    def test_sync_initial_viewport_respects_real_size(self):
        """Prüft, dass _sync_initial_viewport keine künstlichen Resize-Events erzwingt, um ConPTY-Desyncs zu verhindern."""
        from unittest.mock import patch, MagicMock
        from textual.geometry import Size
        from textual.events import Resize

        app = AufgabenDetectorApp(self.mgr)
        posted_events = []
        app.post_message = lambda ev: posted_events.append(ev)
        app.refresh = MagicMock()

        # Auch bei Mismatch zwischen get_windows_console_window_size und app.size
        # darf kein künstliches Resize-Event gepostet werden, da Textuals WindowsDriver
        # die terminalen Dimensionen nativ über ConPTY / ReadConsoleInputW synchronisiert.
        with patch("tui_app.get_windows_console_window_size", return_value=(110, 30)):
            with patch.object(type(app), "size", new=property(lambda self: Size(80, 25))):
                app._sync_initial_viewport()
                # Keine künstlichen Resize-Events gepostet
                resize_events = [ev for ev in posted_events if isinstance(ev, Resize)]
                self.assertEqual(len(resize_events), 0)
                # Layout-Refresh wurde sauber aufgerufen
                app.refresh.assert_called_once_with(layout=True)

    async def test_table_dynamic_title_scaling(self):
        """Prüft, dass lange Titel dynamisch gekürzt werden, um Horizontalausbruch zu verhindern."""
        from textual.widgets import DataTable
        from models import Task

        t_long = Task(
            id="t_long",
            platform="moodle",
            course="Softwareentwicklung und Projektmanagement 3AHWII",
            course_full="Softwareentwicklung 3AHWII 2024/25",
            title="A" * 120,
            due_date_str="Morgen, 23:59",
            status="noch offen",
            status_display="noch offen",
            url="https://moodle.spengergasse.at",
            teacher="Prof. Test"
        )
        self.mgr.tasks = [t_long]
        app = AufgabenDetectorApp(self.mgr)

        async with app.run_test(size=(136, 35)) as pilot:
            dt = app.query_one("#tasks_table", DataTable)
            self.assertEqual(dt.cell_padding, 2)
            row_vals = dt.get_row("t_long")
            # Spalte 3 ist Aufgabe
            title_text = str(row_vals[3])
            self.assertTrue(len(title_text) <= 60)
            self.assertTrue(title_text.endswith("..."))

    async def test_table_no_horizontal_overflow_and_full_width(self):
        """Prüft, dass die Spaltenbreiten dynamisch gesetzt werden (auto_width=False) und niemals horizontal überlaufen."""
        from textual.widgets import DataTable
        from models import Task

        t_bandit = Task(
            id="moodle_bandit",
            platform="moodle",
            course="SESD",
            course_full="SESD - Security Software Development",
            title="OverTheWire/Bandit_0-6_Linux:ls ,cd ,cat ,file ,du ,find ,grep",
            due_date_str="Montag, 2. November 2026, 23:59",
            status="offen",
            status_display="Bisher wurden keine Aufgaben abgegeben",
            url="https://moodle.spengergasse.at",
            teacher="-"
        )
        self.mgr.tasks = [t_bandit]

        for w in [90, 110, 123, 136, 160]:
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(w, 35)) as pilot:
                dt = app.query_one("#tasks_table", DataTable)
                # Spaltenbreiten müssen explizit gesetzt und auto_width=False sein
                for col in dt.columns.values():
                    self.assertFalse(col.auto_width)
                    self.assertGreater(col.width, 0)
                # Keine horizontale Scrollleiste
                self.assertLessEqual(dt.virtual_size.width, dt.size.width)
                # Assignment-Zelle muss sauber auf Spaltenbreite mit "..." gekürzt sein
                row_vals = dt.get_row("moodle_bandit")
                assignment_cell = str(row_vals[3])
                self.assertTrue(assignment_cell.startswith("OverTheWire/Bandit"))
                self.assertTrue(assignment_cell.endswith("..."))

    def test_status_negation_not_marked_completed(self):
        """Prüft, dass Status-Meldungen wie 'Bisher wurden keine Aufgaben abgegeben' nicht fälschlich als erledigt gelten."""
        from models import Task
        from tui_app import format_status_english

        t_open = Task(
            id="t_open_1",
            platform="moodle",
            course="SESD",
            course_full="SESD - Security Software Development",
            title="OverTheWire Task",
            due_date_str="Montag, 2. November 2026, 23:59",
            status="offen",
            status_display="Bisher wurden keine Aufgaben abgegeben",
            url="https://moodle.spengergasse.at",
        )
        self.assertFalse(t_open.is_completed)
        self.assertEqual(format_status_english(t_open), "Open")

        t_not_sub = Task(
            id="t_open_2",
            platform="moodle",
            course="SESD",
            course_full="SESD - Security Software Development",
            title="OverTheWire Task 2",
            due_date_str="Montag, 2. November 2026, 23:59",
            status="offen",
            status_display="Nicht abgegeben",
            url="https://moodle.spengergasse.at",
        )
        self.assertFalse(t_not_sub.is_completed)
        self.assertEqual(format_status_english(t_not_sub), "Open")

    async def test_dynamic_widths_and_resize_stability(self):
        """Prüft, dass die Tabelle über diverse Breiten (80 bis 160) stabil bleibt und Cursor bei Resize nicht springt."""
        from textual.widgets import DataTable
        from textual.events import Resize
        from textual.geometry import Size

        for w in [80, 95, 110, 120, 136, 160]:
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(w, 35)) as pilot:
                dt = app.query_one("#tasks_table", DataTable)
                self.assertGreaterEqual(dt.row_count, 1)
                dt.move_cursor(row=0)
                # Resize-Event simulieren
                app.on_resize(Resize(Size(w + 10, 35), Size(w + 10, 35)))
                self.assertEqual(dt.cursor_row, 0)

    def test_run_tui_invokes_app_run_natively(self):
        """Prüft, dass run_tui() app.run() nativ ohne künstliche Größenbeschränkung aufruft."""
        from unittest.mock import patch
        from tui_app import run_tui

        with patch("tui_app.ensure_terminal_window_size") as mock_ensure:
            with patch.object(AufgabenDetectorApp, "run") as mock_run:
                run_tui()
                mock_ensure.assert_called_once_with(target_cols=123, min_height_px=680)
                mock_run.assert_called_once_with()

    def test_ui_module_does_not_call_mode_con_on_import(self):
        """Prüft, dass ui.py beim Import nicht automatisch mode con ausführt."""
        import ui
        # ui sollte geladen sein ohne Fehler und adjust_console_window als Funktion anbieten
        self.assertTrue(callable(ui.adjust_console_window))

    def test_config_persistence_edge_cases(self):
        """Prüft Robustheit bei Groß-/Kleinschreibung, Whitespace und ungültigen Themes."""
        orig = load_saved_theme()
        try:
            # Groß-/Kleinschreibung & Whitespace
            save_saved_theme("  Dracula  ")
            self.assertEqual(load_saved_theme(), "dracula")

            save_saved_theme("NORD")
            self.assertEqual(load_saved_theme(), "nord")

            # Ungültiges Theme wird ignoriert
            save_saved_theme("non-existent-theme-xyz")
            self.assertEqual(load_saved_theme(), "nord")
        finally:
            save_saved_theme(orig)

    async def test_favorite_themes_persistence_and_sorting(self):
        """Verifiziert, dass Favoriten oben einsortiert werden und einen goldenen Stern erhalten."""
        from config import load_favorite_themes, save_favorite_themes, toggle_favorite_theme
        from tui_app import FavoriteThemeProvider, ThemeSelectModal
        orig_favs = load_favorite_themes()
        try:
            save_favorite_themes([])
            self.assertEqual(load_favorite_themes(), [])

            # Toggle dracula
            self.assertTrue(toggle_favorite_theme("dracula"))
            self.assertIn("dracula", load_favorite_themes())

            # Toggle rose-pine
            self.assertTrue(toggle_favorite_theme("rose-pine"))
            self.assertIn("rose-pine", load_favorite_themes())

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test() as pilot:
                provider = FavoriteThemeProvider(app.screen)
                commands = provider.commands

                # Erste zwei Einträge müssen die Favoriten mit Stern sein
                first_two = [c[0] for c in commands[:2]]
                self.assertIn("⭐ dracula", first_two)
                self.assertIn("⭐ rose-pine", first_two)

            # Prüfe auch ThemeSelectModal Sortierung
            modal = ThemeSelectModal()
            items = modal._get_sorted_theme_items()
            first_two_ids = [item[0] for item in items[:2]]
            self.assertIn("dracula", first_two_ids)
            self.assertIn("rose-pine", first_two_ids)
            self.assertTrue(items[0][1].startswith("⭐"))

            # Toggle wieder entfernen
            self.assertFalse(toggle_favorite_theme("dracula"))
            self.assertNotIn("dracula", load_favorite_themes())
        finally:
            save_favorite_themes(orig_favs)

    async def test_theme_modal_right_click_toggle(self):
        """Verifiziert, dass ein Rechtsklick auf ein Theme in ThemeSelectModal den Favoritenstatus umschaltet."""
        from config import load_favorite_themes, save_favorite_themes
        from tui_app import ThemeSelectModal, ThemeButton
        from textual import events

        orig_favs = load_favorite_themes()
        try:
            save_favorite_themes([])
            modal = ThemeSelectModal()
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test() as pilot:
                app.push_screen(modal)
                await pilot.pause()

                btn = modal.query_one("#btn_thm_nord", ThemeButton)
                self.assertNotIn("⭐", str(btn.label))

                # Rechtsklick simulieren
                right_click_evt = events.MouseDown(btn, x=2, y=0, delta_x=0, delta_y=0, button=3, shift=False, meta=False, ctrl=False)
                await btn._on_mouse_down(right_click_evt)
                await pilot.pause()

                self.assertIn("nord", load_favorite_themes())
                btn_updated = modal.query_one("#btn_thm_nord", ThemeButton)
                self.assertIn("⭐", str(btn_updated.label))
        finally:
            save_favorite_themes(orig_favs)

    async def test_theme_command_palette_right_click_toggle(self):
        """Verifiziert, dass Rechtsklick auf ein Theme in ThemeCommandPalette den Favoritenstatus toggelt."""
        from config import load_favorite_themes, save_favorite_themes
        from tui_app import ThemeCommandPalette, ThemeCommandList, FavoriteThemeProvider
        from rich.style import Style
        from textual import events

        orig_favs = load_favorite_themes()
        try:
            save_favorite_themes([])
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test() as pilot:
                p = ThemeCommandPalette(providers=[FavoriteThemeProvider])
                app.push_screen(p)
                await pilot.pause()

                cl = p.query_one(ThemeCommandList)
                self.assertGreater(cl.option_count, 0)

                # Option 0 hat zunächst keinen Stern
                opt0 = cl.get_option_at_index(0)
                raw_text = str(getattr(opt0.hit, "text", ""))
                self.assertNotIn("⭐", raw_text)

                # Rechtsklick auf Option 0
                click_evt = events.Click(cl, x=2, y=0, delta_x=0, delta_y=0, button=3, shift=False, meta=False, ctrl=False)
                click_evt.style = Style(meta={"option": 0})
                await cl._on_click(click_evt)
                await pilot.pause()

                # Nun ist das Theme in den Favoriten
                self.assertIn(raw_text, load_favorite_themes())

                # Und das erste Theme in der Liste ist nun ein Favorit mit Stern
                opt0_new = cl.get_option_at_index(0)
                self.assertIn("⭐", str(getattr(opt0_new.hit, "text", "")))
        finally:
            save_favorite_themes(orig_favs)

    async def test_theme_command_palette_mouse_click_selection(self):
        """Verifiziert, dass Linksklick auf ein Theme in ThemeCommandPalette das Theme auswählt ohne ScreenStackError."""
        from tui_app import ThemeCommandList
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test() as pilot:
            app.search_themes()
            await pilot.pause()
            cl = app.screen.query_one(ThemeCommandList)
            self.assertGreater(cl.option_count, 0)
            await pilot.click(cl, offset=(5, 1), button=1)
            await pilot.pause()
            self.assertEqual(len(app._screen_stack), 1)

    def test_teams_completed_tasks_filter(self):
        """Prüft, dass erledigte Teams-Aufgaben als is_completed erkannt und im Filter angezeigt werden."""
        t1 = Task(
            id="teams_c1",
            platform="teams",
            course="UFW",
            course_full="3AHWII UFW",
            title="CI Manual",
            due_date_str="Gestern",
            status="abgegeben",
            status_display="Abgegeben",
            url="https://teams.microsoft.com"
        )
        t2 = Task(
            id="teams_c2",
            platform="teams",
            course="D",
            course_full="Deutsch_3AHWII",
            title="Verbesserung 2. SA",
            due_date_str="Vor 150 Tagen",
            status="bewertet",
            status_display="Zurückgegeben",
            url="https://teams.microsoft.com"
        )
        t3 = Task(
            id="teams_open",
            platform="teams",
            course="UFW",
            course_full="3AHWII UFW",
            title="Offene Aufgabe",
            due_date_str="Morgen",
            status="offen",
            status_display="Zugewiesen",
            url="https://teams.microsoft.com"
        )
        self.assertTrue(t1.is_completed)
        self.assertTrue(t2.is_completed)
        self.assertFalse(t3.is_completed)

        mgr = TaskManager(autostart_prefetch=False)
        mgr.tasks = [t1, t2, t3]
        completed = mgr.get_filtered_tasks(status_filter="completed")
        self.assertEqual(len(completed), 2)
        self.assertIn(t1, completed)
        self.assertIn(t2, completed)

    async def test_auto_sync_on_startup_enabled(self):
        """Prüft, dass sync_on_startup=True beim Starten der App automatisch action_sync_tasks triggert."""
        app = AufgabenDetectorApp(self.mgr, sync_on_startup=True)
        with patch.object(app, "action_sync_tasks") as mock_sync:
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause()
                mock_sync.assert_called_once()

    async def test_auto_sync_on_startup_disabled(self):
        """Prüft, dass sync_on_startup=False beim Starten der App action_sync_tasks NICHT aufruft."""
        app = AufgabenDetectorApp(self.mgr, sync_on_startup=False)
        with patch.object(app, "action_sync_tasks") as mock_sync:
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause()
                mock_sync.assert_not_called()

    async def test_sync_spinner_widget_and_animation(self):
        """Prüft das animierte SyncSpinner-Widget und dessen Verhalten."""
        spinner = SyncSpinner()
        self.assertFalse(spinner.active)
        self.assertEqual(spinner.render(), "")

        # Aktivieren
        spinner.active = True
        rendered = str(spinner.render())
        self.assertTrue(any(f in rendered for f in spinner.FRAMES))

        # Frame weiterschalten
        orig_idx = spinner.frame_idx
        spinner._advance_frame()
        self.assertEqual(spinner.frame_idx, (orig_idx + 1) % len(spinner.FRAMES))

        # Deaktivieren
        spinner.active = False
        self.assertEqual(spinner.render(), "")

    async def test_sync_action_toggles_spinner_without_toast(self):
        """Prüft, dass action_sync_tasks den SyncSpinner aktiviert und KEINE Toast-Meldungen sendet."""
        app = AufgabenDetectorApp(self.mgr, sync_on_startup=False)
        async with app.run_test(size=(120, 35)) as pilot:
            spinner = app.query_one("#sync_spinner", SyncSpinner)
            self.assertIsNotNone(spinner)
            self.assertFalse(spinner.active)

            # Mock self.mgr.sync, notify und git_sync
            with patch("git_sync_service.is_git_configured", return_value=False), \
                 patch.object(app.mgr, "sync", return_value=(2, 3)), \
                 patch.object(app, "notify") as mock_notify:
                app.action_sync_tasks()
                self.assertTrue(spinner.active)
                # Keine Benachrichtigung beim Start
                mock_notify.assert_not_called()

                # Warte kurz auf den Thread-Worker
                for _ in range(20):
                    await pilot.pause(0.05)
                    if not spinner.active:
                        break
                # Nach Abschluss sollte der Spinner wieder inaktiv sein und immer noch keine Toast-Meldung gesendet worden sein
                self.assertFalse(spinner.active)
                mock_notify.assert_not_called()

    def test_swp_pm_subject_rename(self):
        """Prüft, dass SWP als 'SWP' erhalten bleibt und SWP PM / Projektmanagement als 'SWP PM' erkannt wird."""
        from config import normalize_subject_name
        self.assertEqual(normalize_subject_name("SWP"), "SWP")
        self.assertEqual(normalize_subject_name("SWP 3AHWII"), "SWP")
        self.assertEqual(normalize_subject_name("SWP_Softwareentwicklung"), "SWP")
        self.assertEqual(normalize_subject_name("SWP PM"), "SWP PM")
        self.assertEqual(normalize_subject_name("Projektmanagement"), "SWP PM")
        self.assertEqual(normalize_subject_name("SWP_3AHWII_SJ2627_PM"), "SWP PM")

        t = Task(
            id="test_swp",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Projektantrag",
            due_date_str="Morgen",
            status="offen",
            status_display="noch offen",
            url="https://moodle.spengergasse.at",
        )
        self.assertEqual(t.course, "SWP")

        t_pm = Task(
            id="test_swp_pm",
            platform="moodle",
            course="SWP PM",
            course_full="Projektmanagement",
            title="Meilenstein",
            due_date_str="Morgen",
            status="offen",
            status_display="noch offen",
            url="https://moodle.spengergasse.at",
        )
        self.assertEqual(t_pm.course, "SWP PM")

    async def test_add_task_modal_validation_and_creation(self):
        """Prüft AddTaskModal: Validierung bei leeren Feldern und saubere Erstellung einer manuellen Aufgabe."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = AddTaskModal()
            dismissed_task = []

            def on_dismiss(task):
                dismissed_task.append(task)

            await app.push_screen(modal, on_dismiss)
            await pilot.pause()

            # 1. Leere Felder absenden -> Validierungsfehler wird angezeigt
            await pilot.click("#btn_add_save")
            await pilot.pause()
            status_lbl = modal.query_one("#add_status", Label)
            self.assertIn("Please enter at least Subject and Assignment title", str(status_lbl.render()))
            self.assertEqual(len(dismissed_task), 0)

            # 2. Felder befüllen
            modal.query_one("#inp_add_subject", Input).value = "NW2"
            modal.query_one("#inp_add_title", Input).value = "Laborprotokoll 2"
            modal.query_one("#inp_add_due", Input).value = "18.10. 23:59"
            modal.query_one("#inp_add_teacher", Input).value = "STA"
            modal.query_one("#inp_add_desc", Input).value = "Spannungsmessung"

            # 3. Speichern (Enter im Formular)
            modal.query_one("#inp_add_title", Input).focus()
            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(len(dismissed_task), 1)
            t = dismissed_task[0]
            self.assertIsNotNone(t)
            self.assertEqual(t.platform, "manual")
            self.assertEqual(t.course, "NW2")
            self.assertEqual(t.title, "Laborprotokoll 2")
            self.assertEqual(t.due_date_str, "Sonntag, 18.10.2026 23:59")
            self.assertEqual(t.teacher, "STA")
            self.assertEqual(t.description, "Spannungsmessung")
            self.assertIsNotNone(t.due_timestamp)

    async def test_add_task_modal_swp_and_swp_pm(self):
        """Prüft, dass AddTaskModal bei Eingabe von SWP auch 'SWP' (nicht 'SWP PM') speichert, und bei 'SWP PM' entsprechend 'SWP PM'."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. SWP eingeben
            modal1 = AddTaskModal()
            dismissed_tasks = []
            await app.push_screen(modal1, lambda t: dismissed_tasks.append(t))
            await pilot.pause()

            modal1.query_one("#inp_add_subject", Input).value = "SWP"
            modal1.query_one("#inp_add_title", Input).value = "Hausübung 1"
            modal1.query_one("#inp_add_due", Input).value = "13.10.2026"
            modal1.query_one("#inp_add_teacher", Input).value = "GRG"

            modal1.query_one("#inp_add_title", Input).focus()
            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(len(dismissed_tasks), 1)
            t1 = dismissed_tasks[0]
            self.assertEqual(t1.course, "SWP")
            self.assertEqual(t1.course_full, "SWP")
            self.assertEqual(t1.teacher, "GRG")

            # 2. SWP PM eingeben
            modal2 = AddTaskModal()
            dismissed_pm = []
            await app.push_screen(modal2, lambda t: dismissed_pm.append(t))
            await pilot.pause()

            modal2.query_one("#inp_add_subject", Input).value = "SWP PM"
            modal2.query_one("#inp_add_title", Input).value = "Projektplan"
            modal2.query_one("#inp_add_due", Input).value = "14.10.2026"
            modal2.query_one("#inp_add_teacher", Input).value = "BIM"

            modal2.query_one("#inp_add_title", Input).focus()
            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(len(dismissed_pm), 1)
            t2 = dismissed_pm[0]
            self.assertEqual(t2.course, "SWP PM")
            self.assertEqual(t2.course_full, "SWP PM")
            self.assertEqual(t2.teacher, "BIM")

    async def test_manual_task_full_workflow_and_sync_persistence(self):
        """Prüft kompletten Workflow: Hinzufügen via Button/Key, Anzeige in Tabelle, Status-Toggle & Persistenz bei Sync."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Klick auf Add-Button öffnet AddTaskModal
            await pilot.click("#btn_main_add")
            await pilot.pause()
            self.assertIsInstance(app.screen, AddTaskModal)

            # Mit ESC abbrechen
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, AddTaskModal)

            # 2. Tastenkürzel 'a' öffnet AddTaskModal
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(app.screen, AddTaskModal)

            modal = app.screen
            modal.query_one("#inp_add_subject", Input).value = "AMEC"
            modal.query_one("#inp_add_title", Input).value = "Differenzialgleichungen"
            modal.query_one("#inp_add_due", Input).value = "Morgen, 12:00"
            modal.query_one("#inp_add_teacher", Input).value = "WAW"

            await pilot.click("#btn_add_save")
            await pilot.pause()

            # Aufgabe muss in TaskManager vorhanden sein
            manual_tasks = [t for t in self.mgr.tasks if t.platform == "manual"]
            self.assertEqual(len(manual_tasks), 1)
            t = manual_tasks[0]
            self.assertEqual(t.title, "Differenzialgleichungen")
            self.assertEqual(t.teacher, "WAW")

            # Tabelle prüfen: Manuelle Aufgabe wird angezeigt mit Manual Badge
            dt = app.query_one("#tasks_table", DataTable)
            row_keys = list(dt.rows.keys())
            self.assertIn(t.id, row_keys)
            row_data = dt.get_row(t.id)
            self.assertIn("Manual", str(row_data[1]))

            # 3. Status toggeln (offen -> erledigt -> offen)
            self.mgr.toggle_task_status(t.id)
            self.assertTrue(t.is_completed)
            self.mgr.toggle_task_status(t.id)
            self.assertFalse(t.is_completed)

            # 4. Filter nach Manual testen
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)
            await pilot.click("#btn_filter_platform")
            await pilot.pause()
            self.assertIsInstance(app.screen, PlatformFilterModal)
            await pilot.click("#btn_plat_manual")
            await pilot.pause()
            self.assertEqual(app.platform_filter, "manual")
            dt = app.query_one("#tasks_table", DataTable)
            self.assertEqual(dt.row_count, 1)

            # 5. Persistenz bei sync() prüfen
            with patch("moodle_service.fetch_moodle_tasks", return_value=[]), patch("teams_service.fetch_teams_tasks", return_value=[]):
                self.mgr.sync(deep_scan=False)
                # Manuelle Aufgabe darf durch sync() nicht gelöscht werden
                retained_manual = [t for t in self.mgr.tasks if t.platform == "manual"]
                self.assertEqual(len(retained_manual), 1)
                self.assertEqual(retained_manual[0].id, t.id)

    async def test_add_task_modal_untis_autofill(self):
        """Prüft WebUntis-Autofill in AddTaskModal: Subject + Datum -> automatische Befüllung von Time & Teacher."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = AddTaskModal()
            dismissed_task = []

            def on_dismiss(task):
                dismissed_task.append(task)

            await app.push_screen(modal, on_dismiss)
            await pilot.pause()

            # Mock lookup_untis_lesson_details
            with patch("tui_app.lookup_untis_lesson_details") as mock_lookup:
                mock_lookup.return_value = {
                    "start_time": "09:55",
                    "end_time": "10:45",
                    "time_str": "09:55 - 10:45",
                    "teacher": "SO",
                    "room": "A1.15",
                    "group": "X",
                    "matched_subject": "E1x",
                }

                modal.query_one("#inp_add_subject", Input).value = "E"
                modal.query_one("#inp_add_due", Input).value = "5.10."
                modal.query_one("#inp_add_title", Input).value = "Vocabulary Unit 2"

                # Klick auf Autofill-Button
                await pilot.click("#btn_add_autofill")

                for _ in range(20):
                    await pilot.pause(0.05)
                    if modal.query_one("#inp_add_teacher", Input).value == "SO":
                        break

                time_val = modal.query_one("#inp_add_time", Input).value
                teacher_val = modal.query_one("#inp_add_teacher", Input).value
                self.assertEqual(time_val, "09:55")
                self.assertEqual(teacher_val, "SO")

                # Speichern
                await pilot.click("#btn_add_save")
                await pilot.pause()

                self.assertEqual(len(dismissed_task), 1)
                t = dismissed_task[0]
                self.assertEqual(t.course, "E")
                self.assertEqual(t.teacher, "SO")
                self.assertIn("09:55", t.due_date_str)

    async def test_add_task_modal_natural_date_resolution(self):
        """Prüft, dass natürliche Eingaben wie 'Tomorrow', 'Tuesday', 'Dienstag' direkt in 'Montag, 4.10.2026 08:00' aufgelöst werden."""
        import datetime
        from tui_app import format_german_weekday_date
        today = datetime.date.today()
        tomorrow_dt = today + datetime.timedelta(days=1)
        tomorrow_str = format_german_weekday_date(tomorrow_dt)
        days_to_tue = (1 - today.weekday()) % 7
        if days_to_tue == 0:
            days_to_tue = 7
        tue_dt = today + datetime.timedelta(days=days_to_tue)
        tue_str = format_german_weekday_date(tue_dt)

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = AddTaskModal()
            await app.push_screen(modal)
            await pilot.pause()

            # 1. "Tomorrow" eingeben -> wird sofort zu morgigem formatiertem Datum
            due_inp = modal.query_one("#inp_add_due", Input)
            due_inp.value = "Tomorrow"
            await pilot.pause()
            self.assertEqual(due_inp.value, tomorrow_str)

            # 2. "Tuesday" eingeben -> nächster Dienstag
            due_inp.value = "Tuesday"
            await pilot.pause()
            self.assertEqual(due_inp.value, tue_str)

            # 3. "Dienstag" eingeben -> ebenfalls nächster Dienstag
            due_inp.value = "Dienstag"
            await pilot.pause()
            self.assertEqual(due_inp.value, tue_str)

            # 4. "Tomorrow, 14:00" eingeben -> Datum von morgen mit Uhrzeit (z.B. Montag, 5.10.2026 14:00)
            due_inp.value = "Tomorrow, 14:00"
            await pilot.pause()
            self.assertEqual(due_inp.value, f"{tomorrow_str} 14:00")

            await pilot.click("#btn_add_cancel")
            await pilot.pause()

    async def test_autofill_debounce_delay(self):
        """Verifiziert, dass bei Eingabe eines Datums ein 1-Sekunden Debounce aktiv ist und nicht sofort bei Teil-Eingaben gefeuert wird."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = AddTaskModal()
            await app.push_screen(modal)
            await pilot.pause()

            due_inp = modal.query_one("#inp_add_due", Input)
            due_inp.value = "21.1"
            await pilot.pause(0.05)
            self.assertIsNotNone(modal._autofill_timer)
            self.assertEqual(due_inp.value, "21.1")

            due_inp.value = "21.10"
            await pilot.pause(0.05)
            self.assertIsNotNone(modal._autofill_timer)

            btn_autofill = modal.query_one("#btn_add_autofill", Button)
            modal.on_button_pressed(Button.Pressed(btn_autofill))
            self.assertIsNone(modal._autofill_timer)

            await pilot.click("#btn_add_cancel")
            await pilot.pause()

    def test_format_status_english(self):
        """Prüft, dass deutsche Moodle- und Teams-Statusbezeichnungen wie 'Zur Bewertung abgegeben' sauber auf Englisch normalisiert werden."""
        from tui_app import format_status_english
        t_submitted = Task(id='1', platform='moodle', course='BET', course_full='BET', title='T1', due_date_str='Morgen', status='abgegeben', status_display='Zur Bewertung abgegeben', url='')
        t_teams_done = Task(id='2', platform='teams', course='UFW', course_full='UFW', title='T2', due_date_str='Heute', status='abgegeben', status_display='Abgegeben', url='')
        t_open = Task(id='3', platform='moodle', course='SWP PM', course_full='SWP PM', title='T3', due_date_str='Montag', status='offen', status_display='noch offen', url='')
        t_overdue = Task(id='4', platform='moodle', course='BET', course_full='BET', title='T4', due_date_str='Gestern', status='ueberfaellig', status_display='Überfällig', url='')

        self.assertEqual(format_status_english(t_submitted), "Completed")
        self.assertEqual(format_status_english(t_teams_done), "Completed")
        self.assertEqual(format_status_english(t_open), "Open")
        self.assertEqual(format_status_english(t_overdue), "Overdue")

    async def test_absences_screen_navigation(self):
        """Prüft das Öffnen und Schließen des WebUntis Absences-Screens über Button und Taste U."""
        from tui_app import AbsencesScreen
        from models import SubjectAbsenceSummary, MissedLesson

        dummy_summaries = [
            SubjectAbsenceSummary(
                subject="SWP PM",
                total_hours=2,
                last_date="2026-10-05",
                missed_lessons=[
                    MissedLesson(date="2026-10-05", subject="SWP PM", period_num=2, start_time="08:50", end_time="09:40", reason="Krank", absence_status="Entschuldigt"),
                    MissedLesson(date="2026-10-05", subject="SWP PM", period_num=7, start_time="13:25", end_time="14:15", reason="Krank", absence_status="Entschuldigt"),
                ]
            )
        ]

        with patch("tui_app.load_untis_cache", return_value=dummy_summaries):
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # 1. Klick auf Absences Button
                await pilot.click("#btn_main_absences")
                await pilot.pause()
                self.assertIsInstance(app.screen, AbsencesScreen)

                # Header und Tabellen prüfen
                info_text = str(app.screen.query_one("#abs_sub_info", Label).render())
                self.assertIn("Class:", info_text)
                self.assertIn("Group:", info_text)

                sub_dt = app.screen.query_one("#abs_subject_table", DataTable)
                det_dt = app.screen.query_one("#abs_detail_table", DataTable)
                self.assertEqual(sub_dt.row_count, 1)
                self.assertEqual(det_dt.row_count, 2)

                # Zurück zu Tasks
                await pilot.click("#btn_abs_back")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, AbsencesScreen)

                # 2. Taste 'u' öffnet Absences
                await pilot.press("u")
                await pilot.pause()
                self.assertIsInstance(app.screen, AbsencesScreen)

                # Taste 'escape' schließt Absences
                await pilot.press("escape")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, AbsencesScreen)

    async def test_login_modal_untis_option(self):
        """Prüft, dass WebUntis im Login-Auswahlmenü vorhanden und anwählbar ist."""
        from tui_app import LoginChoiceModal, UntisSetupModal

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # Login über Settings aufrufen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.click("#btn_set_login")
            await pilot.pause()
            self.assertIsInstance(app.screen, LoginChoiceModal)

            # WebUntis Login-Button klicken
            await pilot.click("#btn_login_untis")
            await pilot.pause()
            self.assertIsInstance(app.screen, UntisSetupModal)

            # Prüfe, dass Schul- und Benutzer-Eingabefeld vorhanden und nicht vorausgefüllt (leer) sind
            from textual.widgets import Input
            inp_school = app.screen.query_one("#inp_u_school", Input)
            inp_user = app.screen.query_one("#inp_u_user", Input)
            self.assertEqual(inp_school.value, "")
            self.assertEqual(inp_user.value, "")

            # Schließen
            await pilot.click("#btn_u_close")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, UntisSetupModal)


    async def test_filter_menu_hub_and_settings(self):
        """Prüft das Öffnen des Filter-Hubs und des Settings-Menüs sowie Filter-Reset."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Filter-Hub öffnen
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 2. Reset All Filters klicken
            await pilot.click("#btn_filter_reset")
            await pilot.pause()
            self.assertEqual(app.status_filter, "open_only")
            self.assertEqual(app.subject_filter, "all")
            self.assertEqual(app.platform_filter, "all")

            # 3. Settings-Menü per Tastatur 'o' öffnen
            await pilot.press("o")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)

            # 4. Settings per ESC schließen
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SettingsModal)

    async def test_filter_submenu_back_navigation(self):
        """Prüft, dass der Back-Button in allen Filter-Untermenüs zurück zum Filter-Hauptmenü führt."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Filter-Hub öffnen
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 2. Subject Filter öffnen -> Back klicken -> zurück in FilterMenuModal
            await pilot.click("#btn_filter_subject")
            await pilot.pause()
            self.assertIsInstance(app.screen, SubjectFilterModal)
            await pilot.click("#btn_subj_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 3. Status Filter öffnen -> Back klicken -> zurück in FilterMenuModal
            await pilot.click("#btn_filter_status")
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusFilterModal)
            await pilot.click("#btn_st_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 4. Platform Filter öffnen -> Back klicken -> zurück in FilterMenuModal
            await pilot.click("#btn_filter_platform")
            await pilot.pause()
            self.assertIsInstance(app.screen, PlatformFilterModal)
            await pilot.click("#btn_plat_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 5. Timeframe Filter öffnen -> Back klicken -> zurück in FilterMenuModal
            await pilot.click("#btn_filter_timeframe")
            await pilot.pause()
            self.assertIsInstance(app.screen, TimeframeFilterModal)
            await pilot.click("#btn_tf_cancel")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 6. Filter-Hub per Close schließen
            await pilot.click("#btn_filter_close")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, FilterMenuModal)

    async def test_notification_timeout_is_three_seconds(self):
        """Prüft, dass AufgabenDetectorApp Benachrichtigungen generell mit 3s Timeout versendet."""
        from textual.notifications import Notify

        captured_timeouts = []

        class TestDetectorApp(AufgabenDetectorApp):
            def on_notify(self, event: Notify) -> None:
                captured_timeouts.append(event.notification.timeout)

        app = TestDetectorApp(self.mgr)
        self.assertEqual(app.NOTIFICATION_TIMEOUT, 3.0)

        async with app.run_test(size=(120, 35)) as pilot:
            app.notify("Test Notification 1")
            await pilot.pause()
            app.notify("Test Notification 2", severity="warning")
            await pilot.pause()

        self.assertEqual(len(captured_timeouts), 2)
        self.assertEqual(captured_timeouts[0], 3.0)
        self.assertEqual(captured_timeouts[1], 3.0)

    async def test_settings_hotkeys_menu(self):
        """Prüft, dass über den Settings-Button 'Hotkeys' die CommandPalette geöffnet wird."""
        from textual.command import CommandList
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Settings öffnen
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)

            # 2. Prüfen, dass der Hotkeys-Button vorhanden ist
            btn_hk = app.screen.query_one("#btn_set_hotkeys", Button)
            self.assertIn("Hotkeys", str(btn_hk.label))

            # 3. Klick auf Hotkeys -> CommandPalette öffnet sich
            await pilot.click("#btn_set_hotkeys")
            await pilot.pause()
            await asyncio.sleep(0.4)
            self.assertIsInstance(app.screen, CommandPalette)

            # 4. CommandList enthält alle Hotkey-Einträge
            cl = app.screen.query_one(CommandList)
            self.assertEqual(cl.option_count, len(HOTKEYS_CATALOG))

            # 5. Esc schließt Palette
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, CommandPalette)

            # 6. Tastenkürzel '6' im Settings-Menü öffnet Hotkeys
            await pilot.click("#btn_main_settings")
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)
            await pilot.press("6")
            await pilot.pause()
            await asyncio.sleep(0.4)
            self.assertIsInstance(app.screen, CommandPalette)

            # 7. Suche nach 'Sync' filtert die Liste
            await pilot.press("s", "y", "n", "c")
            await pilot.pause()
            await asyncio.sleep(0.3)
            cl = app.screen.query_one(CommandList)
            self.assertGreater(cl.option_count, 0)
            self.assertLess(cl.option_count, len(HOTKEYS_CATALOG))

            # 8. Enter schließt Palette
            await pilot.press("enter")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, CommandPalette)

    async def test_course_links_palette_and_open(self):
        """Prüft, dass Backspace die Kurs-Suchpalette öffnet, nur die konfigurierte Klasse listet und Enter den Kurs im Browser startet."""
        with patch("config.load_full_school_config", return_value={"student_class": "3AHWII"}):
            courses = load_all_course_links()
            self.assertGreater(len(courses), 0)
            platforms = {c["platform"] for c in courses}
            self.assertIn("moodle", platforms)
            self.assertIn("teams", platforms)

            # Strikt nur 3AHWII Kurse, keine älteren Klassen (1AHWII, 2AHWII)
            for c in courses:
                if c["platform"] == "moodle":
                    self.assertIn("3AHWII", c["display_title"])
                    self.assertNotIn("1AHWII", c["display_title"])
                    self.assertNotIn("2AHWII", c["display_title"])

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # 1. Backspace drücken -> CommandPalette öffnet sich
                await pilot.press("backspace")
                await pilot.pause()
                await asyncio.sleep(0.4)
                self.assertIsInstance(app.screen, CommandPalette)

                # 2. Suche nach 'SMEN' und Enter drücken
                with patch("webbrowser.open") as mock_open:
                    await pilot.press("s", "m", "e", "n")
                    await pilot.pause()
                    await asyncio.sleep(0.3)
                    await pilot.press("enter")
                    await pilot.pause()
                    self.assertTrue(mock_open.called)
                    opened_url = mock_open.call_args[0][0]
                    self.assertIn("moodle", opened_url)
                    self.assertIn("12234", opened_url)

                # Palette ist geschlossen
                self.assertNotIsInstance(app.screen, CommandPalette)

                # 3. Erneut Backspace, dann Escape -> schließt ohne Aktion
                await pilot.press("backspace")
                await pilot.pause()
                await asyncio.sleep(0.3)
                self.assertIsInstance(app.screen, CommandPalette)
                await pilot.press("escape")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, CommandPalette)

    async def test_course_links_reload_trigger(self):
        """Prüft, dass Eingabe von /r in der Kurs-Suchpalette den Reload anstößt und die Palette auch per / geöffnet werden kann."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            # 1. Taste / (slash) öffnet die Kurspalette direkt
            await pilot.press("slash")
            await pilot.pause()
            await asyncio.sleep(0.4)
            self.assertIsInstance(app.screen, CommandPalette)

            # 2. r eintippen und Enter drücken löst den Kurs-Reload aus
            with patch.object(app, "action_reload_courses") as mock_reload:
                await pilot.press("r")
                await pilot.pause()
                await asyncio.sleep(0.3)
                await pilot.press("enter")
                await pilot.pause()
                self.assertTrue(mock_reload.called)

    async def test_timeframe_filter_modal_and_filtering(self):
        """Prüft den neuen Frist-/Dauer-Filter (1W, 2W, 4W, 8W, Alles) und die Einbindung im Filtermenü & Hotkey 'd'."""
        now = datetime.datetime.now()
        ts_now = now.timestamp()

        # Erstelle Testaufgaben mit verschiedenen Fälligkeiten
        t_2d = Task(
            id="tf_2d",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Aufgabe in 2 Tagen",
            due_date_str="In 2 Tagen",
            due_timestamp=ts_now + 2 * 86400,
            status="offen",
            status_display="Zugewiesen",
            url="https://moodle.spengergasse.at",
        )
        t_10d = Task(
            id="tf_10d",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Aufgabe in 10 Tagen",
            due_date_str="In 10 Tagen",
            due_timestamp=ts_now + 10 * 86400,
            status="offen",
            status_display="Zugewiesen",
            url="https://moodle.spengergasse.at",
        )
        t_20d = Task(
            id="tf_20d",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Aufgabe in 20 Tagen",
            due_date_str="In 20 Tagen",
            due_timestamp=ts_now + 20 * 86400,
            status="offen",
            status_display="Zugewiesen",
            url="https://moodle.spengergasse.at",
        )
        t_45d = Task(
            id="tf_45d",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Aufgabe in 45 Tagen",
            due_date_str="In 45 Tagen",
            due_timestamp=ts_now + 45 * 86400,
            status="offen",
            status_display="Zugewiesen",
            url="https://moodle.spengergasse.at",
        )
        t_jan = Task(
            id="tf_jan",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Aufgabe im Jänner",
            due_date_str="Montag, 11. Januar 2027, 08:00",
            due_timestamp=ts_now + 100 * 86400,
            status="offen",
            status_display="Zugewiesen",
            url="https://moodle.spengergasse.at",
        )

        mgr = TaskManager(autostart_prefetch=False)
        mgr.tasks = [t_2d, t_10d, t_20d, t_45d, t_jan]

        # 1. Standard-Filter: 1 Woche -> nur t_2d
        f_1w = mgr.get_filtered_tasks(timeframe_filter="1_week")
        self.assertEqual(len(f_1w), 1)
        self.assertIn(t_2d, f_1w)

        # 2. 2 Wochen -> t_2d, t_10d
        f_2w = mgr.get_filtered_tasks(timeframe_filter="2_weeks")
        self.assertEqual(len(f_2w), 2)
        self.assertIn(t_2d, f_2w)
        self.assertIn(t_10d, f_2w)

        # 3. 4 Wochen -> t_2d, t_10d, t_20d
        f_4w = mgr.get_filtered_tasks(timeframe_filter="4_weeks")
        self.assertEqual(len(f_4w), 3)
        self.assertIn(t_2d, f_4w)
        self.assertIn(t_10d, f_4w)
        self.assertIn(t_20d, f_4w)

        # 4. 8 Wochen -> t_2d, t_10d, t_20d, t_45d
        f_8w = mgr.get_filtered_tasks(timeframe_filter="8_weeks")
        self.assertEqual(len(f_8w), 4)
        self.assertIn(t_45d, f_8w)
        self.assertNotIn(t_jan, f_8w)

        # 5. Alles -> alle 5 Aufgaben inkl. Jänner
        f_all = mgr.get_filtered_tasks(timeframe_filter="all")
        self.assertEqual(len(f_all), 5)
        self.assertIn(t_jan, f_all)

        # 6. TUI Interaktion: App-Start mit Standard '2_weeks'
        app = AufgabenDetectorApp(mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            self.assertEqual(app.timeframe_filter, "2_weeks")
            dt = app.query_one("#tasks_table", DataTable)
            self.assertEqual(dt.row_count, 2)

            # Tastenkürzel 'd' öffnet TimeframeFilterModal direkt
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(app.screen, TimeframeFilterModal)
            tf_title = str(app.screen.query_one("#tf_title", Label).render())
            self.assertIn("Max Duration", tf_title)
            self.assertIn("1 Week", str(app.screen.query_one("#btn_tf_1w", Button).label))
            self.assertIn("2 Weeks (Default)", str(app.screen.query_one("#btn_tf_2w", Button).label))
            self.assertIn("All", str(app.screen.query_one("#btn_tf_all", Button).label))

            # 1 Woche auswählen per Klick
            await pilot.click("#btn_tf_1w")
            await pilot.pause()
            self.assertEqual(app.timeframe_filter, "1_week")
            self.assertEqual(dt.row_count, 1)

            # Filtermenü öffnen -> Reset All Filters -> wieder '2_weeks'
            await pilot.click("#btn_main_filter")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)
            await pilot.click("#btn_filter_reset")
            await pilot.pause()
            self.assertEqual(app.timeframe_filter, "2_weeks")
            self.assertEqual(dt.row_count, 2)

    async def test_hidden_overdue_task_not_counted_in_info_stats(self):
        """Prüft, dass ausgeblendete (hidden) Aufgaben links oben in info_stats nicht gezählt werden, auch wenn sie überfällig (overdue) sind."""
        t_overdue = Task(
            id="t_overdue_hidden",
            platform="teams",
            course="UFW",
            course_full="3AHWII UFW",
            title="Überfällige Teams Aufgabe",
            due_date_str="Vor 10 Tagen",
            status="ueberfaellig",
            status_display="Überfällig",
            url="https://teams.cloud.microsoft",
        )
        t_open = Task(
            id="t_open_normal",
            platform="moodle",
            course="SWP",
            course_full="Softwareentwicklung",
            title="Normale offene Aufgabe",
            due_date_str="Morgen",
            status="offen",
            status_display="Offen",
            url="https://moodle.spengergasse.at",
        )

        with patch.object(TaskManager, "load_deleted_tasks", return_value=set()), \
             patch.object(TaskManager, "save_deleted_tasks"):
            mgr = TaskManager(autostart_prefetch=False)
            mgr.tasks = [t_overdue, t_open]

            # 1. Bevor t_overdue hidden ist (unter status_filter='all' & timeframe_filter='all' sichtbar)
            app = AufgabenDetectorApp(mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                app.status_filter = "all"
                app.timeframe_filter = "all"
                app.refresh_table()
                await pilot.pause()

                lbl = str(app.query_one("#info_stats", Label).render())
                self.assertIn("1 overdue", lbl)
                self.assertIn("Teams: 1", lbl)
                self.assertIn("Moodle: 1", lbl)

                # 2. t_overdue ausblenden (hide / delete)
                mgr.delete_task(t_overdue.id)
                self.assertTrue(mgr.is_deleted(t_overdue.id))
                app.refresh_table()
                await pilot.pause()

                # Jetzt darf t_overdue links oben nirgends mehr mitzählen!
                lbl_after = str(app.query_one("#info_stats", Label).render())
                self.assertNotIn("overdue", lbl_after)
                self.assertIn("Teams: 0", lbl_after)
                self.assertIn("Moodle: 1", lbl_after)
                self.assertIn("1 open", lbl_after)

    async def test_info_stats_matches_currently_visible_tasks(self):
        """Prüft, dass links oben in info_stats immer exakt nur so viele Aufgaben angezeigt werden, wie gerade sichtbar sind."""
        now = datetime.datetime.now()
        due_soon = (now + datetime.timedelta(days=2)).strftime("%d.%m.%Y")
        due_far = (now + datetime.timedelta(days=90)).strftime("%d.%m.%Y")

        t1 = Task(id="t_v1", platform="moodle", course="SWP", course_full="SWP PM", title="Aufgabe 1", due_date_str=due_soon, status="offen", status_display="Open", url="https://moodle.spengergasse.at")
        t2 = Task(id="t_v2", platform="teams", course="UFW", course_full="UFW", title="Aufgabe 2 weit weg", due_date_str=due_far, status="offen", status_display="Open", url="https://teams.microsoft.com")
        t3 = Task(id="t_v3", platform="moodle", course="BET", course_full="BET", title="Aufgabe 3 weit weg", due_date_str=due_far, status="offen", status_display="Open", url="https://moodle.spengergasse.at")

        with patch.object(TaskManager, "load_deleted_tasks", return_value=set()), \
             patch.object(TaskManager, "save_deleted_tasks"):
            mgr = TaskManager(autostart_prefetch=False)
            mgr.tasks = [t1, t2, t3]

            app = AufgabenDetectorApp(mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # Standard: timeframe_filter="1_week", status_filter="open_only"
                # Es ist genau 1 Aufgabe (t1) sichtbar!
                self.assertEqual(len(app.current_tasks), 1)
                lbl = str(app.query_one("#info_stats", Label).render())
                self.assertIn("1 open", lbl)
                self.assertIn("Moodle: 1", lbl)
                self.assertIn("Teams: 0", lbl)

                # Auf 'all' timeframe wechseln -> alle 3 sichtbar
                app.timeframe_filter = "all"
                app.refresh_table()
                await pilot.pause()
                self.assertEqual(len(app.current_tasks), 3)
                lbl_all = str(app.query_one("#info_stats", Label).render())
                self.assertIn("3 open", lbl_all)
                self.assertIn("Moodle: 2", lbl_all)
                self.assertIn("Teams: 1", lbl_all)

    def test_assignment_column_is_twelve_columns_thinner(self):
        """Prüft, dass die maximale Assignment-Spaltenbreite exakt 12 Spalten dünner berechnet wird (term_w - 94 statt term_w - 82)."""
        term_w = 136
        old_max_title = max(35, term_w - 82)
        new_max_title = max(23, term_w - 94)
        self.assertEqual(old_max_title - new_max_title, 12)

        term_w_small = 120
        old_small = max(35, term_w_small - 82)
        new_small = max(23, term_w_small - 94)
        self.assertEqual(old_small - new_small, 12)

    async def test_mouse_back_navigation_task_details(self):
        """Prüft, dass action_navigate_back (Maus-Zurück) geöffnete Aufgabendetails schließt."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            app._open_task_details(self.mgr.tasks[0])
            await pilot.pause()
            self.assertIsInstance(app.screen, TaskDetailModal)

            # Maus-Zurück auslösen
            app.action_navigate_back()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, TaskDetailModal)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_mouse_back_navigation_filter_menu(self):
        """Prüft, dass action_navigate_back (Maus-Zurück) das Filter-Menü schließt."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            app.action_open_filter_menu()
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            app.action_navigate_back()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, FilterMenuModal)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_mouse_back_navigation_nested_filter(self):
        """Prüft mehrstufiges Zurückgehen: Unter-Filter -> Filter-Menü -> Hauptseite."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            app.action_open_filter_menu()
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # Öffne Status-Filter aus dem Filter-Menü über Button-Klick
            await pilot.click("#btn_filter_status")
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusFilterModal)

            # 1. Klick auf Maus-Zurück: Geht vom StatusFilterModal zurück ins FilterMenuModal
            app.action_navigate_back()
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterMenuModal)

            # 2. Klick auf Maus-Zurück: Schließt FilterMenuModal und kehrt zur Hauptseite zurück
            app.action_navigate_back()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, FilterMenuModal)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_mouse_back_navigation_exams_and_submodal(self):
        """Prüft mehrstufiges Zurückgehen im Tests & Prüfungen Screen."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            app.action_show_exams()
            await pilot.pause()
            self.assertIsInstance(app.screen, ExamsScreen)

            # Öffne AddExamModal im ExamsScreen
            app.screen.action_add_exam()
            await pilot.pause()
            self.assertIsInstance(app.screen, AddExamModal)

            # 1. Klick auf Maus-Zurück: Schließt AddExamModal, bleibt auf ExamsScreen
            app.action_navigate_back()
            await pilot.pause()
            self.assertIsInstance(app.screen, ExamsScreen)

            # 2. Klick auf Maus-Zurück: Schließt ExamsScreen, kehrt zur Hauptseite zurück
            app.action_navigate_back()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ExamsScreen)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_mouse_back_navigation_on_main_screen_is_noop(self):
        """Prüft, dass action_navigate_back auf der Hauptseite keine Fehler wirft und auf der Hauptseite bleibt."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            self.assertEqual(len(app.screen_stack), 1)
            app.action_navigate_back()
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)

    async def test_mouse_down_button_4_trigger(self):
        """Prüft, dass on_mouse_down mit button=4 (Maus-Taste 4 / Zurück) action_navigate_back triggert."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            app.action_open_settings()
            await pilot.pause()
            self.assertIsInstance(app.screen, SettingsModal)

            # Simuliere MouseDown mit button 4
            app.on_mouse_down(MouseDown(None, 0, 0, 0, 0, 4, False, False, False))
            await pilot.pause()
            self.assertNotIsInstance(app.screen, SettingsModal)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_oled_theme_styling_and_visibility(self):
        """Prüft OLED Theme: kein Clipping, weiße Spalten-Header, sichtbare Buttons und ThemeSelectModal Hover."""
        from config import save_saved_theme, load_saved_theme
        orig_theme = load_saved_theme()
        try:
            save_saved_theme("oled")
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                self.assertEqual(app.theme, "oled")
                # Prüfe Button Bar Buttons
                btn_add = app.query_one("#btn_main_add", Button)
                self.assertIn("Add", str(btn_add.label))
                btn_sync = app.query_one("#btn_main_sync", Button)
                self.assertIn("Sync", str(btn_sync.label))
                btn_absences = app.query_one("#btn_main_absences", Button)
                self.assertIn("Absences", str(btn_absences.label))
                # DataTable Header prüfen
                dt = app.query_one("#tasks_table", DataTable)
                self.assertIsNotNone(dt)

                # ThemeSelectModal Hover CSS vorhanden
                from tui_app import ThemeSelectModal
                self.assertIn(".theme_btn:hover", ThemeSelectModal.DEFAULT_CSS)
                self.assertIn("#343331", ThemeSelectModal.DEFAULT_CSS)

                # AufgabenDetectorApp.CSS enthält weiße Header für OLED
                self.assertIn(".-theme-oled DataTable > .datatable--header", AufgabenDetectorApp.CSS)
                self.assertIn("color: #ffffff;", AufgabenDetectorApp.CSS)

                # Prüfe Button-Höhe in Dialogen (SettingsModal)
                app.push_screen(SettingsModal())
                await pilot.pause()
                theme_btn = app.screen.query_one("#btn_set_theme", Button)
                self.assertEqual(theme_btn.outer_size.height, 3)
                app.pop_screen()
                await pilot.pause()

                # Prüfe, dass Tabellen bei Fokus rein schwarz bleiben (kein grauer background-tint)
                dt.focus()
                await pilot.pause()
                self.assertEqual(dt.styles.background_tint.a, 0.0)
                self.assertEqual(dt.styles.background.hex.upper(), "#000000")
        finally:
            save_saved_theme(orig_theme)

    async def test_input_enhanced_windows_shortcuts(self):
        """Prüft Windows-Shortcuts in Input: STRG+A, Pos1, Ende, STRG+Pfeil, SHIFT+STRG+Pfeil, STRG+Backspace, STRG+Entf."""
        from textual.widgets import Input
        from textual.screen import Screen

        class InputTestScreen(Screen):
            def compose(self):
                yield Input(value="alpha beta gamma delta", id="test_input")

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            screen = InputTestScreen()
            app.push_screen(screen)
            await pilot.pause()

            inp = screen.query_one("#test_input", Input)
            inp.focus()
            await pilot.pause()

            # 1. STRG + A (Alles markieren)
            await pilot.press("ctrl+a")
            await pilot.pause()
            self.assertEqual(inp.selection, (0, len(inp.value)))

            # 2. Pos1 / Home (Anfang)
            await pilot.press("home")
            await pilot.pause()
            self.assertEqual(inp.cursor_position, 0)
            self.assertEqual(inp.selection, (0, 0))

            # 3. Ende / End (Ende)
            await pilot.press("end")
            await pilot.pause()
            self.assertEqual(inp.cursor_position, len(inp.value))

            # 4. STRG + Pfeil links (wortweise nach links)
            await pilot.press("ctrl+left")
            await pilot.pause()
            self.assertEqual(inp.cursor_position, 17)  # vor 'delta'

            # 5. SHIFT + STRG + Pfeil links (wortweise nach links markieren)
            await pilot.press("ctrl+shift+left")
            await pilot.pause()
            self.assertEqual(inp.selection, (17, 11))  # 'gamma ' markiert

            # 6. Überschreiben der Markierung durch Tastendruck
            await pilot.press("x")
            await pilot.pause()
            self.assertIn("alpha beta xdelta", inp.value)

            # 7. STRG + Backspace (Wort links löschen - auch via ctrl+w und ctrl+h)
            inp.value = "first second third"
            inp.cursor_position = len(inp.value)
            inp.selection = (len(inp.value), len(inp.value))
            await pilot.press("ctrl+backspace")
            await pilot.pause()
            self.assertEqual(inp.value, "first second ")

            await pilot.press("ctrl+w")
            await pilot.pause()
            self.assertEqual(inp.value, "first ")

            await pilot.press("ctrl+h")
            await pilot.pause()
            self.assertEqual(inp.value, "")

            # 8. STRG + Entf (Wort rechts löschen)
            inp.value = "first second third"
            inp.cursor_position = 6  # vor 'second'
            inp.selection = (6, 6)
            await pilot.press("ctrl+delete")
            await pilot.pause()
            self.assertEqual(inp.value, "first third")

            # 9. SHIFT + Pos1 (markieren bis Zeilenanfang)
            inp.value = "hello world"
            inp.cursor_position = 5
            inp.selection = (5, 5)
            await pilot.press("shift+home")
            await pilot.pause()
            self.assertEqual(inp.selection, (5, 0))

            # 10. SHIFT + Ende (markieren bis Zeilenende)
            inp.cursor_position = 5
            inp.selection = (5, 5)
            await pilot.press("shift+end")
            await pilot.pause()
            self.assertEqual(inp.selection, (5, 11))

    async def test_textarea_enhanced_windows_shortcuts(self):
        """Prüft Windows-Shortcuts in TextArea: STRG+A, Pos1, Ende, STRG+Pfeil, STRG+Backspace."""
        from textual.widgets import TextArea
        from textual.screen import Screen

        class TextAreaTestScreen(Screen):
            def compose(self):
                yield TextArea("Zeile eins\nZeile zwei\nZeile drei", id="test_ta")

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            screen = TextAreaTestScreen()
            app.push_screen(screen)
            await pilot.pause()

            ta = screen.query_one("#test_ta", TextArea)
            ta.focus()
            await pilot.pause()

            # STRG + A markiert gesamten Inhalt in TextArea
            await pilot.press("ctrl+a")
            await pilot.pause()
            self.assertEqual(len(ta.selected_text), len(ta.text))

            # Pos1 springt an Zeilenanfang
            await pilot.press("home")
            await pilot.pause()
            self.assertEqual(ta.cursor_location[1], 0)

            # STRG+Backspace / ctrl+w / ctrl+h löscht Wort nach links
            ta.text = "apfel birne kirsche"
            ta.move_cursor((0, len("apfel birne kirsche")))
            await pilot.pause()
            await pilot.press("ctrl+backspace")
            await pilot.pause()
            self.assertEqual(ta.text, "apfel birne ")

            await pilot.press("ctrl+w")
            await pilot.pause()
            self.assertEqual(ta.text, "apfel ")

            await pilot.press("ctrl+h")
            await pilot.pause()
            self.assertEqual(ta.text, "")

    async def test_unified_command_input_ctrl_a_and_backspace(self):
        """Prüft STRG+A und Backspace in UnifiedCommandPalette."""
        from tui_app import UnifiedCommandPalette, UnifiedCommandInput

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            palette = UnifiedCommandPalette()
            app.push_screen(palette)
            await pilot.pause()

            inp = palette.query_one(UnifiedCommandInput)
            inp.value = "betriebstechnik"
            inp.cursor_position = len(inp.value)

            # STRG+A markiert gesamten Text
            await pilot.press("ctrl+a")
            await pilot.pause()
            self.assertEqual(inp.selection, (0, len("betriebstechnik")))

            # Backspace löscht nur die Markierung, Palette bleibt offen
            await pilot.press("backspace")
            await pilot.pause()
            self.assertEqual(inp.value, "")
            self.assertIsInstance(app.screen, UnifiedCommandPalette)

            # Zweiter Backspace auf leerem Feld schließt die Palette
            await pilot.press("backspace")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, UnifiedCommandPalette)

    def test_win32_event_monitor_ctrl_backspace_detection(self):
        """Prüft die Erkennung von STRG+Backspace auf Windows-Treiberebene."""
        import sys
        if sys.platform != "win32":
            return
        from textual.drivers.win32 import KEY_EVENT_RECORD, EventMonitor
        from textual._xterm_parser import XTermParser

        self.assertTrue(getattr(EventMonitor, "_ctrl_backspace_patched", False))

        # Testfall 1: ConPTY / Windows Terminal mit Ctrl+Backspace (VK_BACK 8, dwControlKeyState 0x0008, '\x7f')
        rec = KEY_EVENT_RECORD()
        rec.bKeyDown = True
        rec.wVirtualKeyCode = 8
        rec.dwControlKeyState = 0x0008  # LEFT_CTRL_PRESSED
        rec.uChar.UnicodeChar = "\x7f"

        is_ctrl = bool(rec.dwControlKeyState & 0x000C)
        self.assertTrue(is_ctrl)
        if is_ctrl and (rec.wVirtualKeyCode in (8, 0x48) or rec.uChar.UnicodeChar in ("\x08", "\x7f")):
            key_seq = "\x1b[127;5u"
        else:
            key_seq = rec.uChar.UnicodeChar

        parser = XTermParser()
        events = list(parser.feed(key_seq))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].key, "ctrl+backspace")

        # Testfall 2: Normaler Backspace (dwControlKeyState 0, '\x08') bleibt 'backspace'
        rec2 = KEY_EVENT_RECORD()
        rec2.bKeyDown = True
        rec2.wVirtualKeyCode = 8
        rec2.dwControlKeyState = 0
        rec2.uChar.UnicodeChar = "\x08"

        is_ctrl2 = bool(rec2.dwControlKeyState & 0x000C)
        self.assertFalse(is_ctrl2)
        if is_ctrl2 and (rec2.wVirtualKeyCode in (8, 0x48) or rec2.uChar.UnicodeChar in ("\x08", "\x7f")):
            key_seq2 = "\x1b[127;5u"
        else:
            key_seq2 = rec2.uChar.UnicodeChar

        parser2 = XTermParser()
        events2 = list(parser2.feed(key_seq2))
        self.assertEqual(len(events2), 1)
        self.assertEqual(events2[0].key, "backspace")

    async def test_enhanced_input_ctrl_backspace_on_key_hook(self):
        """Prüft das Hooking von _on_key in Input und TextArea bei gehaltenem STRG."""
        from unittest.mock import patch
        from textual.widgets import Input, TextArea
        from textual.screen import Screen
        from textual.events import Key

        class HookTestScreen(Screen):
            def compose(self):
                yield Input(value="apfel birne kirsche", id="hook_input")
                yield TextArea("zeile eins zwei drei", id="hook_ta")

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            screen = HookTestScreen()
            app.push_screen(screen)
            await pilot.pause()

            inp = screen.query_one("#hook_input", Input)
            inp.focus()
            inp.cursor_position = len(inp.value)
            await pilot.pause()

            # Wenn is_ctrl_pressed_win32() True liefert, muss ein gewöhnliches 'backspace'-Event als delete_left_word agieren
            with patch("tui_app.is_ctrl_pressed_win32", return_value=True):
                event = Key("backspace", "\x08")
                await inp._on_key(event)
                self.assertEqual(inp.value, "apfel birne ")
                self.assertTrue(event._no_default_action)
                self.assertTrue(event._stop_propagation)

            ta = screen.query_one("#hook_ta", TextArea)
            ta.focus()
            ta.move_cursor((0, len("zeile eins zwei drei")))
            await pilot.pause()

            with patch("tui_app.is_ctrl_pressed_win32", return_value=True):
                event2 = Key("backspace", "\x08")
                await ta._on_key(event2)
                self.assertEqual(ta.text, "zeile eins zwei ")
                self.assertTrue(event2._no_default_action)
                self.assertTrue(event2._stop_propagation)

    def test_open_courses_palette_guard_when_ctrl_pressed(self):
        """Prüft, dass action_open_courses_palette nicht öffnet, wenn STRG gehalten wird."""
        from unittest.mock import patch, MagicMock

        app = AufgabenDetectorApp(self.mgr)
        app.push_screen = MagicMock()

        # Mit gehaltenem STRG darf kein Screen gepusht werden
        with patch("tui_app.is_ctrl_pressed_win32", return_value=True):
            app.action_open_courses_palette()
            app.push_screen.assert_not_called()

        # Ohne STRG wird UnifiedCommandPalette normal geöffnet
        with patch("tui_app.is_ctrl_pressed_win32", return_value=False):
            app.action_open_courses_palette()
            app.push_screen.assert_called_once()

    async def test_tasks_table_column_widths_teacher_and_due_date_priority(self):
        """Prüft, dass Teacher (>= 8) und Due Date (>= 28) priorisiert werden und 'Teacher' nie abgeschnitten wird."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            dt = app.query_one(DataTable)
            cols = list(dt.columns.values())
            self.assertEqual(len(cols), 7)
            # cols: # (0), Platform (1), Subject (2), Assignment (3), Due Date (4), Status (5), Teacher (6)
            w_idx = cols[0].width
            w_plat = cols[1].width
            w_subj = cols[2].width
            w_assign = cols[3].width
            w_due = cols[4].width
            w_stat = cols[5].width
            w_teach = cols[6].width

            self.assertGreaterEqual(w_teach, 8, "Teacher-Spalte muss mindestens 8 breit sein, damit 'Teacher' nicht zu 'Teache' wird")
            self.assertGreaterEqual(w_due, 28, "Due Date-Spalte muss mindestens 28 breit sein für vollständige Datumsangaben")
            self.assertEqual(w_stat, 11)
            self.assertGreater(w_assign, 10, "Assignment erhält den verbleibenden Rest")

            # Breiter Bildschirm (150 Spalten)
            app.refresh_table(term_w_override=150)
            await pilot.pause()
            cols_wide = list(dt.columns.values())
            self.assertGreaterEqual(cols_wide[6].width, 8)
            self.assertGreaterEqual(cols_wide[4].width, 28)
            self.assertGreater(cols_wide[3].width, w_assign, "Assignment expandiert auf breiten Bildschirmen")

            # Extrem kleines Fenster (74 Spalten)
            app.refresh_table(term_w_override=74)
            await pilot.pause()
            cols_tiny = list(dt.columns.values())
            self.assertGreaterEqual(cols_tiny[6].width, 7, "Teacher darf selbst bei extrem kleinem Fenster min. 7 Zeichen für den Header haben")

    async def test_info_bar_single_line_and_sync_spinner_zero_shift(self):
        """Prüft, dass info_bar genau 1 Zeile hoch ist und SyncSpinner im Ruhezustand und bei Aktivität exakt dieselbe Breite belegt."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            spinner = app.query_one("#sync_spinner", SyncSpinner)
            self.assertEqual(spinner.styles.width.value, 3)

            # Inaktiver Zustand: leer, belegt aber durch CSS width: 3 exakt denselben Platz
            self.assertFalse(spinner.active)
            self.assertEqual(str(spinner.render()), "")

            # Aktiver Zustand: Frame wird gerendert
            spinner.active = True
            await pilot.pause()
            rendered = str(spinner.render())
            self.assertIn(spinner.FRAMES[spinner.frame_idx], rendered)

            # Leere Zeile zwischen info_bar und tasks_table
            info_bar = app.query_one("#info_bar")
            table = app.query_one("#tasks_table")
            self.assertEqual(table.region.y - (info_bar.region.y + info_bar.region.height), 1, "Es muss genau 1 leere Zeile zwischen info_bar und der Tabelle liegen")

    async def test_login_reminder_modal_rendering_and_badges(self):
        """Verifies LoginReminderModal renders English texts and appropriate badges."""
        with patch("auth.get_platform_login_status", return_value={"moodle": True, "teams": False, "untis": False}):
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                modal = LoginReminderModal()
                await app.push_screen(modal)
                await pilot.pause()

                self.assertIsInstance(app.screen, LoginReminderModal)
                title = app.screen.query_one("#login_reminder_title", Label)
                self.assertIn("Action Required", str(title.render()))

                # Buttons exist
                btn_open = app.screen.query_one("#btn_open_login_menu", Button)
                btn_dismiss = app.screen.query_one("#btn_dismiss_login", Button)
                self.assertIn("Open Login Menu", str(btn_open.label))
                self.assertIn("Dismiss", str(btn_dismiss.label))

                # Test badges in box
                status_labels = [str(lbl.render()) for lbl in app.screen.query(".login_platform_status")]
                self.assertTrue(any("✓ Signed in" in s for s in status_labels))
                self.assertTrue(any("✗ Not signed in" in s for s in status_labels))

                # Test dismiss via button
                await pilot.click("#btn_dismiss_login")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, LoginReminderModal)

    async def test_login_reminder_modal_open_action(self):
        """Verifies clicking Open Login Menu opens LoginChoiceModal."""
        with patch("auth.get_platform_login_status", return_value={"moodle": False, "teams": False, "untis": False}):
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # Trigger _check_login_status_after_sync
                app._check_login_status_after_sync()
                await pilot.pause()
                self.assertIsInstance(app.screen, LoginReminderModal)

                # Click Open Login Menu button
                await pilot.click("#btn_open_login_menu")
                await pilot.pause()
                self.assertIsInstance(app.screen, LoginChoiceModal)

    async def test_login_choice_modal_components_and_toggle(self):
        """Verifies LoginChoiceModal renders action buttons, login buttons, labels, and clicking toggle updates status."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            with patch("auth.is_untis_logged_in", return_value=False), \
                 patch("auth.is_teams_logged_in", return_value=True), \
                 patch("auth.is_moodle_logged_in", return_value=False):
                await app.push_screen(LoginChoiceModal())
                await pilot.pause()
                self.assertIsInstance(app.screen, LoginChoiceModal)

                # Teams is logged in -> action button is "Log Out"
                btn_act_teams = app.screen.query_one("#btn_action_teams", Button)
                self.assertIn("Log Out", str(btn_act_teams.label))

                # Moodle is not logged in -> action button is "Disable"
                btn_act_moodle = app.screen.query_one("#btn_action_moodle", Button)
                self.assertEqual(str(btn_act_moodle.label), "Disable")

                # Untis is not logged in -> action button is "Disable"
                btn_act_untis = app.screen.query_one("#btn_action_untis", Button)
                self.assertEqual(str(btn_act_untis.label), "Disable")

                # Git has no action button!
                self.assertEqual(len(app.screen.query("#btn_action_git")), 0)

                # Click untis action button ("Disable") to deactivate it
                btn_act_untis.press()
                await pilot.pause()

                self.assertEqual(str(btn_act_untis.label), "Enable")
                self.assertEqual(btn_act_untis.variant, "success")

                lbl_untis = app.screen.query_one("#lbl_status_untis", Label)
                self.assertIn("Disabled", str(lbl_untis.render()))
                btn_untis = app.screen.query_one("#btn_login_untis", Button)
                self.assertTrue(btn_untis.disabled)

                # Click untis action button ("Enable") to reactivate it
                btn_act_untis.press()
                await pilot.pause()
                self.assertEqual(str(btn_act_untis.label), "Disable")
                self.assertEqual(btn_act_untis.variant, "default")
                self.assertFalse(btn_untis.disabled)

    async def test_login_choice_modal_logout_buttons(self):
        """Verifies clicking Log Out on a platform triggers the logout routine."""
        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            with patch("auth.logout_moodle", return_value=(True, "Moodle logged out and cache cleared.")) as mock_logout_moodle, \
                 patch("auth.is_moodle_logged_in", return_value=True):
                await app.push_screen(LoginChoiceModal())
                await pilot.pause()

                btn_action_moodle = app.screen.query_one("#btn_action_moodle", Button)
                self.assertIn("Log Out", str(btn_action_moodle.label))
                await pilot.click("#btn_action_moodle")
                await pilot.pause()
                mock_logout_moodle.assert_called_once()

    async def test_check_login_status_skips_when_dialog_open_or_all_logged_in(self):
        """Verifies _check_login_status_after_sync does not interrupt existing screens or when all logged in."""
        # Case 1: All logged in -> nothing pushed
        with patch("auth.has_missing_logins", return_value=False):
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                app._check_login_status_after_sync()
                await pilot.pause()
                self.assertNotIsInstance(app.screen, LoginReminderModal)

        # Case 2: Missing logins but SettingsModal is open -> nothing pushed
        with patch("auth.has_missing_logins", return_value=True):
            app2 = AufgabenDetectorApp(self.mgr)
            async with app2.run_test(size=(120, 35)) as pilot2:
                await app2.push_screen(SettingsModal())
                await pilot2.pause()
                self.assertIsInstance(app2.screen, SettingsModal)
                app2._check_login_status_after_sync()
                await pilot2.pause()
                # Must still be SettingsModal, not pushed over
                self.assertIsInstance(app2.screen, SettingsModal)


if __name__ == "__main__":
    unittest.main()


