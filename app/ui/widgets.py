"""Reusable UI building blocks shared across CampPhoto AI pages."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
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


class WorkflowSteps(QFrame):
    """Compact visual workflow guide used on task-oriented pages."""

    def __init__(self, steps: list[str], current: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("workflowSteps")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        for index, text in enumerate(steps):
            label = QLabel(f"{index + 1}  {text}")
            label.setObjectName("workflowStepActive" if index == current else "workflowStep")
            layout.addWidget(label)
            if index < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setObjectName("workflowArrow")
                layout.addWidget(arrow)
        layout.addStretch(1)


class DropZone(QFrame):
    """Simple directory drop target for the processing workflow."""

    directory_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(92)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Drop event photo folder here")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignCenter)
        hint = QLabel("or use Browse below")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(hint)

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and Path(urls[0].toLocalFile()).is_dir():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.is_dir():
            self.directory_dropped.emit(str(path))
            event.acceptProposedAction()


class ActivityToast(QFrame):
    """Small animated operator-feedback toast anchored by MainWindow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("activityToast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFixedWidth(420)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setObjectName("activityToastText")
        layout.addWidget(self.label)

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.effect.setOpacity(0.0)

        self.animation = QPropertyAnimation(self.effect, b"opacity", self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, message: str, level: str = "info", duration_ms: int = 3200) -> None:
        self.setProperty("level", level)
        self.style().unpolish(self)
        self.style().polish(self)
        self.label.setText(message)
        self.adjustSize()
        self.setFixedWidth(min(420, max(280, self.sizeHint().width())))
        self.show()
        self.raise_()

        self.animation.stop()
        self.effect.setOpacity(0.0)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        self.hide_timer.start(duration_ms)

    def _fade_out(self) -> None:
        self.animation.stop()
        self.animation.setStartValue(self.effect.opacity())
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self._hide_if_transparent)
        self.animation.start()

    def _hide_if_transparent(self) -> None:
        try:
            self.animation.finished.disconnect(self._hide_if_transparent)
        except (RuntimeError, TypeError):
            pass
        if self.effect.opacity() <= 0.01:
            self.hide()
