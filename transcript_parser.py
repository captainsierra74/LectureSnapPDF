import re
import os
import codecs

from utils import (
    parse_timestamp, format_timestamp, normalize_case, detect_language,
    detect_indic_scripts, contains_keywords, HINGLISH_KEYWORDS,
    HINDI_KEYWORDS, ENGLISH_KEYWORDS, MATH_SYMBOLS, QUESTION_INDICATORS,
    SILENCE_GAP_THRESHOLD, setup_logging
)


class TranscriptParser:
    FORMAT_YOUTUBE = "youtube_copypaste"
    FORMAT_SRT = "srt"
    FORMAT_VTT = "vtt"
    FORMAT_BRACKET = "bracket"
    FORMAT_NONE = "none"

    def __init__(self):
        self.format = None
        self.language = "unknown"
        self.indic_scripts = set()
        self.entries_per_hour = 0
        self.total_duration_sec = 0
        self.raw_lines = []
        self.logger = setup_logging()

    def parse(self, filepath_or_text, video_duration_sec=None):
        raw_text, is_file = self._read_input(filepath_or_text)
        if raw_text is None:
            return []
        self.raw_lines = raw_text.split('\n')
        entries, self.format = self._detect_and_parse(raw_text)
        if not entries:
            return []
        entries = self._post_process(entries)
        self._compute_metadata(entries, video_duration_sec)
        return entries

    def _read_input(self, source):
        if not source:
            return None, False
        if os.path.isfile(source):
            try:
                with open(source, 'rb') as f:
                    raw = f.read()
                if raw.startswith(codecs.BOM_UTF8):
                    raw = raw[len(codecs.BOM_UTF8):]
                for enc in ('utf-8', 'utf-16le', 'utf-16be', 'latin-1', 'cp1252'):
                    try:
                        text = raw.decode(enc)
                        return text, True
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                return raw.decode('utf-8', errors='replace'), True
            except (IOError, OSError) as e:
                self.logger.error("Failed to read transcript file: %s", e)
                return None, False
        else:
            return source, False

    def _detect_and_parse(self, text):
        lines = text.split('\n')
        stripped = [l.strip() for l in lines]
        non_empty = [l for l in stripped if l]

        if not non_empty:
            return [], self.FORMAT_NONE

        first_lines = non_empty[:min(10, len(non_empty))]
        first_text = '\n'.join(first_lines)

        if self._looks_like_srt(first_lines, first_text):
            return self._parse_srt(text), self.FORMAT_SRT

        if self._looks_like_vtt(first_text):
            return self._parse_vtt(text), self.FORMAT_VTT

        if self._looks_like_bracket(first_lines):
            return self._parse_bracket(text), self.FORMAT_BRACKET

        if self._looks_like_youtube(non_empty):
            return self._parse_youtube(text), self.FORMAT_YOUTUBE

        return [], self.FORMAT_NONE

    def _looks_like_srt(self, first_lines, first_text):
        if '-->' in first_text:
            return True
        if len(first_lines) >= 2:
            if first_lines[0].isdigit() and '-->' in first_lines[1]:
                return True
        return False

    def _looks_like_vtt(self, first_text):
        if first_text.strip().upper().startswith('WEBVTT'):
            return True
        if '-->' in first_text and 'WEBVTT' not in first_text:
            return False
        return False

    def _looks_like_bracket(self, first_lines):
        bracket_count = 0
        for line in first_lines[:10]:
            if re.match(r'^\[\d+:\d{2}', line):
                bracket_count += 1
            elif re.match(r'^\(\d+:\d{2}\)', line):
                bracket_count += 1
        return bracket_count >= 2

    def _looks_like_youtube(self, non_empty_lines):
        ts_count = 0
        non_ts_count = 0
        for line in non_empty_lines[:30]:
            if re.match(r'^\d+:\d{2}', line) or re.match(r'^\d+:\d{2}:\d{2}', line):
                ts_count += 1
            else:
                non_ts_count += 1
        return ts_count >= 2 and non_ts_count >= ts_count * 0.3

    def _parse_srt(self, text):
        entries = []
        blocks = re.split(r'\n\s*\n', text.strip())
        for block in blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) < 2:
                continue
            time_line = None
            text_start = 1
            if lines[0].isdigit():
                if len(lines) >= 2:
                    time_line = lines[1]
                    text_start = 2
            else:
                time_line = lines[0]
                text_start = 1
            if not time_line or '-->' not in time_line:
                continue
            parts = time_line.split('-->')
            if len(parts) != 2:
                continue
            start = self._parse_srt_vtt_time(parts[0].strip())
            end = self._parse_srt_vtt_time(parts[1].strip())
            if start is None or end is None:
                continue
            text = ' '.join(lines[text_start:])
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if text:
                entries.append({
                    "start_sec": start,
                    "end_sec": end,
                    "text": text
                })
        return entries

    def _parse_vtt(self, text):
        entries = []
        text = re.sub(r'^WEBVTT.*?\n', '', text, flags=re.DOTALL)
        text = re.sub(r'^(STYLE|REGION|NOTE).*?(?=\n\S|\Z)', '', text, flags=re.DOTALL)
        blocks = re.split(r'\n\s*\n', text.strip())
        for block in blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if not lines:
                continue
            time_line = None
            text_start = 0
            for i, line in enumerate(lines):
                if '-->' in line:
                    time_line = line
                    text_start = i + 1
                    break
            if not time_line:
                continue
            parts = time_line.split('-->')
            if len(parts) < 2:
                continue
            start = self._parse_srt_vtt_time(parts[0].strip())
            end = self._parse_srt_vtt_time(parts[1].strip().split()[0])
            if start is None or end is None:
                continue
            text = ' '.join(lines[text_start:])
            text = re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if text:
                entries.append({
                    "start_sec": start,
                    "end_sec": end,
                    "text": text
                })
        return entries

    def _parse_srt_vtt_time(self, ts):
        ts = ts.replace(',', '.').strip()
        m = re.match(r'(?:(\d+):)?(\d{1,2}):(\d{2})\.?(\d{0,3})?', ts)
        if m:
            h = int(m.group(1)) if m.group(1) else 0
            mi = int(m.group(2))
            s = int(m.group(3))
            ms = m.group(4)
            ms = int(ms.ljust(3, '0')[:3]) if ms else 0
            return h * 3600 + mi * 60 + s + ms / 1000
        return None

    def _parse_bracket(self, text):
        entries = []
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^[\(\[](\d+:\d{2}(?::\d{2})?(?:\.\d+)?)[\)\]]\s*(.*)', line)
            if m:
                ts = parse_timestamp(m.group(1))
                text_content = m.group(2).strip()
                if ts is not None and text_content:
                    entries.append({
                        "start_sec": ts,
                        "end_sec": ts + 5,
                        "text": text_content
                    })
        return entries

    def _parse_youtube(self, text):
        entries = []
        lines = text.split('\n')
        current_text = []
        current_ts = None
        i = 0
        while i < len(lines):
            line = lines[i].rstrip('\r').strip()
            if not line:
                if current_ts is not None and current_text:
                    self._flush_youtube_entry(entries, current_ts, current_text)
                    current_ts = None
                    current_text = []
                i += 1
                continue
            ts = self._match_youtube_timestamp(line)
            if ts is not None:
                if current_ts is not None and current_text:
                    self._flush_youtube_entry(entries, current_ts, current_text)
                current_ts = ts
                current_text = []
            else:
                if current_ts is not None:
                    current_text.append(line)
            i += 1
        if current_ts is not None and current_text:
            self._flush_youtube_entry(entries, current_ts, current_text)
        if not entries:
            return self._parse_bracket(text)
        return entries

    def _match_youtube_timestamp(self, line):
        m = re.match(r'^(\d+:\d{2}(?::\d{2})?)$', line)
        if m:
            return parse_timestamp(m.group(1))
        return None

    def _flush_youtube_entry(self, entries, ts, text_lines):
        text = ' '.join(text_lines).strip()
        text = re.sub(r'\s+', ' ', text)
        if text:
            entries.append({
                "start_sec": ts,
                "end_sec": ts + 10,
                "text": text
            })

    def _post_process(self, entries):
        if not entries:
            return entries
        entries = self._deduplicate_consecutive(entries)
        entries = self._merge_short_fragments(entries)
        entries = self._merge_mid_sentence(entries)
        entries = self._insert_silence_gaps(entries)
        entries = self._assign_end_times(entries)
        for e in entries:
            e["text"] = normalize_case(e["text"])
        self._raw_entries = entries
        return entries

    def _deduplicate_consecutive(self, entries):
        if not entries:
            return []
        result = [entries[0]]
        for e in entries[1:]:
            if e["text"] == result[-1]["text"]:
                result[-1]["end_sec"] = e["end_sec"]
            else:
                result.append(e)
        return result

    def _merge_short_fragments(self, entries):
        if not entries:
            return []
        result = [dict(entries[0])]
        for e in entries[1:]:
            prev = result[-1]
            merged_duration = (e["end_sec"] - prev["start_sec"])
            if merged_duration <= 3:
                prev["text"] = prev["text"] + " " + e["text"]
                prev["text"] = re.sub(r'\s+', ' ', prev["text"]).strip()
                prev["end_sec"] = e["end_sec"]
            else:
                result.append(dict(e))
        return result

    def _merge_mid_sentence(self, entries):
        if not entries:
            return []
        result = [dict(entries[0])]
        for e in entries[1:]:
            prev = result[-1]
            prev_text = prev["text"].rstrip()
            curr_text = e["text"].lstrip()
            ends_without_punct = prev_text and prev_text[-1] not in '.!?।॥'
            starts_lower = curr_text and curr_text[0].islower()
            if ends_without_punct and starts_lower:
                prev["text"] = prev["text"] + " " + e["text"]
                prev["text"] = re.sub(r'\s+', ' ', prev["text"]).strip()
                prev["end_sec"] = e["end_sec"]
            else:
                result.append(dict(e))
        return result

    def _insert_silence_gaps(self, entries):
        if not entries:
            return []
        result = []
        for i, e in enumerate(entries):
            if i > 0:
                prev = entries[i - 1]
                gap = e["start_sec"] - prev["end_sec"]
                if gap > SILENCE_GAP_THRESHOLD:
                    silence_start = prev["end_sec"]
                    silence_end = e["start_sec"]
                    result.append({
                        "start_sec": silence_start,
                        "end_sec": silence_end,
                        "text": "[Silence / Solving Time]",
                        "is_silence": True
                    })
            result.append(dict(e))
        return result

    def _assign_end_times(self, entries):
        if not entries:
            return []
        for i in range(len(entries) - 1):
            if entries[i].get("end_sec", 0) >= entries[i + 1]["start_sec"]:
                entries[i]["end_sec"] = entries[i + 1]["start_sec"] - 0.5
        for e in entries:
            if e.get("end_sec", 0) <= e["start_sec"]:
                e["end_sec"] = e["start_sec"] + 5
        return entries

    def _compute_metadata(self, entries, video_duration_sec):
        if not entries:
            return
        sample_text = ' '.join(e["text"] for e in entries[:20])
        self.language = detect_language([e["text"] for e in entries[:20]])
        self.indic_scripts = detect_indic_scripts(sample_text)
        if entries:
            self.total_duration_sec = int(entries[-1]["end_sec"] - entries[0]["start_sec"])
        if video_duration_sec and video_duration_sec > 0:
            num_entries = len(entries)
            hours = video_duration_sec / 3600
            self.entries_per_hour = int(num_entries / hours) if hours > 0 else 0

    def get_metadata(self):
        return {
            "format": self.format,
            "language": self.language,
            "indic_scripts": list(self.indic_scripts),
            "entries_per_hour": self.entries_per_hour,
            "total_duration_sec": self.total_duration_sec,
            "entry_count": len(self._raw_entries) if hasattr(self, '_raw_entries') else 0,
        }

    def get_context_window(self, entries, timestamp_sec):
        if not entries:
            return ""
        from utils import CONTEXT_WINDOW_BEFORE, CONTEXT_WINDOW_AFTER
        start = timestamp_sec - CONTEXT_WINDOW_BEFORE
        end = timestamp_sec + CONTEXT_WINDOW_AFTER
        context_lines = []
        for e in entries:
            if e["start_sec"] >= start and e["start_sec"] <= end:
                context_lines.append(e["text"])
            elif e["end_sec"] >= start and e["start_sec"] <= end:
                context_lines.append(e["text"])
        return ' '.join(context_lines)

    def find_closest_entry(self, entries, timestamp_sec):
        if not entries:
            return None
        closest = None
        min_diff = float('inf')
        for e in entries:
            diff = abs(e["start_sec"] - timestamp_sec)
            if diff < min_diff:
                min_diff = diff
                closest = e
        return closest
