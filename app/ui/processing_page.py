"""Guided batch photo processing with visual progress and operator feedback."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QStyle, QTextEdit, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.ui.activity import notify_activity
from app.ui.widgets import Card, DropZone, PageHeader, StatTile, WorkflowSteps
from app.ui.workers import ProcessingWorker


class ProcessingPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._worker: ProcessingWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(16)

        layout.addWidget(PageHeader(
            "Process Photos",
            "Choose an event folder, run local face matching, then review uncertain results.",
        ))
        layout.addWidget(WorkflowSteps(["Choose folder", "AI processing", "Review exceptions"], current=0))

        folders_card = Card(
            "Event photos",
            "Drop a folder here or browse manually. Subfolders are scanned automatically.",
        )
        self.drop_zone = DropZone()
        self.drop_zone.directory_dropped.connect(self._set_input_folder)
        folders_card.body.addWidget(self.drop_zone)

        form = QFormLayout()
        form.setSpacing(10)
        self.input_edit = self._folder_row(
            form, "Input folder", context.settings.input_dir
        )
        self.output_edit = self._folder_row(
            form, "Output folder", context.settings.output_dir
        )
        folders_card.body.addLayout(form)
        layout.addWidget(folders_card)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("Start processing")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_btn.setMinimumWidth(160)
        self.start_btn.clicked.connect(self._start)
        controls.addWidget(self.start_btn)

        reset_btn = QPushButton("Use settings defaults")
        reset_btn.setObjectName("ghostButton")
        reset_btn.clicked.connect(self._restore_defaults)
        controls.addWidget(reset_btn)

        self.details_btn = QPushButton("View technical details")
        self.details_btn.setObjectName("ghostButton")
        self.details_btn.clicked.connect(self._toggle_log)
        controls.addWidget(self.details_btn)

        controls.addStretch(1)
        hint = QLabel("Unchanged photos are skipped automatically.")
        hint.setObjectName("hintLabel")
        controls.addWidget(hint)
        layout.addLayout(controls)

        progress_card = Card("Current run")
        progress_row = QHBoxLayout()
        progress_row.setSpacing(14)

        self.preview_label = QLabel("Photo preview")
        self.preview_label.setObjectName("reviewPreview")
        self.preview_label.setFixedSize(190, 120)
        self.preview_label.setAlignment(Qt.AlignCenter)
        progress_row.addWidget(self.preview_label)

        progress_info = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_info.addWidget(self.progress_bar)

        self.stats_label = QLabel("Ready. Choose an input folder and start processing.")
        self.stats_label.setObjectName("infoBanner")
        self.stats_label.setWordWrap(True)
        progress_info.addWidget(self.stats_label)

        self.current_file_label = QLabel("")
        self.current_file_label.setObjectName("cardHint")
        self.current_file_label.setWordWrap(True)
        progress_info.addWidget(self.current_file_label)
        progress_info.addStretch(1)
        progress_row.addLayout(progress_info, stretch=1)

        progress_card.body.addLayout(progress_row)
        layout.addWidget(progress_card)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.processed_tile = StatTile("Processed", "0")
        self.matched_tile = StatTile("Auto-matched", "0")
        self.review_tile = StatTile("Needs review", "0")
        self.errors_tile = StatTile("Errors", "0")
        for tile in (
            self.processed_tile,
            self.matched_tile,
            self.review_tile,
            self.errors_tile,
        ):
            stats_row.addWidget(tile)
        layout.addLayout(stats_row)

        self.log_card = Card("Technical run log")
        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(130)
        self.log_card.body.addWidget(self.log_view)
        self.log_card.hide()
        layout.addWidget(self.log_card)

        layout.addStretch(1)

    def _set_status(self, message: str, kind: str = "info") -> None:
        names = {
            "info": "infoBanner",
            "success": "successBanner",
            "warning": "warningBanner",
            "error": "errorBanner",
        }
        self.stats_label.setObjectName(names.get(kind, "infoBanner"))
        self.stats_label.setText(message)
        self.stats_label.style().unpolish(self.stats_label)
        self.stats_label.style().polish(self.stats_label)

    def _folder_row(self, form: QFormLayout, label: str, default: str = "") -> QLineEdit:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(default)
        row.addWidget(edit, stretch=1)
        browse = QPushButton("Browse")
        browse.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        browse.clicked.connect(lambda: self._browse(edit))
        row.addWidget(browse)
        container = QWidget()
        container.setLayout(row)
        form.addRow(label, container)
        return edit

    def _browse(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", edit.text() or ""
        )
        if path:
            edit.setText(path)
            if edit is self.input_edit:
                notify_activity(f"Event folder selected: {Path(path).name}", "info")

    def _set_input_folder(self, path: str) -> None:
        self.input_edit.setText(path)
        notify_activity(f"Event folder selected: {Path(path).name}", "info")

    def _toggle_log(self) -> None:
        visible = not self.log_card.isVisible()
        self.log_card.setVisible(visible)
        self.details_btn.setText("Hide technical details" if visible else "View technical details")

    def _restore_defaults(self) -> None:
        self.input_edit.setText(self.context.settings.input_dir)
        self.output_edit.setText(self.context.settings.output_dir)
        self._set_status("Folder paths restored from Settings.")

    def _reset_tiles(self) -> None:
        self.processed_tile.set_value("0")
        self.matched_tile.set_value("0")
        self.review_tile.set_value("0")
        self.errors_tile.set_value("0")

    def _start(self) -> None:
        input_text = self.input_edit.text().strip()
        output_text = self.output_edit.text().strip()

        if not input_text or not Path(input_text).is_dir():
            self._set_status("Choose a valid input folder before processing.", "warning")
            notify_activity("Choose a valid event photo folder.", "warning")
            return
        if not output_text:
            self._set_status("Choose an output folder before processing.", "warning")
            notify_activity("Choose an output folder.", "warning")
            return

        output_path = Path(output_text)
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._set_status(f"Could not create the output folder: {exc}", "error")
            notify_activity(f"Could not create output folder: {exc}", "error")
            return

        self.start_btn.setEnabled(False)
        self._reset_tiles()
        self.log_view.clear()
        self.log_view.append(f"Input:  {input_text}")
        self.log_view.append(f"Output: {output_text}")
        self.log_view.append("Starting local processing...")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.current_file_label.clear()
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Preparing…")
        self._set_status("Preparing face model and processing pipeline...")
        notify_activity("Photo processing started.", "info")

        self._worker = ProcessingWorker(
            self.context.settings,
            Path(input_text),
            output_path,
            self.context.embedding_service,
            resume=True,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.model_progress.connect(self._on_model_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_model_progress(self, downloaded: int, total, message: str) -> None:
        if total and total > 1:
            percent = int(downloaded * 100 / total)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self._set_status(
                f"{message} {downloaded_mb:.1f}/{total_mb:.1f} MB ({percent}%)"
            )
        else:
            self.progress_bar.setRange(0, 0)
            self._set_status(message)

    def _on_progress(self, stats, filename: str) -> None:
        self.progress_bar.setRange(0, 100)
        if stats.total_photos > 0:
            self.progress_bar.setValue(
                int(100 * stats.processed / stats.total_photos)
            )

        self.processed_tile.set_value(f"{stats.processed:,}/{stats.total_photos:,}")
        self.matched_tile.set_value(f"{stats.auto_matched:,}")
        self.review_tile.set_value(f"{stats.review:,}")
        self.errors_tile.set_value(f"{stats.errors:,}")

        path = Path(filename)
        self.current_file_label.setText(f"Current file: {path.name}")
        if path.is_file():
            preview = QPixmap(str(path))
            if not preview.isNull():
                self.preview_label.setText("")
                self.preview_label.setPixmap(
                    preview.scaled(190, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        self._set_status(
            f"{stats.images_per_second:.1f} images/sec • "
            f"{stats.unmatched:,} unmatched • "
            f"ETA {int(stats.estimated_remaining_seconds)} sec"
        )

    def _on_finished(self, stats) -> None:
        self.start_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.current_file_label.clear()
        message = (
            f"Processing complete. {stats.auto_matched:,} matched automatically, "
            f"{stats.review:,} need review, {stats.unmatched:,} unmatched."
        )
        self._set_status(message, "success")
        notify_activity(message, "success")
        self.log_view.append(
            f"Completed: {stats.processed} photos, {stats.faces_detected} faces, "
            f"{stats.auto_matched} auto-matched, {stats.review} review, "
            f"{stats.unmatched} unmatched, {stats.errors} errors."
        )

    def _on_failed(self, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self._set_status(f"Processing failed: {message}", "error")
        self.log_view.append(f"ERROR: {message}")
        notify_activity(f"Processing failed: {message}", "error")

    def on_shown(self) -> None:
        if not self.input_edit.text().strip():
            self.input_edit.setText(self.context.settings.input_dir)
        if not self.output_edit.text().strip():
            self.output_edit.setText(self.context.settings.output_dir)
