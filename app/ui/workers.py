"""
QThread workers so the GUI never blocks on face detection/embedding or
batch processing (section 18: "The UI must remain responsive... Never
freeze the GUI during a large batch operation").

Each worker opens its own database session inside run() (SQLAlchemy
sessions aren't safe to share across threads) and communicates results
back to the UI thread exclusively via Qt signals -- widgets are never
touched directly from these threads.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.config.settings import Settings
from app.database.db import get_session
from app.services.face_embedding import FaceEmbeddingService
from app.workers.batch_processor import run_batch


class ProcessingWorker(QThread):
    """Runs run_batch() off the UI thread and re-emits its progress
    callback as a Qt signal. Qt marshals queued-connection signals across
    the thread boundary automatically, so slots connected to `progress`
    run safely on the main thread even though emit() happens here."""

    progress = Signal(object, str)  # BatchStats snapshot, current filename
    finished_ok = Signal(object)    # final BatchStats
    failed = Signal(str)

    def __init__(self, settings: Settings, input_dir: Path, output_dir: Path,
                 embedding_service: FaceEmbeddingService, resume: bool = True,
                 participant_filter: set[str] | None = None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._input_dir = input_dir
        self._output_dir = output_dir
        self._embedding_service = embedding_service
        self._resume = resume
        self._participant_filter = participant_filter

    def run(self) -> None:
        try:
            with get_session() as session:
                stats = run_batch(
                    session, self._settings, self._input_dir, self._output_dir,
                    self._embedding_service,
                    progress_callback=lambda s, f: self.progress.emit(s, f),
                    resume=self._resume,
                    participant_filter=self._participant_filter,
                )
            self.finished_ok.emit(stats)
        except Exception as exc:  # surface any failure to the UI instead of dying silently
            self.failed.emit(str(exc))


@dataclass
class ReferencePhotoResult:
    path: str
    accepted: bool
    message: str
    embedding: object = None   # np.ndarray | None
    thumbnail: object = None   # bytes | None


class RegistrationWorker(QThread):
    """Runs face detection+embedding for a batch of reference photos off
    the UI thread -- model load alone can take several seconds on first
    use, which would otherwise freeze the registration screen."""

    result_ready = Signal(list)  # list[ReferencePhotoResult]
    failed = Signal(str)

    def __init__(self, embedding_service: FaceEmbeddingService, photo_paths: list[Path], parent=None):
        super().__init__(parent)
        self._embedding_service = embedding_service
        self._photo_paths = photo_paths

    def run(self) -> None:
        import cv2

        from app.services.image_processing import encode_thumbnail_jpeg

        results: list[ReferencePhotoResult] = []
        try:
            for path in self._photo_paths:
                image = cv2.imread(str(path))
                if image is None:
                    results.append(ReferencePhotoResult(str(path), False, "could not be read"))
                    continue
                faces = self._embedding_service.embed_image(image)
                if len(faces) == 0:
                    results.append(ReferencePhotoResult(str(path), False, "no face detected"))
                    continue
                if len(faces) > 1:
                    results.append(ReferencePhotoResult(
                        str(path), False, f"{len(faces)} faces detected -- expected exactly 1"
                    ))
                    continue
                embedding, _det_score, _bbox = faces[0]
                thumbnail = encode_thumbnail_jpeg(image)
                results.append(ReferencePhotoResult(str(path), True, "OK", embedding, thumbnail))
            self.result_ready.emit(results)
        except Exception as exc:
            self.failed.emit(str(exc))
