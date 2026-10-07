from pathlib import Path
import zipfile

from scripts.bundle_buffalo_model import (
    REQUIRED_FILES,
    copy_model,
    locate_model,
    model_is_complete,
    resolve_source,
)


def _write_model(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        (folder / name).write_bytes(b"model-bytes")
    return folder


def test_locate_model_accepts_flat_folder(tmp_path):
    model = _write_model(tmp_path)
    assert locate_model(tmp_path) == model


def test_resolve_source_accepts_zip_with_nested_buffalo_folder(tmp_path):
    source_root = tmp_path / "source"
    model = _write_model(source_root / "buffalo_l")
    archive = tmp_path / "buffalo_l.zip"

    with zipfile.ZipFile(archive, "w") as zf:
        for name in REQUIRED_FILES:
            zf.write(model / name, arcname=f"buffalo_l/{name}")

    extract_root = tmp_path / "temp"
    extract_root.mkdir()
    resolved = resolve_source(archive, extract_root)
    assert resolved is not None
    assert model_is_complete(resolved)


def test_copy_model_places_files_in_frozen_app_layout(tmp_path):
    source = _write_model(tmp_path / "source")
    target = tmp_path / "dist" / "CampPhotoAI"
    target.mkdir(parents=True)

    copy_model(source, target)

    bundled = target / "models" / "buffalo_l"
    assert model_is_complete(bundled)
