import os
import sys
import time
import csv
import json
from datetime import datetime
from collections import defaultdict

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QLabel, QPushButton, QComboBox,
    QListWidget, QListWidgetItem, QScrollArea, QSlider,
    QFileDialog, QMessageBox, QInputDialog, QLineEdit,
    QGroupBox, QFormLayout, QAction, QMenu, QDialog,
    QDialogButtonBox, QSpinBox, QCheckBox, QTextEdit, QPlainTextEdit,
    QGridLayout, QFrame, QSizePolicy, QApplication,
    QStyle, QToolButton, QButtonGroup, QAbstractItemView,
    QUndoStack, QUndoCommand,
)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QMediaMetaData
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtCore import (
    Qt, QUrl, QTimer, QThread, pyqtSignal, pyqtSlot,
    QSize, QPoint, QMutex, QMutexLocker, QCoreApplication,
)
from PyQt5.QtGui import (
    QPixmap, QImage, QFont, QIcon, QPalette, QColor,
    QKeySequence, QPainter, QBrush, QPen, QCursor,
)

import cv2
import numpy as np

from utils import (
    setup_logging, format_timestamp, format_timestamp_hms,
    parse_timestamp, sanitize_filename, get_temp_dir,
    get_session_temp_dir, generate_session_id, resolve_path_safe,
    contains_keywords, ENGLISH_KEYWORDS, HINDI_KEYWORDS,
    HINGLISH_KEYWORDS, MATH_SYMBOLS, SCORE_THRESHOLD_CAPTURE,
    MIN_GAP_DEFAULT, SYNC_OFFSET_MIN, SYNC_OFFSET_MAX,
)
from transcript_parser import TranscriptParser
from frame_engine import (
    FrameCaptureEngine, FrameCaptureThread, FrameCaptureConfig, CapturedFrame,
)
from pdf_builder import PdfBuilder
from project_manager import ProjectManager
from font_manager import FontManager
from ui_export_dialog import ExportDialog

try:
    from ocr_extractor import OcrExtractor, is_ocr_available
    _OCR_AVAILABLE = is_ocr_available()
except ImportError:
    OcrExtractor = None
    _OCR_AVAILABLE = False

TAG_OPTIONS = ["QUESTION", "FORMULA", "TRICK", "IMPORTANT", "EXAMPLE", "DIAGRAM"]


