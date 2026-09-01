"""
Accuracy evaluation and threshold calibration (spec sections 21-22).

Real-world, consented validation data is required for meaningful
evaluation -- per section 31, synthetic faces alone are not a valid
benchmark. This module doesn't care where the data came from; it just
expects a directory laid out as:

    dataset/
    |-- person_001/
    |   |-- photo1.jpg
    |   |-- photo2.jpg
    |   `-- photo3.jpg
    |-- person_002/
    |   `-- ...
    `-- _unknown/              (optional: people who should NEVER match)
        |-- stranger1.jpg
        `-- stranger2.jpg

Each labelled identity needs at least 2 usable photos: some become the
"gallery" (used exactly like registration would to build reference
embeddings), the rest become "probes" (run through the same matching
pipeline production uses, and checked against the known answer).
Embeddings are computed ONCE per photo and reused across an entire
threshold sweep -- re-running face detection/embedding per threshold
grid point would be needless, expensive duplicate work.

Section 21 asks that "recognition accuracy" (is the embedding/matching
correctly identifying the right person at all?) be kept distinct from
"automatic assignment accuracy" (given the CURRENT threshold policy, how
many decisions were correct?). recognition_accuracy() answers the first,
threshold-independently; evaluate_at_threshold()/ThresholdMetrics answer
the second, for one threshold configuration at a time.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.services.face_embedding import FaceEmbeddingService
from app.services.face_matching import MatchDecision, ParticipantIndex, evaluate_match
from app.services.image_processing import is_supported, safe_load_image

logger = logging.getLogger("camp_photo_ai.evaluation")

DEFAULT_THRESHOLD_GRID = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75)  # matches spec section 22's example table
UNKNOWN_DIRNAME = "_unknown"


# --- Dataset loading ---------------------------------------------------

@dataclass
class GalleryEntry:
    identity: str
    embeddings: np.ndarray  # (N, D) reference embeddings for this identity


@dataclass
class ProbeResult:
    identity: str          # true identity label, or UNKNOWN_DIRNAME for impostor probes
    photo_path: str
    embedding: np.ndarray
    is_impostor: bool      # True if this identity has no gallery/reference at all


@dataclass
class LoadedDataset:
    gallery: list[GalleryEntry] = field(default_factory=list)
    probes: list[ProbeResult] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (identity_or_path, reason)

    @property
    def known_probe_count(self) -> int:
        return sum(1 for p in self.probes if not p.is_impostor)

    @property
    def impostor_probe_count(self) -> int:
        return sum(1 for p in self.probes if p.is_impostor)


def _embed_single_face_photos(
    photo_paths: list[Path], embedding_service: FaceEmbeddingService, skipped: list[tuple[str, str]],
) -> list[tuple[Path, np.ndarray]]:
    usable = []
    for photo_path in photo_paths:
        load_result = safe_load_image(photo_path)
        if not load_result.success:
            skipped.append((str(photo_path), load_result.error))
            continue
        faces = embedding_service.embed_image(load_result.image)
        if len(faces) != 1:
            skipped.append((str(photo_path), f"{len(faces)} faces detected -- expected exactly 1"))
            continue
        usable.append((photo_path, faces[0][0]))
    return usable


def load_validation_dataset(
    dataset_dir: Path,
    embedding_service: FaceEmbeddingService,
    gallery_size: int = 3,
    unknown_dirname: str = UNKNOWN_DIRNAME,
) -> LoadedDataset:
    """Loads a labelled dataset directory into a gallery (for registering
    simulated participants) and probes (for running through the matching
    pipeline against known answers). See module docstring for layout."""
    result = LoadedDataset()

    identity_dirs = sorted(
        p for p in dataset_dir.iterdir() if p.is_dir() and p.name != unknown_dirname
    )
    for identity_dir in identity_dirs:
        photo_paths = sorted(p for p in identity_dir.iterdir() if is_supported(p))
        if len(photo_paths) < 2:
            result.skipped.append((
                identity_dir.name,
                f"only {len(photo_paths)} usable photo(s) found -- need at least 2 "
                f"(one for the gallery, one to hold back as a probe)",
            ))
            continue

        usable = _embed_single_face_photos(photo_paths, embedding_service, result.skipped)
        if len(usable) < 2:
            result.skipped.append((
                identity_dir.name,
                f"only {len(usable)} photo(s) passed face validation -- need at least 2",
            ))
            continue

        split = gallery_size if len(usable) > gallery_size else len(usable) - 1
        gallery_photos, probe_photos = usable[:split], usable[split:]

        result.gallery.append(GalleryEntry(
            identity=identity_dir.name,
            embeddings=np.stack([e for _, e in gallery_photos]),
        ))
        for path, embedding in probe_photos:
            result.probes.append(ProbeResult(identity_dir.name, str(path), embedding, is_impostor=False))

    unknown_dir = dataset_dir / unknown_dirname
    if unknown_dir.is_dir():
        photo_paths = sorted(p for p in unknown_dir.iterdir() if is_supported(p))
        usable = _embed_single_face_photos(photo_paths, embedding_service, result.skipped)
        for path, embedding in usable:
            result.probes.append(ProbeResult(unknown_dirname, str(path), embedding, is_impostor=True))

    return result


# --- Recognition accuracy (threshold-independent) -----------------------

def recognition_accuracy(
    gallery: list[GalleryEntry],
    probes: list[ProbeResult],
    match_strategy: str = "top_k",
    top_k: int = 3,
    top_n_values: tuple[int, ...] = (1, 5),
) -> dict[int, float]:
    """For each known-identity probe: is the true identity among the
    top-N highest-scoring gallery candidates? Measures the embedding/
    matching quality itself (section 21's "Recognition accuracy"),
    independent of any auto-match/review threshold. top-5 is only
    meaningful with 5+ registered identities; with fewer, it saturates
    trivially -- interpret accordingly on small datasets."""
    index = ParticipantIndex(strategy=match_strategy, top_k=top_k)
    for entry in gallery:
        index.add_participant(entry.identity, entry.embeddings)

    known_probes = [p for p in probes if not p.is_impostor]
    hits = {n: 0 for n in top_n_values}
    for probe in known_probes:
        ranked_ids = [c.participant_id for c in index.score_all(probe.embedding)]
        for n in top_n_values:
            if probe.identity in ranked_ids[:n]:
                hits[n] += 1

    total = len(known_probes) or 1
    return {n: hits[n] / total for n in top_n_values}


# --- Automatic assignment accuracy (per threshold configuration) --------

@dataclass
class ThresholdMetrics:
    auto_match_threshold: float
    review_threshold: float
    minimum_score_margin: float
    match_strategy: str

    true_positives: int = 0        # correct AUTO_MATCH
    false_positives: int = 0       # WRONG AUTO_MATCH (incl. an impostor auto-matched to anyone)
    false_negatives: int = 0       # known identity, but ended UNMATCHED when it should have matched
    true_negatives: int = 0        # impostor correctly left UNMATCHED
    review_correct_candidate: int = 0  # sent to REVIEW, and the suggested candidate IS correct
    review_wrong_candidate: int = 0    # sent to REVIEW, suggested candidate is wrong (or absent)
    review_impostor: int = 0           # impostor sent to REVIEW rather than cleanly rejected

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def false_accept_rate(self) -> float:
        """Of everything that should NOT have auto-matched (impostors,
        plus known people auto-matched to the WRONG person), what
        fraction incorrectly did anyway. The single most important
        number per section 8 -- a wrong auto-assignment is worse than a
        missed one."""
        denom = self.false_positives + self.true_negatives
        return self.false_positives / denom if denom else 0.0

    @property
    def false_reject_rate(self) -> float:
        denom = self.false_negatives + self.true_positives
        return self.false_negatives / denom if denom else 0.0

    @property
    def review_queue_size(self) -> int:
        return self.review_correct_candidate + self.review_wrong_candidate + self.review_impostor

    @property
    def recall_if_review_always_correct(self) -> float:
        """Upper bound: recall if every REVIEW item that had the right
        candidate suggested gets correctly confirmed by a human. Shows
        the ceiling of automation + review together, separate from the
        strict automatic-only recall above."""
        potential_tp = self.true_positives + self.review_correct_candidate
        denom = potential_tp + self.false_negatives + self.review_wrong_candidate
        return potential_tp / denom if denom else 0.0


def evaluate_at_threshold(
    gallery: list[GalleryEntry],
    probes: list[ProbeResult],
    auto_match_threshold: float,
    review_threshold: float,
    minimum_score_margin: float,
    match_strategy: str = "top_k",
    top_k: int = 3,
) -> ThresholdMetrics:
    """Runs every probe through the exact same ParticipantIndex +
    evaluate_match() the production pipeline uses, and classifies each
    outcome against the known-correct answer."""
    index = ParticipantIndex(strategy=match_strategy, top_k=top_k)
    for entry in gallery:
        index.add_participant(entry.identity, entry.embeddings)

    metrics = ThresholdMetrics(auto_match_threshold, review_threshold, minimum_score_margin, match_strategy)

    for probe in probes:
        scored = index.score_all(probe.embedding)
        result = evaluate_match(scored, auto_match_threshold, review_threshold, minimum_score_margin)
        correct_top_candidate = bool(result.best) and result.best.participant_id == probe.identity

        if probe.is_impostor:
            if result.decision == MatchDecision.AUTO_MATCH:
                metrics.false_positives += 1
            elif result.decision == MatchDecision.REVIEW:
                metrics.review_impostor += 1
            else:
                metrics.true_negatives += 1
        else:
            if result.decision == MatchDecision.AUTO_MATCH:
                if correct_top_candidate:
                    metrics.true_positives += 1
                else:
                    metrics.false_positives += 1  # auto-matched to the WRONG person
            elif result.decision == MatchDecision.REVIEW:
                if correct_top_candidate:
                    metrics.review_correct_candidate += 1
                else:
                    metrics.review_wrong_candidate += 1
            else:  # UNMATCHED
                metrics.false_negatives += 1

    return metrics


def sweep_thresholds(
    gallery: list[GalleryEntry],
    probes: list[ProbeResult],
    threshold_grid: tuple[float, ...] = DEFAULT_THRESHOLD_GRID,
    review_gap: float = 0.15,
    minimum_score_margin: float = 0.08,
    match_strategy: str = "top_k",
    top_k: int = 3,
) -> list[ThresholdMetrics]:
    """The section 22 calibration table: evaluates every value in
    threshold_grid as the auto-match threshold (holding review_gap and
    minimum_score_margin fixed), reusing the same pre-computed probe
    embeddings for all of them -- no repeated face detection/embedding."""
    return [
        evaluate_at_threshold(
            gallery, probes,
            auto_match_threshold=t,
            review_threshold=max(0.0, t - review_gap),
            minimum_score_margin=minimum_score_margin,
            match_strategy=match_strategy, top_k=top_k,
        )
        for t in threshold_grid
    ]


def recommend_threshold(results: list[ThresholdMetrics], min_precision: float = 0.98) -> ThresholdMetrics | None:
    """Suggests the highest-recall threshold among those clearing
    min_precision -- "the most permissive setting that still keeps wrong
    auto-matches rare," matching section 8's precision-over-recall
    priority. A starting point for a human to weigh against their own
    risk tolerance, NOT a claim that it's universally correct (section
    22). Returns None if nothing in the sweep clears min_precision."""
    candidates = [m for m in results if m.precision >= min_precision]
    if not candidates:
        return None
    return max(candidates, key=lambda m: m.recall)


# --- Reporting ------------------------------------------------------------

def format_sweep_table(results: list[ThresholdMetrics]) -> str:
    header = f"{'Threshold':>9} | {'Precision':>9} | {'Recall':>7} | {'F1':>6} | {'FAR':>6} | {'FRR':>6} | {'Review Q':>8}"
    lines = [header, "-" * len(header)]
    for m in results:
        lines.append(
            f"{m.auto_match_threshold:>9.2f} | {m.precision:>9.3f} | {m.recall:>7.3f} | "
            f"{m.f1:>6.3f} | {m.false_accept_rate:>6.3f} | {m.false_reject_rate:>6.3f} | "
            f"{m.review_queue_size:>8d}"
        )
    return "\n".join(lines)


def plot_threshold_sweep(results: list[ThresholdMetrics], output_path: Path) -> None:
    """Section 22's trade-off graph. matplotlib is imported lazily here
    (not at module level) so nothing else in this module requires it --
    the metrics/classification logic is fully usable, and unit-testable,
    without matplotlib installed."""
    import matplotlib
    matplotlib.use("Agg")  # headless-safe: no display server required
    import matplotlib.pyplot as plt

    thresholds = [m.auto_match_threshold for m in results]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(thresholds, [m.precision for m in results], marker="o", label="Precision")
    ax.plot(thresholds, [m.recall for m in results], marker="o", label="Recall")
    ax.plot(thresholds, [m.f1 for m in results], marker="o", label="F1")
    ax.plot(thresholds, [m.false_accept_rate for m in results], marker="o", linestyle="--", label="False Accept Rate")
    ax.set_xlabel("Auto-match threshold")
    ax.set_ylabel("Score")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Threshold calibration sweep")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
