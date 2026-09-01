# Performance & load testing

Sections 23-24: images/sec, faces/sec, latency, peak RAM, startup time,
and DB query time at scale, using `pytest-benchmark` (already in
requirements.txt).

**Implemented** in `app/services/benchmarking.py`, wired up as
`python -m app.cli benchmark --target {matching,database,pipeline,all}`.
See `docs/PERFORMANCE.md` for the full methodology, real measured
numbers, and two real performance bugs this found and fixed (a
non-vectorized matching reduction step, and an N+1 database query
pattern -- 38.8x faster after the fix).

- `test_matching_benchmarks.py` / `test_database_benchmarks.py`: real
  `pytest-benchmark` micro-benchmarks against the production
  `ParticipantIndex`/database code paths, at spec-target scale
  (1k/10k participants; 1k/10k/50k rows). Run directly:
  `pytest tests/performance --benchmark-only -v`
- Pure logic (summarization math, extrapolation, result structure) is
  covered by `tests/unit/test_benchmarking.py` -- fast and portable,
  no timing dependency, part of the standard `pytest tests/unit` run.

**Not done here**: GPU benchmarking (no GPU has been available in any
session so far -- see docs/PERFORMANCE.md's closing section), and
multiprocessing for the pipeline stage, which the numbers say would
help the most but which needs multi-core hardware to actually validate
rather than ship blind.
