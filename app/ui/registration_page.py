"""Participant registration with guided reference-photo validation."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.config.settings import APP_ROOT
from app.database.db import get_session
from app.database.models import Participant, ReferenceEmbedding
from app.services.face_embedding import (
    EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_VERSION,
)
from app.ui.image_utils import numpy_to_qpixmap
from app.ui.widgets import Card, PageHeader
from app.ui.workers import ReferencePhotoResult, RegistrationWorker
from app.utilities.file_utils import file_sha256


class RegistrationPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._pending_photos: list[Path] = []
        self._camera = None
        self._camera_frame: np.ndarray | None = None
        self._camera_timer = QTimer(self)
        self._camera_timer.timeout.connect(self._update_camera_frame)
        self._worker: RegistrationWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)

        layout.addWidget(PageHeader(
            "Register Participant",
            "Create one participant profile and add clear reference photos for face matching.",
        ))

        content = QHBoxLayout()
        content.setSpacing(14)

        profile_card = Card(
            "Participant details",
            "Required fields are marked with *. IDs must be unique.",
        )
        profile_card.setMinimumWidth(270)
        form = QFormLayout()
        form.setSpacing(10)

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("e.g. P001")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Full name")
        self.reg_input = QLineEdit()
        self.reg_input.setPlaceholderText("Optional")
        self.category_input = QLineEdit()
        self.category_input.setPlaceholderText("e.g. Platoon 5")

        form.addRow("Participant ID *", self.id_input)
        form.addRow("Full name *", self.name_input)
        form.addRow("Registration no.", self.reg_input)
        form.addRow("Group / platoon", self.category_input)
        profile_card.body.addLayout(form)

        self.consent_checkbox = QCheckBox(
            "Participant has consented to local face processing and storage."
        )
        profile_card.body.addWidget(self.consent_checkbox)

        consent_hint = QLabel(
            "CampPhoto AI stores reference embeddings locally. Do not register a person "
            "without their consent."
        )
        consent_hint.setObjectName("cardHint")
        consent_hint.setWordWrap(True)
        profile_card.body.addWidget(consent_hint)
        profile_card.body.addStretch(1)

        content.addWidget(profile_card, stretch=1)

        photos_card = Card(
            "Reference photos",
            "Use 3–5 clear photos of the same person. Photos with zero or multiple faces are rejected.",
        )

        photo_controls = QHBoxLayout()
        import_btn = QPushButton("Import photos")
        import_btn.setObjectName("secondaryButton")
        import_btn.clicked.connect(self._import_photos)
        photo_controls.addWidget(import_btn)

        self.camera_btn = QPushButton("Open camera")
        self.camera_btn.clicked.connect(self._toggle_camera)
        photo_controls.addWidget(self.camera_btn)

        self.capture_btn = QPushButton("Capture")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._capture_from_camera)
        photo_controls.addWidget(self.capture_btn)

        remove_btn = QPushButton("Remove selected")
        remove_btn.setObjectName("ghostButton")
        remove_btn.clicked.connect(self._remove_selected_photo)
        photo_controls.addWidget(remove_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("ghostButton")
        clear_btn.clicked.connect(self._clear_pending_photos)
        photo_controls.addWidget(clear_btn)
        photo_controls.addStretch(1)
        photos_card.body.addLayout(photo_controls)

        media_row = QHBoxLayout()
        media_row.setSpacing(12)

        self.camera_preview = QLabel("Camera off")
        self.camera_preview.setObjectName("cameraPreview")
        self.camera_preview.setFixedSize(250, 188)
        self.camera_preview.setAlignment(Qt.AlignCenter)
        media_row.addWidget(self.camera_preview)

        photo_list_col = QVBoxLayout()
        self.photo_count_label = QLabel("0 photos selected")
        self.photo_count_label.setObjectName("cardHint")
        photo_list_col.addWidget(self.photo_count_label)

        self.photo_list = QListWidget()
        self.photo_list.setMinimumHeight(188)
        photo_list_col.addWidget(self.photo_list)
        media_row.addLayout(photo_list_col, stretch=1)
        photos_card.body.addLayout(media_row)

        content.addWidget(photos_card, stretch=2)
        layout.addLayout(content)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready to register a participant.")
        self.status_label.setObjectName("infoBanner")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        register_row = QHBoxLayout()
        register_row.addStretch(1)
        self.register_btn = QPushButton("Register participant")
        self.register_btn.setObjectName("primaryButton")
        self.register_btn.setMinimumWidth(180)
        self.register_btn.clicked.connect(self._start_registration)
        register_row.addWidget(self.register_btn)
        layout.addLayout(register_row)
        layout.addStretch(1)

    def _set_status(self, message: str, kind: str = "info") -> None:
        names = {
            "info": "infoBanner",
            "success": "successBanner",
            "warning": "warningBanner",
            "error": "errorBanner",
        }
        self.status_label.setObjectName(names.get(kind, "infoBanner"))
        self.status_label.setText(message)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _update_photo_count(self) -> None:
        count = len(self._pending_photos)
        self.photo_count_label.setText(
            f"{count} photo{'s' if count != 1 else ''} selected"
            + (" • 3–5 recommended" if count < 3 else "")
        )

    def _import_photos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select reference photos",
            "",
            "Images (*.jpg *.jpeg *.png *.webp *.tiff *.tif)",
        )
        for raw_path in paths:
            self._add_photo_to_list(Path(raw_path))

    def _add_photo_to_list(self, path: Path) -> None:
        normalized = path.resolve()
        if any(existing.resolve() == normalized for existing in self._pending_photos):
            self._set_status(f"{path.name} is already selected.", "warning")
            return

        self._pending_photos.append(path)
        item = QListWidgetItem(f"{path.name}  •  pending validation")
        item.setData(Qt.UserRole, str(path))
        self.photo_list.addItem(item)
        self._update_photo_count()

    def _remove_selected_photo(self) -> None:
        row = self.photo_list.currentRow()
        if row < 0 or row >= len(self._pending_photos):
            return
        self.photo_list.takeItem(row)
        self._pending_photos.pop(row)
        self._update_photo_count()

    def _clear_pending_photos(self) -> None:
        self._pending_photos.clear()
        self.photo_list.clear()
        self._update_photo_count()
        self._set_status("Reference-photo selection cleared.")

    def _toggle_camera(self) -> None:
        if self._camera is not None:
            self._stop_camera()
            return

        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            camera.release()
            QMessageBox.warning(
                self,
                "Camera unavailable",
                "CampPhoto AI could not open a camera. You can still import photos from disk.",
            )
            return

        self._camera = camera
        self.camera_btn.setText("Close camera")
        self.capture_btn.setEnabled(True)
        self._camera_timer.start(33)

    def _stop_camera(self) -> None:
        self._camera_timer.stop()
        if self._camera is not None:
            self._camera.release()
        self._camera = None
        self._camera_frame = None
        self.camera_btn.setText("Open camera")
        self.capture_btn.setEnabled(False)
        self.camera_preview.setText("Camera off")
        self.camera_preview.setPixmap(QPixmap())

    def _update_camera_frame(self) -> None:
        if self._camera is None:
            return
        ok, frame = self._camera.read()
        if not ok:
            return
        self._camera_frame = frame
        pixmap = numpy_to_qpixmap(frame)
        self.camera_preview.setPixmap(
            pixmap.scaled(250, 188, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _capture_from_camera(self) -> None:
        if self._camera_frame is None:
            return
        captures_dir = APP_ROOT / "data" / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        out_path = captures_dir / f"capture_{int(time.time() * 1000)}.jpg"
        if cv2.imwrite(str(out_path), self._camera_frame):
            self._add_photo_to_list(out_path)

    def _start_registration(self) -> None:
        participant_id = self.id_input.text().strip()
        full_name = self.name_input.text().strip()

        if not participant_id or not full_name:
            self._set_status("Participant ID and Full name are required.", "warning")
            return
        if not self._pending_photos:
            self._set_status("Add at least one reference photo before registering.", "warning")
            return
        if not self.consent_checkbox.isChecked():
            self._set_status(
                "Confirm the participant's consent before creating biometric reference data.",
                "warning",
            )
            return

        with get_session() as session:
            existing = (
                session.query(Participant)
                .filter_by(participant_id=participant_id)
                .one_or_none()
            )
            if existing:
                self._set_status(
                    f"Participant ID '{participant_id}' is already registered.",
                    "warning",
                )
                return

        self.register_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self._set_status("Validating reference photos and preparing the face model...")

        self._worker = RegistrationWorker(
            self.context.embedding_service,
            list(self._pending_photos),
        )
        self._worker.result_ready.connect(self._on_registration_results)
        self._worker.model_progress.connect(self._on_model_progress)
        self._worker.failed.connect(self._on_registration_failed)
        self._worker.start()

    def _on_model_progress(self, downloaded: int, total, message: str) -> None:
        self.progress_bar.show()
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

    def _on_registration_failed(self, message: str) -> None:
        self.register_btn.setEnabled(True)
        self.progress_bar.hide()
        self._set_status(f"Registration failed: {message}", "error")

    def _on_registration_results(self, results: list[ReferencePhotoResult]) -> None:
        self.register_btn.setEnabled(True)
        self.progress_bar.hide()
        self.photo_list.clear()

        accepted = [result for result in results if result.accepted]
        rejected = [result for result in results if not result.accepted]

        for result in results:
            status = "Accepted" if result.accepted else f"Rejected • {result.message}"
            self.photo_list.addItem(
                QListWidgetItem(f"{Path(result.path).name}  •  {status}")
            )

        if not accepted:
            self._set_status(
                "No usable reference photos were found. Replace the rejected photos and try again.",
                "error",
            )
            return

        participant_id = self.id_input.text().strip()
        full_name = self.name_input.text().strip()
        reg_number = self.reg_input.text().strip() or None
        category = self.category_input.text().strip() or None

        with get_session() as session:
            existing = (
                session.query(Participant)
                .filter_by(participant_id=participant_id)
                .one_or_none()
            )
            if existing:
                self._set_status(
                    f"Participant ID '{participant_id}' was registered before this operation completed.",
                    "warning",
                )
                return

            participant = Participant(
                participant_id=participant_id,
                full_name=full_name,
                registration_number=reg_number,
                category=category,
                consent_given=True,
            )
            session.add(participant)
            session.flush()

            for result in accepted:
                session.add(ReferenceEmbedding(
                    participant_db_id=participant.id,
                    vector=result.embedding.astype(np.float32).tobytes(),
                    dimensions=EMBEDDING_DIMENSIONS,
                    model_name=EMBEDDING_MODEL_NAME,
                    model_version=EMBEDDING_MODEL_VERSION,
                    source_image_hash=file_sha256(Path(result.path)),
                    thumbnail=result.thumbnail,
                ))

        message = (
            f"Registered {full_name} ({participant_id}) with "
            f"{len(accepted)} usable reference photo(s)."
        )
        if rejected:
            message += f" {len(rejected)} photo(s) were rejected."
        self._set_status(message, "success")

        self._pending_photos = []
        self._update_photo_count()
        self.id_input.clear()
        self.name_input.clear()
        self.reg_input.clear()
        self.category_input.clear()
        self.consent_checkbox.setChecked(False)

    def on_shown(self) -> None:
        self._update_photo_count()

    def closeEvent(self, event) -> None:
        self._stop_camera()
        super().closeEvent(event)
