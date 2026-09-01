"""Duplicate photo detection: exact (file hash) and near-duplicate
(perceptual hash), per section 15."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.utilities.file_utils import file_sha256, hashes_are_near_duplicate, perceptual_hash

logger = logging.getLogger("camp_photo_ai.duplicate_detection")


@dataclass
class DuplicateCheckResult:
    is_exact_duplicate: bool
    is_near_duplicate: bool
    duplicate_of: Path | None


class DuplicateIndex:
    """Tracks hashes of photos already seen in the current run so
    incoming photos can be checked against everything processed so far."""

    def __init__(self, perceptual_threshold: int = 6):
        self._perceptual_threshold = perceptual_threshold
        self._by_sha256: dict[str, Path] = {}
        self._by_phash: dict[object, Path] = {}

    def check(self, path: Path) -> DuplicateCheckResult:
        sha = file_sha256(path)
        if sha in self._by_sha256:
            return DuplicateCheckResult(True, True, self._by_sha256[sha])

        try:
            phash = perceptual_hash(path)
        except Exception as exc:
            logger.warning("Could not compute perceptual hash for %s: %s", path, exc)
            self._by_sha256[sha] = path
            return DuplicateCheckResult(False, False, None)

        for existing_hash, existing_path in self._by_phash.items():
            if hashes_are_near_duplicate(phash, existing_hash, self._perceptual_threshold):
                self._by_sha256[sha] = path
                return DuplicateCheckResult(False, True, existing_path)

        self._by_sha256[sha] = path
        self._by_phash[phash] = path
        return DuplicateCheckResult(False, False, None)
