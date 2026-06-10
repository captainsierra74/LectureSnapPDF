import os
import json
import csv
import math
import io
from datetime import datetime
from collections import OrderedDict

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch, cm, mm
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether, Frame, PageTemplate, BaseDocTemplate,
    ListFlowable, ListItem
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.flowables import Flowable

from PIL import Image as PILImage

from utils import (
    setup_logging, sanitize_unicode_for_pdf, format_timestamp,
    format_timestamp_hms, format_timestamp_for_filename,
    sanitize_filename, contains_keywords, ENGLISH_KEYWORDS,
    HINDI_KEYWORDS, HINGLISH_KEYWORDS, MATH_SYMBOLS, QUESTION_INDICATORS,
    calculate_tokens,
)
from font_manager import FontManager


TAG_COLORS = {
    "QUESTION": HexColor("#2196F3"),
    "FORMULA": HexColor("#FF9800"),
    "TRICK": HexColor("#4CAF50"),
    "IMPORTANT": HexColor("#F44336"),
    "EXAMPLE": HexColor("#9C27B0"),
    "DIAGRAM": HexColor("#009688"),
    "DEFAULT": HexColor("#757575"),
}

TAG_BG_COLORS = {
    "QUESTION": HexColor("#E3F2FD"),
    "FORMULA": HexColor("#FFF3E0"),
    "TRICK": HexColor("#E8F5E9"),
    "IMPORTANT": HexColor("#FFEBEE"),
    "EXAMPLE": HexColor("#F3E5F5"),
    "DIAGRAM": HexColor("#E0F2F1"),
    "DEFAULT": HexColor("#F5F5F5"),
}


class TagBadge(Flowable):
    def __init__(self, text, tag_type="DEFAULT", font_name="Helvetica", font_size=8):
        super().__init__()
        self.text = text
        self.tag_type = tag_type.upper() if tag_type.upper() in TAG_COLORS else "DEFAULT"
        self.font_name = font_name
        self.font_size = font_size
        self.bg_color = TAG_BG_COLORS.get(self.tag_type, TAG_BG_COLORS["DEFAULT"])
        self.text_color = TAG_COLORS.get(self.tag_type, TAG_COLORS["DEFAULT"])
        self.padding = 4
        self.border_radius = 3
        text_width = pdfmetrics.stringWidth(text, font_name, font_size)
        self.width = text_width + self.padding * 2 + 4
        self.height = font_size + self.padding * 2

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg_color)
        c.roundRect(0, 0, self.width, self.height, self.border_radius, fill=1, stroke=0)
        c.setFillColor(self.text_color)
        c.setFont(self.font_name, self.font_size)
        c.drawString(self.padding + 2, self.padding, self.text)


