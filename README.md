# CampPhoto AI

AI-assisted camp photography management and automated face-based photo
sorting, for photographers working NYSC camps, schools, conferences,
churches, and other large events with hundreds or thousands of photos and
many different people in them.

Participants register (with consent) and provide a few reference photos.
The app then scans a folder of event photos, finds every face in every
photo, and copies matching photos into each participant's own folder --
so nobody has to scroll through 5,000 photos by hand to find "the ones
with me in them."

**Status: All 6 planned build phases done** -- core engine + CLI (1),
GUI first four screens (2), accuracy evaluation (3), performance testing
(4) -- which found and fixed two real bugs along the way (5.5x-11.5x
faster matching, 38.8x faster database access) -- GUI completion (5),
and docs + Windows packaging (6, this update) -- which found and fixed
a real bug of its own (see "What's built" below). This covers the large
majority of the original spec, but "done" doesn't mean the entire
36-section spec is finished: a few smaller items were never part of any
phase and remain genuinely unbuilt -- an integration test suite, a
synthetic test-data generator, and a model-migration workflow for when
the embedding model changes (sections 26, 31, 32). See "What's next"
for these plus everything else still open.

## Privacy, up front

This app handles biometric data, so a few things are true by design, not
by configuration:

- Everything runs locally. There is no code path in this build that
  sends a photo or an embedding anywhere over the network.
- A participant's reference embeddings (and, as of this phase, their
  small display thumbnail) are deleted, in full, the moment the
  participant is deleted, via cascading foreign keys.
- Raw embedding vectors are never written to any log file, enforced by a
  filter (`app/utilities/logging_config.py`), not just a coding
  convention.

Read `docs/PRIVACY.md` and `docs/SECURITY.md` for the full picture,
including what's *not* yet hardened (e.g. the SQLite file itself isn't
encrypted at rest), and what this phase added to what's collected (a
per-reference-photo thumbnail, so the review screen can show who a
suggested participant is).

## What's built

**Phase 1 -- core engine + CLI:**

- **Core pipeline**: file discovery -> validation/EXIF correction -> face
  detection+embedding (InsightFace) -> vectorized matching against every
  registered participant -> confidence-based decision -> copy to output
  -> cache + audit log. One bad photo never stops the batch.
- **False-positive protection**: auto-match requires both a high
  absolute score *and* a healthy margin over the next-best candidate
  (`app/services/face_matching.py`) -- a close second place always goes
  to human review instead of guessing. Verified against a real photo
  with 6 distinct faces, not just synthetic vectors: a face matched
  against itself scores 1.0000, the other 5 real (different) people in
  the same photo score between -0.08 and 0.06 -- see "Verification" below.
- **Multi-reference matching strategies**: max / mean / centroid / top-k
  similarity across a participant's 3-5 reference photos (`top-k` is the
  default -- see the docstrings in `face_embedding.py` for why).
- **Multi-face photos**: a photo with 3 registered people in it gets
  copied into all 3 participant folders; originals are never moved.
- **Resumable, cached batches**: unchanged files (by hash) are skipped on
  a re-run. A lightweight auto-migration in `app/database/db.py` adds new
  nullable columns to an existing `data/camp_photo_ai.db` automatically
  (e.g. the bbox/thumbnail columns this phase added) instead of breaking.
- **Duplicate detection**: exact (SHA-256) and near-duplicate (perceptual
  hash) with configurable skip/keep/rename behavior.
- **Human review backend**: every uncertain match is recorded with its
  score, runner-up, margin, and (as of this phase) the detected face's
  bounding box; confirm/reject/reassign actually copy the photo once
  confirmed.
- **Hardware detection**: picks GPU (CUDA/TensorRT/DirectML) automatically
  via ONNX Runtime's available providers, falls back to CPU.
- **CLI**: `register`, `process`, `review-queue`, `review-confirm`,
  `review-reject`, `rebuild-cache`, `report`. `evaluate` was stubbed here
  and became real in Phase 3 (below); `benchmark` is still stubbed
  pending a later phase.

**Phase 2 -- PySide6 desktop GUI:**

