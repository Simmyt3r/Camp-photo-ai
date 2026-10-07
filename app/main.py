"""
GUI entry point.

    python -m app.main

Bootstraps the local processing context, applies CampPhoto AI branding,
requires acceptance of the current responsible-use agreement on first run,
then launches the main desktop workspace.

The packaged Windows executable also supports --smoke-test. That mode
constructs the real frozen UI offscreen and exits immediately, allowing CI
to prove that the produced EXE can actually start instead of merely checking
that a file with an .exe suffix exists.
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
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        # Qt sees argv too. Remove our private validation flag before
        # constructing QApplication so it never needs to understand it.
        sys.argv = [arg for arg in sys.argv if arg != "--smoke-test"]

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

    if smoke_test:
        # Build and briefly show the same MainWindow users receive. Running
        # with QT_QPA_PLATFORM=offscreen in CI exercises frozen imports,
        # bootstrap, settings/database initialization, asset lookup and page
        # construction without blocking on the first-run agreement dialog.
        window = MainWindow(context)
        window.show()
        app.processEvents()
        window.close()
        app.processEvents()
        return

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
