"""
pytest-benchmark micro-benchmarks for ParticipantIndex.score_all() --
the real production matching code path, not a reimplementation.

Run directly for interactive numbers:
    pytest tests/performance/test_matching_benchmarks.py --benchmark-only -v

Not part of the documented `pytest tests/unit` workflow (these live
under tests/performance/, not tests/unit/), so they never slow down or
destabilize that fast/portable command; run this file explicitly when
you want performance numbers. (They're fast enough -- vectorized numpy,
no real I/O -- that a bare `pytest` picking them up via pyproject.toml's
`testpaths` isn't a real problem either, just not the primary path.)
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.face_matching import ParticipantIndex


def _build_index(n_participants: int, embeddings_per_participant: int = 3, dim: int = 512, seed: int = 0) -> ParticipantIndex:
    rng = np.random.default_rng(seed)
    index = ParticipantIndex(strategy="top_k", top_k=3)
    for i in range(n_participants):
        vecs = rng.normal(size=(embeddings_per_participant, dim)).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        index.add_participant(f"P{i:07d}", vecs)
    return index


def _random_query(dim: int = 512, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    q = rng.normal(size=dim).astype(np.float32)
    return q / np.linalg.norm(q)


@pytest.mark.parametrize("n_participants", [100, 1_000, 10_000])
def test_score_all_scales_with_participant_count(benchmark, n_participants):
    """Section 24: matching must not degrade into an expensive
    per-embedding Python loop as the registered population grows.
    pytest-benchmark reports mean/min/max/stddev across many calls."""
    index = _build_index(n_participants)
    query = _random_query()

    result = benchmark(index.score_all, query)

    assert len(result) == n_participants


@pytest.mark.parametrize("strategy", ["max", "mean", "centroid", "top_k"])
def test_score_all_across_match_strategies(benchmark, strategy):
    """All four multi-reference strategies (section 6) should have
    comparable performance -- none of them should be a hidden Python
    loop over individual embeddings."""
    rng = np.random.default_rng(2)
    index = ParticipantIndex(strategy=strategy, top_k=3)
    for i in range(1_000):
        vecs = rng.normal(size=(5, 512)).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        index.add_participant(f"P{i:07d}", vecs)
    query = _random_query()

    result = benchmark(index.score_all, query)

    assert len(result) == 1_000
