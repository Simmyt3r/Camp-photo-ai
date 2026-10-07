"""Dashboard: operational summary and next-best workflow action."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.bootstrap import AppContext
from app.database.db import get_session
from app.services.reporting import compute_dashboard_stats
from app.ui.widgets import Card, PageHeader, StatTile

PRIMARY_TILES = [
    ("participants", "Participants"),
    ("photos_processed", "Photos Processed"),
    ("auto_matched", "Matched"),
    ("needs_review", "Needs Review"),
]


class DashboardPage(QWidget):
    def __init__(self, context: AppContext, on_navigate: Callable[[str], None]):
        super().__init__()
        self.context = context
        self._on_navigate = on_navigate
        self._continue_key = "register"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)

        layout.addWidget(PageHeader(
            "Dashboard",
            "Your event-photo workspace: see what happened, what needs attention, and what to do next.",
        ))

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(12)
        self.stats_grid.setVerticalSpacing(12)
        layout.addLayout(self.stats_grid)

        self._tiles: dict[str, StatTile] = {}
        for i, (key, label) in enumerate(PRIMARY_TILES):
            tile = StatTile(label, "0")
            self._tiles[key] = tile
            self.stats_grid.addWidget(tile, 0, i)

        continue_card = Card(
            "Continue workflow",
            "CampPhoto AI prioritises the next useful action instead of making every screen shout at once.",
        )
        self.continue_title = QLabel("Register your first participant")
        self.continue_title.setObjectName("cardTitle")
        self.continue_body = QLabel(
            "Add a participant and clear reference photos before processing an event folder."
        )
        self.continue_body.setObjectName("cardHint")
        self.continue_body.setWordWrap(True)
        self.continue_btn = QPushButton("Register Participant")
        self.continue_btn.setObjectName("primaryButton")
        self.continue_btn.setMinimumHeight(44)
        self.continue_btn.clicked.connect(lambda: self._on_navigate(self._continue_key))
        continue_card.body.addWidget(self.continue_title)
        continue_card.body.addWidget(self.continue_body)
        continue_card.body.addWidget(self.continue_btn, alignment=Qt.AlignLeft)
        layout.addWidget(continue_card)

        actions_card = Card("Other actions")
        actions = QGridLayout()
        actions.setSpacing(10)
        for i, (label, key) in enumerate([
            ("Register Participant", "register"),
            ("Participants", "participants"),
            ("Process Photos", "process"),
            ("Review Matches", "review"),
            ("Reports", "reports"),
            ("Settings", "settings"),
        ]):
            button = QPushButton(label)
            button.setObjectName("secondaryButton")
            button.clicked.connect(lambda checked=False, k=key: self._on_navigate(k))
            actions.addWidget(button, i // 3, i % 3)
        actions_card.body.addLayout(actions)
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

            participants = int(stats.get("participants", 0) or 0)
            needs_review = int(stats.get("needs_review", 0) or 0)

            if participants == 0:
                self._continue_key = "register"
                self.continue_title.setText("Register your first participant")
                self.continue_body.setText(
                    "Create a consented participant profile and add clear reference photos."
                )
                self.continue_btn.setText("Register Participant")
            elif needs_review > 0:
                self._continue_key = "review"
                self.continue_title.setText(f"Review {needs_review:,} uncertain match(es)")
                self.continue_body.setText(
                    "The AI found possible matches that need a human decision before delivery."
                )
                self.continue_btn.setText(f"Review {needs_review:,} Matches")
            else:
                self._continue_key = "process"
                self.continue_title.setText("Process event photos")
                self.continue_body.setText(
                    "Participants are ready and no review items are waiting. Select an event folder to continue."
                )
                self.continue_btn.setText("Process Event Photos")

            self.status_note.setText(
                f"Face model: {self.context.settings.embedding_model_name} • "
                f"Mode: {self.context.mode.upper()} • "
                f"Faces detected: {int(stats.get('faces_detected', 0) or 0):,} • "
                f"Unmatched: {int(stats.get('unmatched', 0) or 0):,} • "
                "Data stays on this computer."
            )
        except Exception as exc:
            for tile in self._tiles.values():
                tile.set_value("--")
            self.status_note.setText(f"Could not load dashboard statistics: {exc}")