- **Dashboard**: live counts (participants, photos processed, faces
  detected, auto-matched, needs review, unmatched), computed straight
  from the database (`app/services/reporting.py::compute_dashboard_stats`).
  Participants/Reports/Settings are shown but disabled with a tooltip --
  not built yet, use the CLI equivalents for now.
- **Registration screen**: form + photo import + optional webcam capture
  (gracefully degrades to "no camera found" if none is available), with
  per-photo accept/reject feedback (no face / multiple faces) before
  anything is written to the database. Embedding generation runs on a
  background `QThread` so the UI never freezes during model load.
- **Processing screen**: input/output folder pickers, a Start button, and
  a live progress bar + stats line driven by `run_batch()` on a
  background `QThread` -- the UI thread is never blocked, matching spec
  section 18.
- **Review screen**: the pending-review queue on the left; selecting an
  item shows the full photo, a cropped detected-face thumbnail (from the
  newly-stored bounding box), the suggested participant's reference
  thumbnail, the score/margin/reason, and Confirm / Reject / Reassign
  actions that call straight into the same `review_service.py` the CLI
  uses.
- No pipeline logic lives in `app/ui/` -- every page calls into the
  existing backend services; the GUI's only job is threading and display.

**Phase 3 -- accuracy evaluation + threshold calibration:**

- **`python -m app.cli evaluate --dataset <path>`** (`app/services/evaluation.py`):
  point it at a directory of `person_id/photo.jpg` folders (plus an
  optional `_unknown/` folder of people who should never match) and it
  reports:
  - **Recognition accuracy** (top-1/top-5) -- threshold-independent: is
    the right identity even the top-scoring candidate at all?
  - **A threshold sweep** -- precision/recall/F1/FAR/FRR/review-queue
    size at each auto-match threshold in a grid (matching spec section
    22's example table), written as both a text table and a graph
    (`threshold_sweep.txt` / `.png`).
  - **A suggested starting threshold** -- highest recall among those
    clearing a minimum precision bar, explicitly labelled as a
    dataset-specific starting point, not a universal answer (section 22).
- Embeddings are computed once per photo and reused across the entire
  threshold sweep -- re-running face detection per grid point would be
  wasted, expensive work.
- See `docs/ACCURACY.md` for the dataset format and a known limitation
  found while verifying this (below): the face *detector* found zero
  faces in masked/occluded test photos, so heavy occlusion currently
  shows up as reduced recall (undetected), not as review-queue volume.

**Phase 4 -- performance & load testing:**

- **`python -m app.cli benchmark --target {matching,database,pipeline,all}`**
  (`app/services/benchmarking.py`): matching and database benchmarks are
  fully synthetic and safe at any scale (achieved 1k/10k/50k directly);
  pipeline uses real photos and real inference since there's no
  synthetic substitute for actual throughput.
- **Found and fixed two real performance bugs**, both with regression
  tests so they can't come back silently:
  - `ParticipantIndex.score_all()` had a Python-level reduction step
    (`np.mean`/`np.partition` called once per participant) that
    dominated its cost far more than the matmul itself did. Now
    vectorized across all participants at once when they share a
    reference-photo count. **5.5x-11.5x faster.**
  - `_build_participant_index()` (runs at the start of every batch) had
    an N+1 query pattern -- one SQL query per participant to lazy-load
    their embeddings. Fixed with `selectinload`. **38.8x faster** at
    5,000 participants (19.7s -> 0.5s).
- Full numbers, methodology, and an honest read on what these numbers
  do and don't tell you about real deployment hardware (this sandbox
  has one CPU core and no GPU) are in `docs/PERFORMANCE.md`.

**Phase 5 -- Participants, Reports, and Settings screens:**

Completes the GUI -- every dashboard button now opens a real screen,
none are stubs anymore.

