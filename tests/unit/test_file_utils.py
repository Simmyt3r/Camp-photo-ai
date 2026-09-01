"""Unit tests for filename sanitization, path-traversal protection, and
safe destination resolution (sections 25, 28)."""
import pytest

from app.utilities.file_utils import (
    ensure_within_root, safe_output_path, sanitize_filename, unique_destination,
)


class TestSanitizeFilename:
    def test_strips_path_separators(self):
        assert "/" not in sanitize_filename("John/../../etc/passwd")
        assert "\\" not in sanitize_filename("John\\..\\..\\Windows")

    def test_strips_traversal_sequences(self):
        result = sanitize_filename("../../../etc/passwd")
        assert ".." not in result

    def test_normal_name_survives_mostly_intact(self):
        assert sanitize_filename("John Doe") == "John Doe"

    def test_empty_name_falls_back(self):
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("....") == "unnamed"

    def test_truncates_long_names(self):
        result = sanitize_filename("A" * 500, max_length=150)
        assert len(result) <= 150


class TestSafeOutputPath:
    def test_normal_join_stays_inside_root(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        result = safe_output_path(root, "P001_John Doe")
        assert root in result.parents

    def test_traversal_sequence_is_neutralized_not_escaped(self, tmp_path):
        # sanitize_filename() already strips ".." before safe_output_path
        # does its own check, so the result should simply be a harmless
        # path inside root rather than raising -- there's nothing
        # dangerous left to reject by the time it gets here. The boundary
        # check itself (what happens if something dangerous *did* get
        # through) is tested directly below in TestEnsureWithinRoot.
        root = tmp_path / "output"
        root.mkdir()
        result = safe_output_path(root, "../../etc")
        assert root in result.parents or result == root


class TestEnsureWithinRoot:
    def test_path_outside_root_is_rejected(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        outside = tmp_path / "outside" / "secret.txt"
        with pytest.raises(ValueError):
            ensure_within_root(root, outside)

    def test_path_inside_root_is_accepted(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        inside = root / "sub" / "file.jpg"
        result = ensure_within_root(root, inside)
        assert result == inside.resolve()

    def test_root_itself_is_accepted(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        assert ensure_within_root(root, root) == root.resolve()


class TestUniqueDestination:
    def test_returns_same_path_if_free(self, tmp_path):
        target = tmp_path / "photo.jpg"
        assert unique_destination(target) == target

    def test_appends_counter_if_taken(self, tmp_path):
        target = tmp_path / "photo.jpg"
        target.write_bytes(b"x")
        result = unique_destination(target)
        assert result == tmp_path / "photo_1.jpg"

    def test_increments_past_multiple_existing(self, tmp_path):
        (tmp_path / "photo.jpg").write_bytes(b"x")
        (tmp_path / "photo_1.jpg").write_bytes(b"x")
        result = unique_destination(tmp_path / "photo.jpg")
        assert result == tmp_path / "photo_2.jpg"
