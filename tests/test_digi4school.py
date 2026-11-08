"""
test_digi4school.py - Unit- und Integrationstests für den Digi4School Book Grabber Service & CLI.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

# Workspace-Pfade für Importe
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "services")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "core")))

try:
    import pymupdf as fitz
except ImportError:
    import fitz  # PyMuPDF fallback
from PIL import Image

from digi4school_service import (
    find_tesseract,
    parse_page_ranges,
    infer_toc_hierarchy,
    encode_image_dct,
    compact_pdf_document,
    Digi4SchoolService,
)
from agent_cli import handle_books_command


def _jpeg_sampling_factors(data: bytes):
    """Liest die Sampling-Faktoren aus dem JPEG SOF-Marker (0x11 = 4:4:4)."""
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            components = data[i + 9]
            offset = i + 10
            factors = []
            for _ in range(components):
                factors.append(data[offset + 1])
                offset += 3
            return factors
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        i += 2 + seg_len
    return []



class TestDigi4SchoolService(unittest.TestCase):
    """Testet Kernfunktionen des Digi4School Service."""

    def test_find_tesseract(self):
        """Prüft, ob Tesseract auf dem System gefunden wird."""
        try:
            tess = find_tesseract()
            self.assertTrue(os.path.isfile(tess), f"Tesseract-Pfad {tess} existiert nicht")
            self.assertIn("tesseract", tess.lower())
        except FileNotFoundError:
            self.skipTest("Tesseract OCR is not installed on this host environment.")

    def test_parse_page_ranges_simple(self):
        """Prüft einfache Seitenbereiche."""
        pages = parse_page_ranges("1-5")
        self.assertEqual(pages, [1, 2, 3, 4, 5])

    def test_parse_page_ranges_mixed(self):
        """Prüft gemischte Seitenangaben mit Kommas und Bereichen."""
        pages = parse_page_ranges("1, 3, 5-7, 10")
        self.assertEqual(pages, [1, 3, 5, 6, 7, 10])

    def test_parse_page_ranges_all(self):
        """Prüft 'all' mit max_pages."""
        pages = parse_page_ranges("all", max_pages=15)
        self.assertEqual(pages, list(range(1, 16)))

    def test_parse_page_ranges_end(self):
        """Prüft '10-end' mit max_pages."""
        pages = parse_page_ranges("10-end", max_pages=14)
        self.assertEqual(pages, [10, 11, 12, 13, 14])

    def test_infer_toc_hierarchy_modules(self):
        """Prüft hierarchische Lesezeichen-Strukturierung mit Modulen und Kapiteln."""
        raw_toc = [
            {"title": "Inhaltsverzeichnis", "page": 3, "level": 1},
            {"title": "Kompetenzmodul 1", "page": 5, "level": 1},
            {"title": "1 Grundlagen", "page": 6, "level": 1},
            {"title": "1.1 Einführung in das Thema", "page": 8, "level": 1},
            {"title": "1.1.1 Detailaspekt", "page": 10, "level": 1},
            {"title": "Kompetenzmodul 2", "page": 20, "level": 1},
            {"title": "2 Vertiefung", "page": 21, "level": 1},
        ]
        inferred = infer_toc_hierarchy(raw_toc)
        self.assertEqual(len(inferred), 7)
        # Modul 1
        self.assertEqual(inferred[1]["level"], 1)
        # Kapitel 1 unter Modul 1
        self.assertEqual(inferred[2]["level"], 2)
        # 1.1 Unterkapitel
        self.assertEqual(inferred[3]["level"], 3)
        # 1.1.1 Unter-Unterkapitel
        self.assertEqual(inferred[4]["level"], 4)
        # Modul 2
        self.assertEqual(inferred[5]["level"], 1)
        # Kapitel 2
        self.assertEqual(inferred[6]["level"], 2)

    def test_infer_toc_hierarchy_no_jumping(self):
        """Stellt sicher, dass Hierarchiestufen niemals um mehr als 1 springen (PyMuPDF Anforderung)."""
        raw_toc = [
            {"title": "Kapitel 1", "page": 5, "level": 1},
            {"title": "1.1.1 Tiefes Unterkapitel", "page": 8, "level": 4},
        ]
        inferred = infer_toc_hierarchy(raw_toc)
        self.assertEqual(inferred[0]["level"], 1)
        # Level 4 darf nicht direkt nach Level 1 folgen, wird maximal auf 2 gekappt
        self.assertLessEqual(inferred[1]["level"], 2)

    def test_default_downloads_dir(self):
        """Prüft, ob der Standard-Download-Ordner existiert."""
        d_dir = Digi4SchoolService.get_default_downloads_dir()
        self.assertTrue(os.path.exists(d_dir))

    def test_encode_image_dct_is_jpeg_with_444_subsampling(self):
        """Prüft JPEG-Header und 4:4:4 Farbsampling (keine Farbfransen)."""
        img = Image.new("RGB", (64, 64), (255, 40, 10))
        data = encode_image_dct(img, quality=90, subsampling=0)
        self.assertGreater(len(data), 100)
        self.assertEqual(data[:2], b"\xff\xd8")
        self.assertEqual(data[-2:], b"\xff\xd9")
        self.assertEqual(_jpeg_sampling_factors(data), [0x11, 0x11, 0x11])

        # RGBA wird vor der JPEG-Kodierung sauber nach RGB konvertiert
        rgba = Image.new("RGBA", (16, 16), (10, 20, 30, 128))
        rgba_data = encode_image_dct(rgba, quality=80, subsampling=0)
        self.assertEqual(rgba_data[:2], b"\xff\xd8")

    def _create_test_pdf(self, path: str) -> None:
        """Erzeugt ein PDF mit Textschicht, TOC und unkomprimiertem Rauschbild."""
        noise = Image.frombytes("RGB", (700, 700), os.urandom(700 * 700 * 3))
        png_buf = io.BytesIO()
        noise.save(png_buf, format="PNG")

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "Unchanged Text Layer 123", fontsize=18)
        page.insert_image(fitz.Rect(72, 150, 522, 600), stream=png_buf.getvalue())
        doc.set_toc([[1, "Chapter 1", 1]])
        doc.save(path)
        doc.close()

    def test_compact_pdf_document_preserves_text_and_shrinks(self):
        """Kompaktiert ein PDF und prüft Dateigröße, Textschicht, TOC und Seitenzahl."""
        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(tmpdir, "compact_test.pdf")
            self._create_test_pdf(pdf_path)
            before_size = os.path.getsize(pdf_path)

            with fitz.open(pdf_path) as doc:
                before_text = doc[0].get_text()
                before_toc = doc.get_toc()
                before_pages = len(doc)

            result = compact_pdf_document(pdf_path, jpeg_quality=80)

            self.assertTrue(result["success"])
            self.assertEqual(result["pages"], before_pages)
            self.assertEqual(result["subsampling"], 0)
            self.assertGreater(result["images_replaced"], 0)
            self.assertLess(os.path.getsize(pdf_path), before_size * 0.9)

            with fitz.open(pdf_path) as doc:
                self.assertEqual(len(doc), before_pages)
                self.assertEqual(doc[0].get_text(), before_text)
                self.assertEqual(doc.get_toc(), before_toc)
                image_filters = [img[8] for img in doc[0].get_images(full=True)]
                self.assertIn("DCTDecode", image_filters)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_compact_pdf_document_keep_original(self):
        """Prüft, dass --keep-original die Originaldatei als *.orig.pdf erhält."""
        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(tmpdir, "keep_test.pdf")
            self._create_test_pdf(pdf_path)

            result = compact_pdf_document(pdf_path, jpeg_quality=85, keep_original=True)
            backup_path = os.path.join(tmpdir, "keep_test.orig.pdf")

            self.assertTrue(result["success"])
            self.assertTrue(os.path.isfile(pdf_path))
            self.assertTrue(os.path.isfile(backup_path))
            self.assertLess(os.path.getsize(pdf_path), os.path.getsize(backup_path))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_quality_and_effective_dpi(self):
        """Prüft Auflösungs-Presets und adaptive DPI-Kopplung."""
        quality_map = {"standard": 2.0, "high": 3.0, "ultra": 4.0}
        self.assertEqual(int(150 * quality_map["ultra"]), 600)
        self.assertEqual(int(150 * quality_map["standard"]), 300)
        self.assertEqual(int(150 * quality_map["high"]), 450)

    def test_download_book_signature(self):
        """Prüft, dass download_book alle neuen Ultra-HD, OCR- und Layout-Parameter unterstützt."""
        import inspect
        sig = inspect.signature(Digi4SchoolService.download_book)
        expected_params = [
            "email", "password", "code", "output_path", "pages",
            "scale", "quality", "jpeg_quality", "dpi", "psm", "lang", "timeout",
            "retries", "no_ocr", "no_toc", "page_offset", "visible",
            "tesseract_cmd", "progress_cb", "cancel_event"
        ]
        for p in expected_params:
            self.assertIn(p, sig.parameters)
        self.assertEqual(sig.parameters["scale"].default, 4.0)
        self.assertEqual(sig.parameters["page_offset"].default, "auto")


class TestDigi4SchoolCLI(unittest.TestCase):
    """Testet die CLI-Integration in `tasks books download`."""

    def test_cli_books_download_missing_target(self):
        """Prüft, dass ohne Zugangscode ein Fehler gemeldet wird."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = handle_books_command(["download", "--json"])
        self.assertEqual(ret, 1)
        data = json.loads(buf.getvalue())
        self.assertIn("error", data)
        self.assertIn("access code", data["error"].lower())

    def test_cli_books_download_missing_credentials(self):
        """Prüft, dass im Non-Interactive-Modus ohne E-Mail/Passwort ein klarer Fehler kommt."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = handle_books_command(["download", "26s7dbu5qxvw", "--json"])
        self.assertEqual(ret, 1)
        data = json.loads(buf.getvalue())
        self.assertIn("error", data)
        self.assertIn("email", data["error"].lower())

    def test_cli_books_download_parses_new_flags(self):
        """Prüft, dass neue CLI-Flags (--quality, --scale, --no-ocr, --no-toc, --page-offset) erkannt werden."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            # Without credentials in non-interactive, it parses flags and errors on missing email
            ret = handle_books_command([
                "download", "26s7dbu5qxvw",
                "--quality", "ultra",
                "--scale", "4.0",
                "--no-ocr",
                "--no-toc",
                "--page-offset", "2",
                "--json"
            ])
        self.assertEqual(ret, 1)
        data = json.loads(buf.getvalue())
        self.assertIn("error", data)
        self.assertIn("email", data["error"].lower())


