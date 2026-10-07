"""Application-wide operator feedback bus.

Pages publish meaningful completed/failed activities here. MainWindow turns
those events into a short animated toast and keeps the latest activity in the
status bar, so operators always know what the app just did.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ActivityBus(QObject):
    message = Signal(str, str)


_activity_bus = ActivityBus()


def activity_bus() -> ActivityBus:
    return _activity_bus


def notify_activity(message: str, level: str = "info") -> None:
    _activity_bus.message.emit(message, level)
