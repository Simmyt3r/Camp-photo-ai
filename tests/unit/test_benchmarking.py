"""Unit tests for the benchmarking framework (sections 23-24). Timing
values are inherently non-deterministic, so these don't assert on actual
speed -- they verify the summarization math, the extrapolation
semantics, and that benchmark_matching/benchmark_database produce
correctly-shaped results at small (fast, portable) scale, using the real
production ParticipantIndex/database code paths."""
import pytest

from app.services.benchmarking import (
    BenchmarkResult, _summarize, benchmark_database, benchmark_matching,
    extrapolate_linear, format_benchmark_table,
)


class TestSummarize:
    def test_percentiles_on_known_values(self):
        # 1..100 ms: p50=50.5 (numpy's linear interpolation), mean=50.5
        timings = [float(i) for i in range(1, 101)]
        r = _summarize("test", n=10, timings_ms=timings)
        assert r.iterations == 100
        assert r.mean_ms == pytest.approx(50.5)
        assert r.p50_ms == pytest.approx(50.5)
        assert r.p99_ms > r.p95_ms > r.p50_ms

    def test_single_value(self):
        r = _summarize("test", n=1, timings_ms=[42.0])
        assert r.mean_ms == r.p50_ms == r.p95_ms == r.p99_ms == 42.0

    def test_carries_peak_rss_and_extra(self):
        r = _summarize("test", n=5, timings_ms=[1.0, 2.0], peak_rss_mb=123.4, extra={"foo": "bar"})
        assert r.peak_rss_mb == 123.4
        assert r.extra == {"foo": "bar"}
        assert r.extrapolated is False


class TestExtrapolateLinear:
    def test_per_item_stats_are_unchanged(self):
        base = BenchmarkResult(
            name="pipeline", n=50, iterations=50, mean_ms=200.0, p50_ms=190.0, p95_ms=250.0, p99_ms=300.0,
            extra={"images_per_sec": 5.0},
        )
        projected = extrapolate_linear(base, target_n=1000)
        # A rate/per-item cost doesn't change just because more items
        # will eventually be processed -- these must carry over exactly.
        assert projected.mean_ms == base.mean_ms
        assert projected.p95_ms == base.p95_ms
        assert projected.extra["images_per_sec"] == 5.0

    def test_adds_estimated_total_time_at_target_n(self):
        base = BenchmarkResult(name="pipeline", n=50, iterations=50, mean_ms=200.0, p50_ms=200.0, p95_ms=200.0, p99_ms=200.0)
        projected = extrapolate_linear(base, target_n=1000)
        # 1000 items * 200ms each = 200 seconds
        assert projected.extra["estimated_total_seconds_at_n"] == pytest.approx(200.0)

    def test_marks_result_as_extrapolated_with_target_n(self):
        base = BenchmarkResult(name="pipeline", n=50, iterations=50, mean_ms=1.0, p50_ms=1.0, p95_ms=1.0, p99_ms=1.0)
        projected = extrapolate_linear(base, target_n=1000)
        assert projected.extrapolated is True
        assert projected.n == 1000
        assert projected.iterations == 0  # nothing was actually run at this n

    def test_does_not_mutate_the_base_result(self):
        base = BenchmarkResult(name="pipeline", n=50, iterations=50, mean_ms=1.0, p50_ms=1.0, p95_ms=1.0, p99_ms=1.0, extra={"a": 1})
        extrapolate_linear(base, target_n=1000)
        assert base.extrapolated is False
        assert base.extra == {"a": 1}


class TestBenchmarkMatchingStructure:
    def test_one_result_per_participant_count(self):
        results = benchmark_matching(participant_counts=[10, 50], queries=5)
        assert [r.n for r in results] == [10, 50]
        assert all(r.name == "matching" for r in results)

    def test_iterations_matches_query_count(self):
        results = benchmark_matching(participant_counts=[10], queries=7)
        assert results[0].iterations == 7

    def test_reports_peak_rss_and_a_rate(self):
        results = benchmark_matching(participant_counts=[20], queries=5)
        assert results[0].peak_rss_mb is not None and results[0].peak_rss_mb > 0
        assert "queries_per_sec" in results[0].extra


class TestBenchmarkDatabaseStructure:
    def test_returns_insert_and_query_results_per_row_count(self, tmp_path):
        db_path = tmp_path / "bench.db"
        results = benchmark_database(row_counts=[5], db_path=db_path)
        names = {r.name for r in results}
        assert names == {"database_insert", "database_query_all_participants"}
        assert all(r.n == 5 for r in results)

    def test_cleans_up_the_database_file(self, tmp_path):
        db_path = tmp_path / "bench.db"
        benchmark_database(row_counts=[3], db_path=db_path)
        assert not db_path.exists()

    def test_insert_result_reports_rows_per_sec(self, tmp_path):
        db_path = tmp_path / "bench.db"
        results = benchmark_database(row_counts=[5], db_path=db_path)
        insert_result = next(r for r in results if r.name == "database_insert")
        assert "rows_per_sec" in insert_result.extra
        assert insert_result.extra["rows_per_sec"] > 0


class TestFormatBenchmarkTable:
    def test_marks_extrapolated_rows(self):
        real = BenchmarkResult(name="pipeline", n=50, iterations=50, mean_ms=1.0, p50_ms=1.0, p95_ms=1.0, p99_ms=1.0)
        projected = extrapolate_linear(real, target_n=1000)
        table = format_benchmark_table([real, projected])
        lines = table.splitlines()
        real_line = next(l for l in lines if " 50 |" in l)
        projected_line = next(l for l in lines if "1,000 |" in l)
        assert "EXTRAPOLATED" not in real_line
        assert "EXTRAPOLATED" in projected_line
