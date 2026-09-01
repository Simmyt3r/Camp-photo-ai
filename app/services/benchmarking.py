"""
Performance and load testing (spec sections 23-24).

Three independent benchmark targets:

- **matching**: ParticipantIndex.score_all() at increasing registered-
  participant counts, using synthetic embeddings. This is the direct
  test of section 24's core requirement -- "do not perform an
  unnecessarily expensive Python loop comparing every face against
  every embedding" -- and is achievable at full spec-target scale
  (1k/10k/100k) on any hardware, since it's pure numpy, no model
  inference involved.
- **database**: insert/query throughput for Participant/
  ReferenceEmbedding/ProcessingCache rows at scale, against a disposable
  SQLite file (never the user's real data/camp_photo_ai.db). Also
  achievable at full target scale on any hardware.
- **pipeline**: real face detection + embedding + disk I/O against real
  photos. This is the one number that has no synthetic substitute --
  actual inference speed depends on the actual CPU/GPU it runs on.
  Results here are only representative of the machine that generated
  them; re-run this target on your real deployment hardware.

All three write into a single BenchmarkResult shape so they can share
formatting/reporting code.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import psutil

from app.services.face_embedding import FaceEmbeddingService
from app.services.face_matching import ParticipantIndex
from app.services.image_processing import safe_load_image

logger = logging.getLogger("camp_photo_ai.benchmarking")


@dataclass
class BenchmarkResult:
    name: str
    n: int                    # the scale parameter (participants, rows, images...)
    iterations: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    peak_rss_mb: float | None = None
    extra: dict = field(default_factory=dict)   # e.g. {"images_per_sec": 12.3}
    extrapolated: bool = False                   # True if n wasn't actually run -- see extrapolate_linear()


def _summarize(name: str, n: int, timings_ms: list[float], peak_rss_mb: float | None = None,
                extra: dict | None = None) -> BenchmarkResult:
    arr = np.array(timings_ms, dtype=np.float64)
    return BenchmarkResult(
        name=name, n=n, iterations=len(arr),
        mean_ms=float(arr.mean()), p50_ms=float(np.percentile(arr, 50)),
        p95_ms=float(np.percentile(arr, 95)), p99_ms=float(np.percentile(arr, 99)),
        peak_rss_mb=peak_rss_mb, extra=extra or {},
    )


class ResourceTracker:
    """Samples this process's RSS memory during a benchmark loop to
    report peak RAM (section 23). Call sample() periodically; cheap
    enough to call every iteration for benchmarks with <100k iterations."""

    def __init__(self):
        self._process = psutil.Process()
        self.peak_rss_mb = self._process.memory_info().rss / (1024 ** 2)

    def sample(self) -> None:
        rss_mb = self._process.memory_info().rss / (1024 ** 2)
        if rss_mb > self.peak_rss_mb:
            self.peak_rss_mb = rss_mb


# --- Matching benchmark (section 24: scales without a per-embedding loop) --

def benchmark_matching(
    participant_counts: list[int],
    embeddings_per_participant: int = 3,
    embedding_dim: int = 512,
    queries: int = 100,
    match_strategy: str = "top_k",
    top_k: int = 3,
    seed: int = 42,
) -> list[BenchmarkResult]:
    """Builds a ParticipantIndex with N synthetic registered participants
    (real production code path -- app.services.face_matching.ParticipantIndex,
    not a reimplementation) and times score_all() over `queries` synthetic
    query vectors, for each N. If matching time grows much faster than
    linearly with N, that's evidence the "efficient in-memory participant
    embedding index" from section 11 needs work before it hits real scale."""
    results = []
    rng = np.random.default_rng(seed)

    for n in participant_counts:
        tracker = ResourceTracker()
        index = ParticipantIndex(strategy=match_strategy, top_k=top_k)
        for i in range(n):
            vecs = rng.normal(size=(embeddings_per_participant, embedding_dim)).astype(np.float32)
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
            index.add_participant(f"P{i:07d}", vecs)
        tracker.sample()

        query_vecs = rng.normal(size=(queries, embedding_dim)).astype(np.float32)
        query_vecs /= np.linalg.norm(query_vecs, axis=1, keepdims=True)

        timings_ms = []
        for q in query_vecs:
            t0 = time.perf_counter()
            index.score_all(q)
            timings_ms.append((time.perf_counter() - t0) * 1000)
        tracker.sample()

        result = _summarize("matching", n, timings_ms, peak_rss_mb=tracker.peak_rss_mb)
        result.extra["queries_per_sec"] = 1000.0 / result.mean_ms if result.mean_ms > 0 else float("inf")
        results.append(result)
        logger.info("matching n=%d: mean=%.3fms p95=%.3fms peak_rss=%.1fMB",
                     n, result.mean_ms, result.p95_ms, tracker.peak_rss_mb)

    return results


