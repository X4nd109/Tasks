"""
test_directories.py - Unit and integration tests for DirectoryService and directory linking.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TEST_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
CORE_DIR = os.path.join(SRC_DIR, "core")
SERVICES_DIR = os.path.join(SRC_DIR, "services")
UI_DIR = os.path.join(SRC_DIR, "ui")

for p in [PROJECT_ROOT, SRC_DIR, CORE_DIR, SERVICES_DIR, UI_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from directory_service import DirectoryService


class TestDirectoryService(unittest.TestCase):
    """Tests for the DirectoryService core logic."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_active_file = DirectoryService._get_active_file()
        self.orig_fallback_file = DirectoryService._get_fallback_file()
        self.test_dirs_file = os.path.join(self.test_dir, "directories.json")
        DirectoryService._get_active_file = staticmethod(lambda: self.test_dirs_file)
        DirectoryService._get_fallback_file = staticmethod(lambda: None)

    def tearDown(self):
        DirectoryService._get_active_file = staticmethod(lambda: self.orig_active_file)
        DirectoryService._get_fallback_file = staticmethod(lambda: self.orig_fallback_file)
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_load_empty_directories(self):
        """Should return empty list when no file exists."""
        dirs = DirectoryService.load_directories()
        self.assertEqual(dirs, [])

    def test_add_directory_auto_title(self):
        """Tests adding a directory with auto-derived title from basename."""
        folder = os.path.join(self.test_dir, "BET")
        os.makedirs(folder, exist_ok=True)

        entry = DirectoryService.add_directory(folder)
        self.assertEqual(entry["title"], "BET")
        self.assertEqual(entry["path"], os.path.abspath(folder))
        self.assertTrue(entry["id"].startswith("dir_"))

        # Verify persistence
        loaded = DirectoryService.load_directories()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["title"], "BET")

    def test_add_directory_custom_title(self):
        """Tests adding a directory with custom user title."""
        folder = os.path.join(self.test_dir, "my_long_folder_name")
        os.makedirs(folder, exist_ok=True)

        entry = DirectoryService.add_directory(folder, title="Betriebstechnik")
        self.assertEqual(entry["title"], "Betriebstechnik")
        self.assertEqual(entry["path"], os.path.abspath(folder))

    def test_add_existing_directory_updates_title(self):
        """Adding the same folder path again should update the title rather than duplicating."""
        folder = os.path.join(self.test_dir, "BET")
        os.makedirs(folder, exist_ok=True)

        DirectoryService.add_directory(folder, title="BET 1")
        DirectoryService.add_directory(folder, title="BET Updated")

        dirs = DirectoryService.load_directories()
        self.assertEqual(len(dirs), 1)
        self.assertEqual(dirs[0]["title"], "BET Updated")

    def test_remove_directory(self):
        """Tests removing a directory by ID, title, or basename."""
        f1 = os.path.join(self.test_dir, "BET")
        f2 = os.path.join(self.test_dir, "AMEC")
        os.makedirs(f1, exist_ok=True)
        os.makedirs(f2, exist_ok=True)

        e1 = DirectoryService.add_directory(f1, "BET")
        e2 = DirectoryService.add_directory(f2, "AMEC")

        # Remove by ID
        removed = DirectoryService.remove_directory(e1["id"])
        self.assertTrue(removed)
        self.assertEqual(len(DirectoryService.load_directories()), 1)

        # Remove by title
        removed2 = DirectoryService.remove_directory("AMEC")
        self.assertTrue(removed2)
        self.assertEqual(len(DirectoryService.load_directories()), 0)

    def test_find_directory(self):
        """Tests finding a directory by ID, exact title, or partial search."""
        folder = os.path.join(self.test_dir, "SWP_Projekte")
        os.makedirs(folder, exist_ok=True)

        entry = DirectoryService.add_directory(folder, "SWP")

        self.assertEqual(DirectoryService.find_directory(entry["id"]), entry)
        self.assertEqual(DirectoryService.find_directory("SWP"), entry)
        self.assertEqual(DirectoryService.find_directory("swp_projekte"), entry)
        self.assertIsNone(DirectoryService.find_directory("NonExistent"))

    def test_open_directory_success(self):
        """Tests opening directory triggers os.startfile on Windows or system launcher."""
        folder = os.path.join(self.test_dir, "BET")
        os.makedirs(folder, exist_ok=True)
        entry = DirectoryService.add_directory(folder)

        with patch("os.startfile", create=True) as mock_startfile, \
             patch("subprocess.Popen") as mock_popen:
            ok, msg = DirectoryService.open_directory(entry)
            self.assertTrue(ok)
            self.assertIn("opened in file explorer", msg)

    def test_open_directory_not_found(self):
        """Tests error handling when directory does not exist on disk."""
        non_existent = os.path.join(self.test_dir, "missing_dir")
        entry = {"id": "dir_123", "title": "Missing", "path": non_existent}

        ok, msg = DirectoryService.open_directory(entry)
        self.assertFalse(ok)
        self.assertIn("Folder not found", msg)


