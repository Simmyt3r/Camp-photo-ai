"""Dashboard: live operational summary + high-frequency workflow shortcuts."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.bootstrap import AppContext
from app.database.db import get_session
from app.services.reporting import compute_dashboard_stats
from app.ui.widgets import Card, PageHeader, StatTile

TILE_SPECS = [
    ("participants", "Registered Participants"),
    ("photos_processed", "Photos Processed"),
    ("faces_detected", "Faces Detected"),
    ("auto_matched", "Automatically Matched"),
    ("needs_review", "Needs Review"),
    ("unmatched", "Unmatched"),
]

ACTION_SPECS = [
    ("Register Participant", "Add a camper and reference photos", "register", True),
    ("Process Photos", "Scan a folder and sort matches", "process", True),
    ("Review Matches", "Resolve uncertain face matches", "review", True),
    ("Participants", "Search, edit, export or reprocess", "participants", False),
    ("Reports", "Inspect previous processing runs", "reports", False),
    ("Settings", "Tune matching and storage options", "settings", False),
]


class DashboardPage(QWidget):
    def __init__(self, context: AppContext, on_navigate: Callable[[str], None]):
        super().__init__()
        self.context = context
        self._on_navigate = on_navigate

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)

        layout.addWidget(PageHeader(
            "Dashboard",
            "See what has been processed, what needs attention, and jump into the next task.",
        ))

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(12)
        self.stats_grid.setVerticalSpacing(12)
        layout.addLayout(self.stats_grid)

        self._tiles: dict[str, StatTile] = {}
        for i, (key, label) in enumerate(TILE_SPECS):
            tile = StatTile(label, "0")
            self._tiles[key] = tile
            self.stats_grid.addWidget(tile, i // 3, i % 3)

        actions_card = Card(
            "Quick actions",
            "The three primary workflows are first. Everything else stays one click away.",
        )
        actions_grid = QGridLayout()
        actions_grid.setSpacing(10)

        for i, (label, description, key, primary) in enumerate(ACTION_SPECS):
            button = QPushButton(f"{label}\n{description}")
            button.setMinimumHeight(58)
            button.setCursor(Qt.PointingHandCursor)
            button.setObjectName("primaryButton" if primary else "secondaryButton")
            button.clicked.connect(lambda checked=False, k=key: self._on_navigate(k))
            actions_grid.addWidget(button, i // 3, i % 3)

        actions_card.body.addLayout(actions_grid)
        layout.addWidget(actions_card)

        self.health_card = Card("Session")
        self.status_note = QLabel("")
        self.status_note.setObjectName("cardHint")
        self.status_note.setWordWrap(True)
        self.health_card.body.addWidget(self.status_note)
        layout.addWidget(self.health_card)

        layout.addStretch(1)
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            with get_session() as session:
                stats = compute_dashboard_stats(session)

            for key, tile in self._tiles.items():
                tile.set_value(f"{stats.get(key, 0):,}")

            needs_review = int(stats.get("needs_review", 0) or 0)
            next_step = (
                f"{needs_review:,} item(s) are waiting for human review."
                if needs_review
                else "No matches are waiting for human review."
            )
            self.status_note.setText(
                f"Processing mode: {self.context.mode.upper()} ({self.context.provider}). "
                f"{next_step} Data is stored locally on this computer."
            )
        except Exception as exc:
            for tile in self._tiles.values():
                tile.set_value("--")
            self.status_note.setText(f"Could not load dashboard statistics: {exc}")
