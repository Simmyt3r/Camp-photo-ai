"""
Batch processing pipeline orchestrator (section 10).

Ties together file discovery, caching, duplicate detection, face
detection+embedding, matching, decisioning, and output copying into one
resumable pipeline. This module has no GUI/CLI-specific code -- app/cli.py
and the PySide6 GUI's ProcessingWorker (app/ui/workers.py) both call
run_batch() and consume the same progress callback.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session, selectinload

from app.config.settings import Settings
from app.database.models import (
    MatchDecisionEnum, MatchRecord, Participant, ProcessingCache, ProcessingRun,
)
from app.services.duplicate_detection import DuplicateIndex
from app.services.face_embedding import EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_VERSION, FaceEmbeddingService
from app.services.face_matching import MatchDecision, ParticipantIndex, evaluate_match
from app.services.image_processing import safe_load_image
from app.services.photo_sorting import assign_photo
from app.utilities.file_utils import file_sha256

logger = logging.getLogger("camp_photo_ai.batch")


@dataclass
class BatchStats:
    """Reflects only the CURRENT run's work: cache-hit photos count
    toward `processed` (for progress-bar purposes) but not toward
    auto_matched/review/unmatched, since those were already tallied by
    the run that originally processed them. For cumulative/historical
    reporting across runs, query MatchRecord/ProcessingCache directly
    (see services/reporting.py + cli.py's `report` command) rather than
    relying on a single run's in-memory BatchStats.
    """
    total_photos: int = 0
    processed: int = 0
    faces_detected: int = 0
    auto_matched: int = 0
    review: int = 0
    unmatched: int = 0
    errors: int = 0
    duplicates_skipped: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def images_per_second(self) -> float:
        return self.processed / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0

    @property
    def estimated_remaining_seconds(self) -> float:
        if self.processed == 0:
            return 0.0
        rate = self.processed / self.elapsed_seconds
        remaining = self.total_photos - self.processed
        return remaining / rate if rate > 0 else 0.0


ProgressCallback = Callable[[BatchStats, str], None]


def _build_participant_index(
    session: Session, settings: Settings, participant_filter: set[str] | None = None,
) -> tuple[ParticipantIndex, dict[str, Participant]]:
    """participant_filter, if given, restricts the index to only those
    participant_ids -- used by the GUI's "Reprocess Participant" action
    (app/ui/participants_page.py) to re-scan a folder for one specific
    person without re-matching against everyone else registered. None
    (the default) preserves the original all-participants behavior."""
    import numpy as np

    index = ParticipantIndex(strategy=settings.match_strategy, top_k=settings.top_k)
    participants_by_id: dict[str, Participant] = {}

    # selectinload fetches every participant's embeddings in ONE extra
    # query (a single "WHERE participant_db_id IN (...)"), instead of
    # the default lazy-loading behavior, which would issue a separate
    # query per participant the first time `.embeddings` is accessed --
    # an N+1 pattern that benchmarking caught costing real time at scale
    # (see docs/PERFORMANCE.md). This runs at the start of every batch,
    # so it matters even before a single photo is processed.
    query = session.query(Participant).options(selectinload(Participant.embeddings))
    if participant_filter is not None:
        query = query.filter(Participant.participant_id.in_(participant_filter))
    for participant in query.all():
        if not participant.embeddings:
            continue
        vectors = np.stack([
            np.frombuffer(e.vector, dtype=np.float32) for e in participant.embeddings
        ])
        index.add_participant(participant.participant_id, vectors)
        participants_by_id[participant.participant_id] = participant

    return index, participants_by_id


def discover_photos(input_dir: Path, extensions: tuple[str, ...]) -> list[Path]:
    return sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    )


def run_batch(
    session: Session,
    settings: Settings,
    input_dir: Path,
    output_dir: Path,
    embedding_service: FaceEmbeddingService,
    progress_callback: Optional[ProgressCallback] = None,
    resume: bool = True,
    participant_filter: set[str] | None = None,
) -> BatchStats:
    """participant_filter restricts matching to only those
    participant_ids -- see _build_participant_index(). Faces that don't
    match anyone in the filtered set still correctly land in Review/
    Unmatched exactly as they would in a full run; this only narrows WHO
    can be auto-matched/suggested, not the pipeline itself."""
    output_dir.mkdir(parents=True, exist_ok=True)
    participant_index, participants_by_id = _build_participant_index(session, settings, participant_filter)
    duplicate_index = DuplicateIndex(perceptual_threshold=settings.perceptual_hash_threshold)

    photos = discover_photos(input_dir, settings.supported_extensions)
    stats = BatchStats(total_photos=len(photos))

    run_record = ProcessingRun(
        input_dir=str(input_dir), output_dir=str(output_dir),
        auto_match_threshold=settings.auto_match_threshold,
        review_threshold=settings.review_threshold,
        model_version=f"{EMBEDDING_MODEL_NAME}-{EMBEDDING_MODEL_VERSION}",
    )
    session.add(run_record)
    session.flush()

    if len(participant_index) == 0:
        logger.warning("No registered participants with embeddings -- every photo will be UNMATCHED.")

    for photo_path in photos:
        try:
            _process_one_photo(
                session, settings, photo_path, output_dir,
                embedding_service, participant_index, participants_by_id,
                duplicate_index, stats, resume,
            )
        except Exception as exc:
            # Section 30: one bad photo must never kill the batch.
            stats.errors += 1
            logger.error("Unexpected error processing %s: %s", photo_path.name, exc, exc_info=True)
            assign_photo(output_dir, photo_path, None, None, bucket="error",
                         duplicate_policy=settings.duplicate_policy)
        finally:
            stats.processed += 1
            if progress_callback:
                progress_callback(stats, photo_path.name)

    run_record.finished_at = dt.datetime.now(dt.timezone.utc)
    run_record.total_photos = stats.total_photos
    run_record.total_faces = stats.faces_detected
    run_record.auto_matched = stats.auto_matched
    run_record.review_count = stats.review
    run_record.unmatched_count = stats.unmatched
    run_record.error_count = stats.errors

    session.commit()
    logger.info(
        "Batch complete: %d photos, %d faces, %d auto-matched, %d review, %d unmatched, %d errors in %.1fs",
        stats.total_photos, stats.faces_detected, stats.auto_matched,
        stats.review, stats.unmatched, stats.errors, stats.elapsed_seconds,
    )
    return stats


def _process_one_photo(
    session: Session,
    settings: Settings,
    photo_path: Path,
    output_dir: Path,
    embedding_service: FaceEmbeddingService,
    participant_index: ParticipantIndex,
    participants_by_id: dict[str, Participant],
    duplicate_index: DuplicateIndex,
    stats: BatchStats,
    resume: bool,
) -> None:
    file_hash = file_sha256(photo_path)

    if resume and settings.cache_enabled:
        cached = session.query(ProcessingCache).filter_by(file_hash=file_hash).one_or_none()
        if cached and cached.status == "done":
            logger.debug("Skipping already-processed %s (cache hit)", photo_path.name)
            return

    dup = duplicate_index.check(photo_path)
    if dup.is_exact_duplicate and settings.duplicate_policy == "skip":
        stats.duplicates_skipped += 1
        logger.info("Skipping duplicate of %s: %s", dup.duplicate_of, photo_path.name)
        return

    load_result = safe_load_image(photo_path, max_dimension=settings.max_image_dimension)
    if not load_result.success:
        stats.errors += 1
        logger.warning(load_result.error)
        assign_photo(output_dir, photo_path, None, None, bucket="error",
                     duplicate_policy=settings.duplicate_policy)
        _upsert_cache(session, photo_path, file_hash, "error", 0, error=load_result.error)
        return

    face_results = embedding_service.embed_image(load_result.image)
    stats.faces_detected += len(face_results)

    if not face_results:
        assign_photo(output_dir, photo_path, None, None, bucket="unmatched",
                     duplicate_policy=settings.duplicate_policy)
        stats.unmatched += 1
        _upsert_cache(session, photo_path, file_hash, "done", 0)
        return

    photo_copied_anywhere = False

    for face_idx, (embedding, _det_score, bbox) in enumerate(face_results):
        scored = participant_index.score_all(embedding)
        result = evaluate_match(
            scored,
            auto_match_threshold=settings.auto_match_threshold,
            review_threshold=settings.review_threshold,
            minimum_score_margin=settings.minimum_score_margin,
        )

        matched_participant = None
        if result.decision == MatchDecision.AUTO_MATCH and result.best:
            matched_participant = participants_by_id.get(result.best.participant_id)

        record = MatchRecord(
            file_path=str(photo_path),
            face_index=face_idx,
            participant_db_id=matched_participant.id if matched_participant else None,
            best_candidate_participant_id=result.best.participant_id if result.best else None,
            best_score=result.best.score if result.best else 0.0,
            second_best_score=result.second_best.score if result.second_best else None,
            second_best_participant_id=result.second_best.participant_id if result.second_best else None,
            score_margin=result.score_margin,
            decision=MatchDecisionEnum(result.decision.value),
            reason=result.reason,
            bbox_x1=bbox[0], bbox_y1=bbox[1], bbox_x2=bbox[2], bbox_y2=bbox[3],
        )
        session.add(record)

        if result.decision == MatchDecision.AUTO_MATCH and matched_participant:
            assign_photo(output_dir, photo_path, matched_participant.participant_id,
                         matched_participant.full_name, bucket="match",
                         duplicate_policy=settings.duplicate_policy)
            stats.auto_matched += 1
            photo_copied_anywhere = True
        elif result.decision == MatchDecision.REVIEW:
            assign_photo(output_dir, photo_path, None, None, bucket="review",
                         duplicate_policy=settings.duplicate_policy)
            stats.review += 1
            photo_copied_anywhere = True
        else:
            stats.unmatched += 1

    if not photo_copied_anywhere:
        # Every face in this photo was UNMATCHED (or there were no
        # registered participants at all) -- still park a copy in
        # Unmatched/ so the photo isn't lost.
        assign_photo(output_dir, photo_path, None, None, bucket="unmatched",
                     duplicate_policy=settings.duplicate_policy)

    _upsert_cache(session, photo_path, file_hash, "done", len(face_results))


def _upsert_cache(session: Session, photo_path: Path, file_hash: str, status: str,
                   faces_detected: int, error: str | None = None) -> None:
    cached = session.query(ProcessingCache).filter_by(file_hash=file_hash).one_or_none()
    if cached is None:
        cached = ProcessingCache(file_path=str(photo_path), file_hash=file_hash)
        session.add(cached)
    cached.status = status
    cached.faces_detected = faces_detected
    cached.error_message = error
    cached.processed_at = dt.datetime.now(dt.timezone.utc)
    cached.modified_at = dt.datetime.fromtimestamp(photo_path.stat().st_mtime, dt.timezone.utc)
    session.flush()
