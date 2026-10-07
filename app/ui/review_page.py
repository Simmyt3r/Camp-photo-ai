"""Human review queue with clear comparison and safe decision actions."""
from __future__ import annotations

from pathlib import Path

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.database.db import get_session
from app.database.models import MatchRecord, Participant, ReferenceEmbedding
from app.services.review_service import (
    confirm_match, list_pending_reviews, reassign_match, reject_match,
)
from app.ui.activity import notify_activity
from app.ui.image_utils import bytes_to_qpixmap, crop_with_padding, numpy_to_qpixmap
from app.ui.widgets import Card, PageHeader


class ReviewPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._current_record_id: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 26, 28, 26)
        outer.setSpacing(16)

        header = PageHeader(
            "Review Matches",
            "Confirm uncertain matches, reject them, or assign the detected face to another participant.",
        )
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        header.trailing.addWidget(refresh_btn)
        outer.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        queue_card = Card("Review queue")
        self.queue_count = QLabel("")
        self.queue_count.setObjectName("cardHint")
        queue_card.body.addWidget(self.queue_count)

        self.queue_list = QListWidget()
        self.queue_list.currentItemChanged.connect(self._on_selection_changed)
        queue_card.body.addWidget(self.queue_list, stretch=1)
        body.addWidget(queue_card, stretch=1)

        detail_card = Card(
            "Match comparison",
            "Compare the detected face with the suggested participant before deciding.",
        )

        self.photo_label = QLabel("Select an item from the review queue")
        self.photo_label.setObjectName("reviewPreview")
        self.photo_label.setMinimumHeight(230)
        self.photo_label.setAlignment(Qt.AlignCenter)
        detail_card.body.addWidget(self.photo_label)

        compare_row = QHBoxLayout()
        compare_row.setSpacing(12)

        crop_card = Card("Detected face")
        self.face_crop_label = QLabel("No face selected")
        self.face_crop_label.setObjectName("reviewPreview")
        self.face_crop_label.setFixedSize(150, 150)
        self.face_crop_label.setAlignment(Qt.AlignCenter)
        crop_card.body.addWidget(self.face_crop_label, alignment=Qt.AlignCenter)
        compare_row.addWidget(crop_card)

        ref_card = Card("Suggested participant")
        self.ref_thumb_label = QLabel("No participant selected")
        self.ref_thumb_label.setObjectName("reviewPreview")
        self.ref_thumb_label.setFixedSize(150, 150)
        self.ref_thumb_label.setAlignment(Qt.AlignCenter)
        ref_card.body.addWidget(self.ref_thumb_label, alignment=Qt.AlignCenter)
        compare_row.addWidget(ref_card)
        compare_row.addStretch(1)
        detail_card.body.addLayout(compare_row)

        self.info_label = QLabel("Choose a review item to see confidence details.")
        self.info_label.setObjectName("infoBanner")
        self.info_label.setWordWrap(True)
        detail_card.body.addWidget(self.info_label)

        actions = QHBoxLayout()
        self.confirm_btn = QPushButton("Confirm match")
        self.confirm_btn.setObjectName("primaryButton")
        self.confirm_btn.clicked.connect(self._confirm)
        actions.addWidget(self.confirm_btn)

        self.reject_btn = QPushButton("Reject")
        self.reject_btn.setObjectName("dangerButton")
        self.reject_btn.clicked.connect(self._reject)
        actions.addWidget(self.reject_btn)

        actions.addStretch(1)
        detail_card.body.addLayout(actions)

        reassign_row = QHBoxLayout()
        reassign_label = QLabel("Assign to:")
        reassign_label.setObjectName("hintLabel")
        reassign_row.addWidget(reassign_label)

        self.reassign_combo = QComboBox()
        reassign_row.addWidget(self.reassign_combo, stretch=1)

        self.reassign_btn = QPushButton("Reassign + confirm")
        self.reassign_btn.setObjectName("secondaryButton")
        self.reassign_btn.clicked.connect(self._reassign)
        reassign_row.addWidget(self.reassign_btn)
        detail_card.body.addLayout(reassign_row)

        body.addWidget(detail_card, stretch=2)
        outer.addLayout(body, stretch=1)

        self._decision_controls = [
            self.confirm_btn,
            self.reject_btn,
            self.reassign_combo,
            self.reassign_btn,
        ]
        self._set_decisions_enabled(False)

        QShortcut(QKeySequence(Qt.Key_Return), self, activated=self._confirm)
        QShortcut(QKeySequence(Qt.Key_Enter), self, activated=self._confirm)
        QShortcut(QKeySequence("X"), self, activated=self._reject)
        QShortcut(QKeySequence("R"), self, activated=self._reassign)
        self.refresh()

    def _set_decisions_enabled(self, enabled: bool) -> None:
        for widget in self._decision_controls:
            widget.setEnabled(enabled)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.queue_list.clear()
        self.reassign_combo.clear()

        try:
            with get_session() as session:
                pending = list_pending_reviews(session, limit=100)
                participants = (
                    session.query(Participant)
                    .order_by(Participant.full_name)
                    .all()
                )

                for participant in participants:
                    self.reassign_combo.addItem(
                        f"{participant.full_name} • {participant.participant_id}",
                        participant.id,
                    )

                for record in pending:
                    candidate = record.best_candidate_participant_id or "No candidate"
                    item = QListWidgetItem(
                        f"{Path(record.file_path).name}\n"
                        f"Face {record.face_index + 1} • {candidate} • score {record.best_score:.2f}"
                    )
                    item.setData(Qt.UserRole, record.id)
                    self.queue_list.addItem(item)
        except Exception as exc:
            self.queue_count.setText(f"Could not load review queue: {exc}")
            self._clear_detail("Review queue could not be loaded.")
            return

        count = self.queue_list.count()
        self.queue_count.setText(
            f"{count} item{'s' if count != 1 else ''} waiting for review"
        )

        if count:
            self.queue_list.setCurrentRow(0)
        else:
            self._clear_detail(
                "Review queue is empty. Uncertain matches will appear here after processing."
            )

    def _clear_detail(self, message: str) -> None:
        self._current_record_id = None
        self.photo_label.setPixmap(QPixmap())
        self.photo_label.setText(message)
        self.face_crop_label.setPixmap(QPixmap())
        self.face_crop_label.setText("No face selected")
        self.ref_thumb_label.setPixmap(QPixmap())
        self.ref_thumb_label.setText("No participant selected")
        self.info_label.setText(message)
        self._set_decisions_enabled(False)

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
                self._clear_detail("This review item no longer exists.")
                return

            photo_path = Path(record.file_path)
            image = cv2.imread(str(photo_path)) if photo_path.exists() else None

            if image is not None:
                pixmap = numpy_to_qpixmap(image)
                self.photo_label.setText("")
                self.photo_label.setPixmap(
                    pixmap.scaled(
                        max(self.photo_label.width(), 420),
                        230,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )

                if record.bbox_x1 is not None:
                    bbox = (
                        record.bbox_x1,
                        record.bbox_y1,
                        record.bbox_x2,
                        record.bbox_y2,
                    )
                    crop = crop_with_padding(image, bbox)
                    crop_pixmap = numpy_to_qpixmap(crop)
                    self.face_crop_label.setText("")
                    self.face_crop_label.setPixmap(
                        crop_pixmap.scaled(
                            150,
                            150,
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        )
                    )
                else:
                    self.face_crop_label.setPixmap(QPixmap())
                    self.face_crop_label.setText("No stored face crop")
            else:
                self.photo_label.setPixmap(QPixmap())
                self.photo_label.setText(
                    f"Original photo is unavailable:\n{photo_path.name}"
                )
                self.face_crop_label.setPixmap(QPixmap())
                self.face_crop_label.setText("No preview")

            candidate_id = record.best_candidate_participant_id
            self.ref_thumb_label.setPixmap(QPixmap())
            self.ref_thumb_label.setText("No thumbnail")

            if candidate_id:
                participant = (
                    session.query(Participant)
                    .filter_by(participant_id=candidate_id)
                    .one_or_none()
                )
                if participant:
                    ref = (
                        session.query(ReferenceEmbedding)
                        .filter_by(participant_db_id=participant.id)
                        .filter(ReferenceEmbedding.thumbnail.isnot(None))
                        .first()
                    )
                    if ref and ref.thumbnail:
                        ref_pixmap = bytes_to_qpixmap(ref.thumbnail)
                        self.ref_thumb_label.setText("")
                        self.ref_thumb_label.setPixmap(
                            ref_pixmap.scaled(
                                150,
                                150,
                                Qt.KeepAspectRatio,
                                Qt.SmoothTransformation,
                            )
                        )

            runner_up = ""
            if record.second_best_participant_id:
                runner_up = (
                    f" • runner-up {record.second_best_participant_id} "
                    f"({record.second_best_score:.3f})"
                )

            confidence_percent = max(0, min(100, round(record.best_score * 100)))
            if record.best_score >= self.context.settings.auto_match_threshold:
                confidence_label = "High"
            elif record.best_score >= self.context.settings.review_threshold:
                confidence_label = "Medium"
            else:
                confidence_label = "Low"

            self.info_label.setText(
                f"Suggested: {candidate_id or 'none'} • "
                f"Similarity {confidence_percent}% • Confidence: {confidence_label} • "
                f"margin {record.score_margin:.3f}{runner_up}. "
                f"Reason: {record.reason}\n"
                "Shortcuts: Enter = Confirm • X = Reject • R = Reassign"
            )

        self._set_decisions_enabled(True)

    def _confirm(self) -> None:
        if self._current_record_id is None:
            return
        try:
            with get_session() as session:
                confirm_match(
                    session,
                    self._current_record_id,
                    reviewer="gui-operator",
                    output_dir=Path(self.context.settings.output_dir),
                    duplicate_policy=self.context.settings.duplicate_policy,
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot confirm", str(exc))
            return
        notify_activity("Match confirmed and photo assigned.", "success")
        self.refresh()

    def _reject(self) -> None:
        if self._current_record_id is None:
            return
        with get_session() as session:
            reject_match(
                session,
                self._current_record_id,
                reviewer="gui-operator",
            )
        notify_activity("Match rejected.", "info")
        self.refresh()

    def _reassign(self) -> None:
        if self._current_record_id is None:
            return

        participant_db_id = self.reassign_combo.currentData()
        if participant_db_id is None:
            QMessageBox.warning(
                self,
                "No participant selected",
                "Choose a participant before reassigning this match.",
            )
            return

        participant_name = self.reassign_combo.currentText()
        with get_session() as session:
            reassign_match(
                session,
                self._current_record_id,
                participant_db_id,
                reviewer="gui-operator",
                output_dir=Path(self.context.settings.output_dir),
                duplicate_policy=self.context.settings.duplicate_policy,
            )
        notify_activity(f"Match reassigned to {participant_name}.", "success")
        self.refresh()
