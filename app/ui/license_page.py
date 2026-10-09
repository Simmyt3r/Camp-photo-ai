"""Licence and activation status page."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap import AppContext
from app.services.licensing import (
    PILOT_ACTIVATION_FEE_NGN,
    get_device_id,
    install_license,
    validate_installed_license,
)
from app.ui.branding import SUPPORT_EMAIL, SUPPORT_PHONE
from app.ui.widgets import Card, PageHeader


class LicensePage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)

        layout.addWidget(
            PageHeader(
                "Licence & Activation",
                "Pilot licence status, device identity, validity, and licence replacement.",
            )
        )

        device = Card("This device")
        device_row = QHBoxLayout()
        self.device_label = QLabel(get_device_id())
        self.device_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        device_row.addWidget(self.device_label, stretch=1)

        copy_btn = QPushButton("Copy Device ID")
        copy_btn.setObjectName("secondaryButton")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(self.device_label.text())
        )
        device_row.addWidget(copy_btn)
        device.body.addLayout(device_row)
        layout.addWidget(device)

        self.status_card = Card(
            "Camp Pilot Licence",
            f"Pilot activation fee: ₦{PILOT_ACTIVATION_FEE_NGN:,}",
        )
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status_card.body.addWidget(self.status)

        import_btn = QPushButton("Import replacement licence")
        import_btn.setObjectName("secondaryButton")
        import_btn.clicked.connect(self._import)
        self.status_card.body.addWidget(import_btn, alignment=Qt.AlignLeft)
        layout.addWidget(self.status_card)

        support = Card("Payment & support")
        support_text = QLabel(
            "Phase-one payment is manually verified by Silabs before a signed licence is issued.<br>"
            f"Phone: {SUPPORT_PHONE}<br>Email: {SUPPORT_EMAIL}"
        )
        support_text.setTextFormat(Qt.RichText)
        support.body.addWidget(support_text)
        layout.addWidget(support)
        layout.addStretch(1)

        self.on_shown()

    def _import(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import CampPhoto AI licence",
            "",
            "CampPhoto AI Licence (*.cpa-license);;All files (*)",
        )
        if not selected:
            return

        validation = install_license(Path(selected))
        if validation.valid:
            QMessageBox.information(
                self,
                "Licence installed",
                "The licence is valid and has been installed.",
            )
        else:
            QMessageBox.critical(self, "Licence not accepted", validation.reason)
        self.on_shown()

    def on_shown(self) -> None:
        validation = validate_installed_license()
        if not validation.valid:
            self.status.setText(f"<b>Status:</b> Not active<br>{validation.reason}")
            return

        payload = validation.payload or {}
        self.status.setText(
            "<b>Status:</b> Active<br>"
            f"<b>Camp:</b> {payload.get('camp_name', '')}<br>"
            f"<b>State:</b> {payload.get('state', '')}<br>"
            f"<b>Batch / Stream:</b> {payload.get('batch_stream', '')}<br>"
            f"<b>Licence ID:</b> {payload.get('license_id', '')}<br>"
            f"<b>Issued:</b> {payload.get('issued_on', '')}<br>"
            f"<b>Expires:</b> {payload.get('expires_on', '')}"
        )
