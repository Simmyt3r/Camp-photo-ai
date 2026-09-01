"""Batch processing: folder pickers + live progress via a background
QThread (section 18: never freeze the GUI during a large batch)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.ui.workers import ProcessingWorker


class ProcessingPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._worker: ProcessingWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        header = QLabel("Process Photos")
        header.setObjectName("pageTitle")
        layout.addWidget(header)

        self.input_edit = self._folder_row("Input folder", layout)
        self.output_edit = self._folder_row("Output folder", layout, default=context.settings.output_dir)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self._start)
        controls.addWidget(self.start_btn)

        hint = QLabel("(unchanged photos from a previous run are skipped automatically)")
        hint.setObjectName("hintLabel")
        controls.addWidget(hint)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("statusLabel")
        layout.addWidget(self.stats_label)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

    def _folder_row(self, label: str, parent_layout: QVBoxLayout, default: str = "") -> QLineEdit:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        edit = QLineEdit(default)
        row.addWidget(edit, stretch=1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(lambda: self._browse(edit))
        row.addWidget(browse)
        parent_layout.addLayout(row)
        return edit

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder", edit.text() or "")
        if path:
            edit.setText(path)

    def _start(self) -> None:
        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip()
        if not input_text or not Path(input_text).is_dir():
            self.log_view.append("Input folder does not exist.")
            return
        if not output_text:
            self.log_view.append("Output folder is required.")
            return

        self.start_btn.setEnabled(False)
        self.log_view.clear()
        self.log_view.append(f"Processing {input_text} -> {output_text} ...")
        self.progress_bar.setValue(0)

        self._worker = ProcessingWorker(
            self.context.settings, Path(input_text), Path(output_text),
            self.context.embedding_service, resume=True,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stats, filename: str) -> None:
        if stats.total_photos > 0:
            self.progress_bar.setValue(int(100 * stats.processed / stats.total_photos))
        self.stats_label.setText(
            f"{stats.processed}/{stats.total_photos} photos | {stats.images_per_second:.1f} img/s | "
            f"auto-matched: {stats.auto_matched}  review: {stats.review}  "
            f"unmatched: {stats.unmatched}  errors: {stats.errors} | "
            f"ETA: {int(stats.estimated_remaining_seconds)}s"
        )

    def _on_finished(self, stats) -> None:
        self.start_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        self.log_view.append(
            f"Done. {stats.processed} photos, {stats.faces_detected} faces, "
            f"{stats.auto_matched} auto-matched, {stats.review} sent to review, "
            f"{stats.unmatched} unmatched, {stats.errors} errors."
        )

    def _on_failed(self, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.log_view.append(f"Processing failed: {message}")

    def on_shown(self) -> None:
        pass
