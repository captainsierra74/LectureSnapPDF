import os
import sys
import urllib.request
import urllib.error
import zipfile
import io
import shutil
from pathlib import Path

from utils import setup_logging


NOTO_FONTS = {
    "NotoSans-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf",
        "filename": "NotoSans-Regular.ttf",
        "fallback_url": "https://fonts.gstatic.com/s/notosans/v36/o-0bIpQlx3QUlC5A4PNB6Ryti20_6n1iPHjc5aPdu2ui.woff2",
    },
    "NotoSans-Bold": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth,wght%5D.ttf",
        "filename": "NotoSans-Bold.ttf",
    },
    "NotoSansDevanagari-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/static/NotoSansDevanagari-Regular.ttf",
        "filename": "NotoSansDevanagari-Regular.ttf",
        "fallback_url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/static/NotoSansDevanagari-Regular.ttf",
    },
    "NotoSansDevanagari-Bold": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/static/NotoSansDevanagari-Bold.ttf",
        "filename": "NotoSansDevanagari-Bold.ttf",
        "fallback_url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/static/NotoSansDevanagari-Bold.ttf",
    },
    "NotoSansDevanagari-Bold": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansDevanagari-Bold.ttf",
    },
    "NotoSansTamil-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosanstamil/NotoSansTamil%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansTamil-Regular.ttf",
    },
    "NotoSansTelugu-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosanstelugu/NotoSansTelugu%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansTelugu-Regular.ttf",
    },
    "NotoSansBengali-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansbengali/NotoSansBengali%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansBengali-Regular.ttf",
    },
    "NotoSansGujarati-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansGujarati-Regular.ttf",
    },
    "NotoSansGurmukhi-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansgurmukhi/NotoSansGurmukhi%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansGurmukhi-Regular.ttf",
    },
    "NotoSansMalayalam-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansmalayalam/NotoSansMalayalam%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansMalayalam-Regular.ttf",
    },
    "NotoSansKannada-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosanskannada/NotoSansKannada%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansKannada-Regular.ttf",
    },
    "NotoSansOriya-Regular": {
        "url": "https://github.com/google/fonts/raw/main/ofl/notosansoriya/NotoSansOriya%5Bwdth,wght%5D.ttf",
        "filename": "NotoSansOriya-Regular.ttf",
    },
}


class FontManager:
    def __init__(self, app_dir=None):
        if app_dir is None:
            app_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_dir = app_dir
        self.font_dir = os.path.join(app_dir, "fonts")
        self._font_cache = {}
        self.logger = setup_logging()

    def get_font_dir(self):
        os.makedirs(self.font_dir, exist_ok=True)
        return self.font_dir

    def check_fonts_exist(self):
        font_dir = self.get_font_dir()
        missing = []
        for name, info in NOTO_FONTS.items():
            path = os.path.join(font_dir, info["filename"])
            if not os.path.isfile(path) or os.path.getsize(path) == 0:
                missing.append(name)
        return missing

    def download_fonts(self, progress_callback=None):
        missing = self.check_fonts_exist()
        if not missing:
            if progress_callback:
                progress_callback(100, 100, "All fonts available")
            return True

        font_dir = self.get_font_dir()
        total = len(missing)
        all_success = True

        for idx, font_name in enumerate(missing):
            if progress_callback:
                progress_callback(idx, total, f"Downloading {font_name}...")
            success = self._download_single_font(font_name, font_dir)
            if not success:
                self.logger.warning("Failed to download font: %s", font_name)
                all_success = False
            if progress_callback:
                progress_callback(idx + 1, total, f"{'Done' if success else 'Failed'}: {font_name}")

        if progress_callback:
            progress_callback(total, total, "Font download complete" if all_success else "Some fonts failed")
        return all_success

    def _download_single_font(self, font_name, font_dir):
        info = NOTO_FONTS.get(font_name)
        if not info:
            return False
        dest_path = os.path.join(font_dir, info["filename"])
        urls_to_try = [info["url"]]
        if "fallback_url" in info:
            urls_to_try.append(info["fallback_url"])
        for url in urls_to_try:
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = response.read()
                if len(data) < 1000:
                    continue
                if url.endswith('.zip'):
                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                        ttf_files = [n for n in zf.namelist() if n.endswith('.ttf')]
                        if ttf_files:
                            for tf in ttf_files:
                                extracted = zf.read(tf)
                                out_name = os.path.basename(tf)
                                out_path = os.path.join(font_dir, out_name)
                                with open(out_path, 'wb') as f:
                                    f.write(extracted)
                            return True
                with open(dest_path, 'wb') as f:
                    f.write(data)
                if self._is_valid_ttf(dest_path):
                    return True
                os.remove(dest_path)
            except (urllib.error.URLError, urllib.error.HTTPError, IOError, OSError, zipfile.BadZipFile) as e:
                self.logger.debug("Download from %s failed: %s", url, e)
                continue
        return False

    def _is_valid_ttf(self, path):
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
            return header in (b'\x00\x01\x00\x00', b'OTTO', b'\x01\x00\x00\x00', b'true')
        except IOError:
            return False

    def get_font_path(self, font_name):
        info = NOTO_FONTS.get(font_name)
        if not info:
            return None
        path = os.path.join(self.get_font_dir(), info["filename"])
        if os.path.isfile(path):
            return path
        return self._find_system_fallback(font_name)

    def _find_system_fallback(self, font_name):
        if sys.platform == "win32":
            system_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
            if "Devanagari" in font_name:
                candidates = ["Nirmala.ttf", "NirmalaB.ttf", "NirmalaS.ttf"]
                for c in candidates:
                    p = os.path.join(system_fonts, c)
                    if os.path.isfile(p):
                        return p
            if "Tamil" in font_name:
                candidates = ["Nirmala.ttf", "Latha.ttf", "Vijaya.ttf"]
                for c in candidates:
                    p = os.path.join(system_fonts, c)
                    if os.path.isfile(p):
                        return p
            if "Telugu" in font_name:
                candidates = ["Nirmala.ttf", "Gautami.ttf"]
                for c in candidates:
                    p = os.path.join(system_fonts, c)
                    if os.path.isfile(p):
                        return p
            if "Bengali" in font_name:
                candidates = ["Nirmala.ttf", "Vrinda.ttf"]
                for c in candidates:
                    p = os.path.join(system_fonts, c)
                    if os.path.isfile(p):
                        return p
        return None

    def register_fonts_with_reportlab(self, scripts=None):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        if scripts is None:
            scripts = ["latin"]
        registered = {}
        for script in scripts:
            if script == "latin" or script == "devanagari":
                font_name = f"NotoSans{script.capitalize()}-Regular"
                path = self.get_font_path(font_name)
                if path:
                    try:
                        rl_name = f"LectureSnap_{script}"
                        pdfmetrics.registerFont(TTFont(rl_name, path))
                        registered[script] = rl_name
                    except Exception as e:
                        self.logger.warning("Failed to register font %s: %s", font_name, e)
        return registered
