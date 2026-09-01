"""
Face matching engine.

Contains the core, side-effect-free matching decision logic from
FACE MATCHING and CRITICAL FALSE-POSITIVE PROTECTION (sections 7-8).
Deliberately free of I/O (no database, no filesystem, no insightface
import) so it can be unit-tested directly with synthetic vectors, and so
the same decision function is used by both the live batch pipeline and
the threshold-calibration utility (app/services/evaluation.py).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

import numpy as np

from app.services.face_embedding import MATCH_STRATEGIES, normalize


class MatchDecision(str, enum.Enum):
    AUTO_MATCH = "auto_match"
    REVIEW = "review"
    UNMATCHED = "unmatched"


@dataclass
class CandidateScore:
    participant_id: str
    score: float


@dataclass
class MatchResult:
    decision: MatchDecision
    best: CandidateScore | None
    second_best: CandidateScore | None
    score_margin: float
    reason: str


class ParticipantIndex:
    """In-memory index of every registered participant's reference
    embeddings, for fast vectorized comparison against a query face
    (section 24: avoid an expensive per-embedding Python loop; section
    11: efficient in-memory participant embedding index).

    score_all() does exactly ONE matrix-vector product across every
    registered participant's representative rows combined. Two
    optimization passes went into this, both driven by actual
    benchmarking (tests/performance/test_matching_benchmarks.py; numbers
    in docs/PERFORMANCE.md), not assumption:

    1. An earlier version vectorized each participant's own references
       but still called that vectorized matmul once per participant in
       Python -- ~830us at 100 participants, ~99ms at 10,000.
    2. Replacing that with one big matmul across all participants (this
       docstring's opening claim) only improved things by ~20%.
       Profiling showed why: the REDUCTION step (np.mean/np.partition
       collapsing each participant's few similarity scores down to one)
       was calling numpy 10,000 times on 3-element arrays, and per-call
       dispatch overhead dominated the actual math. _score_all_uniform()
       fixes this by reducing ALL participants in one vectorized call
       when they share the same reference-photo count (the common case
       in practice -- section 5 recommends "approximately 3-5" per
       participant, and it's always true for the centroid strategy,
       which has exactly one representative row per participant by
       construction). _score_all_ragged() is the correctness fallback
       for a mix of counts -- slower, but correct for any input.

    For the "centroid" strategy specifically, the representative row is
    a single precomputed normalize(mean(references)) vector rather than
    the raw references -- it doesn't depend on the query at all, so
    computing it once here (on add_participant/rebuild) rather than on
    every score_all() call is exactly equivalent, just far cheaper.
    """

    def __init__(self, strategy: str = "top_k", top_k: int = 3):
        if strategy not in MATCH_STRATEGIES:
            raise ValueError(f"Unknown match strategy: {strategy}")
        self._strategy_name = strategy
        self._top_k = top_k
        self._participant_ids: list[str] = []
        self._embeddings_by_participant: dict[str, np.ndarray] = {}
        self._stacked: np.ndarray | None = None          # (total_rows, D) -- rebuilt lazily
        self._boundaries: list[int] | None = None          # participant i occupies rows [boundaries[i], boundaries[i+1])
        self._uniform_row_count: int | None = None           # set only if every participant has the same row count
        self._dirty = True

    def add_participant(self, participant_id: str, embeddings: np.ndarray) -> None:
        """embeddings: (N, D) array of that participant's normalized
        reference embeddings."""
        if embeddings.ndim != 2 or embeddings.shape[0] == 0:
            raise ValueError("embeddings must be a non-empty (N, D) array")
        if participant_id not in self._embeddings_by_participant:
            self._participant_ids.append(participant_id)
        self._embeddings_by_participant[participant_id] = embeddings
        self._dirty = True

    def __len__(self) -> int:
        return len(self._participant_ids)

    def _representative_rows(self, embeddings: np.ndarray) -> np.ndarray:
        if self._strategy_name == "centroid":
            return normalize(np.mean(embeddings, axis=0)).reshape(1, -1)
        return embeddings

    def _rebuild_stacked(self) -> None:
        if not self._participant_ids:
            self._stacked = np.zeros((0, 0), dtype=np.float32)
            self._boundaries = [0]
            self._uniform_row_count = None
            self._dirty = False
            return

        blocks = [
            self._representative_rows(self._embeddings_by_participant[pid])
            for pid in self._participant_ids
        ]
        self._stacked = np.concatenate(blocks, axis=0).astype(np.float32)
        sizes = [b.shape[0] for b in blocks]
        self._boundaries = list(np.cumsum([0] + sizes))
        self._uniform_row_count = sizes[0] if len(set(sizes)) == 1 else None
        self._dirty = False

    def score_all(self, query: np.ndarray) -> list[CandidateScore]:
        """Scores `query` against every registered participant using the
        configured strategy, sorted best-first."""
        if self._dirty:
            self._rebuild_stacked()
        if not self._participant_ids:
            return []

        all_sims = self._stacked @ query  # the one expensive operation, done ONCE for every participant

        if self._uniform_row_count is not None:
            return self._score_all_uniform(all_sims)
        return self._score_all_ragged(all_sims)

    def _score_all_uniform(self, all_sims: np.ndarray) -> list[CandidateScore]:
        """Every participant has the same representative-row count k --
        reshape the flat similarity array into (n_participants, k) and
        reduce along axis=1 for every participant in ONE vectorized call,
        instead of n_participants individual numpy calls on tiny arrays."""
        k = self._uniform_row_count
        grid = all_sims.reshape(len(self._participant_ids), k)

        if self._strategy_name == "centroid":
            reduced = grid[:, 0]  # k is always 1 for centroid
        elif self._strategy_name == "max":
            reduced = grid.max(axis=1)
        elif self._strategy_name == "mean":
            reduced = grid.mean(axis=1)
        else:  # top_k
            top_k = min(self._top_k, k)
            reduced = np.partition(grid, -top_k, axis=1)[:, -top_k:].mean(axis=1)

        scores = [CandidateScore(pid, float(s)) for pid, s in zip(self._participant_ids, reduced)]
        scores.sort(key=lambda c: c.score, reverse=True)
        return scores

    def _score_all_ragged(self, all_sims: np.ndarray) -> list[CandidateScore]:
        """Fallback for a mix of reference-photo counts across
        participants -- correct for any combination, just not vectorized
        across participants the way _score_all_uniform() is."""
        scores = []
        for i, pid in enumerate(self._participant_ids):
            sims = all_sims[self._boundaries[i]:self._boundaries[i + 1]]
            if self._strategy_name == "top_k":
                k = min(self._top_k, len(sims))
                score = float(np.mean(np.partition(sims, -k)[-k:]))
            elif self._strategy_name == "max":
                score = float(np.max(sims))
            else:  # mean (centroid never reaches here -- always uniform, k=1)
                score = float(np.mean(sims))
            scores.append(CandidateScore(pid, score))

        scores.sort(key=lambda c: c.score, reverse=True)
        return scores


def evaluate_match(
    scored_candidates: list[CandidateScore],
    auto_match_threshold: float,
    review_threshold: float,
    minimum_score_margin: float,
) -> MatchResult:
    """Pure decision function -- see CRITICAL FALSE-POSITIVE PROTECTION
    (section 8).

    A wrong identification is treated as worse than a missed one:
      - AUTO_MATCH requires BOTH a high absolute score AND a healthy
        margin over the next-best candidate. A high score alone is not
        enough if a second participant is nearly as close a match --
        that is exactly the ambiguous case a human should look at.
      - REVIEW covers everything that clears the (lower) review bar but
        not the auto-match bar, or that clears the auto-match bar
        without enough margin.
      - Anything below the review bar is UNMATCHED.
    A reason is always populated, per section 8's "Record the reason for
    every match."
    """
    if not scored_candidates:
        return MatchResult(
            decision=MatchDecision.UNMATCHED,
            best=None, second_best=None, score_margin=0.0,
            reason="No registered participants to compare against.",
        )

    best = scored_candidates[0]
    second_best = scored_candidates[1] if len(scored_candidates) > 1 else None
    margin = best.score - second_best.score if second_best else best.score

    if best.score >= auto_match_threshold and margin >= minimum_score_margin:
        return MatchResult(
            decision=MatchDecision.AUTO_MATCH,
            best=best, second_best=second_best, score_margin=margin,
            reason=(
                f"Score {best.score:.3f} >= auto-match threshold "
                f"{auto_match_threshold:.3f} with margin {margin:.3f} over "
                f"the next-best candidate."
            ),
        )

    if best.score >= auto_match_threshold and margin < minimum_score_margin:
        runner_up = second_best.participant_id if second_best else "n/a"
        return MatchResult(
            decision=MatchDecision.REVIEW,
            best=best, second_best=second_best, score_margin=margin,
            reason=(
                f"Score {best.score:.3f} clears the auto-match threshold but "
                f"margin {margin:.3f} over '{runner_up}' is below the minimum "
                f"required margin {minimum_score_margin:.3f} -- too close to "
                f"call automatically."
            ),
        )

    if best.score >= review_threshold:
        return MatchResult(
            decision=MatchDecision.REVIEW,
            best=best, second_best=second_best, score_margin=margin,
            reason=(
                f"Score {best.score:.3f} is between the review threshold "
                f"{review_threshold:.3f} and auto-match threshold "
                f"{auto_match_threshold:.3f}."
            ),
        )

    return MatchResult(
        decision=MatchDecision.UNMATCHED,
        best=best, second_best=second_best, score_margin=margin,
        reason=f"Best score {best.score:.3f} is below the review threshold {review_threshold:.3f}.",
    )