class ThumbnailWidget(QLabel):
    clicked = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    reorder_up = pyqtSignal(int)
    reorder_down = pyqtSignal(int)

    def __init__(self, screenshot_id, timestamp_sec, pixmap, parent=None):
        super().__init__(parent)
        self.screenshot_id = screenshot_id
        self.timestamp_sec = timestamp_sec
        self.setPixmap(pixmap.scaled(120, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setFixedSize(130, 100)
        self.setStyleSheet("border: 2px solid #ddd; border-radius: 4px; padding: 2px; margin: 2px;")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip(f"Screenshot {screenshot_id} @ {format_timestamp(timestamp_sec)}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.screenshot_id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        go_action = menu.addAction(f"Go to {format_timestamp(self.timestamp_sec)}")
        up_action = menu.addAction("Move Left")
        down_action = menu.addAction("Move Right")
        delete_action = menu.addAction("Delete")
        action = menu.exec_(event.globalPos())
        if action == go_action:
            self.clicked.emit(self.screenshot_id)
        elif action == up_action:
            self.reorder_up.emit(self.screenshot_id)
        elif action == down_action:
            self.reorder_down.emit(self.screenshot_id)
        elif action == delete_action:
            self.delete_requested.emit(self.screenshot_id)

    def set_selected(self, selected):
        if selected:
            self.setStyleSheet("border: 3px solid #2196F3; border-radius: 4px; padding: 2px; margin: 2px;")
        else:
            self.setStyleSheet("border: 2px solid #ddd; border-radius: 4px; padding: 2px; margin: 2px;")


class OpenCVFallbackPlayer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Video Player\n(OpenCV Fallback)")
        self.setStyleSheet("background-color: black; color: grey; font-size: 14px;")
        self._cap = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)
        self._fps = 30
        self._playing = False
        self._current_frame = None

    def open_video(self, path):
        if self._cap:
            self._cap.release()
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            self.setText(f"Failed to open: {path}")
            return False
        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        if self._fps <= 0:
            self._fps = 30
        return True

    def play(self):
        if self._cap and not self._playing:
            self._playing = True
            self._timer.start(int(1000 / self._fps))

    def pause(self):
        self._playing = False
        self._timer.stop()

    def stop(self):
        self.pause()
        if self._cap:
            self._cap.release()
            self._cap = None

    def seek(self, position_ms):
        if self._cap:
            self._cap.set(cv2.CAP_PROP_POS_MSEC, position_ms)
            self._update_frame()

    def _update_frame(self):
        if not self._cap or not self._playing:
            return
        ret, frame = self._cap.read()
        if not ret or frame is None:
            self.pause()
            return
        self._current_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        scaled = qt_img.scaled(self.width(), self.height(),
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(QPixmap.fromImage(scaled))

    def get_current_frame(self):
        return self._current_frame

    def get_position(self):
        if self._cap:
            return int(self._cap.get(cv2.CAP_PROP_POS_MSEC))
        return 0

    def get_duration(self):
        if self._cap:
            return int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) / self._fps * 1000)
        return 0


class ReviewDuplicatesDialog(QDialog):
    def __init__(self, screenshots, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Duplicate Screenshots")
        self.setMinimumSize(800, 600)
        self.screenshots = screenshots
        self.to_keep = set(ss.get("id", i) for i, ss in enumerate(screenshots))
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Review pairs of similar screenshots. Uncheck to remove."))

        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        from skimage.metrics import structural_similarity as ssim
        import cv2
        import numpy as np

        checked = []
        for i, ss1 in enumerate(self.screenshots):
            for j in range(i + 1, len(self.screenshots)):
                ss2 = self.screenshots[j]
                p1 = ss1.get("frame_path", "")
                p2 = ss2.get("frame_path", "")
                if not p1 or not p2 or not os.path.isfile(p1) or not os.path.isfile(p2):
                    continue
                try:
                    img1 = cv2.imread(p1, cv2.IMREAD_GRAYSCALE)
                    img2 = cv2.imread(p2, cv2.IMREAD_GRAYSCALE)
                    if img1 is None or img2 is None:
                        continue
                    h = min(img1.shape[0], img2.shape[0])
                    w = min(img1.shape[1], img2.shape[1])
                    img1 = cv2.resize(img1, (320, 180))
                    img2 = cv2.resize(img2, (320, 180))
                    sim = ssim(img1, img2, data_range=255)
                    if sim > 0.80:
                        pair_widget = QWidget()
                        pair_layout = QHBoxLayout(pair_widget)
                        lbl1 = QLabel(f"#{ss1.get('id', i)} @ {format_timestamp(ss1.get('timestamp_sec', 0))}\n{ss1.get('caption', '')}")
                        lbl2 = QLabel(f"#{ss2.get('id', j)} @ {format_timestamp(ss2.get('timestamp_sec', 0))}\n{ss2.get('caption', '')}")
                        px1 = QPixmap(p1).scaled(200, 150, Qt.KeepAspectRatio)
                        px2 = QPixmap(p2).scaled(200, 150, Qt.KeepAspectRatio)
                        img_lbl1 = QLabel()
                        img_lbl1.setPixmap(px1)
                        img_lbl2 = QLabel()
                        img_lbl2.setPixmap(px2)
                        pair_layout.addWidget(img_lbl1)
                        pair_layout.addWidget(lbl1)
                        pair_layout.addWidget(img_lbl2)
                        pair_layout.addWidget(lbl2)
                        cb1 = QCheckBox(f"Keep #{ss1.get('id', i)}")
                        cb1.setChecked(True)
                        cb2 = QCheckBox(f"Keep #{ss2.get('id', j)}")
                        cb2.setChecked(True)
                        pair_layout.addWidget(cb1)
                        pair_layout.addWidget(cb2)
                        sim_label = QLabel(f"Similarity: {sim:.0%}")
                        sim_label.setStyleSheet("color: #F44336; font-weight: bold;")
                        pair_layout.addWidget(sim_label)
                        scroll_layout.addWidget(pair_widget)
                        checked.append((ss1.get("id", i), ss2.get("id", j), cb1, cb2))
                except Exception:
                    continue

        if not checked:
            scroll_layout.addWidget(QLabel("No duplicate pairs found."))

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("Apply & Return")
        apply_btn.clicked.connect(lambda: self._apply(checked))
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _apply(self, checked):
        for sid1, sid2, cb1, cb2 in checked:
            if not cb1.isChecked():
                self.to_keep.discard(sid1)
            if not cb2.isChecked():
                self.to_keep.discard(sid2)
        self.accept()

    def get_filtered_screenshots(self):
        return [ss for ss in self.screenshots if ss.get("id") in self.to_keep]


class MainWindow(QMainWindow):
    def __init__(self, font_manager=None, project_manager=None, recovery_data=None):
        super().__init__()
        self.logger = setup_logging()
        self.font_manager = font_manager or FontManager()
        self.project_manager = project_manager or ProjectManager()
        self.transcript_parser = TranscriptParser()
        self.pdf_builder = PdfBuilder(self.font_manager)
        self.ocr_extractor = OcrExtractor() if _OCR_AVAILABLE else None

        self.session = self.project_manager.new_project()
        self.transcript_entries = []
        self.captured_screenshots = []
        self.keyword_hits = []
        self.video_duration_sec = 0
        self.selected_screenshot_id = None
        self.is_modified = False
        self._capture_engine = None
        self._capture_thread = None
        self._cv2_cap = None
        self._use_fallback_player = False
        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._on_autosave)
        self._video_position_timer = QTimer(self)
        self._video_position_timer.timeout.connect(self._update_video_position)
        self._video_position_timer.start(250)
        self._dark_mode = False
        self.undo_stack = QUndoStack(self)

        self._setup_ui()
        self._setup_connections()
        self._setup_shortcuts()

        if recovery_data:
            self._prompt_recovery(recovery_data)

    def _setup_ui(self):
        self.setWindowTitle("LectureSnapPDF — Study Tool for Competitive Exams")
        self.setMinimumSize(1200, 800)
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._apply_theme()

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        load_video_btn = QAction("📂 Load Video", self)
        load_video_btn.triggered.connect(self._load_video)
        toolbar.addAction(load_video_btn)

        load_transcript_btn = QAction("📄 Load Transcript", self)
        load_transcript_btn.triggered.connect(self._load_transcript)
        toolbar.addAction(load_transcript_btn)

        paste_transcript_btn = QAction("📋 Paste Transcript", self)
        paste_transcript_btn.triggered.connect(self._paste_transcript)
        toolbar.addAction(paste_transcript_btn)

        toolbar.addSeparator()

        save_btn = QAction("💾 Save Project", self)
        save_btn.triggered.connect(self._save_project)
        toolbar.addAction(save_btn)

        load_project_btn = QAction("📂 Open Project", self)
        load_project_btn.triggered.connect(self._load_project)
        toolbar.addAction(load_project_btn)

        toolbar.addSeparator()

        export_btn = QAction("📤 Export PDF", self)
        export_btn.triggered.connect(self._export_pdf)
        toolbar.addAction(export_btn)

        toolbar.addSeparator()

        settings_btn = QAction("⚙ Settings", self)
        settings_btn.triggered.connect(self._show_settings)
        toolbar.addAction(settings_btn)

        theme_btn = QAction("🌙 Dark Mode", self)
        theme_btn.setCheckable(True)
        theme_btn.triggered.connect(self._toggle_theme)
        toolbar.addAction(theme_btn)

        toolbar.addSeparator()

        help_btn = QAction("❓ Help", self)
        help_btn.triggered.connect(self._show_help)
        toolbar.addAction(help_btn)

    def _setup_central_widget(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        top_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(480, 360)
        self.video_widget.setStyleSheet("background-color: black;")
        left_layout.addWidget(self.video_widget, 3)

        self.fallback_player = OpenCVFallbackPlayer()
        self.fallback_player.setVisible(False)
        left_layout.addWidget(self.fallback_player, 3)

        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.error.connect(self._on_player_error)
        self.media_player.stateChanged.connect(self._on_player_state_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.positionChanged.connect(self._on_position_changed)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(40)
        self.play_btn.clicked.connect(self._toggle_play)
        controls_layout.addWidget(self.play_btn)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.sliderMoved.connect(self._seek_video)
        controls_layout.addWidget(self.position_slider)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 11px; min-width: 120px;")
        controls_layout.addWidget(self.time_label)

        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"])
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.currentTextChanged.connect(self._change_speed)
        self.speed_combo.setFixedWidth(60)
        controls_layout.addWidget(self.speed_combo)

        left_layout.addWidget(controls)

        capture_bar = QWidget()
        capture_layout = QHBoxLayout(capture_bar)
        capture_layout.setContentsMargins(0, 4, 0, 0)

        self.capture_btn = QPushButton("📸 Manual (C)")
        self.capture_btn.setToolTip("Capture a single frame manually (keyboard: C)")
        self.capture_btn.clicked.connect(self._manual_capture)
        self.capture_btn.setStyleSheet("background-color: #FF9800; color: white; padding: 6px 12px;")
        capture_layout.addWidget(self.capture_btn)

        capture_layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Smart Auto", "Change Detection", "Manual", "Hybrid"])
        self.mode_combo.setCurrentIndex(0)
        capture_layout.addWidget(self.mode_combo)

        capture_layout.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["Fast", "Normal", "Thorough"])
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setToolTip("Fast=1 sample/entry, no SSIM | Normal=4 samples+SSIM | Thorough=7 samples+strict SSIM")
        capture_layout.addWidget(self.speed_combo)

        self.run_btn = QPushButton("▶ Run Capture")
        self.run_btn.clicked.connect(self._run_capture)
        self.run_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 6px 12px;")
        capture_layout.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("■ Cancel")
        self.cancel_btn.clicked.connect(self._cancel_capture)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("background-color: #F44336; color: white; padding: 6px 12px;")
        capture_layout.addWidget(self.cancel_btn)

        self.capture_count_label = QLabel("✅ 0 captured")
        capture_layout.addWidget(self.capture_count_label)
        capture_layout.addStretch()

        left_layout.addWidget(capture_bar)

        top_splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)

        right_layout.addWidget(QLabel("TRANSCRIPT PANEL"))
        self.transcript_list = QListWidget()
        self.transcript_list.setAlternatingRowColors(True)
        self.transcript_list.itemClicked.connect(self._on_transcript_clicked)
        right_layout.addWidget(self.transcript_list, 1)

        keyword_info = QWidget()
        ki_layout = QHBoxLayout(keyword_info)
        ki_layout.setContentsMargins(0, 0, 0, 0)
        self.keyword_count_label = QLabel("Keyword hits: 0")
        self.keyword_count_label.setStyleSheet("color: #F44336; font-size: 10px;")
        ki_layout.addWidget(self.keyword_count_label)
        ki_layout.addStretch()
        right_layout.addWidget(keyword_info)

        top_splitter.addWidget(right_panel)
        top_splitter.setSizes([700, 400])
        main_layout.addWidget(top_splitter, 3)

        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 4, 0, 0)

        bottom_layout.addWidget(QLabel("SCREENSHOT MANAGER"))

        self.thumbnail_scroll = QScrollArea()
        self.thumbnail_scroll.setWidgetResizable(True)
        self.thumbnail_scroll.setFixedHeight(130)
        self.thumbnail_container = QWidget()
        self.thumbnail_layout = QHBoxLayout(self.thumbnail_container)
        self.thumbnail_layout.setContentsMargins(4, 4, 4, 4)
        self.thumbnail_layout.addStretch()
        self.thumbnail_scroll.setWidget(self.thumbnail_container)
        bottom_layout.addWidget(self.thumbnail_scroll)

        ss_detail = QWidget()
        ss_detail_layout = QHBoxLayout(ss_detail)
        ss_detail_layout.setContentsMargins(0, 4, 0, 0)

        ss_detail_layout.addWidget(QLabel("Caption:"))
        self.caption_edit = QLineEdit()
        self.caption_edit.setPlaceholderText("Enter caption for selected screenshot...")
        self.caption_edit.textChanged.connect(self._on_caption_changed)
        ss_detail_layout.addWidget(self.caption_edit, 2)

        ss_detail_layout.addWidget(QLabel("Tags:"))
        self.tag_combo = QComboBox()
        self.tag_combo.addItems(TAG_OPTIONS)
        self.tag_combo.setEditable(True)
        ss_detail_layout.addWidget(self.tag_combo)

        add_tag_btn = QPushButton("+ Add Tag")
        add_tag_btn.clicked.connect(self._add_tag)
        ss_detail_layout.addWidget(add_tag_btn)

        delete_btn = QPushButton("🗑 Delete")
        delete_btn.clicked.connect(self._delete_screenshot)
        ss_detail_layout.addWidget(delete_btn)

        review_btn = QPushButton("Review Duplicates")
        review_btn.clicked.connect(self._review_duplicates)
        ss_detail_layout.addWidget(review_btn)

        bottom_layout.addWidget(ss_detail)

        main_layout.addWidget(bottom_panel, 1)

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_video_time = QLabel("Video: --:--:--")
        self.status_duration = QLabel("Duration: --:--:--")
        self.status_screenshots = QLabel("Screenshots: 0")
        self.status_pages = QLabel("Est. PDF pages: 2")
        self.status_process = QLabel("Ready")
        self.status_bar.addWidget(self.status_video_time)
        self.status_bar.addWidget(self.status_duration)
        self.status_bar.addWidget(self.status_screenshots)
        self.status_bar.addWidget(self.status_pages)
        self.status_bar.addPermanentWidget(self.status_process)

    def _setup_shortcuts(self):
        self.capture_shortcut = QAction("Manual Capture", self)
        self.capture_shortcut.setShortcut(QKeySequence("C"))
        self.capture_shortcut.triggered.connect(self._manual_capture)
        self.addAction(self.capture_shortcut)

        self.play_shortcut = QAction("Play/Pause", self)
        self.play_shortcut.setShortcut(QKeySequence(Qt.Key_Space))
        self.play_shortcut.triggered.connect(self._toggle_play)
        self.addAction(self.play_shortcut)

        self.open_shortcut = QAction("Open", self)
        self.open_shortcut.setShortcut(QKeySequence("Ctrl+O"))
        self.open_shortcut.triggered.connect(self._load_video)
        self.addAction(self.open_shortcut)

        self.save_shortcut = QAction("Save", self)
        self.save_shortcut.setShortcut(QKeySequence("Ctrl+S"))
        self.save_shortcut.triggered.connect(self._save_project)
        self.addAction(self.save_shortcut)

        self.export_shortcut = QAction("Export", self)
        self.export_shortcut.setShortcut(QKeySequence("Ctrl+E"))
        self.export_shortcut.triggered.connect(self._export_pdf)
        self.addAction(self.export_shortcut)

    def _setup_connections(self):
        self.project_manager.project_loaded.connect(self._on_project_loaded)
        self.project_manager.error_occurred.connect(
            lambda msg: self.status_process.setText(f"Error: {msg}")
        )

    def _apply_theme(self):
        if self._dark_mode:
            dark_palette = QPalette()
            dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.WindowText, Qt.white)
            dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
            dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))
            dark_palette.setColor(QPalette.ToolTipText, Qt.white)
            dark_palette.setColor(QPalette.Text, Qt.white)
            dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
            dark_palette.setColor(QPalette.ButtonText, Qt.white)
            dark_palette.setColor(QPalette.BrightText, Qt.red)
            dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            dark_palette.setColor(QPalette.HighlightedText, Qt.black)
            self.setPalette(dark_palette)
        else:
            self.setPalette(self.style().standardPalette())

    def _toggle_theme(self, checked):
        self._dark_mode = checked
        self._apply_theme()

    def _load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Video File", "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v);;All Files (*)"
        )
        if not path:
            return
        self.status_process.setText(f"Loading video: {os.path.basename(path)}...")
        QApplication.processEvents()
        path = resolve_path_safe(path)
        self.session["video_path"] = path
        self.session["video_filename"] = os.path.basename(path)
        content = QMediaContent(QUrl.fromLocalFile(path))
        self.media_player.setMedia(content)
        self._use_fallback_player = False
        self.fallback_player.setVisible(False)
        self.video_widget.setVisible(True)
        self._cv2_cap = cv2.VideoCapture(path)
        if self._cv2_cap.isOpened():
            fps = self._cv2_cap.get(cv2.CAP_PROP_FPS)
            total = int(self._cv2_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if fps > 0:
                self.video_duration_sec = total / fps
            self.status_duration.setText(f"Duration: {format_timestamp_hms(int(self.video_duration_sec))}")
        self.status_process.setText(f"Loaded: {os.path.basename(path)}")

    def _on_player_error(self, error):
        if error != QMediaPlayer.NoError:
            msg = self.media_player.errorString()
            self.logger.warning("QMediaPlayer error: %s", msg)
            if self._try_fallback_player():
                self.status_process.setText("Using OpenCV fallback player (codec not supported by QMediaPlayer)")
            else:
                self.status_process.setText(f"Player error: {msg}")

    def _on_player_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("⏸")
        elif state == QMediaPlayer.PausedState:
            self.play_btn.setText("▶")
        elif state == QMediaPlayer.StoppedState:
            self.play_btn.setText("▶")

    def _try_fallback_player(self):
        path = self.session.get("video_path", "")
        if not path or not os.path.isfile(path):
            return False
        ok = self.fallback_player.open_video(path)
        if ok:
            self._use_fallback_player = True
            self.video_widget.setVisible(False)
            self.fallback_player.setVisible(True)
            return True
        return False

    def _toggle_play(self):
        if self._use_fallback_player:
            if self.fallback_player._playing:
                self.fallback_player.pause()
                self.play_btn.setText("▶")
            else:
                self.fallback_player.play()
                self.play_btn.setText("⏸")
        else:
            if self.media_player.state() == QMediaPlayer.PlayingState:
                self.media_player.pause()
                self.play_btn.setText("▶")
            else:
                self.media_player.play()
                self.play_btn.setText("⏸")

    def _seek_video(self, position):
        if self._use_fallback_player:
            self.fallback_player.seek(position)
        else:
            self.media_player.setPosition(position)

    def _change_speed(self, speed_text):
        rate = float(speed_text.replace("x", ""))
        self.media_player.setPlaybackRate(rate)

    def _on_duration_changed(self, duration):
        self.video_duration_sec = duration / 1000
        self.position_slider.setRange(0, duration)
        self.status_duration.setText(f"Duration: {format_timestamp_hms(int(self.video_duration_sec))}")

    def _on_position_changed(self, position):
        if not self._use_fallback_player:
            self.position_slider.setValue(position)
            self._update_time_label(position)
            self._highlight_current_transcript(position / 1000)

    def _update_video_position(self):
        if self._use_fallback_player:
            pos = self.fallback_player.get_position()
            self.position_slider.setValue(pos)
            self._update_time_label(pos)
            self._highlight_current_transcript(pos / 1000)

    def _update_time_label(self, position_ms):
        current = format_timestamp_hms(int(position_ms / 1000))
        total = format_timestamp_hms(int(self.video_duration_sec))
        self.time_label.setText(f"{current} / {total}")
        self.status_video_time.setText(f"Video: {current}")

    def _load_transcript(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Transcript File", "",
            "Transcript Files (*.srt *.vtt *.txt);;All Files (*)"
        )
        if not path:
            return
        self.status_process.setText("Parsing transcript...")
        QApplication.processEvents()
        self.transcript_entries = self.transcript_parser.parse(path, self.video_duration_sec)
        if self.transcript_entries:
            self.session["transcript_format"] = self.transcript_parser.format
            self.session["transcript_data"] = self.transcript_entries
            self.session["transcript_file_path"] = path
            self.session["language"] = self.transcript_parser.language
            self._populate_transcript_panel()
            self._count_keywords()
            self.status_process.setText(
                f"Transcript loaded: {len(self.transcript_entries)} lines, "
                f"language: {self.transcript_parser.language}"
            )
        else:
            QMessageBox.information(self, "No Transcript",
                                     "Could not parse transcript. The app will work in change detection mode.")
            self.transcript_entries = []
            self.session["transcript_data"] = []
            self.session["transcript_format"] = "none"

    def _paste_transcript(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Paste Transcript")
        dlg.setMinimumSize(600, 400)
        layout = QVBoxLayout(dlg)

        label = QLabel("Paste YouTube transcript text below (timestamped lines, SRT, VTT, or plain text):")
        layout.addWidget(label)

        text_edit = QPlainTextEdit()
        text_edit.setPlaceholderText(
            "Paste here...\n\n"
            "Example format:\n"
            "0:00  Hello everyone in this video\n"
            "0:05  we are going to discuss important topics"
        )
        layout.addWidget(text_edit)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        parse_btn = QPushButton("Parse & Load")
        parse_btn.setDefault(True)
        parse_btn.clicked.connect(dlg.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(parse_btn)
        layout.addLayout(btn_layout)

        if dlg.exec() != QDialog.Accepted:
            return

        text = text_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Empty", "No text entered.")
            return

        self.status_process.setText("Parsing pasted transcript...")
        QApplication.processEvents()
        self.transcript_entries = self.transcript_parser.parse(text, self.video_duration_sec)
        if self.transcript_entries:
            self.session["transcript_format"] = self.transcript_parser.format
            self.session["transcript_data"] = self.transcript_entries
            self.session["transcript_file_path"] = None
            self.session["language"] = self.transcript_parser.language
            self._populate_transcript_panel()
            self._count_keywords()
            self.status_process.setText(
                f"Transcript loaded: {len(self.transcript_entries)} lines, "
                f"language: {self.transcript_parser.language} (pasted)"
            )
        else:
            QMessageBox.information(self, "No Transcript",
                                     "Could not parse pasted text. The app will work in change detection mode.")
            self.transcript_entries = []
            self.session["transcript_data"] = []
            self.session["transcript_format"] = "none"

    def _populate_transcript_panel(self):
        self.transcript_list.clear()
        for entry in self.transcript_entries:
            ts = format_timestamp(entry.get("start_sec", 0))
            text = entry.get("text", "")
            kw_hits = self._count_keywords_in_line(text)
            kw_badge = f" 🔴" if kw_hits > 0 else ""
            item_text = f"{ts}  {text[:80]}{kw_badge}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, entry.get("start_sec", 0))
            if entry.get("is_silence"):
                item.setForeground(QColor("#9e9e9e"))
            elif kw_hits > 0:
                item.setForeground(QColor("#F44336"))
            self.transcript_list.addItem(item)

    def _highlight_current_transcript(self, current_sec):
        for i in range(self.transcript_list.count()):
            item = self.transcript_list.item(i)
            ts = item.data(Qt.UserRole)
            if abs(ts - current_sec) < 3:
                self.transcript_list.setCurrentItem(item)
                self.transcript_list.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                break

    def _on_transcript_clicked(self, item):
        ts = item.data(Qt.UserRole) * 1000
        self._seek_video(int(ts))

    def _count_keywords_in_line(self, text):
        if not text:
            return 0
        lower = text.lower()
        count = 0
        for kw in ENGLISH_KEYWORDS + HINDI_KEYWORDS + HINGLISH_KEYWORDS:
            if kw in lower:
                count += 1
        for sym in MATH_SYMBOLS:
            if sym in text:
                count += 1
        return count

    def _count_keywords(self):
        total = 0
        self.keyword_hits = []
        for entry in self.transcript_entries:
            count = self._count_keywords_in_line(entry.get("text", ""))
            if count > 0:
                total += count
                self.keyword_hits.append({
                    "keyword": "multiple",
                    "timestamp_sec": entry.get("start_sec", 0),
                    "screenshot_id": None,
                })
        self.keyword_count_label.setText(f"Keyword hits: {total}")

    def _run_capture(self):
        if not self.session.get("video_path") or not os.path.isfile(self.session["video_path"]):
            QMessageBox.warning(self, "No Video", "Load a video file first.")
            return
        mode_map = {
            "Smart Auto": "smart_auto",
            "Change Detection": "change_only",
            "Manual": "manual",
            "Hybrid": "hybrid",
        }
        mode = mode_map[self.mode_combo.currentText()]

        speed_map = {"Fast": "fast", "Normal": "normal", "Thorough": "thorough"}
        speed = speed_map[self.speed_combo.currentText()]

        config = FrameCaptureConfig()
        config.mode = mode
        config.speed = speed
        config.sync_offset = self.session.get("sync_offset_seconds", 0)
        if self.session.get("has_sync_offset"):
            config.sync_offset = self.session["sync_offset_seconds"]

        config.score_override_gap = config.score_threshold + 10

        self.captured_screenshots = []
        self._refresh_thumbnails()

        self._capture_engine = FrameCaptureEngine()
        self._capture_engine.config = config
        self._capture_engine.signals.progress.connect(self._on_capture_progress)
        self._capture_engine.signals.frame_captured.connect(self._on_frame_captured)
        self._capture_engine.signals.frame_rejected.connect(self._on_frame_rejected)
        self._capture_engine.signals.finished.connect(self._on_capture_finished)
        self._capture_engine.signals.error.connect(self._on_capture_error)
        self._capture_engine.signals.status_update.connect(self.status_process.setText)

        self._capture_thread = FrameCaptureThread(
            self._capture_engine,
            self.session["video_path"],
            self.transcript_entries,
        )
        self._capture_thread.start()

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_process.setText("Capture running...")

    def _cancel_capture(self):
        if self._capture_engine:
            self._capture_engine.cancel()
        self.cancel_btn.setEnabled(False)

    @pyqtSlot(int, int, int, str)
    def _on_capture_progress(self, current, total, pct, text):
        if total > 0:
            self.status_process.setText(f"Processing: {pct}% ({current}/{total})")

    @pyqtSlot(object)
    def _on_frame_captured(self, captured_frame):
        self.captured_screenshots.append(captured_frame.to_dict())
        self._refresh_thumbnails()
        self._update_stats()
        self.is_modified = True
        self.project_manager.set_dirty()

    @pyqtSlot(int, str)
    def _on_frame_rejected(self, timestamp, reason):
        self.logger.debug("Frame rejected at %s: %s", format_timestamp(timestamp), reason)

    @pyqtSlot(list)
    def _on_capture_finished(self, frames):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._enforce_minimum_captures()
        self._update_stats()
        self.status_process.setText(f"Capture complete: {len(self.captured_screenshots)} screenshots")

    def _enforce_minimum_captures(self):
        if len(self.captured_screenshots) < 3 and self._cv2_cap and self._cv2_cap.isOpened():
            needed = 3 - len(self.captured_screenshots)
            self.status_process.setText(f"Only {len(self.captured_screenshots)} captured. Forcing {needed} more...")
            QApplication.processEvents()
            step = max(1, int(self.video_duration_sec / (needed + 1)))
            t = step
            cap = self._cv2_cap
            while t < self.video_duration_sec and len(self.captured_screenshots) < 3:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ret, frame = cap.read()
                if ret and frame is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if np.mean(gray) > 20 and np.mean(gray) < 235:
                        cf = CapturedFrame(
                            frame_id=len(self.captured_screenshots) + 1,
                            timestamp_sec=t,
                            frame_array=frame,
                            content_score=50,
                            transcript_text="",
                            is_manual=True,
                        )
                        cf.caption = f"Forced capture at {format_timestamp(t)}"
                        temp_dir = get_session_temp_dir(self.session.get("session_id"))
                        cf.save_to_disk(temp_dir)
                        self.captured_screenshots.append(cf.to_dict())
                t += step
            self._refresh_thumbnails()
            self._update_stats()

    @pyqtSlot(str)
    def _on_capture_error(self, msg):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_process.setText(f"Capture error: {msg}")
        QMessageBox.warning(self, "Capture Error", msg)

    def _manual_capture(self):
        mode = self.mode_combo.currentText()
        if mode == "Change Detection":
            QMessageBox.information(self, "Mode Info",
                                     "Change Detection mode automatically scans every 6 seconds. "
                                     "Use Manual or Hybrid mode for manual captures.")
            return

        frame = None
        if self._use_fallback_player:
            frame = self.fallback_player.get_current_frame()
        elif self._cv2_cap and self._cv2_cap.isOpened():
            pos = self.media_player.position()
            self._cv2_cap.set(cv2.CAP_PROP_POS_MSEC, max(0, pos))
            ret, frame = self._cv2_cap.read()

        if frame is None:
            QMessageBox.warning(self, "No Frame", "No video frame available. Play the video first.")
            return

        from utils import LAPLACIAN_THRESHOLD, BLANK_BRIGHT_THRESHOLD, BLACK_DARK_THRESHOLD
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        rejected = False
        reject_reason = ""
        if mean_brightness > BLANK_BRIGHT_THRESHOLD:
            rejected = True
            reject_reason = "blank (too bright)"
        elif mean_brightness < BLACK_DARK_THRESHOLD:
            rejected = True
            reject_reason = "blank (too dark)"
        elif laplacian_var < LAPLACIAN_THRESHOLD:
            rejected = True
            reject_reason = "blurry"

        if rejected:
            reply = QMessageBox.question(
                self, "Skipped",
                f"This frame was skipped: {reject_reason}.\n\nPress again to force save anyway?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        pos_sec = (self.media_player.position() / 1000) if not self._use_fallback_player else \
                  (self.fallback_player.get_position() / 1000)

        transcript_text = ""
        for entry in self.transcript_entries:
            if entry["start_sec"] <= pos_sec <= entry["end_sec"]:
                transcript_text = entry["text"]
                break

        from transcript_parser import TranscriptParser
        tp = TranscriptParser()
        context = tp.get_context_window(self.transcript_entries, pos_sec)

        sid = len(self.captured_screenshots) + 1
        cf = CapturedFrame(
            frame_id=sid,
            timestamp_sec=pos_sec,
            frame_array=frame,
            content_score=100,
            transcript_text=context,
            is_manual=True,
        )
        temp_dir = get_session_temp_dir(self.session.get("session_id"))
        path = cf.save_to_disk(temp_dir)
        if path:
            ss_dict = cf.to_dict()
            self.captured_screenshots.append(ss_dict)
            self._refresh_thumbnails()
            self._update_stats()
            self.is_modified = True
            self.project_manager.set_dirty()
            self.status_process.setText(f"Manually captured screenshot {sid} at {format_timestamp(pos_sec)}")

    def _on_caption_changed(self, text):
        if self.selected_screenshot_id is not None:
            for ss in self.captured_screenshots:
                if ss.get("id") == self.selected_screenshot_id:
                    ss["caption"] = text
                    self.is_modified = True
                    self.project_manager.set_dirty()
                    break

    def _add_tag(self):
        if self.selected_screenshot_id is None:
            QMessageBox.information(self, "No Selection", "Select a screenshot first.")
            return
        tag = self.tag_combo.currentText().strip()
        if not tag:
            return
        for ss in self.captured_screenshots:
            if ss.get("id") == self.selected_screenshot_id:
                if tag not in ss.get("tags", []):
                    ss.setdefault("tags", []).append(tag)
                    self.is_modified = True
                    self.project_manager.set_dirty()
                    self.status_process.setText(f"Tag '{tag}' added to screenshot {ss['id']}")
                break

    def _delete_screenshot(self):
        if self.selected_screenshot_id is None:
            return
        reply = QMessageBox.question(self, "Delete", "Delete this screenshot?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.captured_screenshots = [
            ss for ss in self.captured_screenshots
            if ss.get("id") != self.selected_screenshot_id
        ]
        self.selected_screenshot_id = None
        self._refresh_thumbnails()
        self._update_stats()
        self.is_modified = True
        self.project_manager.set_dirty()

    def _refresh_thumbnails(self):
        for i in reversed(range(self.thumbnail_layout.count())):
            w = self.thumbnail_layout.itemAt(i)
            if w and w.widget():
                w.widget().deleteLater()
        for ss in self.captured_screenshots:
            path = ss.get("frame_path", "")
            if path and os.path.isfile(path):
                pixmap = QPixmap(path)
                tw = ThumbnailWidget(
                    ss.get("id", 0),
                    ss.get("timestamp_sec", 0),
                    pixmap,
                )
                tw.clicked.connect(self._on_thumbnail_clicked)
                tw.delete_requested.connect(self._delete_thumbnail)
                tw.reorder_up.connect(self._reorder_up)
                tw.reorder_down.connect(self._reorder_down)
                if ss.get("is_manual"):
                    tw.setToolTip(tw.toolTip() + " ✋ Manual capture")
                self.thumbnail_layout.insertWidget(self.thumbnail_layout.count() - 1, tw)
        self.capture_count_label.setText(f"✅ {len(self.captured_screenshots)} captured")

    def _on_thumbnail_clicked(self, screenshot_id):
        self.selected_screenshot_id = screenshot_id
        for i in range(self.thumbnail_layout.count()):
            w = self.thumbnail_layout.itemAt(i)
            if w and w.widget() and isinstance(w.widget(), ThumbnailWidget):
                w.widget().set_selected(w.widget().screenshot_id == screenshot_id)
        for ss in self.captured_screenshots:
            if ss.get("id") == screenshot_id:
                self.caption_edit.setText(ss.get("caption", ""))
                ts = ss.get("timestamp_sec", 0) * 1000
                self._seek_video(int(ts))
                break

    def _delete_thumbnail(self, screenshot_id):
        self.captured_screenshots = [
            ss for ss in self.captured_screenshots
            if ss.get("id") != screenshot_id
        ]
        if self.selected_screenshot_id == screenshot_id:
            self.selected_screenshot_id = None
            self.caption_edit.clear()
        self._refresh_thumbnails()
        self._update_stats()

    def _reorder_up(self, screenshot_id):
        for i, ss in enumerate(self.captured_screenshots):
            if ss.get("id") == screenshot_id and i > 0:
                self.captured_screenshots[i], self.captured_screenshots[i - 1] = \
                    self.captured_screenshots[i - 1], self.captured_screenshots[i]
                self._refresh_thumbnails()
                break

    def _reorder_down(self, screenshot_id):
        for i, ss in enumerate(self.captured_screenshots):
            if ss.get("id") == screenshot_id and i < len(self.captured_screenshots) - 1:
                self.captured_screenshots[i], self.captured_screenshots[i + 1] = \
                    self.captured_screenshots[i + 1], self.captured_screenshots[i]
                self._refresh_thumbnails()
                break

    def _review_duplicates(self):
        if len(self.captured_screenshots) < 2:
            QMessageBox.information(self, "No Duplicates", "Need at least 2 screenshots to compare.")
            return
        dialog = ReviewDuplicatesDialog(self.captured_screenshots, self)
        if dialog.exec_():
            filtered = dialog.get_filtered_screenshots()
            if len(filtered) < len(self.captured_screenshots):
                self.captured_screenshots = filtered
                self._refresh_thumbnails()
                self._update_stats()
                self.status_process.setText(f"Removed duplicates. {len(filtered)} screenshots remaining.")

    def _update_stats(self):
        count = len(self.captured_screenshots)
        est_pages = count + 2
        self.status_screenshots.setText(f"Screenshots: {count}")
        self.status_pages.setText(f"Est. PDF pages: {est_pages}")

    def _export_pdf(self):
        if not self.captured_screenshots:
            QMessageBox.warning(self, "No Screenshots",
                                 "Capture some screenshots first before exporting.")
            return
        metadata = {
            "video_path": self.session.get("video_path", ""),
            "duration_sec": self.video_duration_sec,
            "language": self.session.get("language", "unknown"),
            "subject": self.session.get("subject", ""),
            "exam_target": self.session.get("exam_target", "General"),
            "total_screenshots": len(self.captured_screenshots),
            "indic_scripts": list(self.transcript_parser.indic_scripts) if self.transcript_parser and hasattr(self.transcript_parser, 'indic_scripts') else [],
            "generated": datetime.now().strftime("%Y-%m-%d"),
        }
        try:
            dialog = ExportDialog(
                self.pdf_builder,
                self.captured_screenshots,
                metadata,
                self.transcript_entries,
                self.keyword_hits,
                self,
            )
            dialog.exec_()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.logger.error("Export crashed: %s\n%s", e, tb)
            QMessageBox.critical(self, "Export Error",
                                 f"Export failed:\n{e}\n\nCheck logs for details.")

    def _save_project(self):
        self.session["screenshots"] = self.captured_screenshots
        self.session["keyword_hits"] = self.keyword_hits
        default_name = sanitize_filename(self.session.get("video_filename", "project"))
        default_name = default_name.rsplit(".", 1)[0] + ".lsnp"
        default_dir = os.path.dirname(self.session.get("video_path", "")) or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project",
            os.path.join(default_dir, default_name),
            "LectureSnapPDF Project (*.lsnp)"
        )
        if path:
            if not path.endswith(".lsnp"):
                path += ".lsnp"
            ok = self.project_manager.save(path, self.session)
            if ok:
                self.status_process.setText(f"Project saved: {os.path.basename(path)}")
                self.is_modified = False
            else:
                QMessageBox.warning(self, "Save Failed", "Could not save project file.")

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "",
            "LectureSnapPDF Project (*.lsnp);;All Files (*)"
        )
        if path:
            data = self.project_manager.load(path)
            if data:
                self._on_project_loaded(data)

    def _on_project_loaded(self, data):
        self.session = data
        self.transcript_entries = data.get("transcript_data", [])
        self.captured_screenshots = data.get("screenshots", [])
        self.keyword_hits = data.get("keyword_hits", [])

        if data.get("video_path") and not os.path.isfile(data["video_path"]):
            reply = QMessageBox.question(
                self, "Video Not Found",
                f"Video file not found:\n{data['video_path']}\n\nLocate the video file?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                new_path, _ = QFileDialog.getOpenFileName(
                    self, "Locate Video File",
                    os.path.dirname(data["video_path"]),
                    "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm)"
                )
                if new_path:
                    self.session["video_path"] = new_path
                    content = QMediaContent(QUrl.fromLocalFile(new_path))
                    self.media_player.setMedia(content)

        if self.transcript_entries:
            self._populate_transcript_panel()
            self._count_keywords()

        self._refresh_thumbnails()
        self._update_stats()
        self.status_process.setText(f"Project loaded: {os.path.basename(self.project_manager.current_path or '')}")

    def _show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("LectureSnapPDF Help")
        dlg.setMinimumSize(700, 550)
        layout = QVBoxLayout(dlg)

        tabs = QTabWidget()

        # --- Tab 1: Getting Started ---
        getting_started = QTextEdit()
        getting_started.setReadOnly(True)
        getting_started.setHtml("""
        <h2>Getting Started</h2>
        <p><b>LectureSnapPDF</b> converts lecture videos into structured PDF study material
        by combining video screenshots with transcript context.</p>

        <h3>Basic Workflow</h3>
        <ol>
        <li><b>Load Video</b> — Click "Load Video" and select an MP4/MKV/AVI file</li>
        <li><b>Load/Paste Transcript</b> — Click "Load Transcript" or "Paste Transcript"</li>
        <li><b>▶ Run Capture</b> — Click this button in <b>Smart Auto</b> mode.
            It processes the entire video <b>automatically in the background</b>
            — you do NOT need to play or watch the video</li>
        <li><b>Review & Edit</b> — Click thumbnails to add captions, tags, reorder, or delete</li>
        <li><b>Export</b> — Click "Export PDF" (5 formats) or "Export All" (13 formats)</li>
        </ol>

        <h3>Fastest Way to Get All Screenshots</h3>
        <ol>
        <li>Load video → paste transcript → select <b>Smart Auto</b> → select <b>Fast</b> speed → click <b>▶ Run Capture</b></li>
        <li>The frame engine scans the entire video file in a background thread (not the player)</li>
        <li>Progress is shown in the status bar — go do something else while it runs</li>
        <li>When finished, just click <b>Export PDF</b></li>
        </ol>

        <h3>Supported Transcript Formats</h3>
        <ul>
        <li><b>YouTube copy-paste:</b> <code>0:00  Hello everyone</code></li>
        <li><b>SRT:</b> Standard subtitle format with sequence numbers</li>
        <li><b>VTT:</b> WebVTT format</li>
        <li><b>Bracket timestamps:</b> <code>[00:00.000]</code> style</li>
        <li><b>None:</b> Works in change-detection-only mode</li>
        </ul>

        <h3>Video & Audio</h3>
        <p>The video player supports play/pause (Space), seek, and speed control (0.5x–2x).
        Audio is not required — the app works with mute videos.</p>
        """)
        tabs.addTab(getting_started, "Getting Started")

        # --- Tab 2: Capture Modes ---
        modes_tab = QTextEdit()
        modes_tab.setReadOnly(True)
        modes_tab.setHtml("""
        <h2>Capture Modes</h2>
        <p>Select a mode from the dropdown below the video player.</p>

        <table border='1' cellpadding='6' style='border-collapse: collapse;'>
        <tr bgcolor='#e0e0e0'><td><b>Mode</b></td><td><b>How It Works</b></td><td><b>Best For</b></td></tr>
        <tr>
        <td><b>Smart Auto</b></td>
        <td>Frame engine scores every frame using 8 rules:
            blank rejection, SSIM dedup, speech delay compensation,
            keyword scoring, math symbol detection, context windows,
            adaptive gap, and forced minimum captures</td>
        <td>Most lectures — gives best quality results automatically</td>
        </tr>
        <tr>
        <td><b>Change Detection</b></td>
        <td>Samples every 6s and captures when the frame changes
            significantly (pixel diff). No transcript needed.</td>
        <td>When you have no transcript or want a quick rough capture</td>
        </tr>
        <tr>
        <td><b>Manual</b></td>
        <td>You press <b>C</b> or click the Capture button. Nothing happens automatically.</td>
        <td>When you want total control over every screenshot</td>
        </tr>
        <tr>
        <td><b>Hybrid</b></td>
        <td>Runs the frame engine + lets you manually add extra captures</td>
        <td>Best of both worlds — auto captures key moments + you refine</td>
        </tr>
        </table>

        <h3>Speed Options</h3>
        <table border='1' cellpadding='6' style='border-collapse: collapse;'>
        <tr bgcolor='#e0e0e0'><td><b>Speed</b></td><td><b>Samples per entry</b></td><td><b>SSIM dedup</b></td><td><b>Est. time (1hr)</b></td></tr>
        <tr><td><b>Fast</b></td><td>1 (at 0s)</td><td>Skipped</td><td>~30–60 sec</td></tr>
        <tr><td><b>Normal</b></td><td>4 (at 0, +4, +8, +12s)</td><td>Enabled</td><td>~1–3 min</td></tr>
        <tr><td><b>Thorough</b></td><td>7 (every 2s)</td><td>Strict</td><td>~3–6 min</td></tr>
        </table>

        <h3>Frame Engine Rules (Smart Auto)</h3>
        <ol>
        <li><b>Blank rejection</b> — skips black/white frames and low-Laplacian blur</li>
        <li><b>SSIM dedup</b> — skips near-identical frames (structural similarity)</li>
        <li><b>Speech delay compensation</b> — prefers frames just after new transcript text appears</li>
        <li><b>Minimum gap</b> — at least 10s between captures (adapts to 18s for 4h+ videos)</li>
        <li><b>Content scoring</b> — text density, keyword hits, math symbols</li>
        <li><b>Context window</b> — attaches surrounding transcript to each capture</li>
        <li><b>Adaptive threshold</b> — adjusts sensitivity based on video length</li>
        <li><b>Zero-capture floor</b> — force-captures best frames if &lt;3 captured</li>
        </ol>
        """)
        tabs.addTab(modes_tab, "Capture Modes")

        # --- Tab 3: Captions & Tags ---
        captions_tab = QTextEdit()
        captions_tab.setReadOnly(True)
        captions_tab.setHtml("""
        <h2>Captions & Tags</h2>

        <h3>Captions</h3>
        <p>Each screenshot has a <b>caption</b> field. Click a thumbnail, then type in the
        caption text box. This text appears <b>under the screenshot</b> in the exported PDF.
        Captions are pre-populated from the transcript text at that moment.</p>

        <h3>Tags</h3>
        <p>Tags help you categorize screenshots for later review.</p>
        <ul>
        <li>Select a tag from the dropdown (QUESTION, FORMULA, TRICK, IMPORTANT, EXAMPLE, DIAGRAM)</li>
        <li>Or type a custom tag</li>
        <li>Click <b>"+ Add Tag"</b> to attach it to the selected screenshot</li>
        <li>Tags appear in CSV export and can help with exam revision planning</li>
        </ul>

        <h3>Review Duplicates</h3>
        <p>Click <b>"Review Duplicates"</b> to open a side-by-side comparison of similar
        screenshots. You can delete the worse one while keeping the better version.</p>

        <h3>Reorder & Delete</h3>
        <p>Right-click any thumbnail for options: Move Left, Move Right, Go to timestamp, Delete.</p>
        """)
        tabs.addTab(captions_tab, "Captions & Tags")

        # --- Tab 4: Export Formats ---
        export_tab = QTextEdit()
        export_tab.setReadOnly(True)
        export_tab.setHtml("""
        <h2>Export Formats</h2>

        <h3>Quick Export (5 files)</h3>
        <ul>
        <li><b>Full PDF</b> — Complete PDF with cover, index, screenshots + captions + tags</li>
        <li><b>Visual Transcript PDF</b> — Transcript text + timestamp at top, screenshot below — ideal for multimodal AI (Gemini/GPT-4V/Claude Vision)</li>
        <li><b>AI Context .txt</b> — Timestamped text for LLM prompts ("summarize this lecture")</li>
        <li><b>Markdown .md</b> — Structured markdown with timestamps and screenshots referenced</li>
        <li><b>JSON .json</b> — Machine-readable structured data</li>
        </ul>

        <h3>Export All (13 formats)</h3>
        <ul>
        <li><b>Compressed PDF</b> — Smaller file size (JPEG quality 60) for sharing</li>
        <li><b>Split PDFs</b> — One PDF per chapter/topic chunk</li>
        <li><b>Clean Transcript .txt</b> — Pure text without timestamps</li>
        <li><b>NotebookLM sources</b> — CSV format importable into Google NotebookLM</li>
        <li><b>CSV Index</b> — Spreadsheet with timestamp, caption, tags, keywords</li>
        <li><b>Gemini-optimized .txt</b> — Structured text for Google Gemini prompts</li>
        <li><b>Ollama chunks</b> — Splits into small context windows for local LLMs</li>
        <li><b>Anki .apkg</b> — Flashcard deck (timestamp + screenshot → front; caption → back)</li>
        </ul>

        <p>All exports go to the <code>exports/</code> folder next to your project file.</p>
        """)
        tabs.addTab(export_tab, "Export Formats")

        # --- Tab 5: Settings ---
        settings_tab = QTextEdit()
        settings_tab.setReadOnly(True)
        settings_tab.setHtml("""
        <h2>Settings</h2>

        <table border='1' cellpadding='6' style='border-collapse: collapse;'>
        <tr bgcolor='#e0e0e0'><td><b>Setting</b></td><td><b>Description</b></td></tr>
        <tr><td><b>Sync Offset</b></td><td>Adjusts transcript timing (in seconds). Positive = transcript
            is ahead of video. Use when transcript doesn't align with the video.</td></tr>
        <tr><td><b>Auto-sync</b></td><td>Automatically finds the best sync offset by testing -30 to +30
            seconds and picking the one that lands on the most non-blank frames.</td></tr>
        <tr><td><b>Subject</b></td><td>Subject name (e.g., "Physics", "Mathematics") — appears on PDF cover.</td></tr>
        <tr><td><b>Min Gap</b></td><td>Minimum seconds between auto-captures (1–60).</td></tr>
        <tr><td><b>Score Threshold</b></td><td>Minimum quality score (0–100) for a frame to be captured.</td></tr>
        <tr><td><b>Start / End Time</b></td><td>Limit capture to a specific time range (e.g., skip intro).</td></tr>
        </table>

        <h3>Dark Mode</h3>
        <p>Toggle via the toolbar button. Affects the entire UI.</p>

        <h3>Autosave & Recovery</h3>
        <p>The project autosaves every 2 minutes. If the app crashes, you'll be prompted
        to recover on next launch.</p>
        """)
        tabs.addTab(settings_tab, "Settings")

        # --- Tab 6: Use Cases ---
        usecases_tab = QTextEdit()
        usecases_tab.setReadOnly(True)
        usecases_tab.setHtml("""
        <h2>Use Cases & Test Scenarios</h2>

        <h3>📘 Scenario 1: JEE/NEET Formula Revision</h3>
        <p><b>Problem:</b> 4-hour Physics lecture covering 50+ formulas. Finding key derivations later is hard.</p>
        <p><b>Solution:</b></p>
        <ol>
        <li>Load the video + transcript</li>
        <li>Run <b>Smart Auto</b> — the engine detects math symbols (∑, ∫, √, π) and keywords ("formula", "सूत्र")</li>
        <li>Tag important captures as <b>FORMULA</b> or <b>IMPORTANT</b></li>
        <li>Export to <b>PDF</b> — get a booklet with all formulas visible</li>
        <li>Export to <b>Anki</b> — get flashcards: formula screenshot → front, formula name → back</li>
        </ol>

        <h3>📘 Scenario 2: 10-hour Marathon Session</h3>
        <p><b>Problem:</b> All-day revision video, too long to rewatch. 8GB RAM limit.</p>
        <p><b>Solution:</b></p>
        <ol>
        <li>Frame engine <b>adapts gap</b> to 18s automatically for long videos</li>
        <li>All frames stored as <b>JPEG on disk</b> — never fills RAM</li>
        <li>Set <b>Start/End Time</b> in settings to split into morning/afternoon sessions</li>
        <li>Export <b>Split PDFs</b> — one PDF per topic/hour</li>
        </ol>

        <h3>📘 Scenario 3: Hindi/English Mixed Lecture</h3>
        <p><b>Problem:</b> Teacher uses Hinglish (Hindi words in English script). Normal OCR fails.</p>
        <p><b>Solution:</b></p>
        <ol>
        <li>Transcript parser auto-detects Hindi and handles Devanagari + transliterated Hinglish</li>
        <li>Font system downloads <b>Noto Sans Devanagari</b> — Hindi text renders correctly in PDF</li>
        <li>Keyword system knows <b>both</b> English and Hindi exam keywords ("important", "महत्वपूर्ण", "zaroori")</li>
        </ol>

        <h3>📘 Scenario 4: No Transcript Available</h3>
        <p><b>Problem:</b> The video has no caption file.</p>
        <p><b>Solution:</b></p>
        <ol>
        <li>Select <b>Change Detection</b> mode — captures frames purely on visual change</li>
        <li>Or use <b>Manual</b> mode + press <b>C</b> at key moments while watching</li>
        <li>Add <b>captions manually</b> after capture</li>
        <li>Export still works — just without transcript context</li>
        </ol>

        <h3>📘 Scenario 5: Last-Minute Exam Revision</h3>
        <p><b>Problem:</b> Exam tomorrow, need condensed study material from 20 lectures.</p>
        <p><b>Solution:</b></p>
        <ol>
        <li>Quick Export each lecture → get 4 files per lecture</li>
        <li>The <b>AI Context .txt</b> files can be pasted to ChatGPT/Gemini: "Summarize this lecture"</li>
        <li><b>Markdown</b> files can be merged into a single revision document</li>
        <li><b>Anki deck</b> for spaced-repetition practice</li>
        </ol>

        <h3>📘 Scenario 6: YouTube Live Stream Recording</h3>
        <p><b>Problem:</b> Video has PiP webcam (bottom-right corner) and scrolling ticker (bottom).</p>
        <p><b>Solution:</b></p>
        <ol>
        <li>Frame engine automatically <b>masks</b> bottom 15% and both bottom corners before scoring</li>
        <li>The PiP and ticker are ignored — only the main slide content is evaluated</li>
        </ol>
        """)
        tabs.addTab(usecases_tab, "Use Cases")

        layout.addWidget(tabs)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec_()

    def _show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        layout = QFormLayout(dialog)

        sync_spin = QSpinBox()
        sync_spin.setRange(SYNC_OFFSET_MIN, SYNC_OFFSET_MAX)
        sync_spin.setValue(self.session.get("sync_offset_seconds", 0))
        sync_spin.setSuffix(" seconds")
        layout.addRow("Sync Offset:", sync_spin)

        auto_sync_btn = QPushButton("Auto-sync")
        auto_sync_btn.clicked.connect(lambda: self._auto_sync(sync_spin))
        layout.addRow("", auto_sync_btn)

        subject_edit = QLineEdit(self.session.get("subject", ""))
        layout.addRow("Subject:", subject_edit)

        min_gap_spin = QSpinBox()
        min_gap_spin.setRange(1, 60)
        min_gap_spin.setValue(MIN_GAP_DEFAULT)
        min_gap_spin.setSuffix(" seconds")
        layout.addRow("Min Gap:", min_gap_spin)

        score_spin = QSpinBox()
        score_spin.setRange(0, 100)
        score_spin.setValue(SCORE_THRESHOLD_CAPTURE)
        layout.addRow("Score Threshold:", score_spin)

        start_time = QSpinBox()
        start_time.setRange(0, 86400)
        start_time.setValue(self.session.get("start_time_sec", 0))
        start_time.setSuffix(" sec")
        layout.addRow("Start Time:", start_time)

        end_time = QSpinBox()
        end_time.setRange(0, 86400)
        end_time.setValue(self.session.get("end_time_sec", 86400))
        end_time.setSuffix(" sec")
        layout.addRow("End Time:", end_time)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec_():
            self.session["sync_offset_seconds"] = sync_spin.value()
            self.session["subject"] = subject_edit.text()
            self.session["start_time_sec"] = start_time.value()
            self.session["end_time_sec"] = end_time.value()
            self.is_modified = True
            self.project_manager.set_dirty()

    def _auto_sync(self, sync_spin):
        if not self.transcript_entries or len(self.transcript_entries) < 3:
            QMessageBox.information(self, "Auto-sync", "Need at least 3 transcript entries.")
            return
        if not self._cv2_cap or not self._cv2_cap.isOpened():
            QMessageBox.information(self, "Auto-sync", "Video must be loaded.")
            return
        offsets_tested = []
        for offset in range(-30, 31, 2):
            score = 0
            for entry in self.transcript_entries[:3]:
                ts = entry["start_sec"] + offset
                if ts < 0:
                    continue
                self._cv2_cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
                ret, frame = self._cv2_cap.read()
                if ret and frame is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    laplacian = cv2.Laplacian(gray, cv2.CV_64F).var()
                    if laplacian > 80:
                        score += 1
            offsets_tested.append((offset, score))
        best = max(offsets_tested, key=lambda x: x[1])
        sync_spin.setValue(best[0])
        QMessageBox.information(self, "Auto-sync",
                                 f"Suggested offset: {best[0]} seconds "
                                 f"(confidence: {best[1]}/3)")

    def _on_autosave(self):
        if self.is_modified and self.session:
            self.session["screenshots"] = self.captured_screenshots
            self.session["autosave_timestamp"] = datetime.now().isoformat()
            self.project_manager._autosave()

    def _prompt_recovery(self, recovery_data):
        info = self.project_manager.get_recovery_info(recovery_data)
        if info is None:
            return
        msg = (
            f"Resume previous session?\n\n"
            f"Video: {info['video_filename']}\n"
            f"Screenshots: {info['screenshot_count']}\n"
            f"Last saved: {info['timestamp']}\n"
            f"Subject: {info['subject']}"
        )
        reply = QMessageBox.question(
            self, "Recovery Found", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.project_manager.update_session_from_recovery(recovery_data)
            self._on_project_loaded(recovery_data)
        else:
            self.project_manager.clear_recovery()

    def closeEvent(self, event):
        if self.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if reply == QMessageBox.Save:
                self._save_project()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
                return

        if self._cv2_cap:
            self._cv2_cap.release()
        self.media_player.stop()
        self.project_manager.disable_autosave()
        event.accept()
