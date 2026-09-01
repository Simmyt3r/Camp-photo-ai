"""Participants screen (section 19): search by name/ID/registration
number/category, view reference thumbnails and matched-photo count,
edit metadata, delete, export matched photos, and reprocess (re-scan a
folder for just this one person)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
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
from app.ui.workers import ProcessingWorker


class ReprocessDialog(QDialog):
    """Re-scans a chosen folder for just one participant, bypassing the
    cache (resume=False) since the point is re-evaluating photos that
    were likely already processed once -- see batch_processor.run_batch's
    participant_filter docstring for why resume must be off here."""

    def __init__(self, context: AppContext, participant: Participant, default_input_dir: str, parent=None):
        super().__init__(parent)
        self.context = context
        self.participant = participant
        self._worker: ProcessingWorker | None = None
        self.setWindowTitle(f"Reprocess: {participant.full_name}")
        self.resize(480, 220)

        layout = QVBoxLayout(self)
        info = QLabel(
            f"Re-scans a folder of photos, matching only against {participant.full_name} "
            f"({participant.participant_id}) -- useful after adding better reference photos, "
            f"or if they were missed the first time. Every photo in the folder is re-evaluated, "
            f"even ones already processed before."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        input_row = QHBoxLayout()
        self.input_edit = QLineEdit(default_input_dir)
        input_row.addWidget(self.input_edit, stretch=1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        input_row.addWidget(browse_btn)
        layout.addLayout(input_row)

        self.output_edit = QLineEdit(context.settings.output_dir)
        layout.addWidget(QLabel("Output folder (same structure as normal processing):"))
        layout.addWidget(self.output_edit)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        self.start_btn = QPushButton("Start Reprocessing")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self._start)
        buttons.addButton(self.start_btn, QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder", self.input_edit.text() or "")
        if path:
            self.input_edit.setText(path)

    def _start(self) -> None:
        input_dir = self.input_edit.text().strip()
        if not input_dir or not Path(input_dir).is_dir():
            self.status_label.setText("Choose a valid input folder first.")
            return

        self.start_btn.setEnabled(False)
        self.status_label.setText("Reprocessing...")
        self._worker = ProcessingWorker(
            self.context.settings, Path(input_dir), Path(self.output_edit.text().strip()),
            self.context.embedding_service, resume=False,
            participant_filter={self.participant.participant_id},
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stats, filename: str) -> None:
        if stats.total_photos > 0:
            self.progress_bar.setValue(int(100 * stats.processed / stats.total_photos))
        self.status_label.setText(f"{stats.processed}/{stats.total_photos} -- {filename[:40]}")

    def _on_finished(self, stats) -> None:
        self.start_btn.setEnabled(True)
        self.status_label.setText(
            f"Done. {stats.auto_matched} auto-matched, {stats.review} sent to review, "
            f"{stats.unmatched} still unmatched."
        )

    def _on_failed(self, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.status_label.setText(f"Failed: {message}")


class ParticipantsPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._current_participant_id: int | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        left = QVBoxLayout()
        header = QLabel("Participants")
        header.setObjectName("pageTitle")
        left.addWidget(header)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name, ID, registration number, or category...")
        self.search_edit.returnPressed.connect(self.refresh)
        search_row.addWidget(self.search_edit, stretch=1)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.refresh)
        search_row.addWidget(search_btn)
        left.addLayout(search_row)

        self.results_list = QListWidget()
        self.results_list.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.results_list, stretch=1)
        layout.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Reference photos"))
        self.thumbnails_row = QHBoxLayout()
        self.thumbnails_row.setSpacing(8)
        right.addLayout(self.thumbnails_row)

        self.info_label = QLabel("Select a participant from the list.")
        self.info_label.setObjectName("hintLabel")
        self.info_label.setWordWrap(True)
        right.addWidget(self.info_label)

        right.addWidget(QLabel("Full name"))
        self.name_edit = QLineEdit()
        right.addWidget(self.name_edit)

        right.addWidget(QLabel("Registration number"))
        self.reg_edit = QLineEdit()
        right.addWidget(self.reg_edit)

        right.addWidget(QLabel("Category / group / platoon"))
        self.category_edit = QLineEdit()
        right.addWidget(self.category_edit)

        save_btn = QPushButton("Save Changes")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_metadata)
        right.addWidget(save_btn)

        actions_row = QHBoxLayout()
        export_btn = QPushButton("Export Photos...")
        export_btn.clicked.connect(self._export)
        actions_row.addWidget(export_btn)

        reprocess_btn = QPushButton("Reprocess...")
        reprocess_btn.clicked.connect(self._reprocess)
        actions_row.addWidget(reprocess_btn)

        delete_btn = QPushButton("Delete Participant")
        delete_btn.clicked.connect(self._delete)
        actions_row.addWidget(delete_btn)
        actions_row.addStretch(1)
        right.addLayout(actions_row)

        right.addStretch(1)
        layout.addLayout(right, stretch=2)

        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.results_list.clear()
        with get_session() as session:
            results = search_participants(session, self.search_edit.text())
            for p in results:
                matched = count_matched_photos(session, p.id)
                item = QListWidgetItem(f"{p.participant_id} -- {p.full_name} ({matched} matched photos)")
                item.setData(Qt.UserRole, p.id)
                self.results_list.addItem(item)

        if not results:
            self.info_label.setText("No participants match that search." if self.search_edit.text().strip()
                                     else "No participants registered yet.")
            self._clear_detail()

    def _clear_detail(self) -> None:
        self._current_participant_id = None
        self._clear_thumbnails()
        self.name_edit.clear()
        self.reg_edit.clear()
        self.category_edit.clear()

    def _clear_thumbnails(self) -> None:
        while self.thumbnails_row.count():
            child = self.thumbnails_row.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        self._load_detail(current.data(Qt.UserRole))

    def _load_detail(self, participant_db_id: int) -> None:
        self._current_participant_id = participant_db_id
        with get_session() as session:
            p = session.get(Participant, participant_db_id)
            if p is None:
                return
            matched = count_matched_photos(session, participant_db_id)
            thumbnails = [
                e.thumbnail for e in
                session.query(ReferenceEmbedding).filter_by(participant_db_id=participant_db_id).all()
                if e.thumbnail
            ]

            self.name_edit.setText(p.full_name)
            self.reg_edit.setText(p.registration_number or "")
            self.category_edit.setText(p.category or "")
            self.info_label.setText(
                f"ID: {p.participant_id}  |  Registered: {p.created_at.strftime('%Y-%m-%d')}  |  "
                f"{matched} matched photo(s)  |  {len(thumbnails)} reference photo(s)"
            )

        self._clear_thumbnails()
        for thumb_bytes in thumbnails[:5]:
            label = QLabel()
            label.setObjectName("reviewPreview")
            label.setFixedSize(100, 100)
            label.setAlignment(Qt.AlignCenter)
            pixmap = bytes_to_qpixmap(thumb_bytes)
            label.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.thumbnails_row.addWidget(label)
        self.thumbnails_row.addStretch(1)

    def _save_metadata(self) -> None:
        if self._current_participant_id is None:
            return
        try:
            with get_session() as session:
                update_participant_metadata(
                    session, self._current_participant_id, actor="gui-operator",
                    full_name=self.name_edit.text(),
                    registration_number=self.reg_edit.text(),
                    category=self.category_edit.text(),
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Could not save", str(exc))
            return
        self.refresh()

    def _delete(self) -> None:
        if self._current_participant_id is None:
            return
        confirm = QMessageBox.question(
            self, "Delete participant?",
            "This permanently deletes the participant and every reference embedding on file for "
            "them (see docs/PRIVACY.md) -- it cannot be undone. Photos already copied into their "
            "output folder are not touched by this and need to be removed separately if required.\n\n"
            "Continue?",
        )
        if confirm != QMessageBox.Yes:
            return
        with get_session() as session:
            delete_participant(session, self._current_participant_id, actor="gui-operator")
        self._clear_detail()
        self.refresh()

    def _export(self) -> None:
        if self._current_participant_id is None:
            return
        with get_session() as session:
            p = session.get(Participant, self._current_participant_id)
            if p is None:
                return
            default_name = sanitize_export_filename(p)
            output_dir = Path(self.context.settings.output_dir)

        path_str, _ = QFileDialog.getSaveFileName(self, "Export participant's photos", default_name, "Zip files (*.zip)")
        if not path_str:
            return

        count = export_participant_photos(output_dir, p, Path(path_str))
        if count == 0:
            QMessageBox.information(self, "Nothing to export", "No matched photos found for this participant yet.")
        else:
            QMessageBox.information(self, "Exported", f"{count} photo(s) exported to {path_str}")

    def _reprocess(self) -> None:
        if self._current_participant_id is None:
            return
        with get_session() as session:
            p = session.get(Participant, self._current_participant_id)
            if p is None:
                return
            last_run = session.query(ProcessingRun).order_by(ProcessingRun.id.desc()).first()
            default_input = last_run.input_dir if last_run else self.context.settings.input_dir

        dialog = ReprocessDialog(self.context, p, default_input, parent=self)
        dialog.exec()
        self.refresh()
