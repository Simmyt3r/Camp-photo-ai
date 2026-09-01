"""Processing report generation and CSV/JSON export (section 20), plus
live dashboard stats for the GUI (section 17)."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ProcessingReport:
    started_at: str
    finished_at: str
    input_dir: str
    output_dir: str
    total_photos: int
    total_faces: int
    auto_matched: int
    review_count: int
    unmatched_count: int
    error_count: int
    average_speed_images_per_sec: float
    total_processing_seconds: float
    model_version: str
    auto_match_threshold: float
    review_threshold: float

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2))

    def to_csv(self, path: Path) -> None:
        data = asdict(self)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(data.keys())
            writer.writerow(data.values())


def build_report(run) -> "ProcessingReport":
    """Builds a ProcessingReport from a ProcessingRun database row.
    Shared by app/cli.py's `report` command and the GUI's Reports page
    (app/ui/reports_page.py) so there's exactly one place that knows how
    to turn a stored run into a report, not two copies that could drift."""
    duration = (run.finished_at - run.started_at).total_seconds() if run.finished_at else 0.0
    return ProcessingReport(
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else "",
        input_dir=run.input_dir,
        output_dir=run.output_dir,
        total_photos=run.total_photos,
        total_faces=run.total_faces,
        auto_matched=run.auto_matched,
        review_count=run.review_count,
        unmatched_count=run.unmatched_count,
        error_count=run.error_count,
        average_speed_images_per_sec=(run.total_photos / duration) if duration > 0 else 0.0,
        total_processing_seconds=duration,
        model_version=run.model_version,
        auto_match_threshold=run.auto_match_threshold,
        review_threshold=run.review_threshold,
    )


def compute_dashboard_stats(session) -> dict[str, int]:
    """Live counts for the GUI dashboard (section 17). Distinct from
    ProcessingReport (a snapshot of one past run): this aggregates
    current state across everything ever processed, and reflects the
    *current* decision on each face (so a REVIEW item that gets
    confirmed moves out of "needs review" here, unlike a frozen report)."""
    from sqlalchemy import func

    from app.database.models import MatchDecisionEnum, MatchRecord, Participant, ProcessingCache

    participants = session.query(Participant).count()
    photos_processed = (
        session.query(ProcessingCache)
        .filter(ProcessingCache.status.in_(["done", "error"]))
        .count()
    )
    faces_detected = session.query(func.coalesce(func.sum(ProcessingCache.faces_detected), 0)).scalar()

    decision_counts = dict(
        session.query(MatchRecord.decision, func.count(MatchRecord.id)).group_by(MatchRecord.decision).all()
    )
    return {
        "participants": participants,
        "photos_processed": photos_processed,
        "faces_detected": int(faces_detected or 0),
        "auto_matched": decision_counts.get(MatchDecisionEnum.AUTO_MATCH, 0),
        "needs_review": decision_counts.get(MatchDecisionEnum.REVIEW, 0),
        "unmatched": decision_counts.get(MatchDecisionEnum.UNMATCHED, 0),
    }
