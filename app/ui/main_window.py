"""Main application window: sidebar navigation + stacked content pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QStatusBar, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.ui.dashboard_page import DashboardPage
from app.ui.participants_page import ParticipantsPage
from app.ui.processing_page import ProcessingPage
from app.ui.registration_page import RegistrationPage
from app.ui.reports_page import ReportsPage
from app.ui.review_page import ReviewPage
from app.ui.settings_page import SettingsPage

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("register", "Register Participant"),
    ("process", "Process Photos"),
    ("review", "Review Matches"),
    ("participants", "Participants"),
    ("reports", "Reports"),
    ("settings", "Settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self.setWindowTitle("CampPhoto AI")
        self.resize(1200, 800)
        self.setMinimumSize(960, 640)

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self._pages = {
            "dashboard": DashboardPage(context, on_navigate=self.navigate),
            "register": RegistrationPage(context),
            "process": ProcessingPage(context),
            "review": ReviewPage(context),
            "participants": ParticipantsPage(context),
            "reports": ReportsPage(context),
            "settings": SettingsPage(context),
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        root_layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"Processing mode: {context.mode.upper()} ({context.provider})  |  "
            f"Database: {context.settings.database_path}"
        )

        self.navigate("dashboard")

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 24, 0, 24)
        layout.setSpacing(4)

        title = QLabel("CampPhoto AI")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)
        layout.addSpacing(16)

        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self.navigate(k))
            layout.addWidget(btn)
            self._nav_buttons[key] = btn

        layout.addStretch(1)
        return sidebar

    def navigate(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)
        on_shown = getattr(page, "on_shown", None)
        if callable(on_shown):
            on_shown()

    def closeEvent(self, event) -> None:
        registration_page = self._pages.get("register")
        stop_camera = getattr(registration_page, "_stop_camera", None)
        if callable(stop_camera):
            stop_camera()  # releases the webcam if it was left open
        super().closeEvent(event)
