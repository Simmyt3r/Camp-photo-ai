"""Dashboard: live stats + navigation shortcuts (section 17)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.bootstrap import AppContext
from app.database.db import get_session
from app.services.reporting import compute_dashboard_stats
from app.ui.widgets import StatTile

TILE_SPECS = [
    ("participants", "Registered Participants"),
    ("photos_processed", "Photos Processed"),
    ("faces_detected", "Faces Detected"),
    ("auto_matched", "Automatically Matched"),
    ("needs_review", "Needs Review"),
    ("unmatched", "Unmatched"),
]


class DashboardPage(QWidget):
    def __init__(self, context: AppContext, on_navigate: Callable[[str], None]):
        super().__init__()
        self.context = context
        self._on_navigate = on_navigate

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        header = QLabel("Dashboard")
        header.setObjectName("pageTitle")
        layout.addWidget(header)

        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(16)
        layout.addLayout(self.stats_grid)

        self._tiles: dict[str, StatTile] = {}
        for i, (key, label) in enumerate(TILE_SPECS):
            tile = StatTile(label, "0")
            self._tiles[key] = tile
            self.stats_grid.addWidget(tile, i // 3, i % 3)

        layout.addSpacing(4)
        actions_label = QLabel("Actions")
        actions_label.setObjectName("sectionLabel")
        layout.addWidget(actions_label)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(12)
        self._add_action(actions_row, "Register Participant", lambda: self._on_navigate("register"))
        self._add_action(actions_row, "Process Photos", lambda: self._on_navigate("process"))
        self._add_action(actions_row, "Review Matches", lambda: self._on_navigate("review"))
        self._add_action(actions_row, "Participants", lambda: self._on_navigate("participants"))
        self._add_action(actions_row, "Reports", lambda: self._on_navigate("reports"))
        self._add_action(actions_row, "Settings", lambda: self._on_navigate("settings"))
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        self.status_note = QLabel("")
        self.status_note.setObjectName("hintLabel")
        layout.addWidget(self.status_note)

        layout.addStretch(1)
        self.refresh()

    def _add_action(self, row: QHBoxLayout, label: str, handler, enabled: bool = True, tooltip: str | None = None) -> None:
        btn = QPushButton(label)
        btn.setObjectName("primaryButton" if enabled else "disabledButton")
        btn.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        btn.setEnabled(enabled)
        if tooltip:
            btn.setToolTip(tooltip)
        if handler:
            btn.clicked.connect(handler)
        row.addWidget(btn)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            with get_session() as session:
                stats = compute_dashboard_stats(session)
            for key, tile in self._tiles.items():
                tile.set_value(f"{stats.get(key, 0):,}")
            self.status_note.setText(
                f"Mode: {self.context.mode.upper()} ({self.context.provider})  |  "
                f"Database: {self.context.settings.database_path}"
            )
        except Exception as exc:
            for tile in self._tiles.values():
                tile.set_value("--")
            self.status_note.setText(f"Could not load stats: {exc}")
