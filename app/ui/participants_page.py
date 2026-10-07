"""Participant management: search, edit, export, reprocess, and delete."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QPushButton, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.database.db import get_session
from app.database.models import Participant, ProcessingRun, ReferenceEmbedding
from app.services.participant_management import (
    count_matched_photos, export_participant_photos, sanitize_export_filename,
    search_participants, update_participant_metadata,
)
from app.services.review_service import delete_participant
from app.ui.image_utils import bytes_to_qpixmap
from app.ui.widgets import Card, PageHeader
from app.ui.workers import ProcessingWorker


class ReprocessDialog(QDialog):
    def __init__(self, context: AppContext, participant: Participant, default_input_dir: str, parent=None):
        super().__init__(parent)
        self.context = context
        self.participant = participant
        self._worker: ProcessingWorker | None = None
        self.setWindowTitle(f"Reprocess • {participant.full_name}")
        self.resize(560, 320)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(PageHeader(
            "Reprocess participant",
            f"Scan photos again for {participant.full_name} ({participant.participant_id}) only. "
            "Previously processed files are evaluated again.",
        ))

        card = Card("Folders")
        form = QFormLayout()
        self.input_edit = QLineEdit(default_input_dir)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_edit, stretch=1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse)
        input_row.addWidget(browse_btn)
        input_container = QWidget()
        input_container.setLayout(input_row)
        form.addRow("Input folder", input_container)

        self.output_edit = QLineEdit(context.settings.output_dir)
        form.addRow("Output folder", self.output_edit)
        card.body.addLayout(form)
        layout.addWidget(card)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Ready to reprocess.")
        self.status_label.setObjectName("infoBanner")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        self.start_btn = QPushButton("Start reprocessing")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self._start)
        buttons.addButton(self.start_btn, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

    def _set_status(self, text: str, kind: str = "info") -> None:
        names = {
            "info": "infoBanner",
            "success": "successBanner",
            "warning": "warningBanner",
            "error": "errorBanner",
        }
        self.status_label.setObjectName(names.get(kind, "infoBanner"))
        self.status_label.setText(text)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select folder", self.input_edit.text() or ""
        )
        if path:
            self.input_edit.setText(path)

    def _start(self) -> None:
        input_dir = self.input_edit.text().strip()
        output_dir = self.output_edit.text().strip()
        if not input_dir or not Path(input_dir).is_dir():
            self._set_status("Choose a valid input folder first.", "warning")
            return
        if not output_dir:
            self._set_status("Choose an output folder first.", "warning")
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self._set_status("Preparing model and reprocessing photos...")

        self._worker = ProcessingWorker(
            self.context.settings,
            Path(input_dir),
            Path(output_dir),
            self.context.embedding_service,
            resume=False,
            participant_filter={self.participant.participant_id},
        )
        self._worker.model_progress.connect(self._on_model_progress)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_model_progress(self, downloaded: int, total, message: str) -> None:
        if total and total > 1:
            percent = int(downloaded * 100 / total)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(percent)
            self._set_status(f"{message} {percent}%")
        else:
            self.progress_bar.setRange(0, 0)
            self._set_status(message)

    def _on_progress(self, stats, filename: str) -> None:
        self.progress_bar.setRange(0, 100)
        if stats.total_photos > 0:
            self.progress_bar.setValue(int(100 * stats.processed / stats.total_photos))
        self._set_status(
            f"{stats.processed}/{stats.total_photos} • {Path(filename).name}"
        )

    def _on_finished(self, stats) -> None:
        self.start_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._set_status(
            f"Done. {stats.auto_matched} auto-matched, {stats.review} need review, "
            f"{stats.unmatched} unmatched.",
            "success",
        )

    def _on_failed(self, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self._set_status(f"Reprocessing failed: {message}", "error")


class ParticipantsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._current_participant_id: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 26, 28, 26)
        outer.setSpacing(16)
        outer.addWidget(PageHeader(
            "Participants",
            "Search registered people, edit metadata, export their matched photos, or reprocess them.",
        ))

        body = QHBoxLayout()
        body.setSpacing(14)

        list_card = Card("People")
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Name, participant ID, registration number, or group")
        self.search_edit.returnPressed.connect(self.refresh)
        search_row.addWidget(self.search_edit, stretch=1)

        search_btn = QPushButton("Search")
        search_btn.setObjectName("secondaryButton")
        search_btn.clicked.connect(self.refresh)
        search_row.addWidget(search_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("ghostButton")
        clear_btn.clicked.connect(self._clear_search)
        search_row.addWidget(clear_btn)
        list_card.body.addLayout(search_row)

        self.result_count = QLabel("")
        self.result_count.setObjectName("cardHint")
        list_card.body.addWidget(self.result_count)

        self.results_list = QListWidget()
        self.results_list.currentItemChanged.connect(self._on_selection_changed)
        list_card.body.addWidget(self.results_list, stretch=1)
        body.addWidget(list_card, stretch=1)

        detail_card = Card(
            "Participant details",
            "Select a participant on the left to view and manage their record.",
        )

        self.thumbnails_row = QHBoxLayout()
        self.thumbnails_row.setSpacing(8)
        detail_card.body.addLayout(self.thumbnails_row)

        self.info_label = QLabel("No participant selected.")
        self.info_label.setObjectName("infoBanner")
        self.info_label.setWordWrap(True)
        detail_card.body.addWidget(self.info_label)

        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.reg_edit = QLineEdit()
        self.category_edit = QLineEdit()
        form.addRow("Full name", self.name_edit)
        form.addRow("Registration no.", self.reg_edit)
        form.addRow("Group / platoon", self.category_edit)
        detail_card.body.addLayout(form)

        self.save_btn = QPushButton("Save changes")
        self.save_btn.setObjectName("primaryButton")
        self.save_btn.clicked.connect(self._save_metadata)
        detail_card.body.addWidget(self.save_btn)

        actions_row = QHBoxLayout()
        self.export_btn = QPushButton("Export photos")
        self.export_btn.clicked.connect(self._export)
        actions_row.addWidget(self.export_btn)

        self.reprocess_btn = QPushButton("Reprocess")
        self.reprocess_btn.clicked.connect(self._reprocess)
        actions_row.addWidget(self.reprocess_btn)

        actions_row.addStretch(1)

        self.delete_btn = QPushButton("Delete participant")
        self.delete_btn.setObjectName("dangerButton")
        self.delete_btn.clicked.connect(self._delete)
        actions_row.addWidget(self.delete_btn)
        detail_card.body.addLayout(actions_row)
        detail_card.body.addStretch(1)

        body.addWidget(detail_card, stretch=2)
        outer.addLayout(body, stretch=1)

        self._detail_controls = [
            self.name_edit,
            self.reg_edit,
            self.category_edit,
            self.save_btn,
            self.export_btn,
            self.reprocess_btn,
            self.delete_btn,
        ]
        self._set_detail_enabled(False)
        self.refresh()

    def _set_detail_enabled(self, enabled: bool) -> None:
        for widget in self._detail_controls:
            widget.setEnabled(enabled)

    def _clear_search(self) -> None:
        self.search_edit.clear()
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        selected_id = self._current_participant_id
        self.results_list.clear()

        try:
            with get_session() as session:
                results = search_participants(session, self.search_edit.text())
                for participant in results:
                    matched = count_matched_photos(session, participant.id)
                    item = QListWidgetItem(
                        f"{participant.full_name}\n"
                        f"{participant.participant_id} • {matched} matched photo(s)"
                    )
                    item.setData(Qt.UserRole, participant.id)
                    self.results_list.addItem(item)
        except Exception as exc:
            self.result_count.setText(f"Could not load participants: {exc}")
            self._clear_detail()
            return

        self.result_count.setText(
            f"{len(results)} participant{'s' if len(results) != 1 else ''}"
            + (" found" if self.search_edit.text().strip() else " registered")
        )

        if not results:
            self.info_label.setText(
                "No participants match that search."
                if self.search_edit.text().strip()
                else "No participants have been registered yet."
            )
            self._clear_detail()
            return

        if selected_id is not None:
            for row in range(self.results_list.count()):
                item = self.results_list.item(row)
                if item.data(Qt.UserRole) == selected_id:
                    self.results_list.setCurrentRow(row)
                    return

        self.results_list.setCurrentRow(0)

    def _clear_detail(self) -> None:
        self._current_participant_id = None
        self._clear_thumbnails()
        self.name_edit.clear()
        self.reg_edit.clear()
        self.category_edit.clear()
        self._set_detail_enabled(False)

    def _clear_thumbnails(self) -> None:
        while self.thumbnails_row.count():
            child = self.thumbnails_row.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self._clear_detail()
            return
        self._load_detail(current.data(Qt.UserRole))

    def _load_detail(self, participant_db_id: int) -> None:
        self._current_participant_id = participant_db_id
        with get_session() as session:
            participant = session.get(Participant, participant_db_id)
            if participant is None:
                self._clear_detail()
                return

            matched = count_matched_photos(session, participant_db_id)
            thumbnails = [
                embedding.thumbnail
                for embedding in session.query(ReferenceEmbedding)
                .filter_by(participant_db_id=participant_db_id)
                .all()
                if embedding.thumbnail
            ]

            self.name_edit.setText(participant.full_name)
            self.reg_edit.setText(participant.registration_number or "")
            self.category_edit.setText(participant.category or "")
            self.info_label.setText(
                f"ID {participant.participant_id} • registered "
                f"{participant.created_at.strftime('%Y-%m-%d')} • "
                f"{matched} matched photo(s) • {len(thumbnails)} reference photo(s)"
            )

        self._clear_thumbnails()
        if thumbnails:
            for thumb_bytes in thumbnails[:5]:
                label = QLabel()
                label.setObjectName("reviewPreview")
                label.setFixedSize(92, 92)
                label.setAlignment(Qt.AlignCenter)
                pixmap = bytes_to_qpixmap(thumb_bytes)
                label.setPixmap(
                    pixmap.scaled(92, 92, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.thumbnails_row.addWidget(label)
        else:
            placeholder = QLabel("No stored reference thumbnails")
            placeholder.setObjectName("hintLabel")
            self.thumbnails_row.addWidget(placeholder)
        self.thumbnails_row.addStretch(1)
        self._set_detail_enabled(True)

    def _save_metadata(self) -> None:
        if self._current_participant_id is None:
            return
        try:
            with get_session() as session:
                update_participant_metadata(
                    session,
                    self._current_participant_id,
                    actor="gui-operator",
                    full_name=self.name_edit.text(),
                    registration_number=self.reg_edit.text(),
                    category=self.category_edit.text(),
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return

        QMessageBox.information(self, "Saved", "Participant details were updated.")
        self.refresh()

    def _delete(self) -> None:
        if self._current_participant_id is None:
            return

        confirm = QMessageBox.question(
            self,
            "Delete participant?",
            "This permanently deletes the participant and their stored reference embeddings. "
            "Photos already copied into the output folder are not removed.\n\nContinue?",
        )
        if confirm != QMessageBox.Yes:
            return

        with get_session() as session:
            delete_participant(
                session,
                self._current_participant_id,
                actor="gui-operator",
            )
        self._clear_detail()
        self.refresh()

    def _export(self) -> None:
        if self._current_participant_id is None:
            return

        with get_session() as session:
            participant = session.get(Participant, self._current_participant_id)
            if participant is None:
                return
            default_name = sanitize_export_filename(participant)
            output_dir = Path(self.context.settings.output_dir)

        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export participant photos",
            default_name,
            "Zip files (*.zip)",
        )
        if not path_str:
            return

        count = export_participant_photos(output_dir, participant, Path(path_str))
        if count == 0:
            QMessageBox.information(
                self,
                "Nothing to export",
                "No matched photos were found for this participant.",
            )
        else:
            QMessageBox.information(
                self,
                "Export complete",
                f"{count} photo(s) were exported.",
            )

    def _reprocess(self) -> None:
        if self._current_participant_id is None:
            return

        with get_session() as session:
            participant = session.get(Participant, self._current_participant_id)
            if participant is None:
                return
            last_run = (
                session.query(ProcessingRun)
                .order_by(ProcessingRun.id.desc())
                .first()
            )
            default_input = (
                last_run.input_dir
                if last_run
                else self.context.settings.input_dir
            )

        dialog = ReprocessDialog(
            self.context,
            participant,
            default_input,
            parent=self,
        )
        dialog.exec()
        self.refresh()