- **Participants** (`app/ui/participants_page.py`): search by name/ID/
  registration number/category (`Column.ilike`, verified safe against
  injection-style input directly, not just assumed); view reference
  thumbnails and matched-photo count; edit metadata inline; **delete**
  (reuses `review_service.delete_participant` -- same cascade as the
  CLI); **export** a participant's matched photos as a zip; **reprocess**
  -- re-scan a chosen folder matching against only that one participant,
  for when they were missed the first time or their reference photos
  just got better. Reprocessing deliberately bypasses the cache
  (`resume=False`) since the point is re-evaluating photos already
  processed once -- see `run_batch()`'s new `participant_filter` param.
- **Reports** (`app/ui/reports_page.py`): browse every past
  `ProcessingRun`, see full details, export as JSON/CSV. Shares
  `build_report()` with `python -m app.cli report` -- refactored out of
  the CLI command specifically so there's one implementation, not two
  that could drift apart.
- **Settings** (`app/ui/settings_page.py`): every field from
  `Settings` (paths, thresholds, match strategy, processing mode,
  duplicate policy, cache, log level) in one form, with a warning where
  a change needs a restart to take effect (database path, models
  folder) versus applying to the next run in the same session
  (thresholds, duplicate policy, etc.).

**105 unit tests** (84 from Phases 1-4, plus 17 for participant search/
edit/export and 4 for the new reprocess-scoping logic) -- all runnable
without a GPU or model weights (see "Running the tests").

**Phase 6 -- documentation + Windows packaging:**

- **Every doc from spec section 35** now exists: `docs/INSTALLATION.md`,
  `USER_GUIDE.md`, `DEVELOPER_GUIDE.md`, `TESTING.md`,
  `TROUBLESHOOTING.md`, joining the `PRIVACY`/`SECURITY`/`ACCURACY`/
  `PERFORMANCE` docs already written.
- **`pyinstaller.spec`** builds two Windows executables (`CampPhotoAI.exe`,
  `camp-photo-ai-cli.exe`) from one spec file. `opencv`/`onnxruntime`/
  `insightface` have no built-in PyInstaller hook (unlike `PySide6`/
  `numpy`/`sqlalchemy`, which do), so they're explicitly collected.
- **Found and fixed a real bug by actually building and running the
  frozen app**, not just writing the spec file and hoping: default
  paths (database, output, models, logs) were computed from
  `Path(__file__)`, which resolves to a meaningless location inside a
  PyInstaller bundle instead of the real app directory. Every path-
  dependent feature would have been broken on first launch of the real
  `.exe`. Fixed in `app/config/settings.py::_detect_app_root()` (detects
  frozen mode via `sys.frozen`/`sys.executable`) plus proactive
  directory creation in `app/bootstrap.py` (a frozen build has no
  pre-existing `output/`/`models/` folders the way a source checkout
  does via committed `.gitkeep` files). Verified fixed by rebuilding and
  re-running -- not just reasoning about the fix.
- **What Linux testing can't validate**: the actual Windows `.exe`
  still needs to be built by running `scripts/build_windows.bat` on
  real Windows -- see `docs/INSTALLATION.md` and `pyinstaller.spec`'s
  header comment for exactly what was and wasn't checked.

## Verification

Every phase here was checked at three levels, not just "it compiles":

1. **Static**: every file syntax-checked (`py_compile`) and statically
   analyzed for undefined names/bad imports (`pyflakes`) -- clean.
2. **Unit tests**: all 105 pass, including tests that fabricate an
   old-schema SQLite file and confirm auto-migration, 23 tests that
   verify the evaluation framework's classification logic against
   hand-computed vectors, tests that pin the matching engine's fast
   (uniform-count) and fallback (ragged-count) paths produce identical
   scores across all four matching strategies, and tests that verify
   participant search is safe against injection-style input using real
   hostile strings against a real database, not just assumed safe.
