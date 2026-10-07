"""
Application configuration management.

Settings are loaded from (highest precedence first):
1. Explicit overrides passed at runtime by callers
2. data/settings.json (created with defaults on first run if missing)
3. The hard-coded defaults below

No operational threshold is hard-coded into business logic elsewhere in
the app -- everything reads from this module so thresholds can be
recalibrated (see services/face_matching.py and the future `evaluate`
CLI command) without touching code. Per spec section 22: "Do not claim
that any threshold is universally correct."
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger("camp_photo_ai.config")

ProcessingMode = Literal["cpu", "gpu", "auto"]
MatchStrategy = Literal["max", "mean", "centroid", "top_k"]
DuplicatePolicy = Literal["skip", "keep", "rename"]


def _detect_app_root() -> Path:
    """Path(__file__).resolve().parents[2] finds the real project root
    when running from source, but resolves to a meaningless location
    inside PyInstaller's bundle when frozen (found by actually building
    and running a frozen executable -- see docs/INSTALLATION.md). Under
    PyInstaller, sys.frozen is True and sys.executable is the actual
    .exe path; its parent directory (the --onedir distribution folder)
    is where a portable app's data belongs. This means the distributable
    folder needs to be somewhere the user can write to (Desktop,
    Documents, a dedicated folder) -- NOT Program Files, which normal
    Windows accounts can't write to without admin elevation."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_ROOT = _detect_app_root()
DEFAULT_CONFIG_PATH = APP_ROOT / "data" / "settings.json"


@dataclass
class Settings:
    # Paths
    input_dir: str = str(APP_ROOT / "data" / "input")
    output_dir: str = str(APP_ROOT / "output")
    database_path: str = str(APP_ROOT / "data" / "camp_photo_ai.db")
    models_dir: str = str(APP_ROOT / "models")
    logs_dir: str = str(APP_ROOT / "logs")

    # Matching thresholds -- NOT scientifically valid until calibrated
    # against a real validation dataset for the deployed model (section 22).
    auto_match_threshold: float = 0.62
    review_threshold: float = 0.45
    minimum_score_margin: float = 0.08

    # Multi-reference matching strategy (section 6)
    match_strategy: MatchStrategy = "top_k"
    top_k: int = 3

    # Hardware
    processing_mode: ProcessingMode = "auto"
    worker_count: int = 4

    # Duplicates (section 15)
    duplicate_policy: DuplicatePolicy = "skip"
    perceptual_hash_threshold: int = 6  # max hamming distance considered "near duplicate"

    # Images
    max_image_dimension: int = 4096
    supported_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif")

    # Cache
    cache_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    # Privacy -- see docs/PRIVACY.md. No code path currently checks this
    # flag because no cloud code path exists yet in this build; it's
    # reserved for a future, explicit opt-in integration only.
    allow_external_api: bool = False

    # Model metadata (section 32)
    embedding_model_name: str = "buffalo_l"
    embedding_model_version: str = "1.0"

    # Product onboarding / responsible-use agreement
    user_agreement_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.supported_extensions, tuple):
            self.supported_extensions = tuple(self.supported_extensions)

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=list))

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Settings":
        if not path.exists():
            settings = cls()
            settings.save(path)
            logger.info("No settings file found -- created default at %s", path)
            return settings
        raw = json.loads(path.read_text())
        return cls(**raw)


_settings: Settings | None = None


def get_settings(force_reload: bool = False) -> Settings:
    global _settings
    if _settings is None or force_reload:
        _settings = Settings.load()
    return _settings
