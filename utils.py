import os
import re
import sys
import logging
import tempfile
import unicodedata
import hashlib
from datetime import datetime

import numpy as np

try:
    from langdetect import detect, DetectorFactory, LangDetectException
    DetectorFactory.seed = 0
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False

LAPLACIAN_THRESHOLD = 80
BLANK_BRIGHT_THRESHOLD = 240
BLACK_DARK_THRESHOLD = 15
SSIM_THRESHOLD_DEFAULT = 0.87
SSIM_THRESHOLD_BURST = 0.93
EDGE_DENSITY_THRESHOLD = 0.08
SCORE_THRESHOLD_CAPTURE = 35
SCORE_OVERRIDE_GAP = 75
MIN_GAP_DEFAULT = 10
MIN_GAP_FAST_TEACHER = 18
FAST_TEACHER_ENTRIES_PER_HOUR = 300
ADAPTIVE_BURST_COUNT = 4
ADAPTIVE_BURST_DURATION = 30
MIN_CAPTURE_FLOOR = 3
SYNC_OFFSET_MIN = -60
SYNC_OFFSET_MAX = 60
CONTEXT_WINDOW_BEFORE = 8
CONTEXT_WINDOW_AFTER = 15
SILENCE_GAP_THRESHOLD = 15

HINGLISH_KEYWORDS = [
    "kese", "kaise", "trick", "shortcut", "solve", "karo", "batao",
    "answer", "root", "square", "divided by", "multiply", "plus",
    "minus", "barabar", "formula", "method", "question", "example",
    "find", "calculate", "value", "put", "step", "solution",
    "result", "check", "prove", "show", "rule", "sum", "total",
]

HINDI_KEYWORDS = [
    "सूत्र", "प्रश्न", "उदाहरण", "हल", "तरीका", "नियम",
    "निकालो", "बताइए", "कितना", "ज्ञात करो",
]

ENGLISH_KEYWORDS = [
    "formula", "question", "example", "trick", "shortcut",
    "solve", "method", "rule", "important", "find", "calculate",
]

MATH_SYMBOLS = set("=×÷%√²³")

QUESTION_INDICATORS = [
    "?", "find", "calculate", "निकालो", "बताइए", "कितना",
    "what is", "how many", "how much", "ज्ञात करो", "solve",
]

UNICODE_MATH_REPLACEMENTS = {
    '\u2200': 'for all',
    '\u2202': 'partial',
    '\u2203': 'there exists',
    '\u2204': 'not exists',
    '\u2205': 'empty set',
    '\u2206': 'Delta',
    '\u2207': 'nabla',
    '\u2208': 'element of',
    '\u2209': 'not element of',
    '\u2211': 'Sigma',
    '\u2212': '-',
    '\u2213': '-/+',
    '\u221a': 'sqrt',
    '\u221d': 'proportional to',
    '\u221e': 'infinity',
    '\u222b': 'integral',
    '\u222c': 'double integral',
    '\u222e': 'contour integral',
    '\u2234': 'therefore',
    '\u2235': 'because',
    '\u2248': 'approximately',
    '\u2260': 'not equal',
    '\u2261': 'equivalent to',
    '\u2264': '<=',
    '\u2265': '>=',
    '\u2282': 'subset of',
    '\u2283': 'superset of',
    '\u2286': 'subset or equal',
    '\u2287': 'superset or equal',
    '\u2295': 'direct sum',
    '\u2297': 'tensor product',
    '\u22c5': '.',
    '\u22c6': 'star',
    '\u2122': 'TM',
    '\u212b': 'Angstrom',
    '\u2103': 'C',
    '\u2109': 'F',
    '\u2111': 'Im',
    '\u2113': 'l',
    '\u2118': 'P',
    '\u211c': 'Re',
    '\u212f': 'e',
    '\u2135': 'alef',
    '\u2190': '<-',
    '\u2191': 'up',
    '\u2192': '->',
    '\u2193': 'down',
    '\u2194': '<->',
    '\u21d0': '<=',
    '\u21d2': '=>',
    '\u21d4': '<=>',
    '\u25a0': 'black square',
    '\u25b2': 'triangle',
    '\u25b6': 'play',
    '\u25c6': 'diamond',
    '\u25cb': 'circle',
    '\u2605': 'star',
    '\u2660': 'spade',
    '\u2663': 'club',
    '\u2665': 'heart',
    '\u2666': 'diamond',
}