3. **Real, headless GUI + real model + real evaluation + real
   benchmarks + real functional GUI testing + a real frozen-executable
   build**: with `QT_QPA_PLATFORM=offscreen`, the actual
   `QApplication`/`MainWindow` were instantiated and all seven pages
   navigated to successfully -- and, for Phase 5 specifically, actually
   exercised with real data through the running widgets, not just
   constructed: searching for a seeded participant, editing their name
   and confirming the change persisted to the database, loading a
   report's detail view and confirming the displayed numbers matched
   what was stored, and saving a changed setting and confirming it
   persisted to both `data/settings.json` on disk and the shared
   `AppContext` other pages read from. `insightface`/`onnxruntime` were
   installed and the real `buffalo_l` model downloaded. Against a real
   multi-face photo (InsightFace's own `t1.jpg` sample): 6 faces
   detected, 512-d normalized embeddings generated, and
   `evaluate_match()` correctly auto-matched a face to itself with a
   0.94 margin over 5 different real people. The `evaluate` CLI command
   was run end-to-end against a small real dataset built from that
   photo's face crops, correctly reporting both success at safe
   thresholds and degraded precision/nonzero false-accept-rate at an
   unsafe one. The `benchmark` CLI command was run end-to-end too:
   matching and database benchmarks at full spec-target scale (1k-50k),
   and a real pipeline benchmark (actual face detection + embedding,
   not synthetic) that surfaced the N+1 query bug fixed in Phase 4 --
   see `docs/PERFORMANCE.md` for every number, including the 38.8x and
   5.5-11.5x speedups from the two bugs this found. For Phase 6: both
   `pyinstaller.spec` targets were actually built into real frozen
   executables (on Linux -- see below) and *run*, not just spec-checked
   -- catching and fixing the frozen-path bug described above.
   Two things are *not* verified anywhere in this build: the live
   webcam capture path (no camera in this sandbox -- correct by code
   review and the standard OpenCV/Qt pattern, not exercised against real
   hardware), and anything GPU-related (no GPU has been available in any
   session so far -- every performance number is CPU-only, single core).
   A third, new as of Phase 6: genuine Windows behavior. The frozen
   build was validated by building and running it, but only on Linux
   (PyInstaller doesn't cross-compile) -- see `docs/INSTALLATION.md`.

## What's next

Pick whichever matters most first -- they're independent:

1. **Build and test the real Windows `.exe`**: `scripts/build_windows.bat`
   on actual Windows, then work through `docs/USER_GUIDE.md`'s workflow
   end to end on that machine. Everything about the frozen build so far
   has only been validated on Linux.
2. **Multiprocessing the pipeline stage**: docs/PERFORMANCE.md's
   benchmarks make the case clearly -- pipeline cost (2.5s/image on this
   hardware) dwarfs matching/database cost by two orders of magnitude,
   so that's where parallelism would actually help, unlike matching
   (already fast) or database (already fixed). Deliberately not
   implemented here since this sandbox has exactly one CPU core, so
   there's no way to validate a multiprocessing speedup here -- see
   docs/PERFORMANCE.md for a concrete implementation plan (ProcessPool
   with per-worker model loading, main-process-only DB writes).
3. **Run `evaluate`/`benchmark` against real data and real hardware**:
   every number in this README came from tiny/synthetic demo data on a
   single-core CPU-only sandbox. Real calibration and real performance
   numbers both need your actual event photos and actual deployment
   machine (ideally with a GPU -- `onnxruntime-gpu` swap in
   requirements.txt, never benchmarked in any session so far).
4. **The genuinely-unbuilt spec items**: an integration test suite
   (`tests/integration/`, scoped but empty), a synthetic test-data
   generator (spec section 31), and a model-migration workflow for when
   the embedding model itself changes (spec section 32) -- none of
   these were part of any phase so far.
5. **A GUI for `evaluate`/`benchmark`**: every screen from the original
   spec is now built, but these two stay CLI-only -- a natural next
   addition if the GUI is meant to be the primary interface.
6. **A polished Windows installer**: `pyinstaller.spec` produces a
   runnable folder, not a `setup.exe` wizard -- see
   `docs/INSTALLATION.md` for why, and Inno Setup as a reasonable next
   step if that matters.

## Project structure

```
camp_photo_ai/
├── .github/workflows/tests.yml               # CI: pytest tests/unit on push/PR
├── app/
│   ├── main.py              # GUI entry point -- python -m app.main
│   ├── cli.py                 # CLI entry point -- python -m app.cli --help
│   ├── bootstrap.py            # AppContext: shared by CLI and GUI (settings, hardware, model)
│   ├── config/settings.py       # all thresholds/paths -- nothing hard-coded
│   ├── database/                  # SQLAlchemy models + session mgmt + auto-migration
│   ├── models/                      # reserved for shared domain models (empty for now)
│   ├── services/                      # face_detection, face_embedding, face_matching,
│   │                                   #   image_processing, photo_sorting,
│   │                                   #   duplicate_detection, review_service, reporting,
│   │                                   #   evaluation, benchmarking, participant_management
│   ├── ui/                              # PySide6 GUI: main_window + 7 pages + workers/styles
│   ├── workers/                          # batch_processor.py -- the pipeline orchestrator
│   └── utilities/                         # logging, file safety, hardware detection
├── tests/unit/                              # 105 passing tests, no GPU/model weights needed
├── tests/{integration,accuracy,performance,security}/  # accuracy+performance implemented; rest not yet
├── docs/                                      # every doc from spec section 35 -- all written
├── pyinstaller.spec                            # builds CampPhotoAI.exe + camp-photo-ai-cli.exe
├── scripts/build_windows.bat                    # run ON Windows -- see docs/INSTALLATION.md
├── data/ logs/ output/ models/                   # created at runtime
└── requirements.txt
```

## Installing

```bash
# macOS/Linux
bash scripts/setup_dev_env.sh

# Windows
scripts\setup_dev_env.bat
```

This creates a virtualenv and installs everything in `requirements.txt`.
InsightFace's model weights (~350MB) download the first time you run
`register`/`process` (CLI) or open the Registration/Processing screen
(GUI) -- that's the only network call this app makes, and only for that
one-time setup.

On Windows, a pre-built `.exe` (no Python needed) is also an option --
see `docs/INSTALLATION.md` for both that and full GPU-setup details.

## Using the GUI

```bash
python -m app.main
```

Opens the dashboard. Use the sidebar (or the dashboard's action buttons)
to reach any of the seven screens: Register Participant, Process
Photos, Review Matches, Participants, Reports, or Settings.

## Using the CLI

```bash
# Register a participant from 3-5 reference photos
python -m app.cli register --id P001 --name "John Doe" \
  --photos ref1.jpg --photos ref2.jpg --photos ref3.jpg

# Sort a folder of event photos
python -m app.cli process --input ./event_photos --output ./sorted

# See what needs a human decision
python -m app.cli review-queue

# Confirm the suggested match for review record #14
python -m app.cli review-confirm 14

# ...or send it to a different participant instead
python -m app.cli review-confirm 14 --participant-db-id 7

# Calibrate thresholds against a labelled validation dataset (see docs/ACCURACY.md)
python -m app.cli evaluate --dataset ./validation_photos

# Benchmark performance at scale (see docs/PERFORMANCE.md)
python -m app.cli benchmark --target matching --sizes 1000,10000

python -m app.cli report --format json
```

(The spec's CLI examples show `python -m camp_photo_ai ...` -- that only
works if `camp_photo_ai` itself is the importable package. Section 4's
directory tree nests the code under `app/` instead, so the real
invocation is `python -m app.cli`. After `pip install -e .`,
`camp-photo-ai` also works directly, as a middle ground between the two.)

## Running the tests

```bash
pip install -r requirements.txt
pytest tests/unit -v
```

All 105 tests pass without a GPU or model weights -- they exercise the
pure decision logic (`face_matching.py`, `evaluation.py`), file safety
(`file_utils.py`), duplicate detection, database cascade behavior, and
the review workflow directly, using synthetic vectors and tiny generated
images.

## Configuration

Everything in `app/config/settings.py` -- thresholds, paths, worker
count, duplicate policy -- is read from `data/settings.json` (created
with defaults on first run). **The default thresholds
(`auto_match_threshold=0.62`, `review_threshold=0.45`,
`minimum_score_margin=0.08`) are starting points, not calibrated
values.** Run `python -m app.cli evaluate --dataset <your data>` (see
`docs/ACCURACY.md`) against your own consented photos before trusting
them for a real event, then update `data/settings.json` with whatever
it recommends.

---
Silabs (Simeon's Laboratories and Co Technologies Ltd)
