# Developer Guide

## Architecture

Layered, with a strict dependency direction -- each layer only depends
on the ones below it, never sideways or up:

```
app/cli.py, app/main.py, app/ui/*        <- entry points (CLI, GUI)
        |
app/bootstrap.py (AppContext)             <- shared setup, no UI dependency
        |
app/workers/batch_processor.py            <- orchestration (the pipeline)
        |
app/services/*                            <- business logic, one concern per file
        |
app/database/*, app/utilities/*           <- persistence, cross-cutting helpers
        |
app/config/settings.py                    <- configuration, no dependencies
```

`app/services/face_matching.py` is deliberately the most isolated
module -- no database, no filesystem, no `insightface` import -- so the
core matching decision logic is unit-testable with plain numpy arrays
and reusable by both the live pipeline and `app/services/evaluation.py`
without either depending on the other.

`app/bootstrap.py` (`AppContext.bootstrap()`) exists specifically so
`app/cli.py` and `app/main.py` share one implementation of "load
settings, detect hardware, resolve a processing provider, build an
embedding service" -- it has zero PySide6 dependency, so CLI-only usage
never requires the GUI toolkit to be importable.

## Key design decisions

- **Privacy by construction, not by policy.** There's no code path that
  uploads a photo or embedding anywhere (`docs/PRIVACY.md`). Deletion
  cascades via `ON DELETE CASCADE` foreign keys in one transaction, not
  application-level cleanup that could partially fail. Raw embeddings
  are filtered out of every log line by a regex safety net
  (`app/utilities/logging_config.py::RedactBiometricFilter`), not just
  a "don't log this" convention.
- **Precision over recall for automatic decisions** (spec section 8).
  `evaluate_match()` in `app/services/face_matching.py` requires both a
  high absolute score AND a healthy margin over the runner-up before
  auto-matching -- a close second place always goes to human review.
- **Benchmark before optimizing, and prove it after.** Multiprocessing
  for the pipeline stage was deliberately *not* added despite being
  the highest-leverage remaining optimization (see
  `docs/PERFORMANCE.md`), because this development environment has one
  CPU core and no way to validate a multiprocessing speedup. Two other
  optimizations *were* made, but only after profiling proved where the
  real cost was (not where it was assumed to be) and were validated
  with before/after benchmarks plus regression tests confirming
  identical output.
- **Real verification over inspection.** Every phase of this build was
  checked by actually running it -- installing the real ML dependencies
  and running real inference, building and launching real (if
  Linux-only) frozen executables, driving GUI widgets with real data --
  not just reading the code and asserting it should work. This caught
  real bugs (an N+1 database query, a non-vectorized matching reduction
  step, a broken path computation under PyInstaller) that code review
  alone did not.

## Project layout

| Path | What's there |
|---|---|
| `app/config/settings.py` | The `Settings` dataclass -- every configurable value, loaded from `data/settings.json` |
| `app/database/models.py` | SQLAlchemy models: `Participant`, `ReferenceEmbedding`, `ProcessingCache`, `MatchRecord`, `ProcessingRun` |
| `app/database/db.py` | Engine/session management, FK enforcement, the additive-only auto-migration |
| `app/services/face_detection.py` | Registration-time face validation (reject 0 or 2+ faces) |
| `app/services/face_embedding.py` | Embedding generation + the four multi-reference matching strategies |
| `app/services/face_matching.py` | `ParticipantIndex` + `evaluate_match()` -- the core decision engine |
| `app/services/image_processing.py` | Safe image loading, EXIF correction, thumbnail encoding |
| `app/services/photo_sorting.py` | Copies matched photos into participant folders |
| `app/services/duplicate_detection.py` | Exact (SHA-256) + near-duplicate (perceptual hash) |
| `app/services/review_service.py` | Confirm/reject/reassign/delete |
| `app/services/participant_management.py` | Search, metadata edit, matched-photo count, export |
| `app/services/reporting.py` | `ProcessingReport`, `build_report()`, dashboard stats |
| `app/services/evaluation.py` | Accuracy evaluation + threshold calibration |
| `app/services/benchmarking.py` | Performance/load testing |
| `app/workers/batch_processor.py` | `run_batch()` -- the pipeline orchestrator, GUI-agnostic |
| `app/ui/` | PySide6 GUI: `main_window.py` + one file per screen + `workers.py` (QThread wrappers) + `styles.py` |
| `app/cli.py` | Click-based CLI, one command per spec section 34 entry |

## How to add things

**A new CLI command**: add a `@cli.command()` function in `app/cli.py`
that calls `_bootstrap()` for an `AppContext`, then delegates to a
service function -- don't put business logic directly in the command
body (see `evaluate`/`benchmark` for the pattern: parse options, call
into `app/services/`, format output).

**A new GUI screen**: create `app/ui/<name>_page.py` with a
`QWidget` subclass taking `context: AppContext` in its constructor, an
optional `on_shown()` method (called every time `MainWindow.navigate()`
switches to it -- use it to refresh data), then wire it into
`MainWindow._pages` and `NAV_ITEMS` in `app/ui/main_window.py`. Pages
call service functions directly via `get_session()` -- never put
pipeline logic in a page; if it does real work (face detection,
`run_batch()`), wrap it in a `QThread` in `app/ui/workers.py` so the UI
thread never blocks (see `ProcessingWorker`/`RegistrationWorker`).

**A new matching strategy**: add a `strategy_<name>()` function to
`app/services/face_embedding.py` and register it in `MATCH_STRATEGIES`.
If it needs a per-participant precomputed representative vector (like
`centroid` does, rather than raw per-reference embeddings), extend
`ParticipantIndex._representative_rows()` in `face_matching.py` --
see that method's docstring for why `centroid` is handled specially
(it doesn't depend on the query, so precomputing it once is exactly
equivalent to recomputing it every call, just far cheaper).

**A new database field**: add it as `nullable=True` (or with a
Python-side `default=`) wherever possible -- the auto-migration in
`app/database/db.py::_auto_migrate_add_missing_columns()` can add
nullable/defaulted columns to an existing database automatically, but
skips (and logs a warning for) anything `NOT NULL` with no default,
since there's no safe value to backfill existing rows with.

## Testing philosophy

See `docs/TESTING.md` for how to run things. In short: `tests/unit/` is
fast, portable, and needs no GPU/model weights/dataset -- pure logic
tested with synthetic data (hand-computed vectors where exactness
matters, like the matching engine's TP/FP/FN/TN classification).
`tests/performance/` and `tests/accuracy/` need real data or take
real time, so they're separate from the default `pytest tests/unit`
command, not skipped by an ignore rule.

## A note on scope and what's genuinely unverified

This codebase has been checked more thoroughly than "written once and
assumed correct" -- but three categories of things have never been
validated on real hardware in any development session, and are called
out explicitly wherever they're relevant rather than glossed over:

1. **GPU acceleration** -- implemented, never measured.
2. **The live webcam capture path** -- correct by code review and the
   standard OpenCV/Qt pattern, never exercised against a real camera.
3. **Windows-specific behavior** -- the PyInstaller build was validated
   by actually building and running it, but only on Linux; anything
   genuinely Windows-specific (path separators aside, which `pathlib`
   already handles) hasn't been exercised.

If you hit something in one of these three areas, that's the most
likely place to look first.
