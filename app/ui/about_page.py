"""Branded product/about/contact page."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.bootstrap import AppContext
from app.ui.agreement_dialog import UserAgreementDialog
from app.ui.branding import COMPANY_NAME, SUPPORT_EMAIL, SUPPORT_PHONE, app_logo_path
from app.ui.widgets import Card, PageHeader


class AboutPage(QWidget):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(16)
        layout.addWidget(PageHeader(
            "About CampPhoto AI",
            "Product identity, system status, responsible-use information, and support contacts.",
        ))

        hero = Card()
        row = QHBoxLayout()
        row.setSpacing(18)

        logo = QLabel()
        pixmap = QPixmap(str(app_logo_path()))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setFixedSize(102, 102)
        logo.setAlignment(Qt.AlignCenter)
        row.addWidget(logo)

        copy = QVBoxLayout()
        title = QLabel("CampPhoto AI")
        title.setObjectName("aboutTitle")
        company = QLabel(f"by {COMPANY_NAME}")
        company.setObjectName("pageSubtitle")
        description = QLabel(
            "Local AI-assisted photo matching for camps, schools, conferences, churches, "
            "events, and other large photo collections."
        )
        description.setWordWrap(True)
        description.setObjectName("cardHint")
        copy.addWidget(title)
        copy.addWidget(company)
        copy.addWidget(description)
        copy.addStretch(1)
        row.addLayout(copy, stretch=1)
        hero.body.addLayout(row)
        layout.addWidget(hero)

        system = Card("System status")
        self.system_label = QLabel()
        self.system_label.setWordWrap(True)
        system.body.addWidget(self.system_label)
        layout.addWidget(system)

        contact = Card("Contact & support", "For product support, deployment enquiries, or usage questions.")
        contact_label = QLabel(
            f"<b>{COMPANY_NAME}</b><br>"
            f"Phone: {SUPPORT_PHONE}<br>"
            f"Email: {SUPPORT_EMAIL}"
        )
        contact_label.setTextFormat(Qt.RichText)
        contact.body.addWidget(contact_label)
        agreement_btn = QPushButton("View user agreement")
        agreement_btn.setObjectName("secondaryButton")
        agreement_btn.clicked.connect(self._show_agreement)
        contact.body.addWidget(agreement_btn, alignment=Qt.AlignLeft)
        layout.addWidget(contact)
        layout.addStretch(1)

        self.on_shown()

    def _show_agreement(self) -> None:
        UserAgreementDialog(self, require_acceptance=False).exec()

    def on_shown(self) -> None:
        self.system_label.setText(
            f"Face model: {self.context.settings.embedding_model_name} "
            f"({self.context.settings.embedding_model_version})<br>"
            f"Processing mode: {self.context.mode.upper()}<br>"
            f"Provider: {self.context.provider}<br>"
            "Privacy mode: Local processing"
        )
