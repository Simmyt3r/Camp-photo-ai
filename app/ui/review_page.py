"""Human review queue: list + detail panel with photo, face crop,
candidate info, and confirm/reject/reassign actions (section 14)."""
from __future__ import annotations

from pathlib import Path

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.database.db import get_session
from app.database.models import MatchRecord, Participant, ReferenceEmbedding
from app.services.review_service import confirm_match, list_pending_reviews, reassign_match, reject_match
from app.ui.image_utils import bytes_to_qpixmap, crop_with_padding, numpy_to_qpixmap


class ReviewPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._current_record_id: int | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        left = QVBoxLayout()
        header = QLabel("Review Matches")
        header.setObjectName("pageTitle")
        left.addWidget(header)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        left.addWidget(refresh_btn)

        self.queue_list = QListWidget()
        self.queue_list.currentItemChanged.connect(self._on_selection_changed)
        left.addWidget(self.queue_list, stretch=1)
        layout.addLayout(left, stretch=1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Photo"))
        self.photo_label = QLabel("Select an item from the queue")
        self.photo_label.setObjectName("reviewPreview")
        self.photo_label.setFixedHeight(260)
        self.photo_label.setAlignment(Qt.AlignCenter)
        right.addWidget(self.photo_label)

        crop_and_ref_row = QHBoxLayout()
        crop_col = QVBoxLayout()
        crop_col.addWidget(QLabel("Detected face"))
        self.face_crop_label = QLabel("")
        self.face_crop_label.setObjectName("reviewPreview")
        self.face_crop_label.setFixedSize(160, 160)
        self.face_crop_label.setAlignment(Qt.AlignCenter)
        crop_col.addWidget(self.face_crop_label)
        crop_and_ref_row.addLayout(crop_col)

        ref_col = QVBoxLayout()
        ref_col.addWidget(QLabel("Suggested participant"))
        self.ref_thumb_label = QLabel("")
        self.ref_thumb_label.setObjectName("reviewPreview")
        self.ref_thumb_label.setFixedSize(160, 160)
        self.ref_thumb_label.setAlignment(Qt.AlignCenter)
        ref_col.addWidget(self.ref_thumb_label)
        crop_and_ref_row.addLayout(ref_col)
        right.addLayout(crop_and_ref_row)

        self.info_label = QLabel("")
        self.info_label.setObjectName("hintLabel")
        self.info_label.setWordWrap(True)
        right.addWidget(self.info_label)

        actions = QHBoxLayout()
        confirm_btn = QPushButton("Confirm")
        confirm_btn.setObjectName("primaryButton")
        confirm_btn.clicked.connect(self._confirm)
        actions.addWidget(confirm_btn)

        reject_btn = QPushButton("Reject")
        reject_btn.clicked.connect(self._reject)
        actions.addWidget(reject_btn)

        self.reassign_combo = QComboBox()
        actions.addWidget(self.reassign_combo, stretch=1)

        reassign_btn = QPushButton("Reassign && Confirm")
        reassign_btn.clicked.connect(self._reassign)
        actions.addWidget(reassign_btn)

        right.addLayout(actions)
        right.addStretch(1)
        layout.addLayout(right, stretch=2)

        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.queue_list.clear()
        self.reassign_combo.clear()
        with get_session() as session:
            pending = list_pending_reviews(session, limit=100)
            participants = session.query(Participant).order_by(Participant.full_name).all()
            for p in participants:
                self.reassign_combo.addItem(f"{p.participant_id} -- {p.full_name}", p.id)

            for record in pending:
                second = ""
                if record.second_best_participant_id:
                    second = f" (2nd: {record.second_best_participant_id} @ {record.second_best_score:.2f})"
                label = (
                    f"{Path(record.file_path).name} face#{record.face_index} -- "
                    f"{record.best_candidate_participant_id or '?'} @ {record.best_score:.2f}{second}"
                )
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, record.id)
                self.queue_list.addItem(item)

        empty = self.queue_list.count() == 0
        self.photo_label.setText("Review queue is empty" if empty else "Select an item from the queue")
        self.photo_label.setPixmap(QPixmap())
        self.face_crop_label.clear()
        self.ref_thumb_label.clear()
        self.info_label.setText("")
        self._current_record_id = None

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        record_id = current.data(Qt.UserRole)
        self._current_record_id = record_id
        self._load_detail(record_id)

    def _load_detail(self, record_id: int) -> None:
        with get_session() as session:
            record = session.get(MatchRecord, record_id)
            if record is None:
                return

            photo_path = Path(record.file_path)
            image = cv2.imread(str(photo_path)) if photo_path.exists() else None
            if image is not None:
                pixmap = numpy_to_qpixmap(image)
                self.photo_label.setPixmap(
                    pixmap.scaled(self.photo_label.width() or 400, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                if record.bbox_x1 is not None:
                    bbox = (record.bbox_x1, record.bbox_y1, record.bbox_x2, record.bbox_y2)
                    crop = crop_with_padding(image, bbox)
                    crop_pixmap = numpy_to_qpixmap(crop)
                    self.face_crop_label.setPixmap(
                        crop_pixmap.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                else:
                    self.face_crop_label.setText("No bounding box stored\n(processed before this feature)")
            else:
                self.photo_label.setText(f"Could not load {photo_path.name}")
                self.face_crop_label.clear()

            candidate_id = record.best_candidate_participant_id
            self.ref_thumb_label.clear()
            if candidate_id:
                participant = session.query(Participant).filter_by(participant_id=candidate_id).one_or_none()
                if participant:
                    ref = (
                        session.query(ReferenceEmbedding)
                        .filter_by(participant_db_id=participant.id)
                        .filter(ReferenceEmbedding.thumbnail.isnot(None))
                        .first()
                    )
                    if ref and ref.thumbnail:
                        ref_pixmap = bytes_to_qpixmap(ref.thumbnail)
                        self.ref_thumb_label.setPixmap(
                            ref_pixmap.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        )
                    else:
                        self.ref_thumb_label.setText("No thumbnail\nstored")

            second = ""
            if record.second_best_participant_id:
                second = f"\nRunner-up: {record.second_best_participant_id} @ {record.second_best_score:.3f}"
            self.info_label.setText(
                f"Suggested: {candidate_id or 'none'}\n"
                f"Score: {record.best_score:.3f}   Margin: {record.score_margin:.3f}{second}\n"
                f"Reason: {record.reason}"
            )

    def _confirm(self) -> None:
        if self._current_record_id is None:
            return
        try:
            with get_session() as session:
                confirm_match(
                    session, self._current_record_id, reviewer="gui-operator",
                    output_dir=Path(self.context.settings.output_dir),
                    duplicate_policy=self.context.settings.duplicate_policy,
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot confirm", str(exc))
            return
        self.refresh()

    def _reject(self) -> None:
        if self._current_record_id is None:
            return
        with get_session() as session:
            reject_match(session, self._current_record_id, reviewer="gui-operator")
        self.refresh()

    def _reassign(self) -> None:
        if self._current_record_id is None:
            return
        participant_db_id = self.reassign_combo.currentData()
        if participant_db_id is None:
            QMessageBox.warning(self, "No participant selected", "Choose a participant to reassign to.")
            return
        with get_session() as session:
            reassign_match(
                session, self._current_record_id, participant_db_id, reviewer="gui-operator",
                output_dir=Path(self.context.settings.output_dir),
                duplicate_policy=self.context.settings.duplicate_policy,
            )
        self.refresh()
