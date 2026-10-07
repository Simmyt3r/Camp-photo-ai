"""Reusable UI building blocks shared across CampPhoto AI pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)


class PageHeader(QWidget):
    """Consistent page title/subtitle block with optional trailing content."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("pageHeader")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        copy.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("pageSubtitle")
            subtitle_label.setWordWrap(True)
            copy.addWidget(subtitle_label)

        row.addLayout(copy, stretch=1)
        self.trailing = QHBoxLayout()
        self.trailing.setContentsMargins(0, 0, 0, 0)
        self.trailing.setSpacing(8)
        row.addLayout(self.trailing)


class Card(QFrame):
    """White, bordered content surface with predictable padding."""

    def __init__(self, title: str | None = None, hint: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(12)

        if title:
            label = QLabel(title)
            label.setObjectName("cardTitle")
            self.body.addWidget(label)
        if hint:
            label = QLabel(hint)
            label.setObjectName("cardHint")
            label.setWordWrap(True)
            self.body.addWidget(label)


class EmptyState(QFrame):
    """Small empty-state panel used when a list or workflow has nothing to show."""

    def __init__(self, title: str, body: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 20, 18, 20)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)

        title_label = QLabel(title)
        title_label.setObjectName("emptyTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        if body:
            body_label = QLabel(body)
            body_label.setObjectName("emptyBody")
            body_label.setWordWrap(True)
            body_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(body_label)


class StatTile(QFrame):
    """Dashboard stat card: a prominent value over a short caption."""

    def __init__(self, caption: str, value: str = "0"):
        super().__init__()
        self.setObjectName("statTile")
        self.setMinimumHeight(96)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(3)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("statCaption")
        self.caption_label.setWordWrap(True)

        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)
        layout.addStretch(1)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
