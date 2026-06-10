import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import resolve_path_safe, get_temp_dir


class TestIntegrationBase(unittest.TestCase):
    def test_utils_import(self):
        import utils
        self.assertTrue(hasattr(utils, "parse_timestamp"))
        self.assertTrue(hasattr(utils, "format_timestamp"))
        self.assertTrue(hasattr(utils, "sanitize_unicode_for_pdf"))

    def test_transcript_parser_import(self):
        from transcript_parser import TranscriptParser
        p = TranscriptParser()
        self.assertIsNotNone(p)

    def test_frame_engine_import(self):
        from frame_engine import FrameCaptureEngine, FrameCaptureConfig, CapturedFrame
        self.assertIsNotNone(FrameCaptureEngine)
        self.assertIsNotNone(FrameCaptureConfig)
        self.assertIsNotNone(CapturedFrame)

    def test_pdf_builder_import(self):
        from pdf_builder import PdfBuilder
        self.assertIsNotNone(PdfBuilder)

    def test_font_manager_import(self):
        from font_manager import FontManager
        fm = FontManager()
        self.assertIsNotNone(fm)

    def test_project_manager_import(self):
        from project_manager import ProjectManager
        pm = ProjectManager()
        self.assertIsNotNone(pm)

    def test_path_resolution(self):
        path = resolve_path_safe("C:\\Users\\Test\\video.mp4")
        self.assertIsNotNone(path)

    def test_temp_dir_creation(self):
        d = get_temp_dir()
        self.assertTrue(os.path.isdir(d))

    def test_youtube_to_pdf_data_flow(self):
        from transcript_parser import TranscriptParser
        tp = TranscriptParser()
        text = """0:00
Introduction to BODMAS rule
0:05
First step is to solve brackets
0:10
Then of, then division, multiplication
0:15
Addition and subtraction at the end
0:20
Let's solve an example question now"""
        entries = tp.parse(text)
        self.assertGreater(len(entries), 0)
        self.assertEqual(tp.language, "en")
        from pdf_builder import PdfBuilder
        from font_manager import FontManager
        fm = FontManager()
        builder = PdfBuilder(fm)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 0, "caption": "Introduction",
                "tags": ["FORMULA"], "transcript_context": "Introduction to BODMAS rule",
                "content_score": 78, "frame_path": "",
            }
        ]
        metadata = {
            "video_path": "test.mp4", "duration_sec": 25,
            "language": "en", "subject": "BODMAS", "exam_target": "General",
            "total_screenshots": 1, "indic_scripts": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            ai_path = os.path.join(tmp, "ai_context.txt")
            result = builder.build_ai_context_txt(screenshots, metadata, ai_path)
            self.assertTrue(result)
            with open(ai_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("[SCREENSHOT_001]", content)
            self.assertIn("BODMAS", content)


if __name__ == "__main__":
    unittest.main()
