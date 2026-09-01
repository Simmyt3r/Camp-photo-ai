"""Participant search and management (spec section 19): search by name/
ID/registration number/category, view matched-photo counts, edit
metadata, and export a participant's matched photos. Deletion already
lives in review_service.py (delete_participant) since it was needed
there first for the review workflow -- not duplicated here."""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import MatchDecisionEnum, MatchRecord, Participant
from app.utilities.file_utils import safe_output_path, sanitize_filename

logger = logging.getLogger("camp_photo_ai.participants")
audit = logging.getLogger("camp_photo_ai.audit")


def search_participants(session: Session, query: str, limit: int = 100) -> list[Participant]:
    """Searches by name, participant ID, registration number, or
    category (section 19) -- a blank query returns everyone, up to
    `limit`, ordered by name."""
    q = session.query(Participant)
    if query and query.strip():
        like = f"%{query.strip()}%"
        q = q.filter(or_(
            Participant.full_name.ilike(like),
            Participant.participant_id.ilike(like),
            Participant.registration_number.ilike(like),
            Participant.category.ilike(like),
        ))
    return q.order_by(Participant.full_name).limit(limit).all()


def count_matched_photos(session: Session, participant_db_id: int) -> int:
    """Photos currently assigned to this participant -- AUTO_MATCH or a
    human-CONFIRMED review, which are the two decisions that actually
    result in a copy landing in their output folder (see
    workers/batch_processor.py and services/review_service.py)."""
    return (
        session.query(MatchRecord)
        .filter(
            MatchRecord.participant_db_id == participant_db_id,
            MatchRecord.decision.in_([MatchDecisionEnum.AUTO_MATCH, MatchDecisionEnum.CONFIRMED]),
        )
        .count()
    )


def update_participant_metadata(
    session: Session, participant_db_id: int, actor: str,
    full_name: str | None = None, registration_number: str | None = None, category: str | None = None,
) -> Participant:
    """Updates only the fields explicitly passed (None means "leave
    unchanged", not "clear the field" -- pass an empty string to clear
    registration_number/category instead)."""
    participant = session.get(Participant, participant_db_id)
    if participant is None:
        raise ValueError(f"No participant with db id {participant_db_id}")

    if full_name is not None:
        if not full_name.strip():
            raise ValueError("full_name cannot be blank")
        participant.full_name = full_name.strip()
    if registration_number is not None:
        participant.registration_number = registration_number.strip() or None
    if category is not None:
        participant.category = category.strip() or None

    session.flush()
    audit.info("Participant %s metadata updated by %s", participant.participant_id, actor)
    return participant


def export_participant_photos(output_dir: Path, participant: Participant, dest_zip_path: Path) -> int:
    """Zips every photo in this participant's output folder (matches the
    folder-naming convention in services/photo_sorting.py). Returns the
    number of files zipped -- 0 if the folder doesn't exist or is empty
    (e.g. nothing has been processed for them yet), which the caller
    should treat as "nothing to export," not an error."""
    from app.services.photo_sorting import participant_folder_name

    folder_name = participant_folder_name(participant.participant_id, participant.full_name)
    try:
        participant_dir = safe_output_path(output_dir, folder_name)
    except ValueError:
        return 0
    if not participant_dir.is_dir():
        return 0

    photo_paths = [p for p in participant_dir.iterdir() if p.is_file()]
    if not photo_paths:
        return 0

    dest_zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo_path in photo_paths:
            zf.write(photo_path, arcname=photo_path.name)

    logger.info("Exported %d photo(s) for participant %s to %s",
                len(photo_paths), participant.participant_id, dest_zip_path)
    return len(photo_paths)


def sanitize_export_filename(participant: Participant) -> str:
    """A safe default filename for an export zip -- reuses the same
    sanitization as output folder names so it can't escape the save
    location the operator picks either."""
    return f"{sanitize_filename(participant.participant_id)}_{sanitize_filename(participant.full_name)}.zip"
