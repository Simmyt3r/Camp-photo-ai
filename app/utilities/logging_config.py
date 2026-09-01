"""
Structured logging setup.

Section 29 requires DEBUG/INFO/WARNING/ERROR/CRITICAL logs and explicitly
forbids logging raw biometric vectors. RedactBiometricFilter is a safety
net: even if a caller accidentally passes an embedding into a log call,
this strips it before the record is emitted, rather than relying purely
on the coding convention of "don't log .vector".
"""
from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

# Matches a bracketed list of 16+ floats -- the shape of a face embedding
# (512-d in this build), unlikely to appear in ordinary log messages.
_VECTOR_LIKE = re.compile(r"(\[\s*-?\d+\.\d+(?:e-?\d+)?\s*(?:,\s*-?\d+\.\d+(?:e-?\d+)?\s*){15,}\])")


class RedactBiometricFilter(logging.Filter):
    """Strips anything that looks like a long float vector from log
    messages so an embedding can never end up in a log file."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and _VECTOR_LIKE.search(record.msg):
            record.msg = _VECTOR_LIKE.sub("[REDACTED_VECTOR]", record.msg)
        return True


def configure_logging(logs_dir: str | Path, level: str = "INFO") -> None:
    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("camp_photo_ai")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(RedactBiometricFilter())
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "camp_photo_ai.log", maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactBiometricFilter())
    root.addHandler(file_handler)

    # Dedicated audit trail (section 29): registration, processing
    # start/completion, match decisions, human corrections, config
    # changes, participant deletion.
    audit = logging.getLogger("camp_photo_ai.audit")
    audit_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "audit.log", maxBytes=10_000_000, backupCount=10, encoding="utf-8"
    )
    audit_handler.setFormatter(formatter)
    audit_handler.addFilter(RedactBiometricFilter())
    audit.addHandler(audit_handler)
    audit.setLevel(logging.INFO)
    audit.propagate = False
