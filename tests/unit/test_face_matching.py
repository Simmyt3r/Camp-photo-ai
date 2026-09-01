"""Unit tests for the pure matching-decision logic (section 25). These
don't require insightface/onnxruntime/opencv -- they exercise
evaluate_match() and ParticipantIndex directly with synthetic vectors."""
import numpy as np
import pytest

from app.services.face_matching import (
    CandidateScore, MatchDecision, ParticipantIndex, evaluate_match,
)

AUTO = 0.62
REVIEW = 0.45
MARGIN = 0.08


def test_high_score_clear_margin_auto_matches():
    scores = [CandidateScore("P001", 0.90), CandidateScore("P002", 0.50)]
    result = evaluate_match(scores, AUTO, REVIEW, MARGIN)
    assert result.decision == MatchDecision.AUTO_MATCH
    assert result.best.participant_id == "P001"


def test_high_score_but_close_second_place_goes_to_review():
    # Both candidates clear the auto threshold and are nearly tied --
    # exactly the ambiguous case section 8 requires a human to see.
    scores = [CandidateScore("P001", 0.90), CandidateScore("P002", 0.88)]
    result = evaluate_match(scores, AUTO, REVIEW, MARGIN)
    assert result.decision == MatchDecision.REVIEW


def test_mid_score_goes_to_review():
    scores = [CandidateScore("P001", 0.50)]
    result = evaluate_match(scores, AUTO, REVIEW, MARGIN)
    assert result.decision == MatchDecision.REVIEW


def test_low_score_is_unmatched():
    scores = [CandidateScore("P001", 0.20)]
    result = evaluate_match(scores, AUTO, REVIEW, MARGIN)
    assert result.decision == MatchDecision.UNMATCHED


def test_no_candidates_is_unmatched():
    result = evaluate_match([], AUTO, REVIEW, MARGIN)
    assert result.decision == MatchDecision.UNMATCHED
    assert result.best is None


def test_single_candidate_margin_equals_its_own_score():
    scores = [CandidateScore("P001", 0.70)]
    result = evaluate_match(scores, AUTO, REVIEW, MARGIN)
    assert result.decision == MatchDecision.AUTO_MATCH
    assert result.score_margin == pytest.approx(0.70)


def test_reason_is_always_populated():
    for score_set in ([], [CandidateScore("P001", 0.9)], [CandidateScore("P001", 0.1)]):
        result = evaluate_match(score_set, AUTO, REVIEW, MARGIN)
        assert result.reason  # never blank -- section 8: "Record the reason for every match"


class TestParticipantIndex:
    def _unit_vector(self, seed: int, dim: int = 8) -> np.ndarray:
        rng = np.random.default_rng(seed)
        v = rng.normal(size=dim).astype(np.float32)
        return v / np.linalg.norm(v)

    def test_identical_embedding_scores_near_one(self):
        index = ParticipantIndex(strategy="max")
        vec = self._unit_vector(1)
        index.add_participant("P001", vec.reshape(1, -1))
        scores = index.score_all(vec)
        assert scores[0].participant_id == "P001"
        assert scores[0].score == pytest.approx(1.0, abs=1e-5)

    def test_scores_all_participants_sorted_descending(self):
        index = ParticipantIndex(strategy="max")
        for i, pid in enumerate(["P001", "P002", "P003"]):
            index.add_participant(pid, self._unit_vector(i).reshape(1, -1))
        query = self._unit_vector(0)  # matches P001 exactly
        scores = index.score_all(query)
        assert scores[0].participant_id == "P001"
        assert scores[0].score >= scores[1].score >= scores[2].score

    def test_top_k_strategy_uses_best_k_references(self):
        index = ParticipantIndex(strategy="top_k", top_k=2)
        good = self._unit_vector(1)
        # Two references close to `good`, one deliberately dissimilar --
        # top_k=2 should ignore the bad one, unlike a plain mean.
        bad = -good
        refs = np.stack([good, good * 0.99 + 0.01, bad])
        refs = refs / np.linalg.norm(refs, axis=1, keepdims=True)
        index.add_participant("P001", refs)
        score_top_k = index.score_all(good)[0].score

        index_mean = ParticipantIndex(strategy="mean")
        index_mean.add_participant("P001", refs)
        score_mean = index_mean.score_all(good)[0].score

        assert score_top_k > score_mean

    def test_rejects_empty_embeddings(self):
        index = ParticipantIndex()
        with pytest.raises(ValueError):
            index.add_participant("P001", np.zeros((0, 8), dtype=np.float32))

    def test_mixed_reference_counts_uses_ragged_fallback_correctly(self):
        """Registered participants don't all have the same number of
        reference photos in practice. This specifically exercises
        _score_all_ragged() (uniform counts -- even trivially, with a
        single participant -- always take the _score_all_uniform() fast
        path instead, so a dedicated mixed-count case is the only way to
        cover the fallback). Uses "max" strategy so an exact-match
        reference determines the outcome regardless of how many other,
        unrelated references that participant also has."""
        index = ParticipantIndex(strategy="max")
        p001_refs = np.stack([self._unit_vector(i) for i in range(3)])   # 3 references
        p002_refs = np.stack([self._unit_vector(i) for i in range(10, 15)])  # 5 references
        p003_refs = self._unit_vector(20).reshape(1, -1)                 # 1 reference
        index.add_participant("P001", p001_refs)
        index.add_participant("P002", p002_refs)
        index.add_participant("P003", p003_refs)

        query = self._unit_vector(0)  # matches P001's first reference exactly
        scores = index.score_all(query)

        assert len(scores) == 3
        assert scores[0].participant_id == "P001"
        assert scores[0].score == pytest.approx(1.0, abs=1e-4)

    @pytest.mark.parametrize("strategy", ["max", "mean", "centroid", "top_k"])
    def test_uniform_and_ragged_paths_agree_for_every_strategy(self, strategy):
        """The vectorized uniform-count fast path and the per-participant
        ragged fallback must produce identical scores for the same data
        -- this pins that equivalence for all four strategies, not just
        top_k, by forcing the SAME two participants through both paths:
        once alone (ragged has nothing to compare against, but adding a
        third participant with a different count forces the ragged path
        deliberately)."""
        p001_refs = np.stack([self._unit_vector(i) for i in range(3)])
        p002_refs = np.stack([self._unit_vector(i) for i in range(10, 13)])
        query = self._unit_vector(1)

        uniform_index = ParticipantIndex(strategy=strategy, top_k=2)
        uniform_index.add_participant("P001", p001_refs)
        uniform_index.add_participant("P002", p002_refs)
        uniform_scores = {c.participant_id: c.score for c in uniform_index.score_all(query)}

        ragged_index = ParticipantIndex(strategy=strategy, top_k=2)
        ragged_index.add_participant("P001", p001_refs)
        ragged_index.add_participant("P002", p002_refs)
        ragged_index.add_participant("P003", self._unit_vector(99).reshape(1, -1))  # forces the ragged path
        ragged_scores = {c.participant_id: c.score for c in ragged_index.score_all(query)}

        assert uniform_scores["P001"] == pytest.approx(ragged_scores["P001"], abs=1e-5)
        assert uniform_scores["P002"] == pytest.approx(ragged_scores["P002"], abs=1e-5)
