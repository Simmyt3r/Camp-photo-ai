"""
pytest-benchmark micro-benchmarks for database operations (section 23).
Uses a fresh temporary SQLite file per test (pytest's tmp_path fixture)
-- never the user's real data/camp_photo_ai.db.

Run directly for interactive numbers:
    pytest tests/performance/test_database_benchmarks.py --benchmark-only -v
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import selectinload, sessionmaker

from app.database.models import Base, Participant, ProcessingCache, ReferenceEmbedding


def _make_engine(db_path):
    engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _seed_participants(session, n: int, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)
    for i in range(n):
        p = Participant(participant_id=f"P{i:07d}", full_name=f"Test {i}", consent_given=True)
        session.add(p)
        session.flush()
        vec = rng.normal(size=512).astype(np.float32)
        vec /= np.linalg.norm(vec)
        session.add(ReferenceEmbedding(
            participant_db_id=p.id, vector=vec.tobytes(), dimensions=512,
            model_name="buffalo_l", model_version="1.0", source_image_hash="bench",
        ))
    session.commit()


@pytest.mark.parametrize("n_existing", [100, 1_000, 10_000])
def test_insert_one_participant_at_scale(benchmark, tmp_path, n_existing):
    """How long does registering ONE new participant take once the
    database already has n_existing participants in it? Should stay
    roughly flat -- an insert shouldn't get slower just because the
    table is bigger (indexed primary/unique keys keep insert cost
    independent of table size)."""
    db_path = tmp_path / "bench.db"
    engine = _make_engine(db_path)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    _seed_participants(session, n_existing)

    counter = {"i": n_existing}

    def _insert_one():
        i = counter["i"]
        counter["i"] += 1
        p = Participant(participant_id=f"P{i:07d}", full_name=f"Test {i}", consent_given=True)
        session.add(p)
        session.flush()
        vec = np.random.default_rng(i).normal(size=512).astype(np.float32)
        vec /= np.linalg.norm(vec)
        session.add(ReferenceEmbedding(
            participant_db_id=p.id, vector=vec.tobytes(), dimensions=512,
            model_name="buffalo_l", model_version="1.0", source_image_hash="bench",
        ))
        session.commit()

    benchmark(_insert_one)
    session.close()
    engine.dispose()


@pytest.mark.parametrize("n_participants", [100, 1_000, 10_000])
def test_query_all_participants_with_embeddings(benchmark, tmp_path, n_participants):
    """The exact query batch_processor._build_participant_index() runs
    at the start of every real processing run: fetch every participant
    and their embeddings, via selectinload (2 queries total) rather than
    the default lazy-load (1 + n_participants queries -- see the N+1
    comparison test below for how much that costs)."""
    db_path = tmp_path / "bench.db"
    engine = _make_engine(db_path)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    _seed_participants(session, n_participants)

    def _query_all():
        participants = session.query(Participant).options(selectinload(Participant.embeddings)).all()
        for p in participants:
            _ = p.embeddings
        return participants

    result = benchmark(_query_all)

    assert len(result) == n_participants
    session.close()
    engine.dispose()


def test_eager_loading_beats_lazy_loading_at_scale(tmp_path):
    """Documents the actual N+1 finding, as a real (if one-off, not
    pytest-benchmark-parametrized) timing comparison rather than just an
    assertion of correctness: fetching 5,000 participants' embeddings via
    the default lazy relationship issues 1 + 5,000 queries; selectinload
    issues 2. This is what motivated the selectinload fix in
    batch_processor._build_participant_index() -- see docs/PERFORMANCE.md
    for real numbers measured at larger scale."""
    import time

    db_path = tmp_path / "bench.db"
    engine = _make_engine(db_path)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    _seed_participants(session, 5_000)

    t0 = time.perf_counter()
    lazy_participants = session.query(Participant).all()
    for p in lazy_participants:
        _ = p.embeddings  # each access is a separate query the first time
    lazy_seconds = time.perf_counter() - t0

    session.close()
    session = SessionLocal()

    t0 = time.perf_counter()
    eager_participants = session.query(Participant).options(selectinload(Participant.embeddings)).all()
    for p in eager_participants:
        _ = p.embeddings  # already loaded -- no additional query
    eager_seconds = time.perf_counter() - t0

    assert len(lazy_participants) == len(eager_participants) == 5_000
    assert eager_seconds < lazy_seconds  # the whole point of the fix
    session.close()
    engine.dispose()


@pytest.mark.parametrize("n_cached", [1_000, 10_000, 50_000])
def test_processing_cache_lookup_by_hash(benchmark, tmp_path, n_cached):
    """Every photo in a resumed batch does one indexed lookup by
    file_hash against ProcessingCache (section 13). Should stay fast
    even with 50k prior photos cached, since file_hash is indexed."""
    db_path = tmp_path / "bench.db"
    engine = _make_engine(db_path)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()

    now = dt.datetime.now(dt.timezone.utc)
    for i in range(n_cached):
        session.add(ProcessingCache(
            file_path=f"/photos/img_{i:07d}.jpg", file_hash=f"{i:064x}",
            modified_at=now, status="done", faces_detected=1,
        ))
        if i % 2000 == 0:
            session.commit()
    session.commit()

    target_hash = f"{n_cached // 2:064x}"

    def _lookup():
        return session.query(ProcessingCache).filter_by(file_hash=target_hash).one_or_none()

    result = benchmark(_lookup)

    assert result is not None
    session.close()
    engine.dispose()
