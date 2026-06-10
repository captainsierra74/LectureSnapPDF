import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import format_timestamp
from font_manager import FontManager


class TestPdfBuilderBasic(unittest.TestCase):
    def setUp(self):
        self.font_mgr = FontManager()

    def test_build_ai_context_txt(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 154, "caption": "BODMAS rule",
                "tags": ["FORMULA", "IMPORTANT"],
                "transcript_context": "तो यहां पर BODMAS का rule यह होता है",
                "content_score": 78, "frame_path": "",
            }
        ]
        metadata = {
            "video_path": "test.mp4", "duration_sec": 2732,
            "language": "hi-en", "subject": "Test", "exam_target": "General",
            "total_screenshots": 1, "indic_scripts": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test_ai_context.txt")
            result = builder.build_ai_context_txt(screenshots, metadata, path)
            self.assertTrue(result)
            self.assertTrue(os.path.isfile(path))
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("SCREENSHOT_001", content)
            self.assertIn("BODMAS", content)
            self.assertIn("LectureSnapPDF", content)

    def test_build_markdown(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 154, "caption": "BODMAS",
                "tags": ["FORMULA"], "transcript_context": "BODMAS rule",
                "content_score": 78, "frame_path": "",
            }
        ]
        metadata = {
            "video_path": "test.mp4", "duration_sec": 2732,
            "language": "en", "subject": "Test",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.md")
            result = builder.build_markdown(screenshots, metadata, path)
            self.assertTrue(result)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("## Screenshot 1", content)

    def test_build_json_export(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 154, "caption": "BODMAS",
                "tags": ["FORMULA"], "transcript_context": "rule",
                "content_score": 78, "frame_path": "frame.png", "pdf_page": 3,
            }
        ]
        metadata = {
            "video_path": "test.mp4", "duration_sec": 2732,
            "language": "en", "subject": "Test", "exam_target": "General",
            "total_screenshots": 1, "generated": "2024-01-15",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.json")
            result = builder.build_json_export(screenshots, metadata, [], [], path)
            self.assertTrue(result)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data["metadata"]["total_screenshots"], 1)
            self.assertEqual(len(data["screenshots"]), 1)

    def test_build_csv_index(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 154, "caption": "BODMAS",
                "tags": ["FORMULA"], "transcript_context": "rule",
                "content_score": 78, "pdf_page": 3, "frame_path": "",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.csv")
            result = builder.build_csv_index(screenshots, path)
            self.assertTrue(result)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("Screenshot_ID", content)
            self.assertIn("BODMAS", content)

    def test_build_transcript_clean(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        transcript = [
            {"start_sec": 0, "end_sec": 5, "text": "Hello world"},
            {"start_sec": 5, "end_sec": 10, "text": "Second line"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "transcript.txt")
            builder.build_transcript_clean(transcript, path)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("[00:00]", content)
            self.assertIn("Hello world", content)

    def test_build_gemini_text(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 154, "caption": "BODMAS",
                "tags": ["FORMULA"], "transcript_context": "rule",
                "content_score": 78, "frame_path": "",
            }
        ]
        metadata = {
            "video_path": "test.mp4", "duration_sec": 2732,
            "language": "en", "subject": "Test",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gemini.txt")
            builder.build_gemini_text(screenshots, metadata, path)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("INSTRUCTIONS FOR GEMINI", content)
            self.assertIn("SECTION_001", content)

    def test_build_which_file_to_use(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        with tempfile.TemporaryDirectory() as tmp:
            result = builder.build_which_file_to_use(tmp)
            self.assertTrue(result)
            path = os.path.join(tmp, "WHICH_FILE_TO_USE.txt")
            self.assertTrue(os.path.isfile(path))
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("Claude", content)
            self.assertIn("ChatGPT", content)
            self.assertIn("Gemini", content)

    def test_build_notebooklm_sources(self):
        from pdf_builder import PdfBuilder
        builder = PdfBuilder(self.font_mgr)
        screenshots = [
            {
                "id": 1, "timestamp_sec": 154, "caption": "BODMAS rule",
                "tags": ["FORMULA"], "transcript_context": "BODMAS rule",
                "content_score": 78, "frame_path": "",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            created = builder.build_notebooklm_sources(screenshots, tmp)
            self.assertEqual(len(created), 1)
            with open(created[0], 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("SOURCE: Screenshot 1", content)


if __name__ == "__main__":
    unittest.main()
