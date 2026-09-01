"""Small, reusable widgets shared across pages."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class StatTile(QFrame):
    """A dashboard stat card: a big number over a caption."""

    def __init__(self, caption: str, value: str = "0"):
        super().__init__()
        self.setObjectName("statTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("statCaption")

        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
