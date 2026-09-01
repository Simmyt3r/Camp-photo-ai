"""Unit tests for the accuracy evaluation / threshold calibration engine
(sections 21-22). Uses hand-constructed 2D unit vectors with exactly
computable cosine similarities -- not random high-dimensional vectors --
so every expected classification (TP/FP/FN/TN/review-*) is deterministic
and verifiable by hand, not just "probably far enough apart"."""
import numpy as np
import pytest

from app.services.evaluation import (
    GalleryEntry, ProbeResult, ThresholdMetrics, evaluate_at_threshold,
    format_sweep_table, recognition_accuracy, recommend_threshold, sweep_thresholds,
)

AUTO = 0.62
REVIEW = 0.45
MARGIN = 0.08

# P001 points along x, P002 points along y -- exactly orthogonal (cosine 0).
GALLERY = [
    GalleryEntry("P001", np.array([[1.0, 0.0]])),
    GalleryEntry("P002", np.array([[0.0, 1.0]])),
]

# normalize([1, 0.95]): score vs P001 ~= 0.725 (clears AUTO), margin vs
# P002 ~= 0.036 (below MARGIN) -> REVIEW, with P001 as the (correct, for
# a P001 probe) top candidate.
_V = np.array([1.0, 0.95])
CONFUSABLE = _V / np.linalg.norm(_V)


def _metrics(probes, **overrides):
    kwargs = dict(auto_match_threshold=AUTO, review_threshold=REVIEW, minimum_score_margin=MARGIN)
    kwargs.update(overrides)
    return evaluate_at_threshold(GALLERY, probes, **kwargs)