class TestDigi4SchoolCompactCLI(unittest.TestCase):
    """Testet `tasks books compact`."""

    def test_cli_books_compact_single_file_json(self):
        """Kompaktiert eine konkrete PDF-Datei via CLI und liefert JSON-Statistik."""
        import io
        from contextlib import redirect_stdout

        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(tmpdir, "cli_compact.pdf")
            noise = Image.frombytes("RGB", (600, 600), os.urandom(600 * 600 * 3))
            png_buf = io.BytesIO()
            noise.save(png_buf, format="PNG")

            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), "CLI Compact Text 42", fontsize=18)
            page.insert_image(fitz.Rect(72, 150, 522, 600), stream=png_buf.getvalue())
            doc.save(pdf_path)
            doc.close()
            before_size = os.path.getsize(pdf_path)

            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = handle_books_command(
                    ["compact", pdf_path, "--quality", "85", "--keep-original", "--json"]
                )

            self.assertEqual(ret, 0)
            data = json.loads(buf.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["count"], 1)
            self.assertEqual(data["failed"], 0)
            result = data["results"][0]
            self.assertEqual(result["pages"], 1)
            self.assertEqual(result["jpeg_quality"], 85)
            self.assertEqual(result["subsampling"], 0)
            self.assertLess(result["new_size_mb"], result["original_size_mb"])
            self.assertTrue(os.path.isfile(os.path.join(tmpdir, "cli_compact.orig.pdf")))

            with fitz.open(pdf_path) as doc:
                self.assertEqual(doc[0].get_text().strip(), "CLI Compact Text 42")
            self.assertLess(os.path.getsize(pdf_path), before_size)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_cli_books_compact_invalid_quality(self):
        """Prüft die Validierung des Qualitätsbereichs 1-100."""
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = handle_books_command(["compact", "some.pdf", "--quality", "200", "--json"])
        self.assertEqual(ret, 1)
        data = json.loads(buf.getvalue())
        self.assertIn("quality", data["error"].lower())


    def test_compact_pdf_document_multicore(self):
        """Prüft die parallele Multi-Core Kompaktierung mit max_workers=2."""
        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(tmpdir, "multicore_test.pdf")
            doc = fitz.open()
            for i in range(3):
                p = doc.new_page(width=595, height=842)
                p.insert_text((72, 100), f"MultiCore Page Text {i}", fontsize=18)
                noise = Image.frombytes("RGB", (400, 400), os.urandom(400 * 400 * 3))
                png_buf = io.BytesIO()
                noise.save(png_buf, format="PNG")
                p.insert_image(fitz.Rect(72, 150, 472, 550), stream=png_buf.getvalue())
            doc.save(pdf_path)
            doc.close()
            before_size = os.path.getsize(pdf_path)

            res = compact_pdf_document(pdf_path, jpeg_quality=75, max_workers=2)

            self.assertTrue(res["success"])
            self.assertEqual(res["pages"], 3)
            self.assertEqual(res["workers"], 2)
            self.assertEqual(res["images_replaced"], 3)
            self.assertLess(os.path.getsize(pdf_path), before_size)

            with fitz.open(pdf_path) as check_doc:
                self.assertEqual(len(check_doc), 3)
                for idx in range(3):
                    self.assertIn(f"MultiCore Page Text {idx}", check_doc[idx].get_text())
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_cli_books_compact_workers_flag(self):
        """Prüft die Übergabe des --workers Flags über das CLI."""
        import io
        from contextlib import redirect_stdout

        tmpdir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(tmpdir, "cli_workers.pdf")
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), "CLI Workers Text 42", fontsize=18)
            noise = Image.frombytes("RGB", (400, 400), os.urandom(400 * 400 * 3))
            png_buf = io.BytesIO()
            noise.save(png_buf, format="PNG")
            page.insert_image(fitz.Rect(72, 150, 522, 600), stream=png_buf.getvalue())
            doc.save(pdf_path)
            doc.close()

            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = handle_books_command(["compact", pdf_path, "--workers", "2", "--json"])

            self.assertEqual(ret, 0)
            data = json.loads(buf.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["results"][0]["workers"], 2)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