class TestDirectoryGitExclusion(unittest.TestCase):
    """Ensures directories.json is ignored by git."""

    def test_gitignore_contains_directories(self):
        root_gitignore = os.path.join(PROJECT_ROOT, ".gitignore")
        data_gitignore = os.path.join(PROJECT_ROOT, "data", ".gitignore")

        self.assertTrue(os.path.exists(root_gitignore))
        with open(root_gitignore, "r", encoding="utf-8") as f:
            self.assertIn("directories.json", f.read())

        self.assertTrue(os.path.exists(data_gitignore))
        with open(data_gitignore, "r", encoding="utf-8") as f:
            self.assertIn("directories.json", f.read())


class TestDirectoryCLI(unittest.TestCase):
    """Tests for the CLI command 'tasks dirs'."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_active_file = DirectoryService._get_active_file()
        self.orig_fallback_file = DirectoryService._get_fallback_file()
        self.test_dirs_file = os.path.join(self.test_dir, "directories.json")
        DirectoryService._get_active_file = staticmethod(lambda: self.test_dirs_file)
        DirectoryService._get_fallback_file = staticmethod(lambda: None)

    def tearDown(self):
        DirectoryService._get_active_file = staticmethod(lambda: self.orig_active_file)
        DirectoryService._get_fallback_file = staticmethod(lambda: self.orig_fallback_file)
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_cli_dirs_list_empty(self):
        from agent_cli import run_agent_cli
        ret = run_agent_cli(["dirs", "list", "--json"])
        self.assertEqual(ret, 0)

    def test_cli_dirs_add_list_and_remove(self):
        from agent_cli import run_agent_cli
        folder = os.path.join(self.test_dir, "BET")
        os.makedirs(folder, exist_ok=True)

        ret_add = run_agent_cli(["dirs", "add", folder, "--title", "Betriebstechnik", "--json"])
        self.assertEqual(ret_add, 0)

        dirs = DirectoryService.load_directories()
        self.assertEqual(len(dirs), 1)
        self.assertEqual(dirs[0]["title"], "Betriebstechnik")

        ret_del = run_agent_cli(["dirs", "remove", "1", "--json"])
        self.assertEqual(ret_del, 0)
        self.assertEqual(len(DirectoryService.load_directories()), 0)


class TestUnifiedCommandPaletteDirectories(unittest.IsolatedAsyncioTestCase):
    """Tests for UnifiedCommandPalette and UnifiedQuickOpenProvider in directories mode."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_active_file = DirectoryService._get_active_file()
        self.orig_fallback_file = DirectoryService._get_fallback_file()
        self.test_dirs_file = os.path.join(self.test_dir, "directories.json")
        DirectoryService._get_active_file = staticmethod(lambda: self.test_dirs_file)
        DirectoryService._get_fallback_file = staticmethod(lambda: None)

    def tearDown(self):
        DirectoryService._get_active_file = staticmethod(lambda: self.orig_active_file)
        DirectoryService._get_fallback_file = staticmethod(lambda: self.orig_fallback_file)
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_palette_mode_cycle(self):
        """Palette should cycle courses -> books -> directories -> courses."""
        from tui_app import UnifiedCommandPalette
        palette = UnifiedCommandPalette(initial_mode="courses")
        self.assertEqual(palette.active_mode, "courses")
        self.assertIn("Courses", palette._get_header_text())

        palette.action_switch_mode()
        self.assertEqual(palette.active_mode, "books")
        self.assertIn("Schoolbooks", palette._get_header_text())

        palette.action_switch_mode()
        self.assertEqual(palette.active_mode, "directories")
        self.assertIn("Directories", palette._get_header_text())
        self.assertIn("bold green", palette._get_header_text())
        self.assertIn("Search directories", palette._get_placeholder())

        palette.action_switch_mode()
        self.assertEqual(palette.active_mode, "courses")
        self.assertIn("Courses", palette._get_header_text())

    async def test_provider_directories_discover_and_search(self):
        """Test discover and search in directories mode."""
        from tui_app import UnifiedQuickOpenProvider, UnifiedCommandPalette

        folder = os.path.join(self.test_dir, "BET")
        os.makedirs(folder, exist_ok=True)
        DirectoryService.add_directory(folder, "BET")

        UnifiedCommandPalette.current_mode = "directories"
        palette = UnifiedCommandPalette(initial_mode="directories")
        provider = UnifiedQuickOpenProvider(palette)

        # Discover
        hits = [hit async for hit in provider.discover()]
        self.assertTrue(any("/link" in h.text for h in hits))
        self.assertTrue(any("BET" in h.text for h in hits))

        # Search /link
        link_hits = [h async for h in provider.search("/link")]
        self.assertTrue(len(link_hits) >= 1)

        # Search directory name
        search_hits = [h async for h in provider.search("BET")]
        self.assertTrue(len(search_hits) >= 1)
        self.assertIn("BET", search_hits[0].text)

    def test_palette_mode_switch_preserves_input_text(self):
        """Switching mode via Tab should NOT clear the search bar text."""
        from tui_app import UnifiedCommandPalette
        palette = UnifiedCommandPalette(initial_mode="courses")
        mock_input = MagicMock()
        mock_input.value = "search_term"
        palette.query_one = MagicMock(return_value=mock_input)
        palette._gather_commands = MagicMock()
        palette._cancel_gather_commands = MagicMock()
        palette._stop_no_matches_countdown = MagicMock()

        palette.action_switch_mode()

        self.assertEqual(palette.active_mode, "books")
        self.assertEqual(mock_input.value, "search_term")
        palette._gather_commands.assert_called_with("search_term")

    def test_backspace_on_empty_input_closes_palette(self):
        """Pressing backspace on an empty input should close the palette."""
        from tui_app import UnifiedCommandInput
        inp = UnifiedCommandInput()
        mock_screen = MagicMock()
        with patch.object(UnifiedCommandInput, "screen", new_callable=unittest.mock.PropertyMock) as mock_scr_prop:
            mock_scr_prop.return_value = mock_screen
            inp.action_delete_left()
            mock_screen._action_escape.assert_called_once()

    def test_backspace_on_non_empty_input_does_not_close(self):
        """Pressing backspace with text should delete character, not close screen."""
        from tui_app import UnifiedCommandInput
        inp = UnifiedCommandInput()
        mock_screen = MagicMock()
        with patch.object(UnifiedCommandInput, "value", new_callable=unittest.mock.PropertyMock) as mock_val_prop, \
             patch.object(UnifiedCommandInput, "screen", new_callable=unittest.mock.PropertyMock) as mock_scr_prop, \
             patch("textual.widgets.Input.action_delete_left") as mock_super_delete:
            mock_val_prop.return_value = "BET"
            mock_scr_prop.return_value = mock_screen
            inp.action_delete_left()
            mock_screen._action_escape.assert_not_called()
            mock_super_delete.assert_called_once()

    def test_palette_on_key_backspace_closes_when_empty(self):
        """UnifiedCommandPalette.on_key closes when backspace is pressed with empty input."""
        from tui_app import UnifiedCommandPalette
        palette = UnifiedCommandPalette()
        mock_input = MagicMock()
        mock_input.value = ""
        palette.query_one = MagicMock(return_value=mock_input)
        palette._action_escape = MagicMock()

        event = MagicMock()
        event.key = "backspace"
        palette.on_key(event)

        palette._action_escape.assert_called_once()
        event.prevent_default.assert_called_once()

    def test_oled_theme_properties(self):
        """OLED theme should have pure black background and Flexoki-inspired accents."""
        from tui_app import OLED_THEME
        from config import ALLOWED_THEMES

        self.assertIn("oled", ALLOWED_THEMES)
        self.assertEqual(OLED_THEME.name, "oled")
        self.assertEqual(OLED_THEME.background, "#000000")
        self.assertEqual(OLED_THEME.surface, "#000000")
        self.assertEqual(OLED_THEME.panel, "#000000")
        # Flexoki accents
        self.assertEqual(OLED_THEME.primary, "#205EA6")
        self.assertEqual(OLED_THEME.secondary, "#24837B")
        self.assertEqual(OLED_THEME.error, "#AF3029")
        self.assertEqual(OLED_THEME.success, "#66800B")

    async def test_palette_tabs_layout_and_switch(self):
        """UnifiedCommandPalette should have margin-top: 0 and fixed 3 tabs (Courses, Schoolbooks, Directories) with click support."""
        from textual.app import App, ComposeResult
        from tui_app import UnifiedCommandPalette

        class PaletteTestApp(App):
            def compose(self) -> ComposeResult:
                yield from ()

            def on_mount(self):
                self.push_screen(UnifiedCommandPalette(initial_mode="courses"))

        app = PaletteTestApp()
        async with app.run_test() as pilot:
            p = app.screen
            container = p.query_one("#--container")
            self.assertEqual(container.styles.margin.top, 0)

            tab_courses = p.query_one("#palette-tab-courses")
            tab_books = p.query_one("#palette-tab-books")
            tab_dirs = p.query_one("#palette-tab-directories")

            # Fixed positions: Courses (left), Schoolbooks (center), Directories (right)
            self.assertEqual(str(tab_courses.content), "Courses")
            self.assertEqual(str(tab_books.content), "Schoolbooks")
            self.assertEqual(str(tab_dirs.content), "Directories")

            # Initial: courses active
            self.assertTrue(tab_courses.has_class("-active-courses"))
            self.assertFalse(tab_books.has_class("-active-books"))
            self.assertFalse(tab_dirs.has_class("-active-directories"))

            # Switch mode (next -> books)
            p.action_switch_mode()
            self.assertEqual(p.active_mode, "books")
            self.assertFalse(tab_courses.has_class("-active-courses"))
            self.assertTrue(tab_books.has_class("-active-books"))
            self.assertFalse(tab_dirs.has_class("-active-directories"))

            # Switch mode (next -> directories)
            p.action_switch_mode()
            self.assertEqual(p.active_mode, "directories")
            self.assertFalse(tab_courses.has_class("-active-courses"))
            self.assertFalse(tab_books.has_class("-active-books"))
            self.assertTrue(tab_dirs.has_class("-active-directories"))

            # Click Courses tab directly
            await pilot.click("#palette-tab-courses")
            self.assertEqual(p.active_mode, "courses")
            self.assertTrue(tab_courses.has_class("-active-courses"))
            self.assertFalse(tab_books.has_class("-active-books"))
            self.assertFalse(tab_dirs.has_class("-active-directories"))

            # Click Schoolbooks tab directly
            await pilot.click("#palette-tab-books")
            self.assertEqual(p.active_mode, "books")
            self.assertTrue(tab_books.has_class("-active-books"))

            # Click Directories tab directly
            await pilot.click("#palette-tab-directories")
            self.assertEqual(p.active_mode, "directories")
            self.assertTrue(tab_dirs.has_class("-active-directories"))



if __name__ == "__main__":
    unittest.main()
