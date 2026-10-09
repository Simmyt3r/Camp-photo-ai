"""First-run CampPhoto AI pilot activation dialog."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.services.licensing import (
    PILOT_ACTIVATION_FEE_NGN,
    format_activation_request,
    get_device_id,
    install_license,
)
from app.ui.branding import COMPANY_NAME, SUPPORT_EMAIL, SUPPORT_PHONE


class ActivationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Activate CampPhoto AI")
        self.setModal(True)
        self.resize(680, 720)
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 26)
        root.setSpacing(14)

        title = QLabel("CampPhoto AI Pilot Activation")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "One device • One camp • One batch cycle • Full pilot functionality • Offline after activation"
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        fee = QLabel(f"Activation fee: ₦{PILOT_ACTIVATION_FEE_NGN:,}")
        fee.setObjectName("successBanner")
        root.addWidget(fee)

        payment = QLabel(
            "Phase-one payment is by bank transfer. Obtain the current Silabs payment details "
            f"through {SUPPORT_PHONE} or {SUPPORT_EMAIL}, pay ₦{PILOT_ACTIVATION_FEE_NGN:,}, "
            "then enter the bank/payment reference below. Silabs manually verifies the payment "
            "and sends a signed .cpa-license file."
        )
        payment.setObjectName("infoBanner")
        payment.setWordWrap(True)
        root.addWidget(payment)

        device_frame = QFrame()
        device_frame.setObjectName("card")
        device_row = QHBoxLayout(device_frame)
        device_row.setContentsMargins(14, 12, 14, 12)
        device_row.addWidget(QLabel("Device ID"))

        self.device_id = QLineEdit(get_device_id())
        self.device_id.setReadOnly(True)
        self.device_id.setToolTip("This pilot licence is bound to this device.")
        device_row.addWidget(self.device_id, stretch=1)

        copy_device = QPushButton("Copy")
        copy_device.setObjectName("secondaryButton")
        copy_device.clicked.connect(
            lambda: QApplication.clipboard().setText(self.device_id.text())
        )
        device_row.addWidget(copy_device)
        root.addWidget(device_frame)

        form = QFormLayout()
        form.setSpacing(10)
        self.camp_name = QLineEdit()
        self.camp_name.setPlaceholderText("e.g. NYSC Benue Orientation Camp")
        form.addRow("Camp", self.camp_name)

        self.state = QLineEdit()
        self.state.setPlaceholderText("e.g. Benue")
        form.addRow("State", self.state)

        self.batch_stream = QLineEdit()
        self.batch_stream.setPlaceholderText("e.g. 2026 Batch C Stream I")
        form.addRow("Batch / Stream", self.batch_stream)

        self.contact_name = QLineEdit()
        form.addRow("Contact person", self.contact_name)

        self.contact = QLineEdit()
        self.contact.setPlaceholderText("Phone number or email")
        form.addRow("Phone / Email", self.contact)

        self.payment_reference = QLineEdit()
        self.payment_reference.setPlaceholderText("Bank transfer / transaction reference")
        form.addRow("Payment reference", self.payment_reference)
        root.addLayout(form)

        note = QLabel(
            "After payment, copy the activation request and send it to Silabs. "
            "When the signed licence file is returned, import it below."
        )
        note.setObjectName("cardHint")
        note.setWordWrap(True)
        root.addWidget(note)

        request_row = QHBoxLayout()
        copy_request = QPushButton("Copy activation request")
        copy_request.setObjectName("primaryButton")
        copy_request.clicked.connect(self._copy_request)
        request_row.addWidget(copy_request)

        import_btn = QPushButton("Import .cpa-license")
        import_btn.setObjectName("secondaryButton")
        import_btn.clicked.connect(self._import_license)
        request_row.addWidget(import_btn)
        root.addLayout(request_row)

        root.addStretch(1)

        footer = QLabel(
            f"{COMPANY_NAME}\nSupport: {SUPPORT_PHONE} • {SUPPORT_EMAIL}"
        )
        footer.setObjectName("cardHint")
        footer.setAlignment(Qt.AlignCenter)
        footer.setWordWrap(True)
        root.addWidget(footer)

        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("ghostButton")
        exit_btn.clicked.connect(self.reject)
        root.addWidget(exit_btn, alignment=Qt.AlignRight)

    def _request_values_valid(self) -> bool:
        fields = (
            ("Camp", self.camp_name),
            ("State", self.state),
            ("Batch / Stream", self.batch_stream),
            ("Contact person", self.contact_name),
            ("Phone / Email", self.contact),
            ("Payment reference", self.payment_reference),
        )
        missing = [label for label, field in fields if not field.text().strip()]
        if missing:
            QMessageBox.warning(
                self,
                "Missing activation details",
                "Complete these fields first:\n• " + "\n• ".join(missing),
            )
            return False
        return True

    def _copy_request(self) -> None:
        if not self._request_values_valid():
            return

        request = format_activation_request(
            camp_name=self.camp_name.text(),
            state=self.state.text(),
            batch_stream=self.batch_stream.text(),
            contact_name=self.contact_name.text(),
            contact=self.contact.text(),
            payment_reference=self.payment_reference.text(),
        )
        QApplication.clipboard().setText(request)
        QMessageBox.information(
            self,
            "Activation request copied",
            "The activation request is on your clipboard. Send it to Silabs after payment verification.",
        )

    def _import_license(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import CampPhoto AI licence",
            "",
            "CampPhoto AI Licence (*.cpa-license);;All files (*)",
        )
        if not selected:
            return

        validation = install_license(Path(selected))
        if not validation.valid:
            QMessageBox.critical(self, "Licence not accepted", validation.reason)
            return

        payload = validation.payload or {}
        QMessageBox.information(
            self,
            "Activation successful",
            "CampPhoto AI is activated.\n\n"
            f"Camp: {payload.get('camp_name', '')}\n"
            f"Batch: {payload.get('batch_stream', '')}\n"
            f"Valid until: {payload.get('expires_on', '')}",
        )
        self.accept()
