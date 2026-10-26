"""
test_untis_exams.py - Tests für WebUntis Tests & Schularbeiten (Exams),
einschließlich Modell, Caching, eigener Prüfungsnotizen und TUI-Modals.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import json
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import src

from models import UntisExam
from config import (
    load_exam_notes,
    save_exam_notes,
    save_single_exam_note,
    APP_UNTIS_EXAM_NOTES_FILE,
    UNTIS_EXAM_NOTES_FILE,
)
from untis_service import (
    fetch_untis_exams_api,
    save_untis_cache,
    load_untis_exams_cache,
    save_untis_exams_cache,
    get_next_upcoming_exam,
    get_exam_web_url,
    get_cached_untis_person_id,
    extract_exam_subgroup,
)
from tui_app import TasksApp, AufgabenDetectorApp, ExamsModal, ExamDetailModal
from textual.widgets import Label
from task_manager import TaskManager


class TestUntisExamsModelAndService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mock_cache_file = os.path.join(self.temp_dir, "test_untis_cache.json")
        self.mock_notes_file = os.path.join(self.temp_dir, "test_exam_notes.json")

    def test_exam_model_countdown_and_dict(self):
        """Prüft die Countdown-Berechnung und Serialisierung von UntisExam."""
        exam = UntisExam(
            id="2026-10-19_1515_BET",
            exam_type="TE",
            exam_type_display="Test",
            subject="BET",
            name="Betriebstechnik",
            text="1. Test",
            date="2026-10-19",
            date_display="19.10.2026",
            start_time="15:15",
            end_time="16:05",
            teachers=["WWE"],
            rooms=["A1.15"],
            custom_topics="Kapitel 1-3",
            is_past=False,
            days_until=15,
        )
        self.assertEqual(exam.countdown_display, "in 15d")
        
        # Heute & Morgen
        exam.days_until = 1
        self.assertEqual(exam.countdown_display, "Tomorrow")
        exam.days_until = 0
        self.assertEqual(exam.countdown_display, "Today")
        
        # Vergangenheit
        exam.is_past = True
        exam.days_until = -3
        self.assertEqual(exam.countdown_display, "3d ago")

        # to_dict & from_dict
        d = exam.to_dict()
        self.assertEqual(d["subject"], "BET")
        self.assertEqual(d["custom_topics"], "Kapitel 1-3")
        reconstructed = UntisExam.from_dict(d)
        self.assertEqual(reconstructed.id, exam.id)
        self.assertEqual(reconstructed.name, exam.name)

    def test_exam_notes_persistence(self):
        """Prüft das Speichern und Laden von eigenen Prüfungsnotizen/Stoff."""
        with patch("config.APP_UNTIS_EXAM_NOTES_FILE", self.mock_notes_file), \
             patch("config.UNTIS_EXAM_NOTES_FILE", self.mock_notes_file):
            save_single_exam_note("2026-11-05_1145_AMEC", "Statistik & Wahrscheinlichkeitsrechnung")
            notes = load_exam_notes()
            self.assertIn("2026-11-05_1145_AMEC", notes)
            self.assertEqual(notes["2026-11-05_1145_AMEC"], "Statistik & Wahrscheinlichkeitsrechnung")

    def test_fetch_untis_exams_api_parsing(self):
        """Prüft das Parsen der WebUntis /api/exams Antwort und Normalisierung."""
        mock_response_data = {
            "data": {
                "exams": [
                    {
                        "id": 0,
                        "examType": "SA",
                        "name": "Deutschgruppe x",
                        "examDate": 20261210,
                        "startTime": 1045,
                        "endTime": 1235,
                        "subject": "Dx",
                        "teachers": ["SIL"],
                        "rooms": ["A1.15"],
                        "text": "1. Schularbeit",
                        "assignedStudents": [{"id": 12345}],
                    },
                    {
                        "id": 0,
                        "examType": "TE",
                        "name": "Softwareentwicklung",
                        "examDate": 20261216,
                        "startTime": 850,
                        "endTime": 1045,
                        "subject": "SWP1x",
                        "teachers": ["BIM"],
                        "rooms": ["A1.15"],
                        "text": "1. PLF",
                        "assignedStudents": [{"id": 99999}],  # Anderer Schüler
                    },
                ]
            }
        }
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_data
        mock_session.get.return_value = mock_resp

        exams = fetch_untis_exams_api(
            session=mock_session,
            base_url="https://test.webuntis.com/WebUntis",
            person_id=12345,
            start_date=20260901,
            end_date=20270715,
        )

        # Es sollte nur die Schularbeit für person_id=12345 enthalten sein
        self.assertEqual(len(exams), 1)
        ex = exams[0]
        self.assertEqual(ex.exam_type, "SA")
        self.assertEqual(ex.exam_type_display, "School Exam")
        self.assertEqual(ex.subject, "D")
        self.assertEqual(ex.date, "2026-12-10")
        self.assertEqual(ex.date_display, "10.12.2026")
        self.assertEqual(ex.start_time, "10:45")
        self.assertEqual(ex.end_time, "12:35")
        self.assertEqual(ex.teachers, ["SIL"])

    def test_cache_saving_loading_and_next_upcoming(self):
        """Prüft das Cachen von Prüfungen und get_next_upcoming_exam."""
        d1 = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
        d2 = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        test_exams = [
            UntisExam(
                id="ex1",
                exam_type="TE",
                exam_type_display="Test",
                subject="BET",
                name="Betriebstechnik",
                text="",
                date=d1,
                date_display=d1,
                start_time="15:15",
                end_time="16:05",
                teachers=["WWE"],
                rooms=["A1.15"],
                days_until=10,
                is_past=False,
            ),
            UntisExam(
                id="ex2",
                exam_type="SA",
                exam_type_display="Schularbeit",
                subject="D",
                name="D-SA",
                text="",
                date=d2,
                date_display=d2,
                start_time="10:45",
                end_time="12:35",
                teachers=["SIL"],
                rooms=["A1.15"],
                days_until=67,
                is_past=False,
            ),
        ]

        with patch("untis_service.UNTIS_CACHE_FILE", self.mock_cache_file), \
             patch("untis_service.load_custom_exams", return_value=[]):
            save_untis_exams_cache(test_exams)
            loaded = load_untis_exams_cache()
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].subject, "BET")

            next_ex = get_next_upcoming_exam()
            self.assertIsNotNone(next_ex)
            self.assertEqual(next_ex.subject, "BET")

    def test_exam_web_url_generation(self):
        """Prüft die WebUntis URL-Erzeugung für Prüfungen."""
        # 1. Explizit gesetzte lessonDetails URL (wie vom Benutzer gewünscht)
        expected_url = (
            "https://spengergasse.webuntis.com/timetable/my-student/lessonDetails/"
            "5728991/18342/5/2026-10-19T15:15:00/2026-10-19T16:05:00/false?date=2026-10-19&entityId=18342"
        )
        exam = UntisExam(
            id="2026-10-19_1515_BET",
            exam_type="TE",
            exam_type_display="Test",
            subject="BET",
            name="Betriebstechnik",
            text="1. Test",
            date="2026-10-19",
            date_display="19.10.2026",
            start_time="15:15",
            end_time="16:05",
            url=expected_url,
        )
        self.assertEqual(get_exam_web_url(exam), expected_url)

        # 2. Fallback-URL wenn keine periodId vorhanden
        exam_no_url = UntisExam(
            id="2026-11-05_1145_AMEC",
            exam_type="SA",
            exam_type_display="Schularbeit",
            subject="AMEC",
            name="Mathe",
            text="",
            date="2026-11-05",
            date_display="05.11.2026",
            start_time="11:45",
            end_time="12:35",
        )
        with patch("untis_service.get_cached_untis_person_id", return_value=18342), \
             patch("config.UNTIS_URL", "https://spengergasse.webuntis.com"):
            url = get_exam_web_url(exam_no_url)
            self.assertIn("date=2026-11-05", url)
            self.assertIn("entityId=18342", url)
            self.assertIn("timetable/my-student", url)

    def test_extract_exam_subgroup(self):
        """Prüft die Erkennung von Untergruppen X und Y aus Fach, Name und Text."""
        self.assertEqual(extract_exam_subgroup("SWP1x", "Sofwareentwicklung und Projektmanagement X-Gruppe", "1. PLF"), "X")
        self.assertEqual(extract_exam_subgroup("E1x", "E1x", ""), "X")
        self.assertEqual(extract_exam_subgroup("SESD_1x", "1.SLÜ", "1.SLÜ ganze Klasse"), "X")
        self.assertEqual(extract_exam_subgroup("SMEN_1x", "Test (SMENx)", "1.Test"), "X")
        self.assertEqual(extract_exam_subgroup("BET", "Betriebstechnik", ""), "")
        self.assertEqual(extract_exam_subgroup("AMEC", "Test (AMEC)", "1.Test"), "")
        self.assertEqual(extract_exam_subgroup("SWP1y", "Softwareentwicklung Y-Gruppe", "1. PLF"), "Y")
        self.assertEqual(extract_exam_subgroup("E1y", "Englisch Y-Gruppe", ""), "Y")

    def test_get_next_upcoming_exam_group_filter(self):
        """Prüft, dass get_next_upcoming_exam nur Prüfungen der gewählten Gruppe X oder Y zurückgibt."""
        exams = [
            UntisExam(
                id="ex_x",
                exam_type="TE",
                exam_type_display="Test",
                subject="SWP PM",
                name="SWP X",
                text="",
                date="2026-10-15",
                date_display="15.10.2026",
                start_time="08:00",
                end_time="08:50",
                group="X",
                days_until=5,
            ),
            UntisExam(
                id="ex_y",
                exam_type="TE",
                exam_type_display="Test",
                subject="SWP PM",
                name="SWP Y",
                text="",
                date="2026-10-16",
                date_display="16.10.2026",
                start_time="08:00",
                end_time="08:50",
                group="Y",
                days_until=6,
            ),
            UntisExam(
                id="ex_all",
                exam_type="TE",
                exam_type_display="Test",
                subject="BET",
                name="BET",
                text="",
                date="2026-10-19",
                date_display="19.10.2026",
                start_time="15:15",
                end_time="16:05",
                group="",
                days_until=9,
            ),
        ]
        with patch("untis_service.load_untis_exams_cache", return_value=exams):
            # Für Gruppe X -> ex_x
            next_x = get_next_upcoming_exam(group="X")
            self.assertIsNotNone(next_x)
            self.assertEqual(next_x.id, "ex_x")

            # Für Gruppe Y -> ex_y
            next_y = get_next_upcoming_exam(group="Y")
            self.assertIsNotNone(next_y)
            self.assertEqual(next_y.id, "ex_y")

    def test_custom_exam_crud(self):
        """Prüft das Speichern, Laden und Löschen von benutzerdefinierten Prüfungen."""
        from untis_service import save_custom_exam, load_custom_exams, delete_custom_exam
        custom_file = os.path.join(self.temp_dir, "custom_exams.json")
        with patch("config.CUSTOM_EXAMS_FILE", custom_file), \
             patch("config.APP_CUSTOM_EXAMS_FILE", custom_file), \
             patch("untis_service.UNTIS_CACHE_FILE", self.mock_cache_file):
            new_ex = UntisExam(
                id="my_custom_1",
                exam_type="TE",
                exam_type_display="Test",
                subject="SYP",
                name="Systemplanung",
                text="Stoff Kapitel 1",
                date="2026-11-20",
                date_display="20.11.2026",
                start_time="09:45",
                end_time="10:35",
                teachers=["HOF"],
                rooms=["C2.01"],
                custom_topics="Stoff Kapitel 1",
                is_custom=True,
            )
            save_custom_exam(new_ex)
            loaded = load_custom_exams()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].subject, "SYP")
            self.assertTrue(loaded[0].is_custom)
            self.assertTrue(loaded[0].id.startswith("custom_"))

            # Löschen
            deleted = delete_custom_exam(loaded[0].id)
            self.assertTrue(deleted)
            self.assertEqual(len(load_custom_exams()), 0)

    def test_lookup_untis_lesson_details(self):
        """Prüft die automatische Stundenplan-Suche nach Fach, Datum, Lehrer, Raum und Zeit."""
        from untis_service import lookup_untis_lesson_details, _TIMETABLE_CACHE
        from models import UntisLesson

        mock_lessons = [
            UntisLesson(
                id="l1",
                date="2026-10-05",
                start_time="09:55",
                end_time="10:45",
                period_num=3,
                subject="E1x",
                teacher="SO",
                room="A1.15",
                group="X",
            ),
            UntisLesson(
                id="l2",
                date="2026-10-05",
                start_time="13:25",
                end_time="14:15",
                period_num=6,
                subject="SMEN_1x",
                teacher="RAM",
                room="A1.06",
                group="X",
            ),
            UntisLesson(
                id="l3",
                date="2026-10-05",
                start_time="14:25",
                end_time="15:15",
                period_num=7,
                subject="SMEN_1x",
                teacher="RAM",
                room="A1.06",
                group="X",
            ),
        ]

        with patch.dict(_TIMETABLE_CACHE, {"2026-10-05": mock_lessons}):
            # 1. E suchen
            res_e = lookup_untis_lesson_details("2026-10-05", "E", preferred_group="X")
            self.assertIsNotNone(res_e)
            self.assertEqual(res_e["time_str"], "09:55 - 10:45")
            self.assertEqual(res_e["teacher"], "SO")
            self.assertEqual(res_e["room"], "A1.15")
            self.assertEqual(res_e["group"], "X")

            # 2. Englisch suchen (über Moodle/Untis Normalisierung)
            res_engl = lookup_untis_lesson_details("2026-10-05", "Englisch", preferred_group="X")
            self.assertIsNotNone(res_engl)
            self.assertEqual(res_engl["teacher"], "SO")

            # 3. Doppelstunde SMEN suchen (wird zu 13:25 - 15:15 zusammengefasst)
            res_smen = lookup_untis_lesson_details("2026-10-05", "SMEN", preferred_group="X")
            self.assertIsNotNone(res_smen)
            self.assertEqual(res_smen["time_str"], "13:25 - 15:15")
            self.assertEqual(res_smen["teacher"], "RAM")
            self.assertEqual(res_smen["room"], "A1.06")

            # 4. Nicht vorhandenes Fach
            self.assertIsNone(lookup_untis_lesson_details("2026-10-05", "NICHTS"))

            # 5. Spezifische Fächer-Abkürzungen (SPL_1 vs SPL_3 vs SPL)
            # SPL_3x liegt um 08:00 (Lehrer KRD), SPL_1x liegt um 11:45 (Lehrer STA)
            spl_mock_lessons = mock_lessons + [
                UntisLesson(
                    id="l_spl3",
                    date="2026-10-05",
                    start_time="08:00",
                    end_time="08:50",
                    period_num=1,
                    subject="SPL_3x",
                    teacher="KRD",
                    room="C2.04",
                    group="X",
                ),
                UntisLesson(
                    id="l_spl1_a",
                    date="2026-10-05",
                    start_time="11:45",
                    end_time="12:35",
                    period_num=5,
                    subject="SPL_1x",
                    teacher="STA",
                    room="A1.05",
                    group="X",
                ),
                UntisLesson(
                    id="l_spl1_b",
                    date="2026-10-05",
                    start_time="12:35",
                    end_time="13:25",
                    period_num=6,
                    subject="SPL_1x",
                    teacher="STA",
                    room="A1.05",
                    group="X",
                ),
            ]
            with patch.dict(_TIMETABLE_CACHE, {"2026-10-05": spl_mock_lessons}):
                # a) Explizite Suche nach SPL_1 muss exakt SPL_1 liefern und NIEMALS SPL_3 (obwohl SPL_3 früher ist)
                res_spl1 = lookup_untis_lesson_details("2026-10-05", "SPL_1", preferred_group="X")
                self.assertIsNotNone(res_spl1)
                self.assertEqual(res_spl1["teacher"], "STA")
                self.assertEqual(res_spl1["room"], "A1.05")
                self.assertEqual(res_spl1["time_str"], "11:45 - 13:25")
                self.assertEqual(res_spl1["matched_subject"], "SPL_1x")

                # b) Auch Varianten wie SPL1, SPL 1, SPL-1 müssen sicher SPL_1 matchen
                for variant in ["SPL1", "SPL 1", "SPL-1"]:
                    res_v = lookup_untis_lesson_details("2026-10-05", variant, preferred_group="X")
                    self.assertIsNotNone(res_v, f"Failed for {variant}")
                    self.assertEqual(res_v["teacher"], "STA")
                    self.assertEqual(res_v["matched_subject"], "SPL_1x")

                # c) Explizite Suche nach SPL_3 muss sicher SPL_3 liefern und NIEMALS SPL_1
                res_spl3 = lookup_untis_lesson_details("2026-10-05", "SPL_3", preferred_group="X")
                self.assertIsNotNone(res_spl3)
                self.assertEqual(res_spl3["teacher"], "KRD")
                self.assertEqual(res_spl3["room"], "C2.04")
                self.assertEqual(res_spl3["time_str"], "08:00 - 08:50")
                self.assertEqual(res_spl3["matched_subject"], "SPL_3x")

                # d) Allgemeine Suche nach SPL darf beide finden, wählt die frühere Stunde (08:00 SPL_3)
                res_spl_gen = lookup_untis_lesson_details("2026-10-05", "SPL", preferred_group="X")
                self.assertIsNotNone(res_spl_gen)
                self.assertEqual(res_spl_gen["teacher"], "KRD")
                self.assertEqual(res_spl_gen["time_str"], "08:00 - 08:50")


class TestUntisExamsTUI(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mgr = TaskManager()
        self.mgr.tasks = []

    async def test_exams_modal_and_detail_flow(self):
        """Prüft das Öffnen von ExamsModal, die Tabelle, den Stoff-Editor und den Past-Filter."""
        test_exams = [
            UntisExam(
                id="ex_past",
                exam_type="TE",
                exam_type_display="Test",
                subject="INFI",
                name="Informatik",
                text="",
                date="2026-09-15",
                date_display="15.09.2026",
                start_time="08:00",
                end_time="08:50",
                teachers=["GRG"],
                rooms=["B3.08"],
                days_until=-19,
                is_past=True,
            ),
            UntisExam(
                id="ex_future",
                exam_type="SA",
                exam_type_display="Schularbeit",
                subject="AMEC",
                name="Mathe SA",
                text="1. Schularbeit",
                date="2026-11-05",
                date_display="05.11.2026",
                start_time="11:45",
                end_time="12:35",
                teachers=["RAM"],
                rooms=["A3.05"],
                custom_topics="",
                days_until=32,
                is_past=False,
            ),
        ]

        with patch("tui_app.load_untis_exams_cache", return_value=test_exams), \
             patch("untis_service.load_untis_exams_cache", return_value=test_exams):
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # 1. Klick auf [📝 Tests]
                await pilot.click("#btn_main_exams")
                await pilot.pause()
                self.assertIsInstance(app.screen, ExamsModal)
                modal: ExamsModal = app.screen

                # Standardmäßig ist show_past=False -> nur 1 anstehender Test sichtbar
                dt = modal.query_one("#exams_table", type(modal.query_one("#exams_table")))
                self.assertEqual(dt.row_count, 1)

                # 2. Toggle Past Exams (Taste 'v' oder Klick)
                await pilot.click("#btn_toggle_past_exams")
                await pilot.pause()
                self.assertTrue(modal.show_past)
                self.assertEqual(dt.row_count, 2)

                # 3. Enter auf die Schularbeit öffnet ExamDetailModal
                modal._open_exam_detail(test_exams[1])
                await pilot.pause()
                self.assertIsInstance(app.screen, ExamDetailModal)
                detail_modal: ExamDetailModal = app.screen

                # Prüfe Datenanzeige im DetailModal
                self.assertIn("Schularbeit: AMEC", str(detail_modal.query_one("#exam_detail_title").render()))
                meta_texts = [str(l.render()) for l in detail_modal.query(".exam_meta_row")]
                self.assertTrue(any("RAM" in t for t in meta_texts))
                self.assertIn("Exam Topics / Notes:", str(detail_modal.query_one(".exam_section_label").render()))

                # Prüfe Browser-Button und Klick
                btn_browser = detail_modal.query_one("#btn_exam_browser")
                self.assertIn("Browser", str(btn_browser.label))
                with patch("webbrowser.open") as mock_open:
                    await pilot.click("#btn_exam_browser")
                    await pilot.pause()
                    mock_open.assert_called_once()
                    self.assertIn("timetable", mock_open.call_args[0][0])

                # 4. Stoff eingeben & speichern
                inp = detail_modal.query_one("#inp_exam_topics")
                inp.text = "Analysis Kapitel 1 & 2"
                with patch("tui_app.save_single_exam_note") as mock_save:
                    await pilot.click("#btn_save_exam_topics")
                    await pilot.pause()
                    mock_save.assert_called_once_with("ex_future", "Analysis Kapitel 1 & 2")

                # Zurück in ExamsScreen
                self.assertIsInstance(app.screen, ExamsModal)

                # 5. Gruppe umschalten per Taste 'g' (Button wurde ins zentrale Config-Menü verlagert)
                orig_grp = modal.current_group
                await pilot.press("g")
                await pilot.pause()
                expected_grp = "Y" if orig_grp == "X" else "X"
                self.assertEqual(modal.current_group, expected_grp)

                # Wieder zurückschalten per Taste 'g'
                await pilot.press("g")
                await pilot.pause()
                self.assertEqual(modal.current_group, orig_grp)

                # 6. Zurück zum Hauptmenü (kein AttributeError!)
                await pilot.click("#btn_exams_back")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, ExamsModal)
                info_text = str(app.query_one("#info_stats", Label).render())
                self.assertNotIn("Trash:", info_text)
                self.assertIn("Next: AMEC in 32d", info_text)

    async def test_untis_setup_modal_no_prefill_and_use_moodle_button(self):
        """Verifiziert, dass UntisSetupModal Schule und Benutzer nicht vorbefüllt und den Moodle-Button korrekt benennt."""
        from tui_app import UntisSetupModal
        from textual.widgets import Input, Button

        with patch("auth.get_existing_moodle_credentials", return_value=("moodle_creds.json", {"username": "test_student_user", "password": "pw"})), \
             patch("config._load_untis_school", return_value="spengergasse"):

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                modal = UntisSetupModal()
                app.push_screen(modal)
                await pilot.pause()

                # 1. Felder dürfen NICHT vorbefüllt sein
                school_input = modal.query_one("#inp_u_school", Input)
                user_input = modal.query_one("#inp_u_user", Input)
                self.assertEqual(school_input.value, "")
                self.assertEqual(user_input.value, "")

                # 2. Button muss '⚡ Use Moodle Account' heißen
                btn_moodle = modal.query_one("#btn_u_existing", Button)
                self.assertIn("Use Moodle Account", str(btn_moodle.label))

                # 3. ESC schließt das Fenster
                await pilot.press("escape")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, UntisSetupModal)

    async def test_school_config_modal_and_dynamic_exams_class(self):
        """Prüft das SchoolConfigModal und die dynamische Klassenanzeige im ExamsScreen."""
        from tui_app import SchoolConfigModal, ExamsScreen
        from textual.widgets import Input, Button, Label
        from config import load_full_school_config, save_full_school_config

        orig_cfg = load_full_school_config()

        try:
            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # 1. SchoolConfigModal öffnen
                cfg_modal = SchoolConfigModal()
                app.push_screen(cfg_modal)
                await pilot.pause()

                # Eingabefelder prüfen
                inp_name = cfg_modal.query_one("#inp_cfg_name", Input)
                inp_class = cfg_modal.query_one("#inp_cfg_class", Input)
                inp_school = cfg_modal.query_one("#inp_cfg_school", Input)
                btn_grp = cfg_modal.query_one("#btn_cfg_group", Button)

                self.assertIn("Group:", str(btn_grp.label))

                # Werte ändern
                inp_class.value = "4AHWII"
                await pilot.click("#btn_cfg_group")
                await pilot.pause()

                # Speichern
                await pilot.click("#btn_cfg_save")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, SchoolConfigModal)

                # Überprüfen, dass Daten gespeichert wurden
                saved_cfg = load_full_school_config()
                self.assertEqual(saved_cfg["student_class"], "4AHWII")

                # 2. ExamsScreen öffnen und dynamische Anzeige prüfen
                exams_scr = ExamsScreen()
                app.push_screen(exams_scr)
                await pilot.pause()

                info_text = str(exams_scr.query_one("#exams_sub_info", Label).render())
                self.assertIn("Class: 4AHWII", info_text)

                await pilot.press("escape")
                await pilot.pause()
        finally:
            save_full_school_config(orig_cfg)

    async def test_add_and_delete_custom_exam_tui(self):
        """Verifiziert, dass Custom Exams hinzugefügt werden können und in der Detailansicht kein Browser-, sondern ein Delete-Button erscheint."""
        from tui_app import AddExamModal, ExamDetailModal, ExamsScreen
        from textual.widgets import Input, Button

        custom_temp = os.path.join(tempfile.mkdtemp(), "custom_exams.json")
        with patch("config.CUSTOM_EXAMS_FILE", custom_temp), \
             patch("config.APP_CUSTOM_EXAMS_FILE", custom_temp):

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                # 1. ExamsScreen öffnen
                await pilot.click("#btn_main_exams")
                await pilot.pause()
                self.assertIsInstance(app.screen, ExamsScreen)
                screen: ExamsScreen = app.screen

                # 2. Add-Button prüfen und klicken
                btn_add = screen.query_one("#btn_exams_add", Button)
                self.assertIn("Add", str(btn_add.label))
                await pilot.click("#btn_exams_add")
                await pilot.pause()

                self.assertIsInstance(app.screen, AddExamModal)
                add_modal: AddExamModal = app.screen

                # 3. Felder ausfüllen
                add_modal.query_one("#inp_add_exam_subject", Input).value = "POS"
                add_modal.query_one("#inp_add_exam_date", Input).value = "25.10.2026"
                add_modal.query_one("#inp_add_exam_time", Input).value = "10:00 - 10:50"
                add_modal.query_one("#inp_add_exam_teacher", Input).value = "BIM"
                add_modal.query_one("#inp_add_exam_room", Input).value = "C3.08"
                add_modal.query_one("#inp_add_exam_topics", Input).value = "Python & AsyncIO"

                # Type-Button prüfen: Kein "(Click to toggle)"
                btn_type = add_modal.query_one("#btn_add_exam_type", Button)
                self.assertNotIn("Click to toggle", str(btn_type.label).lower())
                self.assertIn("TEST", str(btn_type.label))

                # Durchschalten: TEST -> SA -> PR -> WDH -> TEST
                await pilot.click("#btn_add_exam_type")
                await pilot.pause()
                self.assertEqual(add_modal.exam_type, "SA")
                self.assertIn("SA", str(btn_type.label))

                add_modal._toggle_type()
                await pilot.pause()
                self.assertEqual(add_modal.exam_type, "PR")
                self.assertIn("PR", str(btn_type.label))

                add_modal._toggle_type()
                await pilot.pause()
                self.assertEqual(add_modal.exam_type, "WDH")
                self.assertIn("WDH", str(btn_type.label))

                add_modal._toggle_type()
                await pilot.pause()
                self.assertEqual(add_modal.exam_type, "TE")
                self.assertIn("TEST", str(btn_type.label))

                # Speichern
                await pilot.click("#btn_add_exam_save")
                await pilot.pause()

                # Zurück in ExamsScreen
                self.assertIsInstance(app.screen, ExamsScreen)
                screen = app.screen
                custom_exam = next((e for e in screen.exams if e.subject == "POS"), None)
                self.assertIsNotNone(custom_exam)
                self.assertTrue(custom_exam.is_custom)

                # 4. Detailansicht des Custom Tests öffnen
                screen._open_exam_detail(custom_exam)
                await pilot.pause()
                self.assertIsInstance(app.screen, ExamDetailModal)
                detail_modal: ExamDetailModal = app.screen

                # Browser-Button darf NICHT vorhanden sein!
                browser_buttons = detail_modal.query("#btn_exam_browser")
                self.assertEqual(len(browser_buttons), 0)

                # Delete-Button MUSS vorhanden sein!
                delete_btn = detail_modal.query_one("#btn_exam_delete", Button)
                self.assertIn("Delete", str(delete_btn.label))

                # 5. Delete-Button anklicken
                await pilot.click("#btn_exam_delete")
                await pilot.pause()

                # Modal geschlossen, zurück in ExamsScreen
                self.assertIsInstance(app.screen, ExamsScreen)
                screen = app.screen
                # Test darf nicht mehr in exams sein
                remaining = [e for e in screen.exams if e.subject == "POS"]
                self.assertEqual(len(remaining), 0)

    async def test_add_exam_autofill_from_untis(self):
        """Prüft, dass bei Eingabe von Fach und Datum Teacher, Room und Time automatisch befüllt werden."""
        from tui_app import AddExamModal, ExamsScreen
        from textual.widgets import Input, Button
        from models import UntisLesson
        from untis_service import _TIMETABLE_CACHE

        mock_lessons = [
            UntisLesson(
                id="l1",
                date="2026-10-05",
                start_time="09:55",
                end_time="10:45",
                period_num=3,
                subject="E1x",
                teacher="SO",
                room="A1.15",
                group="X",
            ),
        ]

        custom_temp = os.path.join(tempfile.mkdtemp(), "custom_exams.json")
        with patch("config.CUSTOM_EXAMS_FILE", custom_temp), \
             patch("config.APP_CUSTOM_EXAMS_FILE", custom_temp), \
             patch.dict(_TIMETABLE_CACHE, {"2026-10-05": mock_lessons}):

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                modal = AddExamModal()
                app.push_screen(modal)
                await pilot.pause()

                # Fach 'E' und Datum '5.10.' eingeben
                modal.query_one("#inp_add_exam_subject", Input).value = "E"
                modal.query_one("#inp_add_exam_date", Input).value = "5.10."

                # Klick auf Autofill
                await pilot.click("#btn_add_exam_autofill")
                await pilot.pause(0.2)

                # Zeit, Lehrer und Raum müssen automatisch befüllt sein!
                time_val = modal.query_one("#inp_add_exam_time", Input).value
                teacher_val = modal.query_one("#inp_add_exam_teacher", Input).value
                room_val = modal.query_one("#inp_add_exam_room", Input).value

                self.assertEqual(time_val, "09:55 - 10:45")
                self.assertEqual(teacher_val, "SO")
                self.assertEqual(room_val, "A1.15")

                # Speichern
                await pilot.click("#btn_add_exam_save")
                await pilot.pause()

                # Prüfung muss mit diesen Daten gespeichert sein
                from untis_service import load_custom_exams
                customs = load_custom_exams()
                self.assertEqual(len(customs), 1)
                self.assertEqual(customs[0].subject, "E")
                self.assertEqual(customs[0].start_time, "09:55")
                self.assertEqual(customs[0].end_time, "10:45")
                self.assertEqual(customs[0].teachers, ["SO"])
                self.assertEqual(customs[0].rooms, ["A1.15"])
                self.assertEqual(customs[0].group, "X")

    async def test_custom_exam_edit_topics_persistence_and_wdh_green(self):
        """Verifiziert, dass WDH in der Tabelle grün dargestellt wird und Stoff-Änderungen an Custom Exams persistent gespeichert werden."""
        from tui_app import ExamDetailModal, ExamsScreen
        from textual.widgets import TextArea, DataTable
        from untis_service import save_custom_exam, load_custom_exams, load_untis_exams_cache

        custom_temp = os.path.join(tempfile.mkdtemp(), "custom_exams.json")
        notes_temp = os.path.join(tempfile.mkdtemp(), "exam_notes.json")

        with patch("config.CUSTOM_EXAMS_FILE", custom_temp), \
             patch("config.APP_CUSTOM_EXAMS_FILE", custom_temp), \
             patch("config.UNTIS_EXAM_NOTES_FILE", notes_temp), \
             patch("config.APP_UNTIS_EXAM_NOTES_FILE", notes_temp):

            # Erstelle eine WDH Prüfung
            wdh_exam = UntisExam(
                id="custom_20261115_test_wdh",
                exam_type="WDH",
                exam_type_display="Wiederholung",
                subject="D",
                name="D",
                text="Alte Themen",
                date="2026-11-15",
                date_display="15.11.2026",
                start_time="08:00",
                end_time="08:50",
                teachers=["SIL"],
                rooms=["A1.15"],
                custom_topics="Alte Themen",
                is_custom=True,
                days_until=42,
            )
            save_custom_exam(wdh_exam)

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                screen = ExamsScreen()
                app.push_screen(screen)
                await pilot.pause()

                # 1. Prüfe, dass WDH in der Tabelle grün ist
                dt = screen.query_one("#exams_table", DataTable)
                row = dt.get_row("custom_20261115_test_wdh")
                # Spalte 1 ist Type
                type_col = row[1]
                self.assertEqual(str(type_col), "WDH")
                self.assertIn("green", str(type_col.style))

                # 2. Detailansicht öffnen
                screen._open_exam_detail(wdh_exam)
                await pilot.pause()
                self.assertIsInstance(app.screen, ExamDetailModal)
                detail_modal: ExamDetailModal = app.screen

                # Stoff ändern
                ta = detail_modal.query_one("#inp_exam_topics", TextArea)
                ta.text = "Komplett neuer Stoff: Barock & Aufklärung"

                # Speichern
                await pilot.click("#btn_save_exam_topics")
                await pilot.pause()

                # 3. Überprüfen, dass die Notiz persistent gespeichert wurde
                loaded_customs = load_custom_exams()
                self.assertEqual(len(loaded_customs), 1)
                self.assertEqual(loaded_customs[0].custom_topics, "Komplett neuer Stoff: Barock & Aufklärung")

                cached_all = load_untis_exams_cache()
                match = next((e for e in cached_all if e.id == "custom_20261115_test_wdh"), None)
                self.assertIsNotNone(match)
                self.assertEqual(match.custom_topics, "Komplett neuer Stoff: Barock & Aufklärung")

    async def test_add_exam_modal_natural_date_resolution(self):
        """Verifiziert, dass 'Tomorrow', 'Tuesday', 'Mittwoch' etc. in AddExamModal direkt aufgelöst werden."""
        from tui_app import AddExamModal
        from textual.widgets import Input
        from tui_app import format_german_weekday_date
        today = datetime.date.today()
        tomorrow_dt = today + datetime.timedelta(days=1)
        tomorrow_str = format_german_weekday_date(tomorrow_dt)
        days_to_tue = (1 - today.weekday()) % 7
        if days_to_tue == 0:
            days_to_tue = 7
        tue_dt = today + datetime.timedelta(days=days_to_tue)
        tue_str = format_german_weekday_date(tue_dt)
        days_to_wed = (2 - today.weekday()) % 7
        if days_to_wed == 0:
            days_to_wed = 7
        wed_dt = today + datetime.timedelta(days=days_to_wed)
        wed_str = format_german_weekday_date(wed_dt)

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(120, 35)) as pilot:
            modal = AddExamModal()
            await app.push_screen(modal)
            await pilot.pause()

            date_inp = modal.query_one("#inp_add_exam_date", Input)

            # 1. "Tomorrow" eingeben -> morgiges Datum
            date_inp.value = "Tomorrow"
            await pilot.pause()
            self.assertEqual(date_inp.value, tomorrow_str)

            # 2. "Tuesday" eingeben -> nächster Dienstag
            date_inp.value = "Tuesday"
            await pilot.pause()
            self.assertEqual(date_inp.value, tue_str)

            # 3. "Mittwoch" eingeben -> nächster Mittwoch
            date_inp.value = "Mittwoch"
            await pilot.pause()
            self.assertEqual(date_inp.value, wed_str)

            await pilot.click("#btn_add_exam_cancel")
            await pilot.pause()

    async def test_exam_topic_truncation_in_table_and_full_in_detail_modal(self):
        """Verifiziert, dass lange/mehrzeilige Notizen in der Tabelle einzeilig mit '...' gekürzt werden,
        aber im Detail-Modal vollständig angezeigt werden."""
        from tui_app import ExamDetailModal, ExamsScreen
        from textual.widgets import TextArea, DataTable
        from untis_service import save_custom_exam

        custom_temp = os.path.join(tempfile.mkdtemp(), "custom_exams.json")
        notes_temp = os.path.join(tempfile.mkdtemp(), "exam_notes.json")

        long_topics_text = "1_Marketing Start with why.pdf, 3_Marketing Ziele 26_27, 4_Marketing Mix Uebung\n5_Extra Zeile"

        with patch("config.CUSTOM_EXAMS_FILE", custom_temp), \
             patch("config.APP_CUSTOM_EXAMS_FILE", custom_temp), \
             patch("config.UNTIS_EXAM_NOTES_FILE", notes_temp), \
             patch("config.APP_UNTIS_EXAM_NOTES_FILE", notes_temp):

            test_exam = UntisExam(
                id="custom_20261120_test_truncation",
                exam_type="WDH",
                exam_type_display="Wiederholung",
                subject="UFW",
                name="UFW",
                text="Notiz",
                date="2026-11-20",
                date_display="20.11.2026",
                start_time="11:45",
                end_time="13:25",
                teachers=["HIN"],
                rooms=["C3.04"],
                custom_topics=long_topics_text,
                is_custom=True,
                days_until=40,
            )
            save_custom_exam(test_exam)

            app = AufgabenDetectorApp(self.mgr)
            async with app.run_test(size=(120, 35)) as pilot:
                screen = ExamsScreen()
                app.push_screen(screen)
                await pilot.pause()

                dt = screen.query_one("#exams_table", DataTable)
                row = dt.get_row("custom_20261120_test_truncation")
                topic_cell = row[5]
                topic_str = str(topic_cell)

                # 1. Muss einzeilig sein (kein Newline)
                self.assertNotIn("\n", topic_str)
                # 2. Muss mit '...' enden
                self.assertTrue(topic_str.endswith("..."))
                # 3. Länge darf maximale Spaltenbreite nicht überschreiten
                self.assertLessEqual(len(topic_str), 36)

                # 4. Detailansicht öffnen
                screen._open_exam_detail(test_exam)
                await pilot.pause()
                self.assertIsInstance(app.screen, ExamDetailModal)
                detail_modal: ExamDetailModal = app.screen

                # 5. Im Detail-Modal muss der gesamte Text stehen (ungekürzt und inklusive Zeilenumbrüche)
                ta = detail_modal.query_one("#inp_exam_topics", TextArea)
                self.assertEqual(ta.text, long_topics_text)

    async def test_exams_screen_full_width_column_distribution_and_resize(self):
        """Verifiziert, dass alle 9 Spalten im ExamsScreen die volle Bildschirmbreite ausfüllen
        ohne Leerraum rechts und ohne horizontale Scrollbar (bei 123 und 160 Spalten)."""
        from tui_app import ExamsScreen
        from textual.widgets import DataTable
        from textual.events import Resize
        from textual.geometry import Size

        app = AufgabenDetectorApp(self.mgr)
        async with app.run_test(size=(123, 33)) as pilot:
            screen = ExamsScreen()
            app.push_screen(screen)
            await pilot.pause()

            dt = screen.query_one("#exams_table", DataTable)
            render_widths_123 = [c.get_render_width(dt) for c in dt.columns.values()]
            sum_123 = sum(render_widths_123)

            # Muss die 123 Spalten (abzüglich Rand/Puffer) ausfüllen und keine horizontale Scrollbar haben
            self.assertGreaterEqual(sum_123, 118)
            self.assertLessEqual(sum_123, 122)
            self.assertFalse(dt.show_horizontal_scrollbar)

            # Auf breites Fenster (160 Spalten) resizen
            await pilot.resize_terminal(160, 40)
            await pilot.pause()

            render_widths_160 = [c.get_render_width(dt) for c in dt.columns.values()]
            sum_160 = sum(render_widths_160)

            # Spalten müssen sich proportional auf die neue Breite dehnen
            self.assertGreaterEqual(sum_160, 155)
            self.assertLessEqual(sum_160, 160)
            self.assertFalse(dt.show_horizontal_scrollbar)
            # Topic-Spalte (Index 5) muss deutlich breiter sein als bei 123 Spalten
            self.assertGreater(render_widths_160[5], render_widths_123[5])


if __name__ == "__main__":
    unittest.main()


