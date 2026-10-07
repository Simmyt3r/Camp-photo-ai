"""Main application window: responsive sidebar navigation + stacked pages."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QStatusBar, QStyle, QVBoxLayout, QWidget,
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
    ("dashboard", "Dashboard", QStyle.SP_ComputerIcon),
    ("register", "Register Participant", QStyle.SP_FileDialogNewFolder),
    ("process", "Process Photos", QStyle.SP_MediaPlay),
    ("review", "Review Matches", QStyle.SP_DialogApplyButton),
    ("participants", "Participants", QStyle.SP_DirHomeIcon),
    ("reports", "Reports", QStyle.SP_FileIcon),
    ("settings", "Settings", QStyle.SP_FileDialogDetailedView),
]


class MainWindow(QMainWindow):
    EXPANDED_WIDTH = 236
    COLLAPSED_WIDTH = 72

    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._sidebar_collapsed = False
        self._auto_collapsed = False

        self.setWindowTitle("CampPhoto AI")
        self.resize(1220, 820)
        self.setMinimumSize(820, 600)

        central = QWidget()
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

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
        self._build_status_bar()
        self.navigate("dashboard")

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(self.EXPANDED_WIDTH)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 14)
        layout.setSpacing(6)

        brand = QFrame()
        brand.setObjectName("brandBlock")
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(4, 0, 4, 10)
        brand_row.setSpacing(8)

        brand_copy = QVBoxLayout()
        brand_copy.setContentsMargins(0, 0, 0, 0)
        brand_copy.setSpacing(0)

        self.brand_title = QLabel("CampPhoto AI")
        self.brand_title.setObjectName("sidebarTitle")
        self.brand_subtitle = QLabel("Local photo intelligence")
        self.brand_subtitle.setObjectName("sidebarSubtitle")
        brand_copy.addWidget(self.brand_title)
        brand_copy.addWidget(self.brand_subtitle)
        brand_row.addLayout(brand_copy, stretch=1)

        self.sidebar_toggle = QPushButton("‹")
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setToolTip("Collapse navigation")
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        brand_row.addWidget(self.sidebar_toggle)

        layout.addWidget(brand)
        layout.addSpacing(4)

        self._nav_buttons: dict[str, QPushButton] = {}
        style = self.style()
        for key, label, icon_type in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(style.standardIcon(icon_type))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(label)
            btn.clicked.connect(lambda checked=False, k=key: self.navigate(k))
            layout.addWidget(btn)
            self._nav_buttons[key] = btn

        layout.addStretch(1)

        self.sidebar_footer = QLabel("Offline-first • biometric data stays local")
        self.sidebar_footer.setObjectName("sidebarFooter")
        self.sidebar_footer.setWordWrap(True)
        layout.addWidget(self.sidebar_footer)

        return sidebar

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)

        self.status_mode = QLabel(
            f"Ready  •  {self.context.mode.upper()}  •  {self.context.provider}"
        )
        self.status_mode.setToolTip(
            "Processing provider selected for this session. "
            f"Database: {self.context.settings.database_path}"
        )
        status.addWidget(self.status_mode)

        local_label = QLabel("Local processing")
        local_label.setToolTip("Photos and face embeddings are processed on this computer.")
        status.addPermanentWidget(local_label)

    def _toggle_sidebar(self) -> None:
        self._auto_collapsed = False
        self._set_sidebar_collapsed(not self._sidebar_collapsed)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._sidebar_collapsed:
            return
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH)

        self.brand_title.setVisible(not collapsed)
        self.brand_subtitle.setVisible(not collapsed)
        self.sidebar_footer.setVisible(not collapsed)
        self.sidebar_toggle.setText("›" if collapsed else "‹")
        self.sidebar_toggle.setToolTip("Expand navigation" if collapsed else "Collapse navigation")

        labels = {key: label for key, label, _icon in NAV_ITEMS}
        for key, btn in self._nav_buttons.items():
            btn.setText("" if collapsed else labels[key])
            btn.setToolTip(labels[key])

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() < 1000 and not self._sidebar_collapsed:
            self._auto_collapsed = True
            self._set_sidebar_collapsed(True)
        elif self.width() > 1160 and self._sidebar_collapsed and self._auto_collapsed:
            self._set_sidebar_collapsed(False)
            self._auto_collapsed = False

    def navigate(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return

        self.stack.setCurrentWidget(page)
        labels = {item_key: label for item_key, label, _icon in NAV_ITEMS}
        self.setWindowTitle(f"{labels.get(key, 'CampPhoto AI')} • CampPhoto AI")

        for nav_key, btn in self._nav_buttons.items():
            btn.setChecked(nav_key == key)

        on_shown = getattr(page, "on_shown", None)
        if callable(on_shown):
            on_shown()

    def closeEvent(self, event) -> None:
        registration_page = self._pages.get("register")
        stop_camera = getattr(registration_page, "_stop_camera", None)
        if callable(stop_camera):
            stop_camera()
        super().closeEvent(event)
