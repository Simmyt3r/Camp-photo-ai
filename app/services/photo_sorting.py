"""Copies matched photographs into per-participant output folders.
Preserves originals (copy, never move), handles multi-face photos
landing in multiple participant folders, and never silently overwrites
an existing file by default (sections 9, 16)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.utilities.file_utils import safe_output_path, unique_destination

logger = logging.getLogger("camp_photo_ai.photo_sorting")

REVIEW_DIRNAME = "Review"
UNMATCHED_DIRNAME = "Unmatched"
ERRORS_DIRNAME = "Errors"


def participant_folder_name(participant_id: str, full_name: str) -> str:
    return f"{participant_id}_{full_name}".strip("_")


def copy_into(output_root: Path, folder_name: str, source_path: Path,
              duplicate_policy: str = "skip") -> Path | None:
    """Copies source_path into output_root/folder_name/, returning the
    destination path, or None if skipped under duplicate_policy=='skip'.
    Uses safe_output_path so a crafted participant/folder name can never
    escape output_root."""
    dest_dir = safe_output_path(output_root, folder_name)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source_path.name

    if dest.exists():
        if duplicate_policy == "skip":
            logger.debug("Skipping existing file %s", dest)
            return None
        elif duplicate_policy == "rename":
            dest = unique_destination(dest)
        # "keep" falls through and overwrites -- only reached if the
        # operator explicitly configured that; default is "skip".

    shutil.copy2(source_path, dest)
    return dest


def assign_photo(
    output_root: Path,
    source_path: Path,
    participant_id: str | None,
    participant_name: str | None,
    bucket: str,  # "match" | "review" | "unmatched" | "error"
    duplicate_policy: str = "skip",
) -> Path | None:
    if bucket == "match":
        if not participant_id:
            raise ValueError("participant_id is required when bucket == 'match'")
        folder = participant_folder_name(participant_id, participant_name or "")
    elif bucket == "review":
        folder = REVIEW_DIRNAME
    elif bucket == "unmatched":
        folder = UNMATCHED_DIRNAME
    elif bucket == "error":
        folder = ERRORS_DIRNAME
    else:
        raise ValueError(f"Unknown bucket: {bucket}")

    return copy_into(output_root, folder, source_path, duplicate_policy)
