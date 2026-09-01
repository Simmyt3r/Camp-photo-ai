"""Tests for the database layer: participant CRUD and cascade deletion of
embeddings/match records (docs/PRIVACY.md, section 25)."""
import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base, MatchDecisionEnum, MatchRecord, Participant, ReferenceEmbedding,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    s = SessionLocal()
    yield s
    s.close()


def _make_participant(session, participant_id="P001", name="John Doe") -> Participant:
    p = Participant(participant_id=participant_id, full_name=name, consent_given=True)
    session.add(p)
    session.flush()
    vec = np.random.default_rng(0).normal(size=512).astype(np.float32)
    session.add(ReferenceEmbedding(
        participant_db_id=p.id, vector=vec.tobytes(), dimensions=512,
        model_name="buffalo_l", model_version="1.0", source_image_hash="deadbeef",
    ))
    session.commit()
    return p


def test_create_and_fetch_participant(session):
    _make_participant(session)
    fetched = session.query(Participant).filter_by(participant_id="P001").one()
    assert fetched.full_name == "John Doe"
    assert len(fetched.embeddings) == 1


def test_duplicate_participant_id_is_rejected_at_schema_level(session):
    _make_participant(session)
    dup = Participant(participant_id="P001", full_name="Someone Else")
    session.add(dup)
    with pytest.raises(Exception):
        session.commit()
    session.rollback()


def test_deleting_participant_cascades_embeddings(session):
    p = _make_participant(session)
    pid = p.id
    assert session.query(ReferenceEmbedding).filter_by(participant_db_id=pid).count() == 1

    session.delete(p)
    session.commit()

    assert session.query(Participant).filter_by(id=pid).one_or_none() is None
    assert session.query(ReferenceEmbedding).filter_by(participant_db_id=pid).count() == 0


def test_deleting_participant_cascades_match_records(session):
    p = _make_participant(session)
    session.add(MatchRecord(
        file_path="/photos/IMG_001.jpg", face_index=0, participant_db_id=p.id,
        best_candidate_participant_id=p.participant_id,
        best_score=0.9, score_margin=0.3, decision=MatchDecisionEnum.AUTO_MATCH,
        reason="test",
    ))
    session.commit()

    session.delete(p)
    session.commit()

    assert session.query(MatchRecord).filter_by(participant_db_id=p.id).count() == 0


def test_auto_migration_adds_new_nullable_columns(tmp_path):
    """Simulates a data/camp_photo_ai.db created before this phase added
    MatchRecord.bbox_* and ReferenceEmbedding.thumbnail, then confirms
    init_engine() adds the missing columns instead of the app just
    breaking with 'no such column' on first query."""
    import sqlite3

    import app.database.db as db_module
    from sqlalchemy import inspect

    db_path = tmp_path / "old_style.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE match_records (id INTEGER PRIMARY KEY, file_path TEXT, "
        "face_index INTEGER, best_score FLOAT, score_margin FLOAT, "
        "decision VARCHAR, reason TEXT, created_at DATETIME)"
    )
    conn.execute(
        "CREATE TABLE reference_embeddings (id INTEGER PRIMARY KEY, "
        "participant_db_id INTEGER, vector BLOB, dimensions INTEGER, "
        "model_name VARCHAR(128), model_version VARCHAR(32), "
        "source_image_hash VARCHAR(64), created_at DATETIME)"
    )
    conn.commit()
    conn.close()

    # Save/restore the module-level engine singleton so this test can't
    # leak state into any other test that touches app.database.db.
    saved_engine, saved_session = db_module._engine, db_module._SessionLocal
    try:
        engine = db_module.init_engine(str(db_path))
        match_cols = {c["name"] for c in inspect(engine).get_columns("match_records")}
        ref_cols = {c["name"] for c in inspect(engine).get_columns("reference_embeddings")}
        assert {"bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"}.issubset(match_cols)
        assert "thumbnail" in ref_cols
    finally:
        db_module._engine, db_module._SessionLocal = saved_engine, saved_session
