"""
GUI entry point.

    python -m app.main

Launches the PySide6 desktop app (dashboard, registration, processing,
review -- section 17). Uses the same AppContext.bootstrap() as the CLI,
so settings/hardware detection/model provider selection are identical
between the two entry points.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.bootstrap import AppContext
from app.ui.main_window import MainWindow
from app.ui.styles import STYLESHEET


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("CampPhoto AI")
    app.setOrganizationName("Silabs")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    context = AppContext.bootstrap()
    window = MainWindow(context)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