DEVANAGARI_RANGE = range(0x0900, 0x0980)
BENGALI_RANGE = range(0x0980, 0x0A00)
GURMUKHI_RANGE = range(0x0A00, 0x0A80)
GUJARATI_RANGE = range(0x0A80, 0x0B00)
ORIYA_RANGE = range(0x0B00, 0x0B80)
TAMIL_RANGE = range(0x0B80, 0x0C00)
TELUGU_RANGE = range(0x0C00, 0x0C80)
KANNADA_RANGE = range(0x0C80, 0x0D00)
MALAYALAM_RANGE = range(0x0D00, 0x0D80)
LATIN_RANGE = range(0x0020, 0x007F)
LATIN_SUPPLEMENT_RANGE = range(0x0080, 0x0100)

INDIC_RANGES = {
    "devanagari": DEVANAGARI_RANGE,
    "bengali": BENGALI_RANGE,
    "gurmukhi": GURMUKHI_RANGE,
    "gujarati": GUJARATI_RANGE,
    "oriya": ORIYA_RANGE,
    "tamil": TAMIL_RANGE,
    "telugu": TELUGU_RANGE,
    "kannada": KANNADA_RANGE,
    "malayalam": MALAYALAM_RANGE,
}

_logger = None


def setup_logging():
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("LectureSnapPDF")
    logger.setLevel(logging.DEBUG)
    log_dir = get_temp_dir()
    log_path = os.path.join(log_dir, "capture_errors.log")
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    fh.setLevel(logging.WARNING)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    _logger = logger
    return logger


def get_error_log_path():
    return os.path.join(get_temp_dir(), "capture_errors.log")