class PdfBuilder:
    def __init__(self, font_manager=None):
        self.font_manager = font_manager or FontManager()
        self.logger = setup_logging()
        self._registered_fonts = {}
        self._latin_font = "Helvetica"
        self._devanagari_font = "Helvetica"

    def _register_fonts(self, scripts=None):
        if scripts is None:
            scripts = ["latin"]
        try:
            latin_path = self.font_manager.get_font_path("NotoSans-Regular")
            if latin_path and os.path.isfile(latin_path):
                pdfmetrics.registerFont(TTFont("NotoSans", latin_path))
                self._latin_font = "NotoSans"
            bold_path = self.font_manager.get_font_path("NotoSans-Bold")
            if bold_path and os.path.isfile(bold_path):
                pdfmetrics.registerFont(TTFont("NotoSans-Bold", bold_path))
            dev_path = self.font_manager.get_font_path("NotoSansDevanagari-Regular")
            if dev_path and os.path.isfile(dev_path):
                pdfmetrics.registerFont(TTFont("NotoSansDevanagari", dev_path))
                self._devanagari_font = "NotoSansDevanagari"
            dev_bold = self.font_manager.get_font_path("NotoSansDevanagari-Bold")
            if dev_bold and os.path.isfile(dev_bold):
                pdfmetrics.registerFont(TTFont("NotoSansDevanagari-Bold", dev_bold))
            for script in scripts:
                if script and script not in ("latin", "devanagari"):
                    key = f"NotoSans{script.capitalize()}-Regular"
                    path = self.font_manager.get_font_path(key)
                    if path and os.path.isfile(path):
                        pdfmetrics.registerFont(TTFont(f"NotoSans{script.capitalize()}", path))
        except Exception as e:
            self.logger.warning("Font registration error: %s", e)

    def _safe_text(self, text):
        return sanitize_unicode_for_pdf(text)

    def _mixed_para(self, text, style_name="Normal", style_overrides=None):
        safe = self._safe_text(text)
        styles = getSampleStyleSheet()
        base_style = styles[style_name] if style_name in styles else styles["Normal"]
        if style_overrides:
            for k, v in style_overrides.items():
                setattr(base_style, k, v)
        return Paragraph(safe, base_style)

    def _build_styles(self):
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            "CoverTitle", parent=styles["Title"],
            fontSize=28, leading=34, spaceAfter=20,
            textColor=HexColor("#1a237e"), alignment=TA_CENTER,
        ))
        styles.add(ParagraphStyle(
            "CoverSubtitle", parent=styles["Normal"],
            fontSize=14, leading=18, spaceAfter=8,
            textColor=HexColor("#455a64"), alignment=TA_CENTER,
            fontName=transcript_font,
        ))
        styles.add(ParagraphStyle(
            "TimestampLabel", parent=styles["Normal"],
            fontSize=9, leading=11, textColor=HexColor("#9e9e9e"),
            spaceBefore=4, spaceAfter=4,
        ))
        transcript_font = getattr(self, "_devanagari_font", None) or self._latin_font
        styles.add(ParagraphStyle(
            "TranscriptBox", parent=styles["Normal"],
            fontSize=10, leading=14, leftIndent=10, rightIndent=10,
            spaceBefore=6, spaceAfter=6,
            backColor=HexColor("#f5f5f5"),
            borderColor=HexColor("#e0e0e0"), borderWidth=1,
            borderPadding=8, fontName=transcript_font,
        ))
        styles.add(ParagraphStyle(
            "CaptionText", parent=styles["Normal"],
            fontSize=14, leading=18, spaceBefore=8, spaceAfter=8,
            textColor=HexColor("#212121"),
            fontName=transcript_font,
        ))
        styles.add(ParagraphStyle(
            "IndexHeader", parent=styles["Normal"],
            fontSize=10, leading=12, fontName=self._latin_font,
            textColor=black,
        ))
        styles.add(ParagraphStyle(
            "IndexCell", parent=styles["Normal"],
            fontSize=8, leading=10, fontName=self._latin_font,
        ))
        styles.add(ParagraphStyle(
            "PageNumber", parent=styles["Normal"],
            fontSize=8, leading=10, textColor=HexColor("#bdbdbd"),
            alignment=TA_RIGHT,
        ))
        return styles

    def _cover_page(self, styles, metadata):
        elements = []
        elements.append(Spacer(1, 2 * inch))
        elements.append(Paragraph("LectureSnapPDF", styles["CoverTitle"]))
        elements.append(Spacer(1, 0.3 * inch))
        video_name = os.path.basename(metadata.get("video_path", ""))
        if metadata.get("subject"):
            elements.append(Paragraph(
                self._safe_text(metadata["subject"]), styles["CoverSubtitle"]
            ))
        elements.append(Paragraph(
            self._safe_text(video_name), styles["CoverSubtitle"]
        ))
        elements.append(Spacer(1, 0.5 * inch))
        stats = [
            f"Date: {metadata.get('generated', datetime.now().strftime('%Y-%m-%d'))}",
            f"Screenshots: {metadata.get('total_screenshots', 0)}",
            f"Duration: {format_timestamp_hms(metadata.get('duration_sec', 0))}",
            f"Language: {metadata.get('language', 'unknown')}",
            f"Exam Target: {metadata.get('exam_target', 'General')}",
        ]
        for s in stats:
            elements.append(Paragraph(s, styles["CoverSubtitle"]))
        elements.append(Spacer(1, 1 * inch))
        elements.append(Paragraph(
            "Generated by LectureSnapPDF — Study Tool for Competitive Exams",
            ParagraphStyle("Footer", parent=styles["Normal"],
                           fontSize=9, textColor=HexColor("#9e9e9e"),
                           alignment=TA_CENTER)
        ))
        elements.append(PageBreak())
        return elements

    def _screenshot_page(self, styles, screenshot, meta, page_num):
        elements = []
        img_path = screenshot.get("frame_path", "")
        if img_path and os.path.isfile(img_path):
            try:
                pil_img = PILImage.open(img_path)
                page_w = letter[0] - 2 * cm
                img_w, img_h = pil_img.size
                aspect = img_h / img_w
                img_width = page_w
                img_height = page_w * aspect
                max_img_height = letter[1] * 0.55
                if img_height > max_img_height:
                    img_height = max_img_height
                    img_width = max_img_height / aspect
                elements.append(Image(img_path, width=img_width, height=img_height))
            except Exception as e:
                self.logger.warning("Image error for %s: %s", img_path, e)
                elements.append(Paragraph(f"[Image unavailable: {os.path.basename(img_path)}]", styles["Normal"]))
        elements.append(Spacer(1, 4))

        ts = screenshot.get("timestamp_sec", 0)
        ts_display = format_timestamp(ts)
        ts_end = format_timestamp(ts + 15)
        elements.append(Paragraph(
            f"{ts_display} to {ts_end}",
            styles["TimestampLabel"]
        ))

        transcript_text = screenshot.get("transcript_context", "")
        if transcript_text:
            safe = self._safe_text(transcript_text)
            elements.append(Paragraph(safe, styles["TranscriptBox"]))

        caption = screenshot.get("caption", "")
        if caption:
            elements.append(Paragraph(
                self._safe_text(caption), styles["CaptionText"]
            ))

        tags = screenshot.get("tags", [])
        if tags:
            badges = []
            for tag in tags:
                badges.append(TagBadge(tag.strip(), tag.strip(),
                                        self._latin_font, 8))
                badges.append(Spacer(0.1 * inch, 0))
            badge_table = Table([[badges]], colWidths=[letter[0] - 2 * cm])
            badge_table.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(badge_table)

        elements.append(Spacer(1, 8))
        elements.append(Paragraph(f"Page {page_num}", styles["PageNumber"]))
        elements.append(PageBreak())
        return elements

    def _index_page(self, styles, screenshots):
        elements = []
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph("Index", styles["CoverTitle"]))
        elements.append(Spacer(1, 0.3 * inch))

        data = [["Page", "Timestamp", "Caption", "Tags"]]
        for ss in screenshots:
            page = ss.get("pdf_page", "")
            ts = format_timestamp(ss.get("timestamp_sec", 0))
            cap = self._safe_text(ss.get("caption", "")[:40])
            tags = ", ".join(ss.get("tags", []))
            data.append([page, ts, cap, tags])

        col_widths = [0.5 * inch, 1.0 * inch, 3.5 * inch, 2.0 * inch]
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), self._latin_font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e0e0e0")),
            ("TEXTCOLOR", (0, 0), (-1, -1), black),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e0e0e0")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)
        elements.append(PageBreak())
        return elements

    def build_visual_transcript_pdf(self, screenshots, metadata, output_path):
        self._register_fonts(metadata.get("indic_scripts", []))
        styles = self._build_styles()
        doc = SimpleDocTemplate(
            output_path, pagesize=letter,
            leftMargin=1*cm, rightMargin=1*cm,
            topMargin=1.2*cm, bottomMargin=1*cm,
        )
        elements = []
        elements.extend(self._cover_page(styles, metadata))
        page_num = 2
        for ss in screenshots:
            ss["pdf_page"] = page_num
            elements.extend(self._visual_transcript_page(styles, ss, metadata, page_num))
            page_num += 1
        elements.extend(self._index_page(styles, screenshots))
        try:
            doc.build(elements)
            return True
        except Exception as e:
            self.logger.error("Visual transcript PDF build failed: %s", e, exc_info=True)
            return False

    def _visual_transcript_page(self, styles, screenshot, meta, page_num):
        elements = []

        ts = screenshot.get("timestamp_sec", 0)
        ts_display = format_timestamp(ts)
        ts_end = format_timestamp(ts + 15)
        elements.append(Paragraph(
            f"⏱ {ts_display} to {ts_end}",
            styles["CoverSubtitle"]
        ))
        elements.append(Spacer(1, 6))

        transcript_text = screenshot.get("transcript_context", "")
        caption = screenshot.get("caption", "")
        display_text = caption if caption else transcript_text
        if display_text:
            safe = self._safe_text(display_text)
            elements.append(Paragraph(safe, styles["CaptionText"]))
        elements.append(Spacer(1, 8))

        tags = screenshot.get("tags", [])
        if tags:
            badges = []
            for tag in tags:
                badges.append(TagBadge(tag.strip(), tag.strip(),
                                        self._latin_font, 8))
                badges.append(Spacer(0.1 * inch, 0))
            badge_table = Table([[badges]], colWidths=[letter[0] - 2 * cm])
            badge_table.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            elements.append(badge_table)
            elements.append(Spacer(1, 4))

        img_path = screenshot.get("frame_path", "")
        if img_path and os.path.isfile(img_path):
            try:
                pil_img = PILImage.open(img_path)
                page_w = letter[0] - 2 * cm
                img_w, img_h = pil_img.size
                aspect = img_h / img_w
                img_width = page_w
                img_height = page_w * aspect
                max_img_height = letter[1] * 0.55
                if img_height > max_img_height:
                    img_height = max_img_height
                    img_width = max_img_height / aspect
                elements.append(Image(img_path, width=img_width, height=img_height))
            except Exception as e:
                self.logger.warning("Image error on visual transcript page: %s", e)
                elements.append(Paragraph("[Image unavailable]", styles["Normal"]))

        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"Page {page_num}", styles["PageNumber"]))
        elements.append(PageBreak())
        return elements

    def build_full_pdf(self, screenshots, metadata, output_path):
        self._register_fonts(metadata.get("indic_scripts", []))
        styles = self._build_styles()
        doc = SimpleDocTemplate(
            output_path, pagesize=letter,
            leftMargin=1*cm, rightMargin=1*cm,
            topMargin=1*cm, bottomMargin=1*cm,
        )
        elements = []
        elements.extend(self._cover_page(styles, metadata))
        page_num = 2
        for ss in screenshots:
            ss["pdf_page"] = page_num
            elements.extend(self._screenshot_page(styles, ss, metadata, page_num))
            page_num += 1
        elements.extend(self._index_page(styles, screenshots))
        try:
            doc.build(elements)
            return True
        except Exception as e:
            self.logger.error("PDF build failed: %s", e, exc_info=True)
            return False

    def build_compressed_pdf(self, screenshots, metadata, output_path):
        temp_dir = os.path.join(os.path.dirname(output_path), "_temp_compress")
        os.makedirs(temp_dir, exist_ok=True)
        compressed_screenshots = []
        for ss in screenshots:
            compressed = dict(ss)
            src_path = ss.get("frame_path", "")
            if src_path and os.path.isfile(src_path):
                try:
                    pil_img = PILImage.open(src_path)
                    temp_path = os.path.join(temp_dir, f"comp_{os.path.basename(src_path)}")
                    pil_img.save(temp_path, "JPEG", quality=60)
                    compressed["frame_path"] = temp_path
                except Exception:
                    pass
            compressed_screenshots.append(compressed)
        result = self.build_full_pdf(compressed_screenshots, metadata, output_path)
        for f in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, f))
            except IOError:
                pass
        try:
            os.rmdir(temp_dir)
        except IOError:
            pass
        return result

    def build_split_pdfs(self, screenshots, metadata, output_dir, base_name,
                         screenshots_per_part=15):
        parts = []
        total = len(screenshots)
        num_parts = math.ceil(total / screenshots_per_part)
        for part_idx in range(num_parts):
            start = part_idx * screenshots_per_part
            end = min(start + screenshots_per_part, total)
            chunk = screenshots[start:end]
            part_meta = dict(metadata)
            part_meta["total_screenshots"] = len(chunk)
            ss_from = format_timestamp(chunk[0]["timestamp_sec"]) if chunk else "00:00"
            ss_to = format_timestamp(chunk[-1]["timestamp_sec"]) if chunk else "00:00"
            part_meta["part_info"] = f"Part {part_idx + 1} of {num_parts} — {ss_from} to {ss_to}"
            part_path = os.path.join(output_dir, f"{base_name}_part{part_idx + 1}.pdf")
            success = self.build_full_pdf(chunk, part_meta, part_path)
            parts.append({
                "path": part_path,
                "part": part_idx + 1,
                "total_parts": num_parts,
                "screenshots": len(chunk),
                "success": success,
            })
        return parts

    def build_ai_context_txt(self, screenshots, metadata, output_path):
        lines = []
        lines.append("=" * 50)
        lines.append("LECTURESNAPPDF CONTEXT FILE")
        lines.append("=" * 50)
        lines.append(f"VIDEO: {os.path.basename(metadata.get('video_path', ''))}")
        lines.append(f"DURATION: {format_timestamp_hms(metadata.get('duration_sec', 0))}")
        lines.append(f"LANGUAGE: {metadata.get('language', 'unknown')}")
        lines.append(f"SCREENSHOTS: {len(screenshots)}")
        lines.append(f"GENERATED: {metadata.get('generated', datetime.now().strftime('%Y-%m-%d'))}")
        lines.append(f"SUBJECT: {metadata.get('subject', '')}")
        lines.append(f"EXAM: {metadata.get('exam_target', 'General')}")
        lines.append("")
        lines.append("USAGE: Upload this file and the companion PDF to Claude, ChatGPT, Gemini,")
        lines.append("Grok, DeepSeek, or any AI assistant. Ask questions like:")
        lines.append('  "Explain screenshot 3"')
        lines.append('  "Give me 5 practice questions like screenshot 7"')
        lines.append('  "What is the trick shown at 12:34?"')
        lines.append("=" * 50)
        lines.append("")

        for ss in screenshots:
            sid = ss.get("id", 0)
            ts = format_timestamp(ss.get("timestamp_sec", 0))
            ts_end = format_timestamp(ss.get("timestamp_sec", 0) + 15)
            cap = ss.get("caption", "")
            tags = ", ".join(ss.get("tags", []))
            score = ss.get("content_score", 0)
            context = ss.get("transcript_context", "")

            lines.append(f"[SCREENSHOT_{sid:03d}]")
            lines.append(f"TIMESTAMP: {ts} to {ts_end}")
            lines.append(f"CAPTION: {cap}")
            lines.append(f"TAGS: {tags}")
            lines.append(f"CONTENT_SCORE: {score}")
            lines.append("TRANSCRIPT_CONTEXT:")
            lines.append(context)
            lines.append("-" * 45)
            lines.append("")

        lines.append("=" * 50)
        lines.append("Generated by LectureSnapPDF — End of Document")
        lines.append("=" * 50)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True

    def build_markdown(self, screenshots, metadata, output_path):
        lines = []
        subject = metadata.get("subject", "Lecture Notes")
        lines.append(f"# {subject}")
        lines.append("")
        video_name = os.path.basename(metadata.get("video_path", ""))
        duration = format_timestamp_hms(metadata.get("duration_sec", 0))
        lines.append(f"**Video:** {video_name}  ")
        lines.append(f"**Duration:** {duration} | **Screenshots:** {len(screenshots)} | **Language:** {metadata.get('language', 'unknown')}  ")
        lines.append("")
        lines.append("---")
        lines.append("")

        for ss in screenshots:
            sid = ss.get("id", 0)
            ts = format_timestamp(ss.get("timestamp_sec", 0))
            cap = ss.get("caption", "")
            tags = ", ".join(f"`{t}`" for t in ss.get("tags", []))
            context = ss.get("transcript_context", "")

            title = cap if cap else f"Screenshot {sid}"
            lines.append(f"## Screenshot {sid} — {ts} — {title}")
            if tags:
                lines.append(f"**Tags:** {tags}")
            lines.append("")
            lines.append("**Transcript:**")
            if context:
                for ctx_line in context.split('\n'):
                    lines.append(f"> {ctx_line}")
            lines.append("")
            img_rel = ss.get("frame_path", "")
            if img_rel and os.path.isfile(img_rel):
                img_name = os.path.basename(img_rel)
                lines.append(f"![Screenshot {sid}](screenshots/{img_name})")
            lines.append("")
            lines.append("---")
            lines.append("")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True

    def build_transcript_clean(self, transcript_data, output_path):
        lines = []
        for entry in transcript_data:
            ts = format_timestamp(entry.get("start_sec", 0))
            text = entry.get("text", "")
            lines.append(f"[{ts}] {text}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True

    def build_json_export(self, screenshots, metadata, transcript_data,
                          keyword_hits, output_path):
        data = OrderedDict()
        data["metadata"] = OrderedDict([
            ("video", os.path.basename(metadata.get("video_path", ""))),
            ("duration_seconds", metadata.get("duration_sec", 0)),
            ("language", metadata.get("language", "unknown")),
            ("subject", metadata.get("subject", "")),
            ("exam_target", metadata.get("exam_target", "General")),
            ("generated", metadata.get("generated", datetime.now().strftime("%Y-%m-%d"))),
            ("total_screenshots", len(screenshots)),
            ("app_version", "1.0"),
        ])
        data["screenshots"] = []
        for ss in screenshots:
            data["screenshots"].append(OrderedDict([
                ("id", ss.get("id", 0)),
                ("timestamp_sec", ss.get("timestamp_sec", 0)),
                ("timestamp_display", format_timestamp(ss.get("timestamp_sec", 0))),
                ("caption", ss.get("caption", "")),
                ("tags", ss.get("tags", [])),
                ("transcript_context", ss.get("transcript_context", "")),
                ("content_score", ss.get("content_score", 0)),
                ("image_file", os.path.basename(ss.get("frame_path", "")) if ss.get("frame_path") else ""),
                ("pdf_page", ss.get("pdf_page", 0)),
            ]))
        data["full_transcript"] = []
        for entry in transcript_data:
            data["full_transcript"].append(OrderedDict([
                ("start_sec", entry.get("start_sec", 0)),
                ("end_sec", entry.get("end_sec", 0)),
                ("text", entry.get("text", "")),
            ]))
        data["keyword_hits"] = keyword_hits
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    def build_csv_index(self, screenshots, output_path):
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Screenshot_ID", "Timestamp", "Caption", "Tags",
                             "Transcript_Preview", "PDF_Page", "Content_Score"])
            for ss in screenshots:
                sid = ss.get("id", 0)
                ts = format_timestamp(ss.get("timestamp_sec", 0))
                cap = ss.get("caption", "")
                tags = "|".join(ss.get("tags", []))
                preview = ss.get("transcript_context", "")[:80].replace('\n', ' ')
                page = ss.get("pdf_page", 0)
                score = ss.get("content_score", 0)
                writer.writerow([sid, ts, cap, tags, preview, page, score])
        return True

    def build_notebooklm_sources(self, screenshots, output_dir):
        src_dir = os.path.join(output_dir, "notebooklm_sources")
        os.makedirs(src_dir, exist_ok=True)
        created = []
        for ss in screenshots:
            sid = ss.get("id", 0)
            ts = format_timestamp(ss.get("timestamp_sec", 0))
            cap = ss.get("caption", "screenshot")
            safe_cap = sanitize_filename(cap)[:30] if cap else f"screenshot_{sid}"
            filename = f"source_{sid:02d}_{safe_cap}_{ts.replace(':','m')}s.txt"
            filepath = os.path.join(src_dir, filename)
            lines = []
            lines.append(f"SOURCE: Screenshot {sid}")
            lines.append(f"TIMESTAMP: {ts}")
            lines.append(f"CAPTION: {cap}")
            lines.append(f"TAGS: {', '.join(ss.get('tags', []))}")
            lines.append("")
            lines.append("TRANSCRIPT CONTEXT:")
            lines.append(ss.get("transcript_context", ""))
            lines.append("")
            lines.append(f"Refer to screenshot {sid} in the companion PDF for the visual.")
            lines.append("")
            lines.append("Generated by LectureSnapPDF — End of Document")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            created.append(filepath)
        return created

    def build_gemini_text(self, screenshots, metadata, output_path):
        lines = []
        lines.append("INSTRUCTIONS FOR GEMINI:")
        lines.append("This document contains lecture notes from a math/reasoning video.")
        lines.append("Each section has a timestamp, visual description, and transcript.")
        lines.append("You can be asked to: explain concepts, generate practice questions,")
        lines.append("create summaries, identify patterns across screenshots, or build")
        lines.append("a study plan based on this content.")
        lines.append("")
        lines.append("DOCUMENT_START")
        lines.append("=" * 50)
        lines.append("")

        for ss in screenshots:
            sid = ss.get("id", 0)
            ts = format_timestamp(ss.get("timestamp_sec", 0))
            cap = ss.get("caption", "")
            tags = ss.get("tags", [])
            context = ss.get("transcript_context", "")
            score = ss.get("content_score", 0)

            lines.append("=" * 40)
            lines.append(f"SECTION_{sid:03d} | TIME: {ts} | TOPIC: {cap or 'Untitled'}")
            diff = "High" if score >= 70 else ("Medium" if score >= 50 else "Foundation")
            relevance = "High" if any(t in ["FORMULA", "IMPORTANT", "TRICK"] for t in tags) else "Medium"
            lines.append(f"DIFFICULTY: {diff} | EXAM_RELEVANCE: {relevance}")
            lines.append(f"TAGS: {', '.join(tags)}")
            lines.append(f"CONTENT_SCORE: {score}")
            lines.append("TRANSCRIPT:")
            lines.append(context or "No transcript available.")
            if cap:
                lines.append(f"CAPTION: {cap}")
            lines.append("=" * 40)
            lines.append("")

        lines.append("")
        lines.append("DOCUMENT_END")
        lines.append("Generated by LectureSnapPDF — End of Document")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True

    def build_ollama_chunks(self, screenshots, metadata, output_dir, max_tokens=2000):
        chunk_dir = os.path.join(output_dir, "ollama_chunks")
        os.makedirs(chunk_dir, exist_ok=True)
        system_prompt = (
            "You are a study assistant. The user is preparing for banking exams. "
            "The following content is from a math lecture. Help them understand "
            "concepts, solve questions, and practice. Always cite the timestamp "
            "when referring to specific content."
        )
        sys_path = os.path.join(chunk_dir, "system_prompt.txt")
        with open(sys_path, 'w', encoding='utf-8') as f:
            f.write(system_prompt)

        current_chunk = []
        current_tokens = 0
        chunk_num = 1
        ts_start = 0
        chunks = []

        for ss in screenshots:
            ts = ss.get("timestamp_sec", 0)
            ts_str = format_timestamp(ts)
            cap = ss.get("caption", "")
            tags = ", ".join(ss.get("tags", []))
            context = ss.get("transcript_context", "")
            block = (
                f"[SCREENSHOT {ss.get('id', 0)} | TIME: {ts_str}]\n"
                f"CAPTION: {cap}\n"
                f"TAGS: {tags}\n"
                f"TRANSCRIPT: {context}\n\n"
            )
            block_tokens = calculate_tokens(block)
            if current_tokens + block_tokens > max_tokens and current_chunk:
                self._save_ollama_chunk(chunk_dir, chunk_num, current_chunk,
                                         ts_start, ts_str, metadata)
                chunks.append({
                    "chunk": chunk_num,
                    "time_range": f"{format_timestamp(ts_start)} to {ts_str}",
                })
                chunk_num += 1
                current_chunk = []
                current_tokens = 0
                ts_start = ts
            if not current_chunk:
                ts_start = ts
            current_chunk.append(block)
            current_tokens += block_tokens

        if current_chunk:
            self._save_ollama_chunk(chunk_dir, chunk_num, current_chunk,
                                     ts_start, "end", metadata)
            chunks.append({
                "chunk": chunk_num,
                "time_range": f"{format_timestamp(ts_start)} to end",
            })

        load_order_path = os.path.join(chunk_dir, "load_order.txt")
        with open(load_order_path, 'w', encoding='utf-8') as f:
            f.write("OLLAMA LOAD ORDER\n")
            f.write("=" * 40 + "\n")
            f.write("1. First load system_prompt.txt\n")
            f.write("2. Then load chunks in numeric order\n\n")
            for c in chunks:
                f.write(f"chunk_{c['chunk']:02d}_timestamps_{c['time_range'].replace(':', '-')}.txt\n")
        return chunks

    def _save_ollama_chunk(self, chunk_dir, chunk_num, blocks, ts_start, ts_end, metadata):
        filename = f"chunk_{chunk_num:02d}_timestamps_{format_timestamp(ts_start).replace(':', '-')}_to_{format_timestamp_for_filename(ts_end)}.txt"
        filepath = os.path.join(chunk_dir, filename)
        lines = []
        lines.append(f"LECTURESNAPPDF OLLAMA CHUNK {chunk_num}")
        lines.append(f"VIDEO: {os.path.basename(metadata.get('video_path', ''))}")
        lines.append(f"TIME RANGE: {format_timestamp(ts_start)} to {format_timestamp(ts_end) if isinstance(ts_end, (int, float)) else ts_end}")
        lines.append(f"SUBJECT: {metadata.get('subject', '')}")
        lines.append("=" * 40)
        lines.append("")
        lines.extend(blocks)
        lines.append("=" * 40)
        lines.append("Generated by LectureSnapPDF — End of Document")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def build_anki_apkg(self, screenshots, output_path):
        try:
            import genanki
        except ImportError:
            self.logger.warning("genanki not installed. Skipping Anki export.")
            return False
        model_id = hash("LectureSnapPDF Anki Model") % (2 ** 31)
        model = genanki.Model(
            model_id,
            "LectureSnapPDF Model",
            fields=[
                {"name": "ScreenshotID"},
                {"name": "Timestamp"},
                {"name": "Caption"},
                {"name": "Tags"},
                {"name": "Transcript"},
                {"name": "ImagePath"},
            ],
            templates=[{
                "name": "LectureSnapPDF Card",
                "qfmt": "{{#ImagePath}}<img src='{{ImagePath}}'/>{{/ImagePath}}<br><b>{{Caption}}</b><br>{{Timestamp}}",
                "afmt": "{{FrontSide}}<hr><b>Tags:</b> {{Tags}}<br><br><b>Transcript:</b><br>{{Transcript}}",
            }],
        )
        deck = genanki.Deck(
            hash("LectureSnapPDF Deck") % (2 ** 31),
            "LectureSnapPDF - " + os.path.basename(output_path).replace("_anki.apkg", "")
        )
        for ss in screenshots:
            img_path = ss.get("frame_path", "")
            img_name = ""
            if img_path and os.path.isfile(img_path):
                img_name = os.path.basename(img_path)
                deck.add_file(img_path)
            note = genanki.Note(
                model=model,
                fields=[
                    str(ss.get("id", "")),
                    format_timestamp(ss.get("timestamp_sec", 0)),
                    ss.get("caption", ""),
                    ", ".join(ss.get("tags", [])),
                    ss.get("transcript_context", ""),
                    img_name,
                ],
            )
            deck.add_note(note)
        genanki.Package(deck).write_to_file(output_path)
        return True

    def build_which_file_to_use(self, output_dir):
        lines = []
        lines.append("WHICH FILE TO UPLOAD TO WHICH AI PLATFORM")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"{'Platform':<20} {'Max Upload':<15} {'Recommended File':<40}")
        lines.append("-" * 75)
        lines.append(f"{'Claude':<20} {'32MB':<15} {'*_full.pdf + *_AI_context.txt':<40}")
        lines.append(f"{'ChatGPT':<20} {'512MB session':<15} {'*_full.pdf + *_data.json':<40}")
        lines.append(f"{'Gemini':<20} {'1M tokens':<15} {'*_gemini.txt or *_study_notes.md':<40}")
        lines.append(f"{'NotebookLM':<20} {'200MB/source':<15} {'notebooklm_sources/ folder':<40}")
        lines.append(f"{'Grok':<20} {'~25MB':<15} {'*_compressed.pdf + *_transcript_clean.txt':<40}")
        lines.append(f"{'Qwen':<20} {'~10MB':<15} {'*_compressed.pdf':<40}")
        lines.append(f"{'DeepSeek':<20} {'~20MB':<15} {'*_AI_context.txt + *_data.json':<40}")
        lines.append(f"{'Ollama (local)':<20} {'depends on RAM':<15} {'ollama_chunks/ folder':<40}")
        lines.append(f"{'Perplexity':<20} {'paste text':<15} {'*_transcript_clean.txt':<40}")
        lines.append(f"{'Mistral':<20} {'~10MB':<15} {'*_compressed.pdf':<40}")
        lines.append("")
        lines.append("QUICK GUIDE:")
        lines.append("  For Claude/ChatGPT: Upload *_full.pdf + *_AI_context.txt together")
        lines.append("  For Gemini: Upload *_gemini.txt (paste the whole thing)")
        lines.append("  For NotebookLM: Zip the notebooklm_sources/ folder and upload")
        lines.append("  For Ollama: Load system_prompt.txt, then chunks in order")
        lines.append("  For quick review: Just use *_study_notes.md")
        lines.append("")
        lines.append("Generated by LectureSnapPDF — End of Document")

        path = os.path.join(output_dir, "WHICH_FILE_TO_USE.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
