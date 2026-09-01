"""
SQLAlchemy ORM models.

Design notes (full detail in docs/PRIVACY.md):
- Biometric vectors (embeddings) are stored as opaque binary blobs, never
  as plaintext floats in logs.
- Participants are referenced internally by `participant_id` wherever
  possible; personal fields (name, registration number) live only on the
  Participant row itself.
- Deleting a Participant cascades to ReferenceEmbedding and MatchRecord
  rows in the same transaction, so no biometric trace is left behind
  (see services/review_service.py::delete_participant). This requires
  SQLite's foreign_keys PRAGMA to be on -- see database/db.py.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    registration_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_given: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    embeddings: Mapped[list["ReferenceEmbedding"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )
    matches: Mapped[list["MatchRecord"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Participant {self.participant_id} ({self.full_name})>"


class ReferenceEmbedding(Base):
    """One reference face embedding for a participant. Multiple rows per
    participant are expected (section 6: ~3-5 recommended). `vector` is
    raw float32 bytes and is never logged -- see
    utilities/logging_config.py, which redacts anything vector-shaped.

    `thumbnail` (added for the Phase 2 review screen): a small JPEG of the
    reference photo, so a human reviewer can see who a candidate
    participant actually is without the app keeping the original
    reference photo file (see docs/PRIVACY.md -- this is a deliberate,
    documented exception to that "we don't retain reference photos"
    stance, scoped to a small, low-resolution display copy)."""
    __tablename__ = "reference_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_db_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    dimensions: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(32))
    source_image_hash: Mapped[str] = mapped_column(String(64))
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    thumbnail: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    participant: Mapped["Participant"] = relationship(back_populates="embeddings")


class ProcessingCache(Base):
    """Per-photo processing record. Makes batches resumable and avoids
    reprocessing unchanged files (sections 11/13)."""
    __tablename__ = "processing_cache"
    __table_args__ = (UniqueConstraint("file_hash", name="uq_processing_cache_file_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_path: Mapped[str] = mapped_column(Text)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    modified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|done|error
    faces_detected: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(32), default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MatchDecisionEnum(str, enum.Enum):
    """Mirrors services.face_matching.MatchDecision's three values
    (auto_match/review/unmatched) plus two states that only exist once a
    human has acted on a REVIEW record. Kept as a separate enum here (not
    imported from face_matching.py) so the core matching module has no
    dependency on the database layer and stays independently testable."""
    AUTO_MATCH = "auto_match"
    REVIEW = "review"
    UNMATCHED = "unmatched"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class MatchRecord(Base):
    """One face-to-participant match decision for one detected face in
    one photograph. A photo with 3 faces produces up to 3 MatchRecords."""
    __tablename__ = "match_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_path: Mapped[str] = mapped_column(Text)
    face_index: Mapped[int] = mapped_column(Integer)  # which face in the photo (0-based)

    # The CONFIRMED/AUTO_MATCHED participant, if any -- set at auto-match
    # time, or later by a human via review_service.confirm_match/reassign_match.
    participant_db_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=True
    )
    # The top-scoring candidate's participant_id, regardless of decision --
    # always populated when there was at least one registered participant
    # to compare against, so the review workflow can act on a REVIEW
    # record even though participant_db_id is still None for it.
    best_candidate_participant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    best_score: Mapped[float] = mapped_column(Float)
    second_best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    second_best_participant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    score_margin: Mapped[float] = mapped_column(Float)
    decision: Mapped[MatchDecisionEnum] = mapped_column(Enum(MatchDecisionEnum))
    reason: Mapped[str] = mapped_column(Text)  # human-readable, always recorded (section 8)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Detected face's bounding box in the original photo (added for the
    # Phase 2 review screen's face-crop display). Nullable so old rows
    # from before this field existed don't break -- the review UI simply
    # shows "no bounding box stored" for those instead of a crop.
    bbox_x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_x2: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y2: Mapped[float | None] = mapped_column(Float, nullable=True)

    participant: Mapped["Participant | None"] = relationship(back_populates="matches")


class ProcessingRun(Base):
    """One execution of the batch pipeline, for reporting (section 20)."""
    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_dir: Mapped[str] = mapped_column(Text)
    output_dir: Mapped[str] = mapped_column(Text)
    total_photos: Mapped[int] = mapped_column(Integer, default=0)
    total_faces: Mapped[int] = mapped_column(Integer, default=0)
    auto_matched: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    model_version: Mapped[str] = mapped_column(String(32), default="")
    auto_match_threshold: Mapped[float] = mapped_column(Float)
    review_threshold: Mapped[float] = mapped_column(Float)
