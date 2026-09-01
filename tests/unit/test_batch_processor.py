"""Unit tests for batch_processor internals that don't require real face
detection/embedding -- currently just _build_participant_index()'s
participant_filter, which powers the GUI's "Reprocess Participant"
action (app/ui/participants_page.py)."""
import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config.settings import Settings
from app.database.models import Base, Participant, ReferenceEmbedding
from app.workers.batch_processor import _build_participant_index


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


def _make_participant_with_embedding(session, participant_id, name, seed=0) -> Participant:
    p = Participant(participant_id=participant_id, full_name=name, consent_given=True)
    session.add(p)
    session.flush()
    vec = np.random.default_rng(seed).normal(size=512).astype(np.float32)
    vec /= np.linalg.norm(vec)
    session.add(ReferenceEmbedding(
        participant_db_id=p.id, vector=vec.tobytes(), dimensions=512,
        model_name="buffalo_l", model_version="1.0", source_image_hash="test",
    ))
    session.commit()
    return p


class TestParticipantFilter:
    def test_no_filter_includes_everyone(self, session):
        _make_participant_with_embedding(session, "P001", "Jane", seed=1)
        _make_participant_with_embedding(session, "P002", "John", seed=2)
        index, by_id = _build_participant_index(session, Settings(), participant_filter=None)
        assert len(index) == 2
        assert set(by_id.keys()) == {"P001", "P002"}

    def test_filter_restricts_to_named_participants_only(self, session):
        _make_participant_with_embedding(session, "P001", "Jane", seed=1)
        _make_participant_with_embedding(session, "P002", "John", seed=2)
        _make_participant_with_embedding(session, "P003", "Alex", seed=3)

        index, by_id = _build_participant_index(session, Settings(), participant_filter={"P002"})

        assert len(index) == 1
        assert set(by_id.keys()) == {"P002"}

    def test_filter_with_unknown_id_yields_empty_index(self, session):
        _make_participant_with_embedding(session, "P001", "Jane", seed=1)
        index, by_id = _build_participant_index(session, Settings(), participant_filter={"P999"})
        assert len(index) == 0
        assert by_id == {}

    def test_filter_does_not_affect_which_participant_appears_in_results(self, session):
        """Filtering to P002 must not accidentally include or rename
        P001's data -- a real risk if the filter were applied to the
        wrong query stage."""
        _make_participant_with_embedding(session, "P001", "Jane", seed=1)
        p2 = _make_participant_with_embedding(session, "P002", "John", seed=2)
        index, by_id = _build_participant_index(session, Settings(), participant_filter={"P002"})
        assert by_id["P002"].id == p2.id
        assert by_id["P002"].full_name == "John"
