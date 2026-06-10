import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import (
    parse_timestamp, format_timestamp, format_timestamp_hms,
    sanitize_filename, sanitize_unicode_for_pdf, normalize_case,
    detect_language, detect_indic_scripts, calculate_tokens,
    get_temp_dir,
)


class TestTimeFunctions(unittest.TestCase):
    def test_parse_mmss(self):
        self.assertEqual(parse_timestamp("5:30"), 330)
        self.assertEqual(parse_timestamp("0:05"), 5)
        self.assertEqual(parse_timestamp("10:00"), 600)

    def test_parse_hmmss(self):
        self.assertEqual(parse_timestamp("1:05:30"), 3930)
        self.assertEqual(parse_timestamp("0:00:30"), 30)

    def test_parse_with_millis(self):
        self.assertEqual(parse_timestamp("5:30.500"), 330)
        self.assertEqual(parse_timestamp("5:30.5"), 330)

    def test_parse_bracket(self):
        self.assertEqual(parse_timestamp("[5:30]"), 330)
        self.assertEqual(parse_timestamp("[1:05:30]"), 3930)

    def test_parse_none(self):
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp("abc"))

    def test_parse_hindi_numerals(self):
        self.assertEqual(parse_timestamp("०:०५"), 5)
        self.assertEqual(parse_timestamp("१:३०"), 90)

    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(330), "05:30")
        self.assertEqual(format_timestamp(0), "00:00")
        self.assertEqual(format_timestamp(3661), "61:01")

    def test_format_timestamp_hms(self):
        self.assertEqual(format_timestamp_hms(3661), "01:01:01")
        self.assertEqual(format_timestamp_hms(0), "00:00:00")
        self.assertEqual(format_timestamp_hms(7384), "02:03:04")


class TestSanitization(unittest.TestCase):
    def test_sanitize_filename(self):
        safe = sanitize_filename("Hello: World? File.mp4")
        self.assertNotIn(":", safe)
        self.assertNotIn("?", safe)

    def test_sanitize_filename_empty(self):
        self.assertEqual(sanitize_filename(""), "untitled")
        self.assertEqual(sanitize_filename(None), "untitled")

    def test_sanitize_unicode_control_chars(self):
        result = sanitize_unicode_for_pdf("Hello\x00World\x01Test")
        self.assertNotIn("\x00", result)

    def test_sanitize_unicode_math_symbols(self):
        result = sanitize_unicode_for_pdf("√ ∫ ≈ integral")
        self.assertIn("sqrt", result)
        self.assertIn("integral", result)

    def test_sanitize_preserves_hindi(self):
        text = "नमस्ते दोस्तों"
        result = sanitize_unicode_for_pdf(text)
        self.assertIn("नमस्ते", result)

    def test_sanitize_zwj_preserved(self):
        text = "क्ष"  # uses ZWJ
        result = sanitize_unicode_for_pdf(text)
        self.assertIn("क्ष", result)

    def test_normalize_case_allcaps(self):
        result = normalize_case("HELLO WORLD THIS IS A TEST")
        self.assertFalse(result.isupper())

    def test_normalize_case_already_normal(self):
        result = normalize_case("Hello World")
        self.assertEqual(result, "Hello World")


class TestLanguageDetection(unittest.TestCase):
    def test_indic_scripts_hindi(self):
        scripts = detect_indic_scripts("नमस्ते दोस्तों")
        self.assertIn("devanagari", scripts)

    def test_indic_scripts_english(self):
        scripts = detect_indic_scripts("Hello world")
        self.assertEqual(len(scripts), 0)


class TestTokenCalculation(unittest.TestCase):
    def test_token_count(self):
        tokens = calculate_tokens("Hello world this is a test")
        self.assertGreater(tokens, 0)

    def test_empty_token_count(self):
        self.assertEqual(calculate_tokens(""), 0)
        self.assertEqual(calculate_tokens(None), 0)


class TestTempDir(unittest.TestCase):
    def test_get_temp_dir(self):
        d = get_temp_dir()
        self.assertTrue(os.path.isdir(d))
        self.assertIn("LectureSnapPDF", d)


if __name__ == "__main__":
    unittest.main()
