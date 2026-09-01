# Testing

## Quick start

```bash
pip install -r requirements.txt
pytest tests/unit -v
```

105 tests, all passing, no GPU or model weights required, typically
under 15 seconds.

## Test organization

| Directory | What it covers | Needs real data/GPU? |
|---|---|---|
| `tests/unit/` | Pure logic: matching decisions, file safety, duplicate detection, database cascades + auto-migration, review workflow, participant search/edit/export, evaluation/benchmarking classification and math | No -- synthetic vectors, tiny generated images, in-memory SQLite |
| `tests/performance/` | Real `pytest-benchmark` micro-benchmarks of the production `ParticipantIndex`/database code paths at spec-target scale | No (synthetic embeddings/rows) -- but takes real wall-clock time, so kept separate from the default `pytest tests/unit` run |
| `tests/accuracy/` | Scoped, not implemented -- see `tests/accuracy/README.md` | Would need a real, consented dataset |
| `tests/integration/` | Scoped, not implemented -- see `tests/integration/README.md` | Would need `insightface`/`onnxruntime` + real images |
| `tests/security/` | Scoped, not implemented -- see `tests/security/README.md`; the path-traversal and SQL-injection cases that exist today live in `tests/unit/` instead (`test_file_utils.py::TestSafeOutputPath`/`TestEnsureWithinRoot`, and the injection-string tests in `test_participant_management.py`) since they're fast, deterministic, and don't need a dedicated slow-test category |

## Running specific things

```bash
# Everything in tests/unit, verbose
pytest tests/unit -v

# One file
pytest tests/unit/test_face_matching.py -v

# One test
pytest tests/unit/test_face_matching.py::test_high_score_clear_margin_auto_matches -v

# Real performance numbers (takes longer -- see docs/PERFORMANCE.md)
pytest tests/performance --benchmark-only -v

# Everything pytest can find (tests/unit + tests/performance, since
# pyproject.toml's testpaths includes all of tests/) -- fine, just
# slower than tests/unit alone
pytest
```

## What's deliberately NOT covered by automated tests

- **Real face detection/embedding accuracy.** `tests/unit/` tests the
  *decision logic* (given some similarity scores, is the classification
  correct?) with synthetic vectors, not whether InsightFace's actual
  model is accurate on real faces. That's what `docs/ACCURACY.md`'s
  `evaluate` command is for, against your own dataset.
- **Real hardware performance.** Same split -- `tests/performance/`
  proves the *code path* is efficient (no accidental O(n²), no N+1
  queries), not what your specific deployment machine will actually
  achieve. `docs/PERFORMANCE.md` has real numbers, clearly scoped to
  the single-CPU-core, no-GPU environment they were measured on.
- **The GUI's visual appearance.** Smoke-tested by actually
  instantiating every page headless (`QT_QPA_PLATFORM=offscreen`) and
  driving real interactions against them during development (search,
  edit-and-save, settings persistence, etc. -- see `docs/DEVELOPER_
  GUIDE.md`), but there's no automated visual regression suite. A
  layout or stylesheet change could look wrong without any test
  failing.
- **Windows-specific behavior**, since every test in this repository
  runs on whatever OS `pytest` is invoked on, and every development
  session for this project has been on Linux. See `docs/DEVELOPER_
  GUIDE.md`'s closing section.

## Continuous integration

`.github/workflows/tests.yml` runs `pytest tests/unit` on every push
and pull request against `main`, on Ubuntu with Python 3.11 and 3.12.
It does not install `insightface`/`onnxruntime`/`PySide6` (heavy, and
`tests/unit/` doesn't need them by design -- see the table above), so
CI stays fast. If you add a test that needs those, it belongs in
`tests/performance/`, `tests/accuracy/`, or `tests/integration/`
instead of `tests/unit/`, specifically so CI doesn't silently get
slower and heavier over time.

## Writing new tests

- Keep `tests/unit/` fast and dependency-light -- if a test needs
  `insightface` or takes more than a fraction of a second, it doesn't
  belong there. Use synthetic embeddings (see `tests/unit/
  test_face_matching.py`'s hand-computed 2D vectors, or `tests/unit/
  test_evaluation.py`'s deterministic scenarios) rather than real model
  inference wherever the thing under test is decision logic, not the
  model itself.
- Prefer hand-computable expected values over "probably works" when
  testing anything numeric -- several bugs in this codebase were caught
  specifically because a test asserted an exact expected value (derived
  by hand, then double-checked by actually running the scenario) rather
  than a loose "score should be reasonably high."
- When fixing a bug found through manual/real-world testing (not just
  writing a new feature), add a regression test for it in the same
  change -- every bug fix mentioned in `docs/PERFORMANCE.md` and
  `docs/DEVELOPER_GUIDE.md` has one.
