import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from transcript_parser import TranscriptParser


class TestTranscriptParserYoutube(unittest.TestCase):
    def setUp(self):
        self.parser = TranscriptParser()

    def test_youtube_simple_format(self):
        text = """0:00
है तो दोस्तों सिंपलीफिकेशन
0:05
लगता है कि सबसे छोटा टॉपिक है
0:10
वह गलतफहमी दूर करने वाला हूं"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["start_sec"], 0)
        self.assertEqual(entries[1]["start_sec"], 5)
        self.assertEqual(entries[2]["start_sec"], 10)
        self.assertIn("सिंपलीफिकेशन", entries[0]["text"])

    def test_youtube_with_hours(self):
        text = """0:00:00
Introduction
1:05:30
Main topic starts"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[2]["start_sec"], 3930)
        self.assertEqual(entries[1]["text"], "[Silence / Solving Time]")

    def test_youtube_empty_text(self):
        text = """0:00
0:05"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 0)


class TestTranscriptParserSRT(unittest.TestCase):
    def setUp(self):
        self.parser = TranscriptParser()

    def test_srt_simple(self):
        text = """1
00:00:05,000 --> 00:00:08,000
है तो दोस्तों सिंपलीफिकेशन

2
00:00:08,500 --> 00:00:12,000
लगता है कि सबसे छोटा टॉपिक"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["start_sec"], 5)
        self.assertEqual(entries[0]["end_sec"], 8)

    def test_srt_with_html_tags(self):
        text = """1
00:00:01,000 --> 00:00:04,000
<i>Italic text</i> and <b>bold</b>"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 1)
        self.assertNotIn("<i>", entries[0]["text"])


class TestTranscriptParserVTT(unittest.TestCase):
    def setUp(self):
        self.parser = TranscriptParser()

    def test_vtt_simple(self):
        text = """WEBVTT

00:00.000 --> 00:05.000
है तो दोस्तों

00:05.000 --> 00:10.000
सिंपलीफिकेशन जो आपको"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["start_sec"], 0)
        self.assertEqual(entries[1]["start_sec"], 5)

    def test_vtt_no_header(self):
        text = """00:00.000 --> 00:05.000
Hello world"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["start_sec"], 0)


class TestTranscriptParserBracket(unittest.TestCase):
    def setUp(self):
        self.parser = TranscriptParser()

    def test_bracket_simple(self):
        text = """[0:05] है तो दोस्तों सिंपलीफिकेशन
[0:10] लगता है कि सबसे छोटा"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["start_sec"], 5)

    def test_bracket_parenthesis(self):
        text = """(0:05) है तो दोस्तों
(0:10) लगता है कि"""
        entries = self.parser.parse(text)
        self.assertEqual(len(entries), 2)


class TestTranscriptPostProcessing(unittest.TestCase):
    def setUp(self):
        self.parser = TranscriptParser()

    def test_merge_short_fragments(self):
        text = """0:00
Hello
0:01
world
0:02
this is
0:05
a test"""
        entries = self.parser.parse(text)
        self.assertGreaterEqual(len(entries), 1)
        merged = " ".join(e["text"] for e in entries)
        self.assertIn("Hello", merged)
        self.assertIn("world", merged)

    def test_deduplicate_consecutive(self):
        text = """0:00
Same line
0:05
Same line
0:10
Different line"""
        entries = self.parser.parse(text)
        found_same = sum(1 for e in entries if "Same line" in e["text"])
        self.assertLessEqual(found_same, 2)

    def test_silence_gap_insertion(self):
        text = """0:00
First line
0:30
Second line after silence"""
        entries = self.parser.parse(text)
        silence_entries = [e for e in entries if e.get("is_silence")]
        self.assertGreaterEqual(len(silence_entries), 1)

    def test_all_caps_normalization(self):
        text = """0:00
HELLO WORLD THIS IS A TEST
0:05
ANOTHER LINE HERE"""
        entries = self.parser.parse(text)
        for e in entries:
            self.assertFalse(e["text"].isupper())

    def test_empty_file(self):
        entries = self.parser.parse("")
        self.assertEqual(len(entries), 0)

    def test_no_valid_format(self):
        entries = self.parser.parse("This is just some random text\nwithout timestamps")
        self.assertEqual(len(entries), 0)


class TestTranscriptLanguageDetection(unittest.TestCase):
    def setUp(self):
        self.parser = TranscriptParser()

    def test_hindi_detection(self):
        text = """0:00
नमस्ते दोस्तों आज हम सीखेंगे
0:05
गणित का एक बहुत ही आसान सवाल"""
        self.parser.parse(text)
        self.assertIn(self.parser.language, ["hi", "hi-en"])

    def test_english_detection(self):
        text = """0:00
Hello friends today we will learn
0:05
mathematics in a very simple way"""
        self.parser.parse(text)
        self.assertEqual(self.parser.language, "en")


if __name__ == "__main__":
    unittest.main()
