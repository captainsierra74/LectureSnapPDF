import os
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QLabel, QProgressBar,
    QGroupBox, QFileDialog, QScrollArea, QWidget, QMessageBox,
    QDialogButtonBox, QTextEdit, QGridLayout
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont

from utils import setup_logging, format_timestamp_hms, sanitize_filename


EXPORT_FORMATS = [
    ("full_pdf", "Full Quality PDF (*_full.pdf)", True),
    ("compressed_pdf", "Compressed PDF (*_compressed.pdf)", True),
    ("split_pdfs", "Split PDFs (*_part1.pdf, *_part2.pdf, ...)", True),
    ("ai_context_txt", "AI Context Text (*_AI_context.txt)", True),
    ("study_notes_md", "Markdown Notes (*_study_notes.md)", True),
    ("json_data", "JSON Structured Data (*_data.json)", True),
    ("transcript_clean", "Clean Transcript (*_transcript_clean.txt)", True),
    ("notebooklm_sources", "NotebookLM Sources (folder)", True),
    ("csv_index", "CSV Index (*_index.csv)", True),
    ("gemini_text", "Gemini Optimized Text (*_gemini.txt)", True),
    ("ollama_chunks", "Ollama Chunks (folder)", True),
    ("anki_apkg", "Anki Flashcards (*_anki.apkg)", True),
    ("visual_transcript_pdf", "Visual Transcript PDF (*_visual_transcript.pdf)", True),
    ("screenshots", "Screenshots Folder", True),
]

EXAM_TARGETS = ["General", "SBI PO", "IBPS PO", "SSC CGL", "UPSC", "Other"]


class ExportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, pdf_builder, screenshots, metadata, transcript_data,
                 keyword_hits, output_dir, base_name, formats_to_generate):
        super().__init__()
        self.builder = pdf_builder
        self.screenshots = screenshots
        self.metadata = metadata
        self.transcript_data = transcript_data
        self.keyword_hits = keyword_hits
        self.output_dir = output_dir
        self.base_name = base_name
        self.formats_to_generate = formats_to_generate
        self.results = []

    def run(self):
        total = len(self.formats_to_generate)
        for idx, fmt in enumerate(self.formats_to_generate):
            self.progress.emit(idx, total, f"Generating {fmt}...")
            try:
                self._generate_format(fmt)
            except Exception as e:
                self.error.emit(f"{fmt}: {e}")
        self.finished.emit({"files": self.results, "output_dir": self.output_dir})

    def _generate_format(self, fmt):
        if fmt == "full_pdf":
            path = os.path.join(self.output_dir, f"{self.base_name}_full.pdf")
            ok = self.builder.build_full_pdf(self.screenshots, self.metadata, path)
            if ok:
                self.results.append(("Full PDF", path, os.path.getsize(path)))

        elif fmt == "compressed_pdf":
            path = os.path.join(self.output_dir, f"{self.base_name}_compressed.pdf")
            ok = self.builder.build_compressed_pdf(self.screenshots, self.metadata, path)
            if ok:
                self.results.append(("Compressed PDF", path, os.path.getsize(path)))

        elif fmt == "split_pdfs":
            parts = self.builder.build_split_pdfs(self.screenshots, self.metadata,
                                                   self.output_dir, self.base_name)
            for p in parts:
                if p["success"]:
                    self.results.append((f"Split PDF Part {p['part']}",
                                          p["path"], os.path.getsize(p["path"])))

        elif fmt == "ai_context_txt":
            path = os.path.join(self.output_dir, f"{self.base_name}_AI_context.txt")
            self.builder.build_ai_context_txt(self.screenshots, self.metadata, path)
            self.results.append(("AI Context", path, os.path.getsize(path)))

        elif fmt == "study_notes_md":
            path = os.path.join(self.output_dir, f"{self.base_name}_study_notes.md")
            self.builder.build_markdown(self.screenshots, self.metadata, path)
            self.results.append(("Markdown", path, os.path.getsize(path)))

        elif fmt == "json_data":
            path = os.path.join(self.output_dir, f"{self.base_name}_data.json")
            self.builder.build_json_export(self.screenshots, self.metadata,
                                            self.transcript_data, self.keyword_hits, path)
            self.results.append(("JSON", path, os.path.getsize(path)))

        elif fmt == "transcript_clean":
            path = os.path.join(self.output_dir, f"{self.base_name}_transcript_clean.txt")
            self.builder.build_transcript_clean(self.transcript_data, path)
            self.results.append(("Clean Transcript", path, os.path.getsize(path)))

        elif fmt == "notebooklm_sources":
            created = self.builder.build_notebooklm_sources(self.screenshots, self.output_dir)
            total_size = sum(os.path.getsize(f) for f in created)
            self.results.append(("NotebookLM Sources", created[0] if created else "", total_size))

        elif fmt == "csv_index":
            path = os.path.join(self.output_dir, f"{self.base_name}_index.csv")
            self.builder.build_csv_index(self.screenshots, path)
            self.results.append(("CSV Index", path, os.path.getsize(path)))

        elif fmt == "gemini_text":
            path = os.path.join(self.output_dir, f"{self.base_name}_gemini.txt")
            self.builder.build_gemini_text(self.screenshots, self.metadata, path)
            self.results.append(("Gemini Text", path, os.path.getsize(path)))

        elif fmt == "ollama_chunks":
            self.builder.build_ollama_chunks(self.screenshots, self.metadata, self.output_dir)
            chunk_dir = os.path.join(self.output_dir, "ollama_chunks")
            total_size = 0
            for root, dirs, files in os.walk(chunk_dir):
                for f in files:
                    total_size += os.path.getsize(os.path.join(root, f))
            self.results.append(("Ollama Chunks", chunk_dir, total_size))

        elif fmt == "anki_apkg":
            path = os.path.join(self.output_dir, f"{self.base_name}_anki.apkg")
            ok = self.builder.build_anki_apkg(self.screenshots, path)
            if ok:
                self.results.append(("Anki Deck", path, os.path.getsize(path)))

        elif fmt == "visual_transcript_pdf":
            path = os.path.join(self.output_dir, f"{self.base_name}_visual_transcript.pdf")
            ok = self.builder.build_visual_transcript_pdf(self.screenshots, self.metadata, path)
            if ok:
                self.results.append(("Visual Transcript PDF", path, os.path.getsize(path)))

        elif fmt == "screenshots":
            ss_dir = os.path.join(self.output_dir, "screenshots")
            os.makedirs(ss_dir, exist_ok=True)
            total_size = 0
            for ss in self.screenshots:
                src = ss.get("frame_path", "")
                if src and os.path.isfile(src):
                    ts = format_timestamp_for_filename(ss.get("timestamp_sec", 0))
                    cap = sanitize_filename(ss.get("caption", ""))[:20]
                    ext = os.path.splitext(src)[1]
                    dst = os.path.join(ss_dir, f"{ss.get('id', 0):03d}_{ts}_{cap}{ext}")
                    try:
                        import shutil
                        shutil.copy2(src, dst)
                        total_size += os.path.getsize(dst)
                    except IOError:
                        pass
            self.results.append(("Screenshots", ss_dir, total_size))


def format_timestamp_for_filename(sec):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}m{s:02d}s"


