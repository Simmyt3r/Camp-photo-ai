import json
from dataclasses import asdict
from pathlib import Path

from app.config import settings as settings_module


def _settings_for_root(root: Path) -> settings_module.Settings:
    return settings_module.Settings(
        input_dir=str(root / "data" / "input"),
        output_dir=str(root / "output"),
        database_path=str(root / "data" / "camp_photo_ai.db"),
        models_dir=str(root / "models"),
        logs_dir=str(root / "logs"),
    )


def test_save_uses_relative_paths_for_portable_app_data(tmp_path, monkeypatch):
    app_root = tmp_path / "CampPhotoAI"
    app_root.mkdir()
    monkeypatch.setattr(settings_module, "APP_ROOT", app_root)

    config_path = app_root / "data" / "settings.json"
    settings = _settings_for_root(app_root)
    settings.save(config_path)

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["input_dir"] == "data/input"
    assert raw["output_dir"] == "output"
    assert raw["database_path"] == "data/camp_photo_ai.db"
    assert raw["models_dir"] == "models"
    assert raw["logs_dir"] == "logs"

    loaded = settings_module.Settings.load(config_path)
    assert Path(loaded.input_dir) == app_root / "data" / "input"
    assert Path(loaded.output_dir) == app_root / "output"
    assert Path(loaded.database_path) == app_root / "data" / "camp_photo_ai.db"
    assert Path(loaded.models_dir) == app_root / "models"
    assert Path(loaded.logs_dir) == app_root / "logs"


def test_load_repairs_stale_github_runner_paths(tmp_path, monkeypatch):
    app_root = tmp_path / "ExtractedCampPhotoAI"
    app_root.mkdir()
    monkeypatch.setattr(settings_module, "APP_ROOT", app_root)

    stale_root = r"D:\a\Camp-photo-ai\Camp-photo-ai\dist\CampPhotoAI"
    payload = asdict(settings_module.Settings())
    payload.update(
        {
            "input_dir": stale_root + r"\data\input",
            "output_dir": stale_root + r"\output",
            "database_path": stale_root + r"\data\camp_photo_ai.db",
            "models_dir": stale_root + r"\models",
            "logs_dir": stale_root + r"\logs",
        }
    )

    config_path = app_root / "data" / "settings.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = settings_module.Settings.load(config_path)

    assert Path(loaded.input_dir) == app_root / "data" / "input"
    assert Path(loaded.output_dir) == app_root / "output"
    assert Path(loaded.database_path) == app_root / "data" / "camp_photo_ai.db"
    assert Path(loaded.models_dir) == app_root / "models"
    assert Path(loaded.logs_dir) == app_root / "logs"

    # Loading migrates the legacy settings file immediately so a later move
    # remains portable instead of resurrecting the CI runner's D: drive.
    migrated = json.loads(config_path.read_text(encoding="utf-8"))
    assert migrated["input_dir"] == "data/input"
    assert migrated["output_dir"] == "output"
    assert migrated["database_path"] == "data/camp_photo_ai.db"
    assert migrated["models_dir"] == "models"
    assert migrated["logs_dir"] == "logs"


def test_repair_preserves_a_custom_external_path(tmp_path, monkeypatch):
    app_root = tmp_path / "ExtractedCampPhotoAI"
    app_root.mkdir()
    monkeypatch.setattr(settings_module, "APP_ROOT", app_root)

    stale_root = r"D:\a\Camp-photo-ai\Camp-photo-ai\dist\CampPhotoAI"
    custom_output = r"E:\My Event Exports"
    payload = asdict(settings_module.Settings())
    payload.update(
        {
            "input_dir": stale_root + r"\data\input",
            "output_dir": custom_output,
            "database_path": stale_root + r"\data\camp_photo_ai.db",
            "models_dir": stale_root + r"\models",
            "logs_dir": stale_root + r"\logs",
        }
    )

    config_path = app_root / "data" / "settings.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = settings_module.Settings.load(config_path)

    assert loaded.output_dir == custom_output
    assert Path(loaded.models_dir) == app_root / "models"
