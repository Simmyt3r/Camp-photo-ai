"""Human review queue operations (section 14).

Every action here is recorded, and the system never silently overrides a
human decision: rejecting a match never assigns a participant, and
confirming/reassigning always requires an explicit target participant
(resolved either from the top-candidate that was already suggested, or
from a participant id the reviewer supplies directly).
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MatchDecisionEnum, MatchRecord, Participant
from app.services.photo_sorting import assign_photo

logger = logging.getLogger("camp_photo_ai.review")
audit = logging.getLogger("camp_photo_ai.audit")


def list_pending_reviews(session: Session, limit: int = 50) -> list[MatchRecord]:
    stmt = (
        select(MatchRecord)
        .where(MatchRecord.decision == MatchDecisionEnum.REVIEW)
        .order_by(MatchRecord.created_at)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def _resolve_best_candidate_db_id(session: Session, record: MatchRecord) -> int | None:
    if record.participant_db_id is not None:
        return record.participant_db_id
    if not record.best_candidate_participant_id:
        return None
    participant = session.query(Participant).filter_by(
        participant_id=record.best_candidate_participant_id
    ).one_or_none()
    return participant.id if participant else None


def confirm_match(
    session: Session, match_id: int, reviewer: str,
    output_dir: Path | None = None, duplicate_policy: str = "skip",
) -> MatchRecord:
    """Confirms the suggested (top-candidate) participant for a REVIEW
    record. Use reassign_match instead if the reviewer wants to pick a
    different participant than the one the system suggested. If
    output_dir is given, also copies the photo into that participant's
    folder -- confirming a review shouldn't leave the photo stranded."""
    record = session.get(MatchRecord, match_id)
    if record is None:
        raise ValueError(f"No match record with id {match_id}")

    target_id = _resolve_best_candidate_db_id(session, record)
    if target_id is None:
        raise ValueError(
            f"Match {match_id} has no candidate participant to confirm -- "
            f"use reassign_match to pick one explicitly."
        )

    record.participant_db_id = target_id
    record.decision = MatchDecisionEnum.CONFIRMED
    record.reviewed_by = reviewer
    session.flush()
    audit.info("Match %s confirmed by %s (participant_db_id=%s)", match_id, reviewer, target_id)

    if output_dir is not None:
        participant = session.get(Participant, target_id)
        assign_photo(output_dir, Path(record.file_path), participant.participant_id,
                     participant.full_name, bucket="match", duplicate_policy=duplicate_policy)
    return record


def reject_match(session: Session, match_id: int, reviewer: str) -> MatchRecord:
    """Marks a REVIEW record as rejected. Never assigns a participant."""
    record = session.get(MatchRecord, match_id)
    if record is None:
        raise ValueError(f"No match record with id {match_id}")
    record.decision = MatchDecisionEnum.REJECTED
    record.reviewed_by = reviewer
    record.participant_db_id = None
    session.flush()
    audit.info("Match %s rejected by %s", match_id, reviewer)
    return record


def reassign_match(
    session: Session, match_id: int, new_participant_db_id: int, reviewer: str,
    output_dir: Path | None = None, duplicate_policy: str = "skip",
) -> MatchRecord:
    """Assigns a REVIEW record to a participant explicitly chosen by the
    reviewer, overriding whatever the system suggested (or lack thereof)."""
    record = session.get(MatchRecord, match_id)
    if record is None:
        raise ValueError(f"No match record with id {match_id}")
    participant = session.get(Participant, new_participant_db_id)
    if participant is None:
        raise ValueError(f"No participant with db id {new_participant_db_id}")

    record.participant_db_id = new_participant_db_id
    record.decision = MatchDecisionEnum.CONFIRMED
    record.reviewed_by = reviewer
    session.flush()
    audit.info("Match %s reassigned to participant %s by %s",
                match_id, participant.participant_id, reviewer)

    if output_dir is not None:
        assign_photo(output_dir, Path(record.file_path), participant.participant_id,
                     participant.full_name, bucket="match", duplicate_policy=duplicate_policy)
    return record


def delete_participant(session: Session, participant_db_id: int, actor: str) -> None:
    """Deletes a participant and (via ON DELETE CASCADE) every reference
    embedding and match record that points to them -- no biometric trace
    is left behind (see docs/PRIVACY.md)."""
    participant = session.get(Participant, participant_db_id)
    if participant is None:
        raise ValueError(f"No participant with db id {participant_db_id}")
    pid = participant.participant_id
    session.delete(participant)
    session.flush()
    audit.info("Participant %s deleted by %s (embeddings and match records cascaded)", pid, actor)
