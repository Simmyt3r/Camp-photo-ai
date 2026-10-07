"""Guided batch photo processing with clear progress and run feedback."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.ui.widgets import Card, PageHeader, StatTile
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

        folders_card = Card(
            "Folders",
            "Input is scanned recursively. Output keeps the participant-based folder structure.",
        )
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
        self.start_btn.setMinimumWidth(150)
        self.start_btn.clicked.connect(self._start)
        controls.addWidget(self.start_btn)

        reset_btn = QPushButton("Use settings defaults")
        reset_btn.setObjectName("ghostButton")
        reset_btn.clicked.connect(self._restore_defaults)
        controls.addWidget(reset_btn)

        controls.addStretch(1)
        hint = QLabel("Unchanged photos are skipped automatically.")
        hint.setObjectName("hintLabel")
        controls.addWidget(hint)
        layout.addLayout(controls)

        progress_card = Card("Current run")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_card.body.addWidget(self.progress_bar)

        self.stats_label = QLabel("Ready. Choose an input folder and start processing.")
        self.stats_label.setObjectName("infoBanner")
        self.stats_label.setWordWrap(True)
        progress_card.body.addWidget(self.stats_label)

        self.current_file_label = QLabel("")
        self.current_file_label.setObjectName("cardHint")
        self.current_file_label.setWordWrap(True)
        progress_card.body.addWidget(self.current_file_label)
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

        log_card = Card("Run log")
        self.log_view = QTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(150)
        log_card.body.addWidget(self.log_view)
        layout.addWidget(log_card, stretch=1)

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
            return
        if not output_text:
            self._set_status("Choose an output folder before processing.", "warning")
            return

        output_path = Path(output_text)
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._set_status(f"Could not create the output folder: {exc}", "error")
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
        self._set_status("Preparing face model and processing pipeline...")

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

        self.processed_tile.set_value(
            f"{stats.processed:,}/{stats.total_photos:,}"
        )
        self.matched_tile.set_value(f"{stats.auto_matched:,}")
        self.review_tile.set_value(f"{stats.review:,}")
        self.errors_tile.set_value(f"{stats.errors:,}")

        self.current_file_label.setText(f"Current file: {filename}")
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
        self._set_status(
            f"Processing complete. {stats.auto_matched:,} matched automatically, "
            f"{stats.review:,} need review, {stats.unmatched:,} unmatched.",
            "success",
        )
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

    def on_shown(self) -> None:
        if not self.input_edit.text().strip():
            self.input_edit.setText(self.context.settings.input_dir)
        if not self.output_edit.text().strip():
            self.output_edit.setText(self.context.settings.output_dir)
