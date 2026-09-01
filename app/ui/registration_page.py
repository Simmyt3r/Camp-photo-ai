"""Participant registration: form + reference photo import/webcam capture
+ validation feedback + background embedding generation (section 5)."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.config.settings import APP_ROOT
from app.database.db import get_session
from app.database.models import Participant, ReferenceEmbedding
from app.services.face_embedding import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_VERSION
from app.ui.image_utils import numpy_to_qpixmap
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
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        header = QLabel("Register Participant")
        header.setObjectName("pageTitle")
        layout.addWidget(header)

        form = QFormLayout()
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("e.g. P001")
        self.name_input = QLineEdit()
        self.reg_input = QLineEdit()
        self.category_input = QLineEdit()
        form.addRow("Participant ID *", self.id_input)
        form.addRow("Full Name *", self.name_input)
        form.addRow("Registration Number", self.reg_input)
        form.addRow("Category / Group / Platoon", self.category_input)
        layout.addLayout(form)

        photos_label = QLabel("Reference Photos (3-5 recommended)")
        photos_label.setObjectName("sectionLabel")
        layout.addWidget(photos_label)

        photo_controls = QHBoxLayout()
        import_btn = QPushButton("Import Photos...")
        import_btn.clicked.connect(self._import_photos)
        photo_controls.addWidget(import_btn)

        self.camera_btn = QPushButton("Open Camera")
        self.camera_btn.clicked.connect(self._toggle_camera)
        photo_controls.addWidget(self.camera_btn)

        self.capture_btn = QPushButton("Capture Photo")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._capture_from_camera)
        photo_controls.addWidget(self.capture_btn)
        photo_controls.addStretch(1)
        layout.addLayout(photo_controls)

        content_row = QHBoxLayout()
        self.camera_preview = QLabel("Camera off")
        self.camera_preview.setObjectName("cameraPreview")
        self.camera_preview.setFixedSize(320, 240)
        self.camera_preview.setAlignment(Qt.AlignCenter)
        content_row.addWidget(self.camera_preview)

        self.photo_list = QListWidget()
        content_row.addWidget(self.photo_list, stretch=1)
        layout.addLayout(content_row)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        register_row = QHBoxLayout()
        self.register_btn = QPushButton("Register Participant")
        self.register_btn.setObjectName("primaryButton")
        self.register_btn.clicked.connect(self._start_registration)
        register_row.addWidget(self.register_btn)
        register_row.addStretch(1)
        layout.addLayout(register_row)

        layout.addStretch(1)

    # --- Photo import ----------------------------------------------------

    def _import_photos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select reference photos", "",
            "Images (*.jpg *.jpeg *.png *.webp *.tiff *.tif)",
        )
        for p in paths:
            self._add_photo_to_list(Path(p))

    def _add_photo_to_list(self, path: Path) -> None:
        self._pending_photos.append(path)
        item = QListWidgetItem(f"{path.name}  (pending validation)")
        item.setData(Qt.UserRole, str(path))
        self.photo_list.addItem(item)

    # --- Webcam (section 5: "Capture a photograph using a webcam where
    # available"). Untestable in a headless sandbox -- verify on a machine
    # with an actual camera. Degrades gracefully if none is found. --------

    def _toggle_camera(self) -> None:
        if self._camera is not None:
            self._stop_camera()
            return
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            camera.release()
            QMessageBox.warning(
                self, "No camera found",
                "Could not open a camera. You can still import photos from disk.",
            )
            return
        self._camera = camera
        self.camera_btn.setText("Close Camera")
        self.capture_btn.setEnabled(True)
        self._camera_timer.start(33)  # ~30fps preview

    def _stop_camera(self) -> None:
        self._camera_timer.stop()
        if self._camera is not None:
            self._camera.release()
        self._camera = None
        self._camera_frame = None
        self.camera_btn.setText("Open Camera")
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
            pixmap.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _capture_from_camera(self) -> None:
        if self._camera_frame is None:
            return
        captures_dir = APP_ROOT / "data" / "captures"
        captures_dir.mkdir(parents=True, exist_ok=True)
        out_path = captures_dir / f"capture_{int(time.time() * 1000)}.jpg"
        cv2.imwrite(str(out_path), self._camera_frame)
        self._add_photo_to_list(out_path)

    # --- Registration ------------------------------------------------------

    def _start_registration(self) -> None:
        participant_id = self.id_input.text().strip()
        full_name = self.name_input.text().strip()
        if not participant_id or not full_name:
            QMessageBox.warning(self, "Missing information", "Participant ID and Full Name are required.")
            return
        if not self._pending_photos:
            QMessageBox.warning(self, "No photos", "Add at least one reference photo.")
            return

        with get_session() as session:
            existing = session.query(Participant).filter_by(participant_id=participant_id).one_or_none()
            if existing:
                QMessageBox.warning(self, "Duplicate ID", f"Participant ID '{participant_id}' already exists.")
                return

        self.register_btn.setEnabled(False)
        self.status_label.setText("Validating photos and generating embeddings...")

        self._worker = RegistrationWorker(self.context.embedding_service, list(self._pending_photos))
        self._worker.result_ready.connect(self._on_registration_results)
        self._worker.failed.connect(self._on_registration_failed)
        self._worker.start()

    def _on_registration_failed(self, message: str) -> None:
        self.register_btn.setEnabled(True)
        QMessageBox.critical(self, "Registration failed", message)

    def _on_registration_results(self, results: list[ReferencePhotoResult]) -> None:
        self.register_btn.setEnabled(True)
        self.photo_list.clear()
        accepted = [r for r in results if r.accepted]
        rejected = [r for r in results if not r.accepted]

        for r in results:
            status = "OK" if r.accepted else f"REJECTED: {r.message}"
            self.photo_list.addItem(QListWidgetItem(f"{Path(r.path).name} -- {status}"))

        if not accepted:
            self.status_label.setText("No usable reference photos -- fix the issues above and try again.")
            return

        participant_id = self.id_input.text().strip()
        full_name = self.name_input.text().strip()
        reg_number = self.reg_input.text().strip() or None
        category = self.category_input.text().strip() or None

        with get_session() as session:
            existing = session.query(Participant).filter_by(participant_id=participant_id).one_or_none()
            if existing:
                self.status_label.setText(f"Participant ID '{participant_id}' was registered by someone else just now.")
                return

            participant = Participant(
                participant_id=participant_id, full_name=full_name,
                registration_number=reg_number, category=category, consent_given=True,
            )
            session.add(participant)
            session.flush()

            for r in accepted:
                session.add(ReferenceEmbedding(
                    participant_db_id=participant.id,
                    vector=r.embedding.astype(np.float32).tobytes(),
                    dimensions=EMBEDDING_DIMENSIONS,
                    model_name=EMBEDDING_MODEL_NAME,
                    model_version=EMBEDDING_MODEL_VERSION,
                    source_image_hash=file_sha256(Path(r.path)),
                    thumbnail=r.thumbnail,
                ))

        msg = f"Registered {full_name} ({participant_id}) with {len(accepted)} reference embedding(s)."
        if rejected:
            msg += f" {len(rejected)} photo(s) were rejected -- see the list above."
        self.status_label.setText(msg)
        self._pending_photos = []
        self.id_input.clear()
        self.name_input.clear()
        self.reg_input.clear()
        self.category_input.clear()

    def on_shown(self) -> None:
        pass

    def closeEvent(self, event) -> None:
        self._stop_camera()
        super().closeEvent(event)
