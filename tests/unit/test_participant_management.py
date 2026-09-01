"""Unit tests for participant search, metadata editing, matched-photo
counting, and export (section 19)."""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, MatchDecisionEnum, MatchRecord, Participant
from app.services.participant_management import (
    count_matched_photos, export_participant_photos, sanitize_export_filename,
    search_participants, update_participant_metadata,
)
from app.services.photo_sorting import participant_folder_name


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


def _make_participant(session, participant_id, name, reg_number=None, category=None) -> Participant:
    p = Participant(participant_id=participant_id, full_name=name,
                     registration_number=reg_number, category=category, consent_given=True)
    session.add(p)
    session.commit()
    return p


class TestSearchParticipants:
    def test_matches_by_name_case_insensitively(self, session):
        _make_participant(session, "P001", "Jane Doe")
        _make_participant(session, "P002", "John Smith")
        results = search_participants(session, "jane")
        assert [p.participant_id for p in results] == ["P001"]

    def test_matches_by_participant_id(self, session):
        _make_participant(session, "P001", "Jane Doe")
        _make_participant(session, "P002", "John Smith")
        results = search_participants(session, "P002")
        assert [p.participant_id for p in results] == ["P002"]

    def test_matches_by_registration_number(self, session):
        _make_participant(session, "P001", "Jane Doe", reg_number="NYSC-2026-001")
        results = search_participants(session, "NYSC-2026")
        assert [p.participant_id for p in results] == ["P001"]

    def test_matches_by_category(self, session):
        _make_participant(session, "P001", "Jane Doe", category="Batch A")
        results = search_participants(session, "Batch A")
        assert [p.participant_id for p in results] == ["P001"]

    def test_blank_query_returns_everyone(self, session):
        _make_participant(session, "P001", "Jane Doe")
        _make_participant(session, "P002", "John Smith")
        results = search_participants(session, "")
        assert len(results) == 2

    def test_no_match_returns_empty(self, session):
        _make_participant(session, "P001", "Jane Doe")
        assert search_participants(session, "zzz_nomatch") == []

    def test_null_fields_on_other_participants_do_not_break_search(self, session):
        _make_participant(session, "P001", "Jane Doe")  # no reg_number/category
        _make_participant(session, "P002", "John Smith", reg_number="X-1")
        results = search_participants(session, "John")
        assert [p.participant_id for p in results] == ["P002"]


class TestCountMatchedPhotos:
    def test_counts_auto_match_and_confirmed_only(self, session):
        p = _make_participant(session, "P001", "Jane Doe")
        session.add(MatchRecord(file_path="/a.jpg", face_index=0, participant_db_id=p.id,
                                 best_score=0.9, score_margin=0.3, decision=MatchDecisionEnum.AUTO_MATCH, reason="x"))
        session.add(MatchRecord(file_path="/b.jpg", face_index=0, participant_db_id=p.id,
                                 best_score=0.9, score_margin=0.3, decision=MatchDecisionEnum.CONFIRMED, reason="x"))
        session.add(MatchRecord(file_path="/c.jpg", face_index=0, participant_db_id=None,
                                 best_score=0.5, score_margin=0.05, decision=MatchDecisionEnum.REVIEW, reason="x"))
        session.commit()
        assert count_matched_photos(session, p.id) == 2

    def test_zero_for_participant_with_no_matches(self, session):
        p = _make_participant(session, "P001", "Jane Doe")
        assert count_matched_photos(session, p.id) == 0


class TestUpdateParticipantMetadata:
    def test_updates_only_provided_fields(self, session):
        p = _make_participant(session, "P001", "Jane Doe", reg_number="R1", category="A")
        updated = update_participant_metadata(session, p.id, actor="tester", category="B")
        assert updated.full_name == "Jane Doe"       # unchanged
        assert updated.registration_number == "R1"   # unchanged
        assert updated.category == "B"                # changed

    def test_rejects_blank_full_name(self, session):
        p = _make_participant(session, "P001", "Jane Doe")
        with pytest.raises(ValueError):
            update_participant_metadata(session, p.id, actor="tester", full_name="   ")

    def test_empty_string_clears_optional_fields(self, session):
        p = _make_participant(session, "P001", "Jane Doe", reg_number="R1", category="A")
        updated = update_participant_metadata(session, p.id, actor="tester", registration_number="", category="")
        assert updated.registration_number is None
        assert updated.category is None

    def test_unknown_participant_raises(self, session):
        with pytest.raises(ValueError):
            update_participant_metadata(session, 9999, actor="tester", full_name="Someone")


class TestExportParticipantPhotos:
    def test_zips_all_files_in_participant_folder(self, session, tmp_path):
        p = _make_participant(session, "P001", "Jane Doe")
        folder = tmp_path / "output" / participant_folder_name(p.participant_id, p.full_name)
        folder.mkdir(parents=True)
        (folder / "a.jpg").write_bytes(b"one")
        (folder / "b.jpg").write_bytes(b"two")

        dest = tmp_path / "export.zip"
        count = export_participant_photos(tmp_path / "output", p, dest)

        assert count == 2
        assert dest.exists()
        import zipfile
        with zipfile.ZipFile(dest) as zf:
            assert sorted(zf.namelist()) == ["a.jpg", "b.jpg"]

    def test_returns_zero_for_participant_with_no_folder(self, session, tmp_path):
        p = _make_participant(session, "P001", "Jane Doe")
        count = export_participant_photos(tmp_path / "output", p, tmp_path / "export.zip")
        assert count == 0
        assert not (tmp_path / "export.zip").exists()

    def test_returns_zero_for_empty_folder(self, session, tmp_path):
        p = _make_participant(session, "P001", "Jane Doe")
        folder = tmp_path / "output" / participant_folder_name(p.participant_id, p.full_name)
        folder.mkdir(parents=True)
        count = export_participant_photos(tmp_path / "output", p, tmp_path / "export.zip")
        assert count == 0


class TestSanitizeExportFilename:
    def test_produces_a_safe_zip_filename(self, session):
        p = _make_participant(session, "P001", "Jane/../Doe")
        name = sanitize_export_filename(p)
        assert name.endswith(".zip")
        assert "/" not in name and ".." not in name
