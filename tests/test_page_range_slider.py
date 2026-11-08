"""
Unit tests for TwoThumbRangeSlider widget, Digi4SchoolPageRangeModal, and page range parsing.
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from src.ui.range_slider import TwoThumbRangeSlider
from src.services.digi4school_service import parse_page_ranges, Digi4SchoolService


class TestTwoThumbRangeSlider(unittest.TestCase):
    """Tests für das interaktive TwoThumbRangeSlider Widget."""

    def test_initial_bounds_and_values(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=250, start_val=20, end_val=50)
        self.assertEqual(slider.min_val, 1)
        self.assertEqual(slider.max_val, 250)
        self.assertEqual(slider.start_val, 20)
        self.assertEqual(slider.end_val, 50)
        self.assertEqual(slider.active_thumb, "start")

    def test_default_values_span_all_pages(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=120)
        self.assertEqual(slider.start_val, 1)
        self.assertEqual(slider.end_val, 120)

    def test_clamping_on_initialization(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=100, start_val=-10, end_val=500)
        self.assertEqual(slider.start_val, 1)
        self.assertEqual(slider.end_val, 100)

        # start_val greater than end_val should be corrected
        slider2 = TwoThumbRangeSlider(min_val=1, max_val=100, start_val=80, end_val=30)
        self.assertTrue(slider2.start_val <= slider2.end_val)

    def test_set_range(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=200, start_val=1, end_val=200)
        slider.set_range(25, 75)
        self.assertEqual(slider.start_val, 25)
        self.assertEqual(slider.end_val, 75)

        # Clamping bounds
        slider.set_range(0, 300)
        self.assertEqual(slider.start_val, 1)
        self.assertEqual(slider.end_val, 200)

    def test_set_bounds(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=50, start_val=10, end_val=40)
        slider.set_bounds(5, 30)
        self.assertEqual(slider.min_val, 5)
        self.assertEqual(slider.max_val, 30)
        self.assertEqual(slider.start_val, 10)
        self.assertEqual(slider.end_val, 30)

    def test_val_to_pos_and_pos_to_val(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=101)
        track_width = 101

        # Page 1 should map to pos 0
        self.assertEqual(slider._val_to_pos(1, track_width), 0)
        # Page 101 should map to pos 100
        self.assertEqual(slider._val_to_pos(101, track_width), 100)

        # Pos 0 should map to page 1
        self.assertEqual(slider._pos_to_val(0, track_width), 1)
        # Pos 100 should map to page 101
        self.assertEqual(slider._pos_to_val(100, track_width), 101)

    def test_allow_select_is_disabled(self):
        """Stellt sicher, dass Textauswahl auf dem Slider deaktiviert ist."""
        slider = TwoThumbRangeSlider(min_val=1, max_val=100)
        self.assertFalse(slider.ALLOW_SELECT)
        self.assertFalse(slider.allow_select)

    def test_mouse_events_stop_propagation_and_prevent_selection(self):
        """Prüft, dass Maus-Events gestoppt werden, um Textmarkierung zu verhindern."""
        slider = TwoThumbRangeSlider(min_val=1, max_val=100)

        from textual.geometry import Size
        from unittest.mock import PropertyMock
        mock_screen = MagicMock()
        mock_down_event = MagicMock()
        mock_down_event.x = 30
        mock_down_event.y = 1

        with patch.object(TwoThumbRangeSlider, "screen", new_callable=PropertyMock, return_value=mock_screen), \
             patch.object(TwoThumbRangeSlider, "size", new_callable=PropertyMock, return_value=Size(80, 3)), \
             patch.object(slider, "focus"), \
             patch.object(slider, "capture_mouse"), \
             patch.object(slider, "post_message"), \
             patch.object(slider, "refresh"):
            slider.on_mouse_down(mock_down_event)

        self.assertTrue(slider._is_dragging)
        mock_down_event.stop.assert_called_once()
        mock_down_event.prevent_default.assert_called_once()
        mock_screen.clear_selection.assert_called_once()

        # Test MouseMove while dragging
        mock_move_event = MagicMock()
        mock_move_event.x = 40
        mock_move_event.y = 1
        with patch.object(TwoThumbRangeSlider, "size", new_callable=PropertyMock, return_value=Size(80, 3)), \
             patch.object(slider, "post_message"), \
             patch.object(slider, "refresh"):
            slider.on_mouse_move(mock_move_event)
        mock_move_event.stop.assert_called_once()
        mock_move_event.prevent_default.assert_called_once()

        # Test MouseUp
        mock_up_event = MagicMock()
        with patch.object(slider, "release_mouse"):
            slider.on_mouse_up(mock_up_event)
        self.assertFalse(slider._is_dragging)
        mock_up_event.stop.assert_called_once()
        mock_up_event.prevent_default.assert_called_once()

    def test_render_output_contains_labels(self):
        slider = TwoThumbRangeSlider(min_val=1, max_val=300, start_val=20, end_val=50)
        text = slider.render().plain
        self.assertIn("1", text)
        self.assertIn("300", text)
        self.assertIn("Start: 20", text)
        self.assertIn("Ende: 50", text)
        self.assertIn("31 Seiten", text)


class TestPageRangesAndService(unittest.TestCase):
    """Tests für die Seitenbereichs-Parsinglogik und Service-Methoden."""

    def test_parse_page_ranges(self):
        # Range string "20-25"
        pages = parse_page_ranges("20-25", max_pages=100)
        self.assertEqual(pages, [20, 21, 22, 23, 24, 25])

        # Single page and range combined "1, 5, 10-12"
        pages = parse_page_ranges("1, 5, 10-12", max_pages=100)
        self.assertEqual(pages, [1, 5, 10, 11, 12])

        # Clamped to max_pages
        pages = parse_page_ranges("98-105", max_pages=100)
        self.assertEqual(pages, [98, 99, 100])

    @patch("src.services.digi4school_service.async_playwright")
    def test_inspect_book_empty_code_raises(self, mock_playwright):
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(Digi4SchoolService.inspect_book("test@example.com", "pass", ""))

    def test_digi4school_progress_modal_accepts_pages(self):
        from src.ui.tui_app import Digi4SchoolProgressModal
        modal = Digi4SchoolProgressModal(
            email="test@example.com",
            password="pass",
            code="26s0h5hr5hyv",
            quality="standard",
            pages="1-5",
        )
        self.assertEqual(modal.pages, "1-5")
        self.assertEqual(modal.code, "26s0h5hr5hyv")
        self.assertEqual(modal.quality, "standard")

    def test_digi4school_page_range_modal_layout(self):
        from src.ui.tui_app import Digi4SchoolPageRangeModal
        modal = Digi4SchoolPageRangeModal(
            email="test@example.com",
            password="pass",
            code="26s0h5hr5hyv",
            quality="standard",
            title="Betriebstechnik",
            total_pages=420,
        )
        self.assertEqual(modal.code, "26s0h5hr5hyv")
        self.assertEqual(modal.max_pages, 420)
        self.assertEqual(modal.start_page, 1)
        self.assertEqual(modal.end_page, 420)

    def test_ocr_worker_process_bold_and_underlined(self):
        from src.services.digi4school_service import ocr_worker_process, find_tesseract
        from PIL import Image, ImageDraw, ImageFont
        import io
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        try:
            tess_path = find_tesseract()
        except FileNotFoundError:
            tess_path = None

        if not tess_path:
            self.skipTest("Tesseract OCR not installed on this system.")

        img = Image.new("RGB", (600, 150), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 36)
        except Exception:
            font = None

        text = "Wirtschaftsingenieur"
        # Bold text (draw with bold offset)
        draw.text((20, 30), text, fill=(0, 0, 0), font=font)
        draw.text((21, 30), text, fill=(0, 0, 0), font=font)
        # Horizontal underline line directly below text
        draw.line((20, 80, 420, 80), fill=(0, 0, 0), width=3)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        # Run worker with 300 DPI
        p_num, pdf_bytes = ocr_worker_process((1, img_bytes, "deu+eng", 300, 3, tess_path))
        self.assertEqual(p_num, 1)
        self.assertTrue(len(pdf_bytes) > 0)

        # Inspect generated PDF page text layer
        doc = fitz.open("pdf", pdf_bytes)
        self.assertEqual(len(doc), 1)
        extracted = doc[0].get_text()
        doc.close()
        self.assertIn("Wirtschaftsingenieur", extracted)


if __name__ == "__main__":
    unittest.main()
