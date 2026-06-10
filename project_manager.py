import os
import json
import time
import shutil
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from utils import (
    setup_logging, get_temp_dir, generate_session_id, sanitize_filename,
    format_timestamp,
)


PROJECT_FILE_EXTENSION = ".lsnp"
PROJECT_VERSION = "1.0"
AUTOSAVE_INTERVAL_MS = 120000


class ProjectManager(QObject):
    project_loaded = pyqtSignal(dict)
    project_saved = pyqtSignal(str)
    autosave_performed = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.logger = setup_logging()
        self.current_path = None
        self.session_data = None
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)
        self._is_dirty = False
        self._session_id = generate_session_id()

    def new_project(self):
        self.current_path = None
        self.session_data = self._create_empty_session()
        self._is_dirty = False
        return self.session_data

    def _create_empty_session(self):
        return {
            "version": PROJECT_VERSION,
            "video_path": "",
            "video_filename": "",
            "video_duration_sec": 0,
            "transcript_format": "",
            "transcript_data": [],
            "transcript_file_path": "",
            "sync_offset_seconds": 0,
            "subject": "",
            "exam_target": "",
            "capture_mode": "smart_auto",
            "screenshots": [],
            "autosave_timestamp": datetime.now().isoformat(),
            "session_id": self._session_id,
            "language": "unknown",
            "keyword_hits": [],
        }

    def save(self, filepath, session_data):
        try:
            data = dict(session_data)
            data["autosave_timestamp"] = datetime.now().isoformat()
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            temp_path = filepath + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.isfile(filepath):
                os.remove(filepath)
            os.rename(temp_path, filepath)
            self.current_path = filepath
            self.session_data = data
            self._is_dirty = False
            self.project_saved.emit(filepath)
            return True
        except (IOError, OSError, json.JSONEncodeError) as e:
            self.logger.error("Save failed: %s", e)
            self.error_occurred.emit(f"Save failed: {e}")
            return False

    def load(self, filepath):
        if not os.path.isfile(filepath):
            self.error_occurred.emit(f"File not found: {filepath}")
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Invalid project file format")
            data["version"] = data.get("version", "0.0")
            required = ["video_path", "screenshots", "transcript_data"]
            for key in required:
                if key not in data:
                    data[key] = [] if key != "video_path" else ""
            if "session_id" not in data:
                data["session_id"] = generate_session_id()
            self.current_path = filepath
            self.session_data = data
            self._is_dirty = False
            self._session_id = data["session_id"]
            self._validate_screenshot_paths(data)
            self.project_loaded.emit(data)
            return data
        except (json.JSONDecodeError, ValueError, IOError) as e:
            self.logger.error("Load failed: %s", e)
            self.error_occurred.emit(f"Load failed: {e}")
            return None

    def _validate_screenshot_paths(self, data):
        for ss in data.get("screenshots", []):
            path = ss.get("frame_path", "")
            if path and not os.path.isfile(path):
                self.logger.warning("Screenshot file missing: %s", path)

    def set_dirty(self):
        self._is_dirty = True

    def is_dirty(self):
        return self._is_dirty

    def get_autosave_path(self):
        return os.path.join(get_temp_dir(), f"autosave_{self._session_id}.json")

    def _autosave(self):
        if not self._is_dirty or self.session_data is None:
            return
        path = self.get_autosave_path()
        try:
            data = dict(self.session_data)
            data["autosave_timestamp"] = datetime.now().isoformat()
            data["_autosave"] = True
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.autosave_performed.emit()
        except (IOError, OSError) as e:
            self.logger.warning("Autosave failed: %s", e)

    def enable_autosave(self):
        if not self._autosave_timer.isActive():
            self._autosave_timer.start(AUTOSAVE_INTERVAL_MS)

    def disable_autosave(self):
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()

    def check_recovery(self):
        temp_dir = get_temp_dir()
        if not os.path.isdir(temp_dir):
            return None
        autosave_files = [f for f in os.listdir(temp_dir)
                          if f.startswith("autosave_") and f.endswith(".json")]
        if not autosave_files:
            return None
        best = None
        best_time = 0
        for fname in autosave_files:
            fpath = os.path.join(temp_dir, fname)
            try:
                mtime = os.path.getmtime(fpath)
                if mtime > best_time:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("_autosave"):
                        best = data
                        best_time = mtime
            except (IOError, json.JSONDecodeError):
                continue
        if best:
            best["_recovery_mtime"] = best_time
        return best

    def clear_recovery(self):
        temp_dir = get_temp_dir()
        if not os.path.isdir(temp_dir):
            return
        for fname in os.listdir(temp_dir):
            if fname.startswith("autosave_") and fname.endswith(".json"):
                try:
                    os.remove(os.path.join(temp_dir, fname))
                except IOError:
                    pass

    def get_recovery_info(self, recovery_data):
        if not recovery_data:
            return None
        return {
            "video_filename": os.path.basename(recovery_data.get("video_path", "")),
            "screenshot_count": len(recovery_data.get("screenshots", [])),
            "timestamp": datetime.fromtimestamp(
                recovery_data.get("_recovery_mtime", 0)
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "subject": recovery_data.get("subject", ""),
            "language": recovery_data.get("language", "unknown"),
        }

    def update_session_from_recovery(self, recovery_data):
        if recovery_data:
            recovery_data.pop("_autosave", None)
            recovery_data.pop("_recovery_mtime", None)
            self.session_data = recovery_data
            self._is_dirty = True
            self._session_id = recovery_data.get("session_id", generate_session_id())
            return recovery_data
        return None
