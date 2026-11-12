"""Malformed PDF glyphs must block a checked resume export."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from resumeforge.layout import Selection, Typesetter


class _Page:
    chars = []

    def __init__(self, extracted):
        self.extracted = extracted

    def extract_text(self):
        return self.extracted


class _Document:
    def __init__(self, extracted):
        self.pages = [_Page(extracted)]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class GlyphIntegrityTests(unittest.TestCase):
    def test_rejects_unmapped_cid_glyph(self):
        typesetter = Typesetter()
        selection = Selection([], [], 0, 0, True, [])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.pdf"
            path.write_bytes(b"placeholder")
            with patch("resumeforge.layout.pdfplumber.open",
                       return_value=_Document("Risk / (cid:11) ISO 27001")):
                result = typesetter.verify(path, selection, [])
        self.assertFalse(result["geometry_passed"])
        self.assertTrue(any("unmapped glyph" in issue for issue in result["issues"]))

    def test_rejects_control_characters(self):
        typesetter = Typesetter()
        selection = Selection([], [], 0, 0, True, [])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.pdf"
            path.write_bytes(b"placeholder")
            with patch("resumeforge.layout.pdfplumber.open",
                       return_value=_Document("Security log\x0b alert")):
                result = typesetter.verify(path, selection, [])
        self.assertFalse(result["geometry_passed"])


if __name__ == "__main__":
    unittest.main()
