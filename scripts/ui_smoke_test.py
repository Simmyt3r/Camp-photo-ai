"""Minimal headless GUI smoke test used by the Windows packaging workflow."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.bootstrap import AppContext
from app.config.settings import Settings
from app.database.db import get_engine, init_engine
from app.services.face_embedding import FaceEmbeddingService
from app.ui.agreement_dialog import UserAgreementDialog
from app.ui.branding import app_logo_path
from app.ui.main_window import MainWindow
from app.ui.styles import STYLESHEET


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="camp-photo-ui-") as temp_dir:
        root = Path(temp_dir)
        settings = Settings(
            input_dir=str(root / "input"),
            output_dir=str(root / "output"),
            database_path=str(root / "camp_photo_ai.db"),
            models_dir=str(root / "models"),
            logs_dir=str(root / "logs"),
        )
        Path(settings.input_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.output_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.models_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)
        init_engine(settings.database_path)

        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        app.setStyleSheet(STYLESHEET)

        context = AppContext(
            settings=settings,
            mode="cpu",
            provider="CPUExecutionProvider",
            embedding_service=FaceEmbeddingService(
                provider="CPUExecutionProvider",
                models_dir=settings.models_dir,
            ),
        )
        assert app_logo_path().is_file()

        agreement = UserAgreementDialog(require_acceptance=False)
        agreement.show()
        app.processEvents()
        agreement.close()
        app.processEvents()

        window = MainWindow(context)
        window.show()
        app.processEvents()

        assert window.stack.count() == 8
        assert window.minimumWidth() <= 820
        assert window.windowTitle().endswith("CampPhoto AI")

        for key in (
            "dashboard",
            "register",
            "process",
            "review",
            "participants",
            "reports",
            "settings",
            "about",
        ):
            window.navigate(key)
            app.processEvents()

        window.close()
        app.processEvents()
        get_engine().dispose()
        app.processEvents()


if __name__ == "__main__":
    main()