# --- Database benchmark ----------------------------------------------------

def benchmark_database(row_counts: list[int], db_path: Path, seed: int = 42) -> list[BenchmarkResult]:
    """Insert and query throughput for participants+embeddings at scale,
    against a disposable SQLite file at db_path (created fresh, deleted
    if it already exists -- never the user's real database)."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.database.models import Base, Participant, ReferenceEmbedding

    results = []
    rng = np.random.default_rng(seed)

    for n in row_counts:
        db_path.unlink(missing_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, future=True)
        tracker = ResourceTracker()

        # --- Insert throughput: N participants, 3 embeddings each ---
        insert_timings = []
        session = SessionLocal()
        for i in range(n):
            t0 = time.perf_counter()
            p = Participant(participant_id=f"P{i:07d}", full_name=f"Test Participant {i}", consent_given=True)
            session.add(p)
            session.flush()
            for _ in range(3):
                vec = rng.normal(size=512).astype(np.float32)
                vec /= np.linalg.norm(vec)
                session.add(ReferenceEmbedding(
                    participant_db_id=p.id, vector=vec.tobytes(), dimensions=512,
                    model_name="buffalo_l", model_version="1.0", source_image_hash="benchmark",
                ))
            insert_timings.append((time.perf_counter() - t0) * 1000)
            if i % 500 == 0:
                session.commit()
                tracker.sample()
        session.commit()
        tracker.sample()
        session.close()

        insert_result = _summarize("database_insert", n, insert_timings, peak_rss_mb=tracker.peak_rss_mb)
        insert_result.extra["rows_per_sec"] = 1000.0 / insert_result.mean_ms if insert_result.mean_ms > 0 else float("inf")
        results.append(insert_result)

        # --- Query throughput: rebuild the full participant index from
        # the DB, exactly like batch_processor._build_participant_index
        # does at the start of every real processing run. Uses
        # selectinload for the same reason production code does -- see
        # that function's docstring: without it this is an N+1 query
        # pattern (one query per participant to lazy-load embeddings),
        # which is dramatically slower at scale and is a big part of why
        # this benchmark exists. ---
        from sqlalchemy.orm import selectinload
        session = SessionLocal()
        query_timings = []
        for _ in range(20):
            t0 = time.perf_counter()
            participants = session.query(Participant).options(selectinload(Participant.embeddings)).all()
            for p in participants:
                _ = p.embeddings  # already loaded by selectinload -- no extra query
            query_timings.append((time.perf_counter() - t0) * 1000)
        session.close()

        query_result = _summarize("database_query_all_participants", n, query_timings)
        results.append(query_result)

        engine.dispose()
        logger.info("database n=%d: insert mean=%.3fms/row, query-all mean=%.1fms",
                     n, insert_result.mean_ms, query_result.mean_ms)

    db_path.unlink(missing_ok=True)
    return results


# --- Pipeline benchmark (real photos, real inference -- no synthetic substitute) --

def benchmark_pipeline(
    photo_paths: list[Path],
    n: int,
    embedding_service: FaceEmbeddingService,
    max_dimension: int = 4096,
) -> BenchmarkResult:
    """Runs safe_load_image() + embed_image() -- real disk I/O, real EXIF
    handling, real model inference -- over `n` photos, cycling through
    photo_paths if it has fewer than n entries. Deliberately bypasses
    ProcessingCache/DuplicateIndex (unlike the real batch pipeline) so
    repeated files are still fully reprocessed each time; this measures
    raw per-image throughput, not batch efficiency with caching."""
    if not photo_paths:
        raise ValueError("photo_paths must contain at least one image")

    tracker = ResourceTracker()
    timings_ms = []
    total_faces = 0

    for i in range(n):
        path = photo_paths[i % len(photo_paths)]
        t0 = time.perf_counter()
        load_result = safe_load_image(path, max_dimension=max_dimension)
        if not load_result.success:
            continue
        faces = embedding_service.embed_image(load_result.image)
        timings_ms.append((time.perf_counter() - t0) * 1000)
        total_faces += len(faces)
        if i % 10 == 0:
            tracker.sample()

    tracker.sample()
    result = _summarize("pipeline", n, timings_ms, peak_rss_mb=tracker.peak_rss_mb)
    total_seconds = sum(timings_ms) / 1000
    result.extra["images_per_sec"] = n / total_seconds if total_seconds > 0 else float("inf")
    result.extra["faces_per_sec"] = total_faces / total_seconds if total_seconds > 0 else float("inf")
    result.extra["total_faces"] = total_faces
    return result


# --- Startup / model load timing -------------------------------------------

def measure_model_load_time(embedding_service: FaceEmbeddingService) -> float:
    """Time-to-first-inference: model weights load (and, on first run
    ever, download) lazily on the first call. Returns milliseconds."""
    dummy = np.zeros((640, 640, 3), dtype=np.uint8)
    t0 = time.perf_counter()
    embedding_service.embed_image(dummy)
    return (time.perf_counter() - t0) * 1000


# --- Extrapolation (clearly-labeled, not a substitute for real runs) -------

def extrapolate_linear(base: BenchmarkResult, target_n: int) -> BenchmarkResult:
    """Projects the total wall-clock time to process target_n items,
    assuming each item costs the same as the measured mean_ms --
    reasonable for per-item-independent work (one photo's pipeline time
    doesn't depend on how many other photos exist), NOT reasonable for
    anything where cost depends on n (matching time vs. registered-
    participant count is exactly the kind of relationship this framework
    measures for real rather than assumes -- never extrapolate that one).
    Per-item timing/rate stats (mean_ms, images_per_sec, ...) don't
    change with n, so they're carried over unchanged; only a new
    estimated-total-time figure is added. Always labelled via
    extrapolated=True so a report can't mistake this for a real run."""
    extra = dict(base.extra)
    extra["estimated_total_seconds_at_n"] = target_n * base.mean_ms / 1000
    return BenchmarkResult(
        name=base.name, n=target_n, iterations=0,
        mean_ms=base.mean_ms, p50_ms=base.p50_ms, p95_ms=base.p95_ms, p99_ms=base.p99_ms,
        peak_rss_mb=base.peak_rss_mb, extra=extra, extrapolated=True,
    )


# --- Reporting ---------------------------------------------------------------

def format_benchmark_table(results: list[BenchmarkResult]) -> str:
    header = f"{'Benchmark':>28} | {'n':>9} | {'Mean':>9} | {'P95':>9} | {'Peak RSS':>10} | Notes"
    lines = [header, "-" * len(header)]
    for r in results:
        notes = ", ".join(f"{k}={v:.1f}" if isinstance(v, float) else f"{k}={v}"
                           for k, v in r.extra.items() if k != "total_faces")
        if r.extrapolated:
            notes = "[EXTRAPOLATED, not measured] " + notes
        rss = f"{r.peak_rss_mb:.1f}MB" if r.peak_rss_mb is not None else "n/a"
        lines.append(
            f"{r.name:>28} | {r.n:>9,} | {r.mean_ms:>7.2f}ms | {r.p95_ms:>7.2f}ms | {rss:>10} | {notes}"
        )
    return "\n".join(lines)


def plot_benchmark_results(results: list[BenchmarkResult], output_path: Path, metric: str = "mean_ms") -> None:
    """Groups results by `name` and plots `metric` vs n for each group.
    matplotlib imported lazily -- not required to use the rest of this
    module (e.g. in tests)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_name: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        by_name.setdefault(r.name, []).append(r)

    fig, ax = plt.subplots(figsize=(8, 5))
    for name, group in by_name.items():
        group = sorted(group, key=lambda r: r.n)
        xs = [r.n for r in group]
        ys = [getattr(r, metric) for r in group]
        style = "--" if any(r.extrapolated for r in group) else "-"
        ax.plot(xs, ys, marker="o", linestyle=style, label=name)
    ax.set_xlabel("n (scale)")
    ax.set_ylabel(metric)
    ax.set_xscale("log")
    ax.set_title("Benchmark results (dashed = extrapolated, not measured)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
