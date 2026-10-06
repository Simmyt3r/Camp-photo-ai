"""
Face embedding service.

Generates normalized embeddings via the shared InsightFace model (see
_face_analysis_loader.py) and implements the multi-reference matching
strategies from section 6 (max / mean / centroid / top-k similarity
against a participant's stored reference embeddings).
"""
from __future__ import annotations

import logging

import numpy as np

from app.services._face_analysis_loader import get_face_analysis_app

logger = logging.getLogger("camp_photo_ai.face_embedding")

EMBEDDING_MODEL_NAME = "buffalo_l"
EMBEDDING_MODEL_VERSION = "1.0"
EMBEDDING_DIMENSIONS = 512  # buffalo_l's ArcFace recognition head output size


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


class FaceEmbeddingService:
    def __init__(self, provider: str = "CPUExecutionProvider", models_dir: str | None = None):
        self._provider = provider
        self._models_dir = models_dir
        self._model_progress_callback = None

    def set_model_progress_callback(self, callback) -> None:
        """Set an optional callback(downloaded_bytes, total_bytes, message).

        Desktop workers use this to show first-run model download progress.
        It is intentionally optional so CLI/tests keep the same API surface.
        """
        self._model_progress_callback = callback

    def embed_image(self, image: np.ndarray) -> list[tuple[np.ndarray, float, tuple[float, float, float, float]]]:
        """Runs detection+embedding on a full image. Returns a list of
        (normalized_embedding, detection_score, bbox) tuples, one per
        detected face, in the order InsightFace returns them. bbox is
        (x1, y1, x2, y2) in the original image's pixel coordinates --
        kept alongside the embedding so callers (e.g. the batch pipeline)
        can store it for later display without a second detection pass."""
        app = get_face_analysis_app(
            provider=self._provider, model_name=EMBEDDING_MODEL_NAME, models_dir=self._models_dir,
            progress_callback=self._model_progress_callback,
        )
        faces = app.get(image)
        return [
            (normalize(f.embedding.astype(np.float32)), float(f.det_score),
             tuple(float(v) for v in f.bbox))
            for f in faces
        ]

    def embed_single_face_image(self, image: np.ndarray) -> np.ndarray | None:
        """For registration: expects exactly one face. Returns None if
        zero or more than one face is found so the caller can reject/warn
        per section 5 (see also FaceDetectionService.validate_reference_photo)."""
        results = self.embed_image(image)
        if len(results) != 1:
            return None
        return results[0][0]

    def warm_up(self) -> None:
        """Loads the model and runs one dummy inference so the first real
        image in a batch doesn't pay model-load latency (section 11:
        "Model warm-up")."""
        app = get_face_analysis_app(
            provider=self._provider, model_name=EMBEDDING_MODEL_NAME, models_dir=self._models_dir
        )
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        app.get(dummy)


# --- Multi-reference matching strategies (section 6) -----------------------
# Each takes a normalized (D,) query vector and a normalized (N, D) matrix
# of one participant's reference embeddings, and returns a single score.

def strategy_max(query: np.ndarray, references: np.ndarray) -> float:
    """Best-case similarity: the query only needs to resemble ONE
    reference photo. Most permissive strategy -- most exposed to a single
    mislabeled or low-quality reference photo."""
    return float(np.max(references @ query))


def strategy_mean(query: np.ndarray, references: np.ndarray) -> float:
    """Average similarity across all references. Penalizes participants
    whose reference set is inconsistent (e.g. one blurry photo drags the
    whole score down)."""
    return float(np.mean(references @ query))


def strategy_centroid(query: np.ndarray, references: np.ndarray) -> float:
    """Similarity to the re-normalized average reference embedding.
    Cheap at query time since the centroid can be precomputed once per
    participant, rather than compared against every reference individually."""
    centroid = normalize(np.mean(references, axis=0))
    return float(centroid @ query)


def strategy_top_k(query: np.ndarray, references: np.ndarray, k: int = 3) -> float:
    """Mean of the top-k reference similarities (default strategy): more
    robust than `max` (not swayed by one lucky high-scoring reference)
    while still tolerant of a participant having one or two poor-quality
    reference photos, unlike a plain `mean`."""
    sims = references @ query
    k = min(k, len(sims))
    top = np.partition(sims, -k)[-k:]
    return float(np.mean(top))


MATCH_STRATEGIES = {
    "max": strategy_max,
    "mean": strategy_mean,
    "centroid": strategy_centroid,
    "top_k": strategy_top_k,
}
