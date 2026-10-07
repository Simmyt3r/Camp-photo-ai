from pathlib import Path

from app.services._face_analysis_loader import (
    BUFFALO_L_REQUIRED_FILES,
    BUFFALO_L_SHA256,
    BUFFALO_L_URL,
    _find_existing_model_dir,
    _locate_extracted_model,
    _model_is_complete,
)


def _write_model_files(model_dir: Path) -> None:
    model_dir.mkdir(parents=True)
    for name in BUFFALO_L_REQUIRED_FILES:
        (model_dir / name).write_bytes(b"x")


def test_buffalo_source_is_current_official_model_zoo_release():
    assert "/releases/download/model-zoo/buffalo_l.zip" in BUFFALO_L_URL
    assert len(BUFFALO_L_SHA256) == 64


def test_model_is_complete_requires_every_nonempty_file(tmp_path):
    model_dir = tmp_path / "models" / "buffalo_l"
    _write_model_files(model_dir)
    assert _model_is_complete(model_dir)

    (model_dir / next(iter(BUFFALO_L_REQUIRED_FILES))).write_bytes(b"")
    assert not _model_is_complete(model_dir)


def test_find_existing_model_uses_insightface_root_layout(tmp_path):
    model_dir = tmp_path / "models" / "buffalo_l"
    _write_model_files(model_dir)

    assert _find_existing_model_dir(str(tmp_path), "buffalo_l") == model_dir.resolve()


def test_locate_extracted_model_accepts_files_at_archive_root(tmp_path):
    _write_model_files(tmp_path)
    assert _locate_extracted_model(tmp_path) == tmp_path


def test_locate_extracted_model_accepts_named_folder(tmp_path):
    model_dir = tmp_path / "buffalo_l"
    _write_model_files(model_dir)
    assert _locate_extracted_model(tmp_path) == model_dir


def test_locate_extracted_model_accepts_extra_wrapper_folder(tmp_path):
    model_dir = tmp_path / "release" / "buffalo_l"
    _write_model_files(model_dir)
    assert _locate_extracted_model(tmp_path) == model_dir
