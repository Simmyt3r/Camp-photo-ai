"""
Face detection service.

Used primarily during participant registration (section 5) to validate a
reference photo before an embedding is even generated: reject photos
with no face, flag photos with multiple faces, and expose bounding boxes
for future UI preview/cropping. The main batch pipeline
(workers/batch_processor.py) calls FaceEmbeddingService directly instead
of this, since InsightFace computes detection + embedding together in
one forward pass -- calling both services separately there would mean
running the detector twice for no benefit. Both share one loaded model
via _face_analysis_loader either way, so there's no duplicate
memory/startup cost regardless of which path is used.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from app.services._face_analysis_loader import get_face_analysis_app

logger = logging.getLogger("camp_photo_ai.face_detection")


@dataclass
class DetectedFace:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    landmarks: np.ndarray  # 5x2 keypoints
    detection_score: float


class FaceDetectionService:
    def __init__(self, provider: str = "CPUExecutionProvider", models_dir: str | None = None):
        self._provider = provider
        self._models_dir = models_dir

    def detect(self, image: np.ndarray) -> list[DetectedFace]:
        """image: BGR numpy array (as returned by cv2.imread /
        services.image_processing.safe_load_image)."""
        app = get_face_analysis_app(provider=self._provider, models_dir=self._models_dir)
        faces = app.get(image)
        return [
            DetectedFace(bbox=tuple(float(v) for v in f.bbox), landmarks=f.kps,
                         detection_score=float(f.det_score))
            for f in faces
        ]

    def validate_reference_photo(self, image: np.ndarray) -> tuple[bool, str]:
        """Returns (ok, message) for the registration workflow (section 5):
        rejects photos with zero faces, and rejects (with a clear reason)
        photos with more than one face, since a reference embedding must
        come from exactly one person."""
        faces = self.detect(image)
        if len(faces) == 0:
            return False, "No face detected in this photo -- please choose another."
        if len(faces) > 1:
            return False, (
                f"{len(faces)} faces detected -- reference photos must contain "
                f"exactly one face. Crop the photo or choose a different one."
            )
        return True, "OK"
