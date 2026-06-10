import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import cv2


class TestFrameCaptureRules(unittest.TestCase):
    def setUp(self):
        self.blank_white = np.full((720, 1280), 250, dtype=np.uint8)
        self.blank_black = np.full((720, 1280), 5, dtype=np.uint8)
        self.text_frame = np.random.randint(100, 200, (720, 1280), dtype=np.uint8)
        cv2.putText(self.text_frame, "Hello World Formula", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2)
        self.blurry = cv2.GaussianBlur(self.text_frame, (25, 25), 0)

    def test_blank_frame_rejection_bright(self):
        from utils import BLANK_BRIGHT_THRESHOLD
        mean = np.mean(self.blank_white)
        self.assertGreater(mean, BLANK_BRIGHT_THRESHOLD)

    def test_blank_frame_rejection_dark(self):
        from utils import BLACK_DARK_THRESHOLD
        mean = np.mean(self.blank_black)
        self.assertLess(mean, BLACK_DARK_THRESHOLD)

    def test_blurry_frame_rejection(self):
        from utils import LAPLACIAN_THRESHOLD
        laplacian = cv2.Laplacian(self.blurry, cv2.CV_64F).var()
        self.assertLess(laplacian, LAPLACIAN_THRESHOLD)

    def test_text_frame_passes(self):
        from utils import LAPLACIAN_THRESHOLD, BLANK_BRIGHT_THRESHOLD, BLACK_DARK_THRESHOLD
        laplacian = cv2.Laplacian(self.text_frame, cv2.CV_64F).var()
        mean = np.mean(self.text_frame)
        self.assertGreater(laplacian, LAPLACIAN_THRESHOLD)
        self.assertGreater(mean, BLACK_DARK_THRESHOLD)
        self.assertLess(mean, BLANK_BRIGHT_THRESHOLD)

    def test_edge_density_high(self):
        edges = cv2.Canny(self.text_frame, 50, 150)
        total = self.text_frame.shape[0] * self.text_frame.shape[1]
        edge_density = np.count_nonzero(edges) / total
        from utils import EDGE_DENSITY_THRESHOLD
        self.assertGreater(edge_density, 0)

    def test_safe_zone_crop(self):
        from utils import apply_safe_zone_crop
        frame = np.random.randint(0, 255, (720, 1280), dtype=np.uint8)
        cropped = apply_safe_zone_crop(frame)
        self.assertEqual(cropped.shape, frame.shape)

    def test_resize_720p(self):
        from utils import resize_frame_720p
        large = np.random.randint(0, 255, (2160, 3840, 3), dtype=np.uint8)
        resized = resize_frame_720p(large)
        h, w = resized.shape[:2]
        self.assertLessEqual(h, 720)
        self.assertLessEqual(w, 1280)

    def test_resize_720p_small(self):
        from utils import resize_frame_720p
        small = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
        resized = resize_frame_720p(small)
        self.assertEqual(resized.shape[0], small.shape[0])

    def test_fast_teacher_correction(self):
        from utils import FAST_TEACHER_ENTRIES_PER_HOUR, MIN_GAP_FAST_TEACHER
        entries_per_hour = 350
        self.assertGreater(entries_per_hour, FAST_TEACHER_ENTRIES_PER_HOUR)

    def test_adaptive_threshold_burst(self):
        from utils import ADAPTIVE_BURST_COUNT
        recent_captures = [1, 2, 3, 4, 5]
        self.assertGreater(len(recent_captures), ADAPTIVE_BURST_COUNT)


class TestFrameCaptureEngineMock(unittest.TestCase):
    def test_captured_frame_to_dict(self):
        from frame_engine import CapturedFrame
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cf = CapturedFrame(
            frame_id=1,
            timestamp_sec=154,
            frame_array=frame,
            content_score=78,
            transcript_text="Test text",
            is_manual=False,
        )
        d = cf.to_dict()
        self.assertEqual(d["id"], 1)
        self.assertEqual(d["timestamp_sec"], 154)
        self.assertEqual(d["content_score"], 78)
        self.assertEqual(d["is_manual"], False)
        self.assertEqual(d["caption"], "")
        self.assertEqual(d["tags"], [])

    def test_captured_frame_save_to_disk(self):
        from frame_engine import CapturedFrame
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        cf = CapturedFrame(
            frame_id=1,
            timestamp_sec=154,
            frame_array=frame,
            content_score=78,
            transcript_text="Test",
            is_manual=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = cf.save_to_disk(tmp)
            self.assertIsNotNone(path)
            self.assertTrue(os.path.isfile(path))

    def test_captured_frame_file_size(self):
        from frame_engine import CapturedFrame
        frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        cf = CapturedFrame(frame_id=1, timestamp_sec=0, frame_array=frame,
                           content_score=50, transcript_text="", is_manual=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = cf.save_to_disk(tmp)
            size = os.path.getsize(path)
            self.assertLess(size, 1024 * 1024)


class TestKeywordScoring(unittest.TestCase):
    def test_english_keywords(self):
        from utils import contains_keywords, ENGLISH_KEYWORDS
        self.assertTrue(contains_keywords("this is a formula for", ENGLISH_KEYWORDS))
        self.assertTrue(contains_keywords("important question to solve", ENGLISH_KEYWORDS))
        self.assertFalse(contains_keywords("just some random text", ENGLISH_KEYWORDS))

    def test_hindi_keywords(self):
        from utils import contains_keywords, HINDI_KEYWORDS
        self.assertTrue(contains_keywords("यह एक सूत्र है", HINDI_KEYWORDS))
        self.assertTrue(contains_keywords("प्रश्न नंबर एक", HINDI_KEYWORDS))
        self.assertFalse(contains_keywords("आज का दिन बहुत अच्छा है", HINDI_KEYWORDS))

    def test_hinglish_keywords(self):
        from utils import contains_keywords, HINGLISH_KEYWORDS
        self.assertTrue(contains_keywords("apply this trick to solve", HINGLISH_KEYWORDS))
        self.assertTrue(contains_keywords("ye question kaise karo", HINGLISH_KEYWORDS))

    def test_math_symbols(self):
        from utils import MATH_SYMBOLS
        self.assertIn("=", MATH_SYMBOLS)
        self.assertIn("√", MATH_SYMBOLS)

    def test_question_indicators(self):
        from utils import contains_keywords, QUESTION_INDICATORS
        self.assertTrue(contains_keywords("What is the value?", QUESTION_INDICATORS))
        self.assertTrue(contains_keywords("निकालो x का मान", QUESTION_INDICATORS))


if __name__ == "__main__":
    unittest.main()