def parse_timestamp(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip().replace('\u200e', '').replace('\u200f', '')
    s = s.replace(',', '.')
    s = s.replace('\u0966', '0').replace('\u0967', '1').replace('\u0968', '2')
    s = s.replace('\u0969', '3').replace('\u096a', '4').replace('\u096b', '5')
    s = s.replace('\u096c', '6').replace('\u096d', '7').replace('\u096e', '8').replace('\u096f', '9')
    s = re.sub(r'^\[|\]$', '', s)
    patterns = [
        r'^(\d+):(\d{1,2}):(\d{1,2})\.?(\d{0,3})$',
        r'^(\d+):(\d{1,2})\.?(\d{0,3})$',
        r'^(\d{1,2}):(\d{2})$',
        r'^(\d+)s$',
    ]
    for pat in patterns:
        m = re.match(pat, s)
        if m:
            groups = m.groups()
            if len(groups) == 4:
                h, mi, sec, ms = groups
                ms = ms.ljust(3, '0')[:3] if ms else '000'
                return int(h) * 3600 + int(mi) * 60 + int(sec) + int(ms) // 1000
            elif len(groups) == 3 and ':' in s:
                mi, sec, ms = groups
                ms = ms.ljust(3, '0')[:3] if ms else '000'
                return int(mi) * 60 + int(sec) + int(ms) // 1000
            elif len(groups) == 2:
                mi, sec = groups
                return int(mi) * 60 + int(sec)
            elif len(groups) == 1:
                return int(groups[0])
    return None


def format_timestamp(sec):
    if sec is None or sec < 0:
        return "00:00"
    sec = int(sec)
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


def format_timestamp_hms(sec):
    if sec is None or sec < 0:
        return "00:00:00"
    sec = int(sec)
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_timestamp_for_filename(sec):
    if sec is None or sec < 0:
        return "00m00s"
    sec = int(sec)
    m, s = divmod(sec, 60)
    return f"{m:02d}m{s:02d}s"


def sanitize_filename(name, max_length=200):
    if not name:
        return "untitled"
    name = unicodedata.normalize('NFKC', name)
    name = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', '_', name)
    name = re.sub(r'[^\w\s\.\-\(\)\[\]@#!\'%,~\u0080-\uffff]', '_', name)
    name = name.strip('._ ')
    if not name:
        name = "untitled"
    if len(name) > max_length:
        base, ext = os.path.splitext(name)
        ext = ext[:10]
        name = base[:max_length - len(ext) - 1] + ext
    return name


def sanitize_unicode_for_pdf(text, preserve_indic=True):
    if not text:
        return ""
    text = unicodedata.normalize('NFC', text)
    result = []
    for ch in text:
        cp = ord(ch)
        in_indic = False
        if preserve_indic:
            for r in INDIC_RANGES.values():
                if cp in r:
                    in_indic = True
                    break
        if in_indic or cp in LATIN_RANGE or cp in LATIN_SUPPLEMENT_RANGE:
            result.append(ch)
        elif cp in UNICODE_MATH_REPLACEMENTS:
            result.append(UNICODE_MATH_REPLACEMENTS[cp])
        elif cp in (0x200B, 0x200C, 0x200D, 0xFEFF):
            continue
        elif cp < 0x20 and cp not in (0x0009, 0x000a, 0x000d):
            continue
        elif cp in range(0x7f, 0xa0):
            continue
        elif cp in range(0x2000, 0x2070):
            result.append(ch)
        elif cp in range(0x20A0, 0x20D0):
            result.append(ch)
        elif cp in range(0x2100, 0x2300):
            result.append(UNICODE_MATH_REPLACEMENTS.get(ch, ' '))
        elif cp == 0x00a0:
            result.append(' ')
        elif cp in (0x000a, 0x000d, 0x0009):
            result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def detect_indic_scripts(text):
    found = set()
    for ch in text:
        cp = ord(ch)
        for name, r in INDIC_RANGES.items():
            if cp in r:
                found.add(name)
    return found


def normalize_case(text):
    if not text:
        return ""
    text = text.strip()
    if not text:
        return ""
    upper_count = sum(1 for c in text if c.isupper())
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha > 0 and upper_count / total_alpha > 0.8:
        lines = text.split('\n')
        processed = []
        for line in lines:
            line = line.strip()
            if not line:
                processed.append('')
                continue
            lower_line = line.lower()
            lower_line = lower_line[0].upper() + lower_line[1:] if lower_line else lower_line
            processed.append(lower_line)
        return '\n'.join(processed)
    lower_count = sum(1 for c in text if c.islower())
    if total_alpha > 0 and lower_count / total_alpha > 0.8:
        lines = text.split('\n')
        processed = []
        for line in lines:
            line = line.strip()
            if not line:
                processed.append('')
                continue
            processed.append(line[0].upper() + line[1:] if line else line)
        return '\n'.join(processed)
    return text


def detect_language(lines):
    if not _LANGDETECT_AVAILABLE or not lines:
        return "unknown"
    sample = ' '.join(lines[:20])
    if not sample.strip():
        return "unknown"
    try:
        lang = detect(sample)
        indic_scripts = detect_indic_scripts(sample)
        if len(indic_scripts) > 0:
            if lang == 'en':
                return "hi-en"
            return "hi"
        if lang in ('hi', 'mr', 'ne'):
            return "hi"
        if lang == 'en':
            return "en"
        return lang
    except LangDetectException:
        return "unknown"


def is_hinglish_word(word):
    return word.lower().strip() in HINGLISH_KEYWORDS


def contains_keywords(text, keyword_list):
    if not text:
        return False
    lower_text = text.lower()
    for kw in keyword_list:
        if kw in lower_text:
            return True
    return False


def resolve_path_safe(path):
    if not path:
        return path
    if sys.platform == "win32":
        path = os.path.abspath(path)
        if any(ord(c) > 127 for c in path):
            try:
                decoded = path.encode('utf-8').decode('utf-8')
                return decoded
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return path


def calculate_tokens(text):
    if not text:
        return 0
    return len(text) // 4 + len(re.findall(r'\s+', text))


def get_temp_dir():
    base = os.path.join(tempfile.gettempdir(), "LectureSnapPDF")
    os.makedirs(base, exist_ok=True)
    return base


def get_session_temp_dir(session_id=None):
    if session_id is None:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(get_temp_dir(), f"session_{session_id}")
    os.makedirs(path, exist_ok=True)
    return path


def generate_session_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def apply_safe_zone_crop(frame, config=None):
    if config is None:
        config = {"crop_bottom_pct": 15, "crop_corner_pct": 20}
    h, w = frame.shape[:2]
    safe = frame.copy()
    crop_bottom = int(h * config.get("crop_bottom_pct", 15) / 100)
    crop_corner = int(w * config.get("crop_corner_pct", 20) / 100)
    if crop_bottom > 0:
        safe[h - crop_bottom:, :] = 128
    if crop_corner > 0 and crop_bottom > 0:
        safe[h - crop_bottom:, :crop_corner] = 128
        safe[h - crop_bottom:, w - crop_corner:] = 128
    return safe


def resize_frame_720p(frame):
    h, w = frame.shape[:2]
    if w > 1280 or h > 720:
        scale = min(1280.0 / w, 720.0 / h, 1.0)
        if scale < 1.0:
            new_w, new_h = int(w * scale), int(h * scale)
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return frame


def log_capture_error(timestamp_sec, message):
    logger = setup_logging()
    logger.warning("Timestamp %s: %s", format_timestamp(timestamp_sec), message)


try:
    import cv2
except ImportError:
    cv2 = None
