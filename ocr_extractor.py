import os
import numpy as np
import cv2

from utils import apply_safe_zone_crop, setup_logging

_OCR_AVAILABLE = False
try:
    import pytesseract
    _OCR_AVAILABLE = True
except ImportError:
    pass


def is_ocr_available():
    return _OCR_AVAILABLE


def check_tesseract_installed():
    if not _OCR_AVAILABLE:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


class OcrExtractor:
    def __init__(self):
        self.logger = setup_logging()
        self.enabled = is_ocr_available() and check_tesseract_installed()
        if not self.enabled:
            self.logger.info("OCR unavailable. Install Tesseract and pytesseract.")

    def extract_text(self, frame, safe_zone_config=None):
        if not self.enabled or frame is None:
            return {"text": "", "confidence": 0, "lang": ""}
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if safe_zone_config:
                gray = apply_safe_zone_crop(gray, safe_zone_config)
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            config = '--oem 3 --psm 6 -l hin+eng'
            data = pytesseract.image_to_data(gray, config=config, output_type=pytesseract.Output.DICT)
            text_parts = []
            confidences = []
            for i, txt in enumerate(data.get("text", [])):
                txt = txt.strip()
                if txt and int(data.get("conf", [0])[i]) > 30:
                    text_parts.append(txt)
                    confidences.append(int(data.get("conf", [0])[i]))
            text = ' '.join(text_parts)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            return {"text": text, "confidence": avg_conf, "lang": "hin+eng"}
        except Exception as e:
            self.logger.debug("OCR extraction failed: %s", e)
            return {"text": "", "confidence": 0, "lang": ""}

    def extract_text_fallback(self, frame, safe_zone_config=None):
        if not self.enabled or frame is None:
            return {"text": "", "confidence": 0, "lang": ""}
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if safe_zone_config:
                gray = apply_safe_zone_crop(gray, safe_zone_config)
            config = '--oem 3 --psm 3'
            text = pytesseract.image_to_string(gray, config=config, lang='hin+eng')
            return {"text": text.strip(), "confidence": 0, "lang": "hin+eng"}
        except Exception as e:
            self.logger.debug("OCR fallback failed: %s", e)
            return {"text": "", "confidence": 0, "lang": ""}
