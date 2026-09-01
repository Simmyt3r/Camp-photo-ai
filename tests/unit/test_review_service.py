"""Unit tests for the human-review queue operations (section 14): confirm,
reject, reassign, and cascade-safe participant deletion."""
import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base, MatchDecisionEnum, MatchRecord, Participant, ReferenceEmbedding,
)
from app.services.review_service import (
    confirm_match, delete_participant, list_pending_reviews, reassign_match, reject_match,
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


def _make_participant(session, participant_id, name) -> Participant:
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


def _make_review_record(session, best_candidate_id, photo="/photos/a.jpg") -> MatchRecord:
    record = MatchRecord(
        file_path=photo, face_index=0, participant_db_id=None,
        best_candidate_participant_id=best_candidate_id,
        best_score=0.55, second_best_score=0.50, second_best_participant_id=None,
        score_margin=0.05, decision=MatchDecisionEnum.REVIEW, reason="test review case",
    )
    session.add(record)
    session.commit()
    return record


class TestListPendingReviews:
    def test_only_returns_review_decisions(self, session):
        p = _make_participant(session, "P001", "John")
        _make_review_record(session, "P001")
        session.add(MatchRecord(
            file_path="/photos/b.jpg", face_index=0, participant_db_id=p.id,
            best_candidate_participant_id="P001", best_score=0.9, score_margin=0.3,
            decision=MatchDecisionEnum.AUTO_MATCH, reason="auto",
        ))
        session.commit()

        pending = list_pending_reviews(session)
        assert len(pending) == 1
        assert pending[0].decision == MatchDecisionEnum.REVIEW


class TestConfirmMatch:
    def test_confirm_resolves_best_candidate_when_no_participant_db_id(self, session):
        _make_participant(session, "P001", "John Doe")
        record = _make_review_record(session, "P001")

        result = confirm_match(session, record.id, reviewer="tester")

        assert result.decision == MatchDecisionEnum.CONFIRMED
        assert result.reviewed_by == "tester"
        participant = session.query(Participant).filter_by(participant_id="P001").one()
        assert result.participant_db_id == participant.id

    def test_confirm_without_any_candidate_raises(self, session):
        record = _make_review_record(session, best_candidate_id=None)
        with pytest.raises(ValueError):
            confirm_match(session, record.id, reviewer="tester")

    def test_confirm_unknown_match_id_raises(self, session):
        with pytest.raises(ValueError):
            confirm_match(session, 9999, reviewer="tester")


class TestRejectMatch:
    def test_reject_marks_rejected_and_never_assigns_participant(self, session):
        _make_participant(session, "P001", "John Doe")
        record = _make_review_record(session, "P001")

        result = reject_match(session, record.id, reviewer="tester")
        assert result.decision == MatchDecisionEnum.REJECTED
        assert result.reviewed_by == "tester"
        assert result.participant_db_id is None


class TestReassignMatch:
    def test_reassign_to_different_participant(self, session):
        _make_participant(session, "P001", "John Doe")
        other = _make_participant(session, "P002", "Jane Smith")
        record = _make_review_record(session, "P001")

        result = reassign_match(session, record.id, other.id, reviewer="tester")
        assert result.participant_db_id == other.id
        assert result.decision == MatchDecisionEnum.CONFIRMED

    def test_reassign_unknown_participant_raises(self, session):
        _make_participant(session, "P001", "John Doe")
        record = _make_review_record(session, "P001")
        with pytest.raises(ValueError):
            reassign_match(session, record.id, 9999, reviewer="tester")


class TestDeleteParticipant:
    def test_delete_cascades(self, session):
        p = _make_participant(session, "P001", "John Doe")
        pid = p.id
        delete_participant(session, pid, actor="tester")
        assert session.query(Participant).filter_by(id=pid).one_or_none() is None

    def test_delete_unknown_participant_raises(self, session):
        with pytest.raises(ValueError):
            delete_participant(session, 9999, actor="tester")