class ExportDialog(QDialog):
    def __init__(self, pdf_builder, screenshots, metadata, transcript_data,
                 keyword_hits, parent=None):
        super().__init__(parent)
        self.builder = pdf_builder
        self.screenshots = screenshots
        self.metadata = metadata
        self.transcript_data = transcript_data
        self.keyword_hits = keyword_hits
        self.logger = setup_logging()
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Export LectureSnapPDF Package")
        self.setMinimumSize(600, 500)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.subject_edit = QLineEdit(self.metadata.get("subject", ""))
        form.addRow("Subject/Chapter:", self.subject_edit)

        self.exam_combo = QComboBox()
        self.exam_combo.addItems(EXAM_TARGETS)
        exam_val = self.metadata.get("exam_target", "General")
        idx = EXAM_TARGETS.index(exam_val) if exam_val in EXAM_TARGETS else 0
        self.exam_combo.setCurrentIndex(idx)
        form.addRow("Exam Target:", self.exam_combo)
        layout.addLayout(form)

        formats_group = QGroupBox("Export Formats")
        formats_layout = QGridLayout()
        self.format_checks = {}
        for i, (key, label, default) in enumerate(EXPORT_FORMATS):
            cb = QCheckBox(label)
            cb.setChecked(default)
            formats_layout.addWidget(cb, i // 2, i % 2)
            self.format_checks[key] = cb
        formats_group.setLayout(formats_layout)
        layout.addWidget(formats_group)

        output_group = QGroupBox("Output Location")
        output_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        default_dir = os.path.join(
            os.path.expanduser("~"), "Desktop",
            f"LectureSnapPDF_Export_{datetime.now().strftime('%Y%m%d')}"
        )
        self.output_path_edit.setText(default_dir)
        output_layout.addWidget(self.output_path_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(browse_btn)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        info_label = QLabel(
            f"Screenshots: {len(self.screenshots)} | "
            f"Est. PDF pages: {len(self.screenshots) + 2} | "
            f"Est. size: {self._estimate_size()}"
        )
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()
        quick_btn = QPushButton("Quick Export (PDF + TXT + MD + JSON)")
        quick_btn.clicked.connect(self._quick_export)
        quick_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px;")
        export_all_btn = QPushButton("Export All")
        export_all_btn.clicked.connect(self._export_all)
        export_all_btn.setStyleSheet("background-color: #4CAF50; color: white; padding: 8px;")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(quick_btn)
        btn_layout.addWidget(export_all_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if path:
            self.output_path_edit.setText(path)

    def _estimate_size(self):
        count = len(self.screenshots)
        if count == 0:
            return "< 1 MB"
        est_mb = count * 0.3
        if est_mb < 1:
            return f"~{est_mb * 1000:.0f} KB"
        return f"~{est_mb:.1f} MB"

    def _quick_export(self):
        self._run_export(["full_pdf", "visual_transcript_pdf", "ai_context_txt", "study_notes_md", "json_data"])

    def _export_all(self):
        selected = [k for k, cb in self.format_checks.items() if cb.isChecked()]
        self._run_export(selected)

    def _run_export(self, formats):
        subject = self.subject_edit.text().strip()
        exam = self.exam_combo.currentText()
        base_name = sanitize_filename(subject if subject else "lecture_notes")
        output_dir = self.output_path_edit.text().strip()

        if not output_dir:
            QMessageBox.warning(self, "Error", "Please select an output folder.")
            return

        metadata = dict(self.metadata)
        metadata["subject"] = subject
        metadata["exam_target"] = exam
        metadata["generated"] = datetime.now().strftime("%Y-%m-%d")
        metadata["total_screenshots"] = len(self.screenshots)

        os.makedirs(output_dir, exist_ok=True)

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(formats))
        self.progress_bar.setValue(0)

        self._worker = ExportWorker(
            self.builder, self.screenshots, metadata,
            self.transcript_data, self.keyword_hits,
            output_dir, base_name, formats
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        self.builder.build_which_file_to_use(output_dir)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(0)

    @pyqtSlot(int, int, str)
    def _on_progress(self, current, total, message):
        self.status_label.setText(message)
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    @pyqtSlot(dict)
    def _on_finished(self, result):
        self.progress_bar.setVisible(False)
        files = result.get("files", [])
        output_dir = result.get("output_dir", "")

        summary = QDialog(self)
        summary.setWindowTitle("Export Complete")
        summary.setMinimumSize(500, 400)
        layout = QVBoxLayout(summary)

        layout.addWidget(QLabel(f"<b>Export complete! {len(files)} files generated.</b>"))
        layout.addWidget(QLabel(f"Location: {output_dir}"))

        text = QTextEdit()
        text.setReadOnly(True)
        summary_text = f"{'Format':<25} {'Size':<12} {'File':<40}\n"
        summary_text += "-" * 77 + "\n"
        for name, path, size in sorted(files, key=lambda x: x[0]):
            size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
            fname = os.path.basename(path) if path else "(folder)"
            summary_text += f"{name:<25} {size_str:<12} {fname:<40}\n"
        text.setText(summary_text)
        layout.addWidget(text)

        btn_layout = QHBoxLayout()
        open_btn = QPushButton("Open Export Folder")
        open_btn.clicked.connect(lambda: os.startfile(output_dir))
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(summary.accept)
        btn_layout.addWidget(open_btn)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        summary.exec_()
        self.accept()

    @pyqtSlot(str)
    def _on_error(self, msg):
        self.logger.error("Export error: %s", msg)
        self.status_label.setText(f"Error: {msg}")
