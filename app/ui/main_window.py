"""Branded main application shell with responsive navigation and activity feedback."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QStackedWidget, QStatusBar, QStyle, QVBoxLayout, QWidget,
)

from app.bootstrap import AppContext
from app.services.licensing import validate_installed_license
from app.ui.about_page import AboutPage
from app.ui.activity import activity_bus
from app.ui.branding import (
    COMPANY_NAME, PRODUCT_NAME, SUPPORT_EMAIL, SUPPORT_PHONE, app_logo_path,
)
from app.ui.dashboard_page import DashboardPage
from app.ui.license_page import LicensePage
from app.ui.participants_page import ParticipantsPage
from app.ui.processing_page import ProcessingPage
from app.ui.registration_page import RegistrationPage
from app.ui.reports_page import ReportsPage
from app.ui.review_page import ReviewPage
from app.ui.settings_page import SettingsPage
from app.ui.widgets import ActivityToast

NAV_ITEMS = [
    ("dashboard", "Dashboard", QStyle.SP_ComputerIcon),
    ("register", "Register Participant", QStyle.SP_FileDialogNewFolder),
    ("participants", "Participants", QStyle.SP_DirHomeIcon),
    ("process", "Process Photos", QStyle.SP_MediaPlay),
    ("review", "Review Matches", QStyle.SP_DialogApplyButton),
    ("reports", "Reports", QStyle.SP_FileIcon),
    ("settings", "Settings", QStyle.SP_FileDialogDetailedView),
    ("license", "Licence & Activation", QStyle.SP_DialogYesButton),
    ("about", "About & Contact", QStyle.SP_MessageBoxInformation),
]

MODEL_FILES = {
    "det_10g.onnx",
    "1k3d68.onnx",
    "2d106det.onnx",
    "genderage.onnx",
    "w600k_r50.onnx",
}


class MainWindow(QMainWindow):
    EXPANDED_WIDTH = 252
    COLLAPSED_WIDTH = 72

    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._sidebar_collapsed = False
        self._auto_collapsed = False
        self._page_animation: QPropertyAnimation | None = None

        self.setWindowTitle(PRODUCT_NAME)
        logo_path = app_logo_path()
        if logo_path.is_file():
            self.setWindowIcon(QIcon(str(logo_path)))

        self.resize(1240, 820)
        self.setMinimumSize(820, 600)

        central = QWidget()
        self._central = central
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root_layout.addWidget(self.sidebar)

        content_shell = QWidget()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.top_status = self._build_top_status()
        content_layout.addWidget(self.top_status)

        self.stack = QStackedWidget()
        self._pages = {
            "dashboard": DashboardPage(context, on_navigate=self.navigate),
            "register": RegistrationPage(context),
            "participants": ParticipantsPage(context),
            "process": ProcessingPage(context),
            "review": ReviewPage(context),
            "reports": ReportsPage(context),
            "settings": SettingsPage(context),
            "license": LicensePage(context),
            "about": AboutPage(context),
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        content_layout.addWidget(self.stack, stretch=1)

        root_layout.addWidget(content_shell, stretch=1)
        self.setCentralWidget(central)

        self.activity_toast = ActivityToast(central)
        activity_bus().message.connect(self.show_activity)

        self._build_status_bar()
        self.navigate("dashboard")
        self.show_activity("CampPhoto AI is ready.", "success", duration_ms=1800)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(self.EXPANDED_WIDTH)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(6)

        brand = QFrame()
        brand.setObjectName("brandBlock")
        brand_row = QHBoxLayout(brand)
        brand_row.setContentsMargins(2, 0, 2, 10)
        brand_row.setSpacing(9)

        self.brand_logo = QLabel()
        self.brand_logo.setObjectName("brandLogo")
        self.brand_logo.setFixedSize(44, 44)
        self.brand_logo.setAlignment(Qt.AlignCenter)
        pixmap = QPixmap(str(app_logo_path()))
        if not pixmap.isNull():
            self.brand_logo.setPixmap(
                pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        brand_row.addWidget(self.brand_logo)

        brand_copy = QVBoxLayout()
        brand_copy.setContentsMargins(0, 0, 0, 0)
        brand_copy.setSpacing(0)
        self.brand_title = QLabel(PRODUCT_NAME)
        self.brand_title.setObjectName("sidebarTitle")
        self.brand_subtitle = QLabel("AI photo matching")
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

        self.sidebar_footer = QLabel(
            f"{COMPANY_NAME}\n{SUPPORT_PHONE} • {SUPPORT_EMAIL}"
        )
        self.sidebar_footer.setObjectName("sidebarFooter")
        self.sidebar_footer.setWordWrap(True)
        layout.addWidget(self.sidebar_footer)

        return sidebar

    def _build_top_status(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topStatusBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 8, 18, 8)
        row.setSpacing(8)

        product = QLabel(f"{PRODUCT_NAME} workspace")
        product.setObjectName("companyFooter")
        row.addWidget(product)
        row.addStretch(1)

        model = QLabel("● Model Ready" if self._model_ready() else "○ Model not ready")
        model.setObjectName("statusChipReady" if self._model_ready() else "statusChip")
        row.addWidget(model)

        licence = validate_installed_license()
        licence_chip = QLabel("● Pilot Licensed" if licence.valid else "○ Licence issue")
        licence_chip.setObjectName("statusChipReady" if licence.valid else "statusChip")
        licence_chip.setToolTip(licence.reason)
        row.addWidget(licence_chip)

        mode = QLabel(self.context.mode.upper())
        mode.setObjectName("statusChip")
        mode.setToolTip(self.context.provider)
        row.addWidget(mode)

        local = QLabel("Local processing")
        local.setObjectName("statusChip")
        local.setToolTip("Photos and facial reference data are processed on this computer.")
        row.addWidget(local)
        return bar

    def _model_ready(self) -> bool:
        candidates = [
            Path(self.context.settings.models_dir) / "buffalo_l",
            Path(self.context.settings.models_dir) / "models" / "buffalo_l",
        ]
        return any(
            path.is_dir()
            and all((path / name).is_file() and (path / name).stat().st_size > 0 for name in MODEL_FILES)
            for path in candidates
        )

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)

        self.status_activity = QLabel(
            f"Ready • {self.context.mode.upper()} • {self.context.provider}"
        )
        self.status_activity.setToolTip(
            f"Database: {self.context.settings.database_path}"
        )
        status.addWidget(self.status_activity, stretch=1)

        support = QLabel(f"Support: {SUPPORT_PHONE}")
        support.setToolTip(SUPPORT_EMAIL)
        status.addPermanentWidget(support)

    def show_activity(
        self,
        message: str,
        level: str = "info",
        *,
        duration_ms: int = 3200,
    ) -> None:
        self.status_activity.setText(message)
        self.activity_toast.show_message(message, level, duration_ms)
        self._position_toast()

    def _position_toast(self) -> None:
        if not hasattr(self, "activity_toast"):
            return
        margin = 22
        x = max(margin, self._central.width() - self.activity_toast.width() - margin)
        y = max(16, self.top_status.height() + 16)
        self.activity_toast.move(x, y)
        self.activity_toast.raise_()

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
        self.brand_logo.setFixedSize(40, 40)
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
        self._position_toast()

    def navigate(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return

        self.stack.setCurrentWidget(page)
        labels = {item_key: label for item_key, label, _icon in NAV_ITEMS}
        self.setWindowTitle(f"{labels.get(key, PRODUCT_NAME)} • {PRODUCT_NAME}")

        for nav_key, btn in self._nav_buttons.items():
            btn.setChecked(nav_key == key)

        self._animate_page(page)

        on_shown = getattr(page, "on_shown", None)
        if callable(on_shown):
            on_shown()

    def _animate_page(self, page: QWidget) -> None:
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(140)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        self._page_animation = animation
        animation.start()

    def closeEvent(self, event) -> None:
        registration_page = self._pages.get("register")
        stop_camera = getattr(registration_page, "_stop_camera", None)
        if callable(stop_camera):
            stop_camera()
        super().closeEvent(event)
