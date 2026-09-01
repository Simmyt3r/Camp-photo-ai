"""
Shared application bootstrap: settings, hardware-resolved processing
provider, and a ready-to-use FaceEmbeddingService.

Lives at the app package root (not under app/ui/) deliberately: this has
no PySide6 dependency, and CLI-only usage should never require the GUI
toolkit to be importable. Both app/cli.py and app/main.py (the GUI entry
point) call AppContext.bootstrap() so hardware detection and provider
resolution live in exactly one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.database.db import init_engine
from app.services.face_embedding import FaceEmbeddingService
from app.utilities.hardware import detect_hardware, resolve_processing_mode
from app.utilities.logging_config import configure_logging


@dataclass
class AppContext:
    settings: Settings
    mode: str      # "cpu" | "gpu"
    provider: str  # ONNX Runtime execution provider name
    embedding_service: FaceEmbeddingService

    @classmethod
    def bootstrap(cls) -> "AppContext":
        settings = get_settings()

        # data/ (via init_engine) and logs/ (via configure_logging) both
        # already create themselves -- output_dir and models_dir don't,
        # and nothing had called detect_hardware() on a fresh install
        # before this existed. Found by actually building and running a
        # frozen executable, where NOTHING pre-exists next to the .exe
        # (unlike a source checkout, which ships these as empty
        # directories via .gitkeep) -- see docs/INSTALLATION.md.
        Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.models_dir).mkdir(parents=True, exist_ok=True)

        configure_logging(settings.logs_dir, settings.log_level)
        init_engine(settings.database_path)

        profile = detect_hardware(settings.output_dir)
        mode = resolve_processing_mode(settings.processing_mode, profile)
        provider = "CPUExecutionProvider" if mode == "cpu" else profile.gpu_provider

        embedding_service = FaceEmbeddingService(provider=provider, models_dir=settings.models_dir)
        return cls(settings=settings, mode=mode, provider=provider, embedding_service=embedding_service)
