"""
GUI entry point.

    python -m app.main

Bootstraps the local processing context, applies CampPhoto AI branding,
requires acceptance of the current responsible-use agreement on first run,
then launches the main desktop workspace.
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from app.bootstrap import AppContext
from app.ui.agreement_dialog import UserAgreementDialog
from app.ui.branding import (
    AGREEMENT_VERSION, COMPANY_NAME, PRODUCT_NAME, app_logo_path,
)
from app.ui.main_window import MainWindow
from app.ui.styles import STYLESHEET


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setOrganizationName(COMPANY_NAME)
    app.setOrganizationDomain("silabtechnologies")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    logo_path = app_logo_path()
    if logo_path.is_file():
        app.setWindowIcon(QIcon(str(logo_path)))

    context = AppContext.bootstrap()

    if context.settings.user_agreement_version != AGREEMENT_VERSION:
        agreement = UserAgreementDialog(require_acceptance=True)
        if agreement.exec() != QDialog.Accepted or not agreement.accepted:
            raise SystemExit(0)
        context.settings.user_agreement_version = AGREEMENT_VERSION
        context.settings.save()

    window = MainWindow(context)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
