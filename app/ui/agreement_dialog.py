"""First-run responsible-use agreement for CampPhoto AI."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from app.ui.branding import (
    AGREEMENT_VERSION, COMPANY_NAME, SUPPORT_EMAIL, SUPPORT_PHONE, app_logo_path,
)

AGREEMENT_TEXT = f"""
<b>CampPhoto AI Responsible Use Agreement</b><br><br>

CampPhoto AI is a local photo-matching tool produced by
<b>{COMPANY_NAME}</b>. It uses facial reference data to help an authorised
operator find photos that may contain registered participants.<br><br>

<b>By using this application, you agree that:</b><br>
• You will register a participant only after obtaining appropriate consent for
  facial reference processing and storage.<br>
• You will use CampPhoto AI only for legitimate photo organisation and delivery,
  not covert surveillance, harassment, discrimination, or unlawful tracking.<br>
• Automated matches are assistance, not legal proof of identity. Human review
  remains necessary for uncertain or consequential decisions.<br>
• You are responsible for protecting the computer, database, reference photos,
  exports, and other personal data created or stored through the application.<br>
• Personal and biometric data should be deleted when it is no longer required
  for the event or purpose for which it was collected.<br>
• You will follow applicable privacy, data-protection, event, school, workplace,
  or organisational rules where CampPhoto AI is used.<br><br>

CampPhoto AI is designed for local processing. Model/provider information may
be shown inside the application for diagnostics.<br><br>

<b>Support</b><br>
Phone: {SUPPORT_PHONE}<br>
Email: {SUPPORT_EMAIL}<br><br>

Agreement version: {AGREEMENT_VERSION}
"""


class UserAgreementDialog(QDialog):
    def __init__(self, parent=None, *, require_acceptance: bool = True):
        super().__init__(parent)
        self.require_acceptance = require_acceptance
        self.accepted = False
        self.setWindowTitle("CampPhoto AI • User Agreement")
        self.resize(720, 650)
        self.setMinimumSize(560, 520)
        self.setModal(require_acceptance)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        brand = QHBoxLayout()
        logo = QLabel()
        pixmap = QPixmap(str(app_logo_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand.addWidget(logo)

        title_box = QVBoxLayout()
        title = QLabel("CampPhoto AI")
        title.setObjectName("pageTitle")
        subtitle = QLabel(f"by {COMPANY_NAME}")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        brand.addLayout(title_box, stretch=1)
        layout.addLayout(brand)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        agreement = QLabel(AGREEMENT_TEXT)
        agreement.setWordWrap(True)
        agreement.setTextFormat(Qt.RichText)
        agreement.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        body_layout.addWidget(agreement)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        if require_acceptance:
            self.checkbox = QCheckBox(
                "I have read this agreement and accept responsibility for using CampPhoto AI appropriately."
            )
            self.checkbox.setObjectName("agreementCheckbox")
            self.checkbox.toggled.connect(self._sync_accept_button)
            layout.addWidget(self.checkbox)

        buttons = QHBoxLayout()
        if require_acceptance:
            exit_btn = QPushButton("Exit")
            exit_btn.setObjectName("ghostButton")
            exit_btn.clicked.connect(self.reject)
            buttons.addWidget(exit_btn)
            buttons.addStretch(1)

            self.accept_btn = QPushButton("Accept and continue")
            self.accept_btn.setObjectName("primaryButton")
            self.accept_btn.setEnabled(False)
            self.accept_btn.clicked.connect(self._accept)
            buttons.addWidget(self.accept_btn)
        else:
            buttons.addStretch(1)
            close_btn = QPushButton("Close")
            close_btn.setObjectName("primaryButton")
            close_btn.clicked.connect(self.accept)
            buttons.addWidget(close_btn)

        layout.addLayout(buttons)

    def _sync_accept_button(self, checked: bool) -> None:
        if self.require_acceptance:
            self.accept_btn.setEnabled(checked)

    def _accept(self) -> None:
        self.accepted = True
        self.accept()
