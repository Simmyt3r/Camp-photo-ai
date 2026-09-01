"""Unit tests for exact and near-duplicate photo detection (section 15)."""
from PIL import Image, ImageDraw

from app.services.duplicate_detection import DuplicateIndex


def _make_image(path, color, size=(64, 64)):
    Image.new("RGB", size, color=color).save(path)


def _make_patterned_image(path, variant: str, size=(64, 64)):
    """Perceptual hashing (phash) is DCT-based: it encodes structure
    (edges/gradients), not raw color. A flat, textureless swatch has no
    structure regardless of its color, so two different solid colors can
    hash identically -- that's not a phash bug, but it does mean solid
    colors are a degenerate, misleading fixture for "these two images are
    genuinely different" tests. Real event photos always have real
    structure (faces, backgrounds, clothing), so this only matters for
    test data, not for the app's actual behavior."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    if variant == "a":
        draw.rectangle([4, 4, 28, 28], fill=(20, 20, 20))
        draw.ellipse([34, 34, 60, 60], fill=(200, 50, 50))
    else:
        draw.rectangle([34, 4, 60, 28], fill=(50, 200, 50))
        draw.ellipse([4, 34, 28, 60], fill=(50, 50, 200))
    img.save(path)


class TestDuplicateIndex:
    def test_first_occurrence_is_not_a_duplicate(self, tmp_path):
        path = tmp_path / "a.jpg"
        _make_image(path, (255, 0, 0))
        index = DuplicateIndex()
        result = index.check(path)
        assert not result.is_exact_duplicate
        assert not result.is_near_duplicate

    def test_byte_identical_copy_is_exact_duplicate(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        _make_image(a, (10, 20, 30))
        b.write_bytes(a.read_bytes())

        index = DuplicateIndex()
        index.check(a)
        result = index.check(b)
        assert result.is_exact_duplicate
        assert result.is_near_duplicate

    def test_visually_similar_image_is_near_duplicate_not_exact(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        _make_image(a, (100, 100, 100))
        _make_image(b, (102, 100, 100))  # tiny difference, same phash bucket

        index = DuplicateIndex(perceptual_threshold=10)
        index.check(a)
        result = index.check(b)
        assert result.is_near_duplicate
        assert not result.is_exact_duplicate

    def test_different_images_are_not_duplicates(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        _make_patterned_image(a, "a")
        _make_patterned_image(b, "b")

        index = DuplicateIndex(perceptual_threshold=6)
        index.check(a)
        result = index.check(b)
        assert not result.is_exact_duplicate
        assert not result.is_near_duplicate