class TestEvaluateAtThresholdClassification:
    def test_exact_match_is_true_positive(self):
        probes = [ProbeResult("P001", "p1.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        m = _metrics(probes)
        assert (m.true_positives, m.false_positives) == (1, 0)

    def test_auto_matched_to_wrong_identity_is_false_positive(self):
        # Labelled P002, but the embedding is P001's exact reference vector.
        probes = [ProbeResult("P002", "p2.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        m = _metrics(probes)
        assert (m.true_positives, m.false_positives) == (0, 1)

    def test_low_score_known_identity_is_false_negative(self):
        probes = [ProbeResult("P001", "p1.jpg", np.array([0.0, -1.0]), is_impostor=False)]
        m = _metrics(probes)
        assert m.false_negatives == 1
        assert (m.true_positives, m.false_positives) == (0, 0)

    def test_low_score_impostor_is_true_negative(self):
        probes = [ProbeResult("_unknown", "x.jpg", np.array([0.0, -1.0]), is_impostor=True)]
        m = _metrics(probes)
        assert m.true_negatives == 1

    def test_impostor_auto_matched_is_false_positive(self):
        probes = [ProbeResult("_unknown", "x.jpg", np.array([1.0, 0.0]), is_impostor=True)]
        m = _metrics(probes)
        assert m.false_positives == 1

    def test_confusable_known_probe_with_correct_top_candidate_goes_to_review(self):
        probes = [ProbeResult("P001", "p1.jpg", CONFUSABLE, is_impostor=False)]
        m = _metrics(probes)
        assert (m.review_correct_candidate, m.review_wrong_candidate) == (1, 0)
        assert (m.true_positives, m.false_positives, m.false_negatives) == (0, 0, 0)

    def test_confusable_known_probe_with_wrong_top_candidate_goes_to_review(self):
        # Labelled P002, but scores closer to P001 -- "similar-looking
        # individuals" per section 21.
        probes = [ProbeResult("P002", "p2.jpg", CONFUSABLE, is_impostor=False)]
        m = _metrics(probes)
        assert (m.review_correct_candidate, m.review_wrong_candidate) == (0, 1)

    def test_confusable_impostor_goes_to_review_impostor(self):
        probes = [ProbeResult("_unknown", "x.jpg", CONFUSABLE, is_impostor=True)]
        m = _metrics(probes)
        assert m.review_impostor == 1
        assert m.false_positives == 0

    def test_mixed_probe_set_aggregates_all_counters(self):
        probes = [
            ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False),   # TP
            ProbeResult("P002", "b.jpg", np.array([1.0, 0.0]), is_impostor=False),   # FP (wrong id)
            ProbeResult("P001", "c.jpg", np.array([0.0, -1.0]), is_impostor=False),  # FN
            ProbeResult("_unknown", "d.jpg", np.array([0.0, -1.0]), is_impostor=True),  # TN
            ProbeResult("P001", "e.jpg", CONFUSABLE, is_impostor=False),  # review, correct
        ]
        m = _metrics(probes)
        assert m.true_positives == 1
        assert m.false_positives == 1
        assert m.false_negatives == 1
        assert m.true_negatives == 1
        assert m.review_correct_candidate == 1
        assert m.review_queue_size == 1

    def test_empty_gallery_means_every_known_probe_is_a_false_negative(self):
        m = evaluate_at_threshold(
            [], [ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False)],
            auto_match_threshold=AUTO, review_threshold=REVIEW, minimum_score_margin=MARGIN,
        )
        assert m.false_negatives == 1


class TestThresholdMetricsMath:
    def test_precision_recall_f1(self):
        m = ThresholdMetrics(0.6, 0.45, 0.08, "top_k", true_positives=8, false_positives=2, false_negatives=2)
        assert m.precision == pytest.approx(0.8)   # 8 / (8+2)
        assert m.recall == pytest.approx(0.8)       # 8 / (8+2)
        assert m.f1 == pytest.approx(0.8)

    def test_far_and_frr(self):
        m = ThresholdMetrics(
            0.6, 0.45, 0.08, "top_k",
            true_positives=9, false_positives=1, false_negatives=3, true_negatives=17,
        )
        assert m.false_accept_rate == pytest.approx(1 / 18)   # FP / (FP + TN)
        assert m.false_reject_rate == pytest.approx(3 / 12)   # FN / (FN + TP)

    def test_zero_denominators_return_zero_not_error(self):
        m = ThresholdMetrics(0.6, 0.45, 0.08, "top_k")
        assert m.precision == 0.0
        assert m.recall == 0.0
        assert m.f1 == 0.0
        assert m.false_accept_rate == 0.0
        assert m.false_reject_rate == 0.0

    def test_recall_if_review_always_correct_is_an_upper_bound(self):
        m = ThresholdMetrics(
            0.6, 0.45, 0.08, "top_k",
            true_positives=5, false_negatives=3, review_correct_candidate=2, review_wrong_candidate=1,
        )
        strict_recall = m.recall  # 5 / (5+3) = 0.625
        optimistic = m.recall_if_review_always_correct  # (5+2) / (5+2+3+1) = 7/11
        assert optimistic > strict_recall
        assert optimistic == pytest.approx(7 / 11)


class TestRecognitionAccuracy:
    def test_top1_hit_and_miss(self):
        probes = [
            ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False),  # top-1 hit
            ProbeResult("P002", "b.jpg", np.array([1.0, 0.0]), is_impostor=False),  # top-1 miss (P001 wins)
        ]
        acc = recognition_accuracy(GALLERY, probes, top_n_values=(1,))
        assert acc[1] == pytest.approx(0.5)

    def test_ignores_impostor_probes(self):
        probes = [ProbeResult("_unknown", "x.jpg", np.array([1.0, 0.0]), is_impostor=True)]
        acc = recognition_accuracy(GALLERY, probes, top_n_values=(1,))
        assert acc[1] == 0.0  # no known probes at all -- not "0% accurate", just none to score; see docstring caveat

    def test_top5_saturates_with_fewer_than_5_identities(self):
        probes = [ProbeResult("P002", "b.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        acc = recognition_accuracy(GALLERY, probes, top_n_values=(1, 5))
        assert acc[1] == 0.0    # P001 outranks P002 for this probe
        assert acc[5] == 1.0    # but P002 is trivially "in the top 5" of only 2 identities


class TestSweepThresholds:
    def test_produces_one_result_per_grid_value(self):
        probes = [ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        results = sweep_thresholds(GALLERY, probes, threshold_grid=(0.5, 0.6, 0.7))
        assert [r.auto_match_threshold for r in results] == [0.5, 0.6, 0.7]

    def test_review_threshold_derived_from_gap(self):
        probes = [ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        results = sweep_thresholds(GALLERY, probes, threshold_grid=(0.6,), review_gap=0.2)
        assert results[0].review_threshold == pytest.approx(0.4)

    def test_review_threshold_never_goes_negative(self):
        probes = [ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        results = sweep_thresholds(GALLERY, probes, threshold_grid=(0.1,), review_gap=0.5)
        assert results[0].review_threshold == 0.0


class TestRecommendThreshold:
    def test_picks_highest_recall_among_candidates_clearing_min_precision(self):
        low_recall_high_precision = ThresholdMetrics(0.75, 0.6, 0.08, "top_k", true_positives=5, false_positives=0, false_negatives=5)
        high_recall_ok_precision = ThresholdMetrics(0.55, 0.4, 0.08, "top_k", true_positives=9, false_positives=0, false_negatives=1)
        too_risky = ThresholdMetrics(0.5, 0.35, 0.08, "top_k", true_positives=10, false_positives=3, false_negatives=0)

        result = recommend_threshold(
            [low_recall_high_precision, high_recall_ok_precision, too_risky], min_precision=0.98
        )
        assert result is high_recall_ok_precision

    def test_returns_none_if_nothing_clears_min_precision(self):
        risky = ThresholdMetrics(0.5, 0.35, 0.08, "top_k", true_positives=5, false_positives=5, false_negatives=0)
        assert recommend_threshold([risky], min_precision=0.98) is None


class TestFormatSweepTable:
    def test_contains_a_row_per_result(self):
        probes = [ProbeResult("P001", "a.jpg", np.array([1.0, 0.0]), is_impostor=False)]
        results = sweep_thresholds(GALLERY, probes, threshold_grid=(0.5, 0.6))
        table = format_sweep_table(results)
        assert "0.50" in table
        assert "0.60" in table
        assert "Precision" in table and "Recall" in table
