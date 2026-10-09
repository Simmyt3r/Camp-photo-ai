"""
Application configuration management.

Settings are loaded from (highest precedence first):
1. Explicit overrides passed at runtime by callers
2. data/settings.json (created with defaults on first run if missing)
3. The hard-coded defaults below

Portable paths that live inside the CampPhoto AI application directory are
stored relative to that directory. This keeps a Windows onedir build usable
after it is extracted or moved to a different folder.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal

logger = logging.getLogger("camp_photo_ai.config")

ProcessingMode = Literal["cpu", "gpu", "auto"]
MatchStrategy = Literal["max", "mean", "centroid", "top_k"]
DuplicatePolicy = Literal["skip", "keep", "rename"]


def _detect_app_root() -> Path:
    """Return the writable application root for source and frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_ROOT = _detect_app_root()
DEFAULT_CONFIG_PATH = APP_ROOT / "data" / "settings.json"

# These paths belong to the portable application itself. They are kept
# relative in settings.json, then expanded against APP_ROOT when loaded.
_PORTABLE_PATH_FIELDS: dict[str, Path] = {
    "input_dir": Path("data") / "input",
    "output_dir": Path("output"),
    "database_path": Path("data") / "camp_photo_ai.db",
    "models_dir": Path("models"),
    "logs_dir": Path("logs"),
}


def _slash_normalise(value: str | Path) -> str:
    return str(value).replace("\\", "/").rstrip("/")


def _is_absolute_like(value: str | Path) -> bool:
    """Recognise native absolute paths and Windows drive paths cross-platform."""
    text = str(value)
    return Path(text).is_absolute() or bool(PureWindowsPath(text).drive)


def _portable_root_for(value: str, relative_path: Path) -> str | None:
    """Return the root if *value* exactly ends with a known portable suffix."""
    if not _is_absolute_like(value):
        return None

    normalised = _slash_normalise(value)
    suffix = "/" + relative_path.as_posix().strip("/")
    if not normalised.casefold().endswith(suffix.casefold()):
        return None

    root = normalised[: -len(suffix)].rstrip("/")
    return root or None


def _repair_legacy_portable_paths(raw: dict) -> bool:
    """Rebase stale absolute defaults left behind by an older installation.

    Older builds stored paths such as
    D:/a/Camp-photo-ai/Camp-photo-ai/dist/CampPhotoAI/output in settings.json.
    If at least three known portable fields point to the same old application
    root, treat them as generated defaults and rebase only those matching
    fields to the current APP_ROOT. A genuinely custom external path is left
    untouched.
    """
    matches: dict[str, tuple[str, Path]] = {}
    roots: Counter[str] = Counter()

    for field_name, relative_path in _PORTABLE_PATH_FIELDS.items():
        value = raw.get(field_name)
        if not isinstance(value, str) or not value:
            continue

        root = _portable_root_for(value, relative_path)
        if root is None:
            continue

        root_key = root.casefold()
        matches[field_name] = (root_key, relative_path)
        roots[root_key] += 1

    if not roots:
        return False

    old_root, count = roots.most_common(1)[0]
    current_root = _slash_normalise(APP_ROOT).casefold()
    if count < 3 or old_root == current_root:
        return False

    repaired = False
    for field_name, (root_key, relative_path) in matches.items():
        if root_key == old_root:
            raw[field_name] = str(APP_ROOT / relative_path)
            repaired = True

    if repaired:
        logger.warning(
            "Rebased stale portable paths from %s to %s",
            old_root,
            APP_ROOT,
        )
    return repaired


def _expand_relative_paths(raw: dict) -> None:
    """Resolve portable relative path values against the current APP_ROOT."""
    for field_name in _PORTABLE_PATH_FIELDS:
        value = raw.get(field_name)
        if not isinstance(value, str) or not value:
            continue
        if not _is_absolute_like(value):
            raw[field_name] = str(APP_ROOT / Path(value))


def _serialise_portable_path(value: str) -> str:
    """Store paths inside APP_ROOT as relative values for portability."""
    if not _is_absolute_like(value):
        return Path(value).as_posix()

    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(APP_ROOT.resolve()).as_posix()
        except (OSError, ValueError):
            pass

    # A Windows absolute path seen on a non-Windows host cannot be resolved by
    # pathlib there. Preserve it rather than accidentally converting it.
    return str(value)


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
    perceptual_hash_threshold: int = 6

    # Images
    max_image_dimension: int = 4096
    supported_extensions: tuple[str, ...] = (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".tiff",
        ".tif",
    )

    # Cache
    cache_enabled: bool = True

    # Logging
    log_level: str = "INFO"

    # Privacy
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
        payload = asdict(self)
        for field_name in _PORTABLE_PATH_FIELDS:
            value = payload.get(field_name)
            if isinstance(value, str) and value:
                payload[field_name] = _serialise_portable_path(value)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, default=list),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Settings":
        if not path.exists():
            settings = cls()
            settings.save(path)
            logger.info("No settings file found -- created default at %s", path)
            return settings

        raw = json.loads(path.read_text(encoding="utf-8"))
        repaired = _repair_legacy_portable_paths(raw)
        _expand_relative_paths(raw)

        settings = cls(**raw)
        if repaired:
            # Immediately migrate stale absolute defaults to portable relative
            # values so the bad build-machine path cannot return next launch.
            settings.save(path)

        return settings


_settings: Settings | None = None


def get_settings(force_reload: bool = False) -> Settings:
    global _settings
    if _settings is None or force_reload:
        _settings = Settings.load()
    return _settings
