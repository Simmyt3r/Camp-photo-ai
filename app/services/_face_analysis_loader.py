"""
Internal shared loader for InsightFace's FaceAnalysis model.

InsightFace's `buffalo_l` pack performs detection and embedding together
in a single forward pass (its recognition model is bundled with its
detector). FaceDetectionService and FaceEmbeddingService are kept as
separate services for clean architecture and future model-swap
flexibility (section 32), but both call through here so they share one
loaded model instance instead of each loading their own copy into
memory. Import of insightface itself is lazy -- this module is safe to
import even when insightface isn't installed; only calling
get_face_analysis_app() requires it.
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger("camp_photo_ai.face_model")

_lock = threading.Lock()
_apps: dict[tuple, object] = {}


def get_face_analysis_app(
    provider: str = "CPUExecutionProvider",
    model_name: str = "buffalo_l",
    det_size: tuple[int, int] = (640, 640),
    models_dir: str | None = None,
):
    key = (provider, model_name, models_dir or "")
    with _lock:
        if key not in _apps:
            try:
                from insightface.app import FaceAnalysis
            except ImportError as exc:
                raise RuntimeError(
                    "insightface is not installed. Run `pip install insightface "
                    "onnxruntime` (or `onnxruntime-gpu` for GPU mode) to enable "
                    "face detection/embedding, then re-run this command."
                ) from exc

            kwargs = {"name": model_name, "providers": [provider]}
            if models_dir:
                kwargs["root"] = models_dir  # keeps model weights inside the project (models/)

            logger.info("Loading FaceAnalysis model=%s provider=%s ...", model_name, provider)
            app = FaceAnalysis(**kwargs)
            app.prepare(ctx_id=0 if provider != "CPUExecutionProvider" else -1, det_size=det_size)
            _apps[key] = app
            logger.info("FaceAnalysis model ready.")
        return _apps[key]
