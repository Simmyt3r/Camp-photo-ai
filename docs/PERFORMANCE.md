# Performance & Load Testing

Sections 23-24 of the original spec. Implemented in
`app/services/benchmarking.py`, run via `python -m app.cli benchmark`.
Every number below was actually measured in this project's sandbox
(single CPU core, ~3.9GB RAM, no GPU) -- not estimated. That hardware
profile matters a lot for reading these numbers correctly; see
"Reading these numbers on your own hardware" at the end.

## Two real bugs found and fixed here

Benchmarking isn't just for the report -- it changed the code. Both of
these were found by measuring, not by inspection, and both are now
covered by regression tests so they can't silently come back.

### 1. Matching had two layers of avoidable overhead

`ParticipantIndex.score_all()` (section 24: "do not perform an
unnecessarily expensive Python loop") originally vectorized each
participant's *own* references, but still looped once per participant
in Python:

| n participants | Original | After: 1 big matmul | After: + vectorized reduction |
|---:|---:|---:|---:|
| 100 | 830us | 653us | **72us** |
| 1,000 | 8.61ms | 6.94ms | **1.20ms** |
| 10,000 | 98.6ms | 80.9ms | **17.9ms** |

The first fix (one matmul across every participant instead of one per
participant) only bought ~20%. Profiling why showed the real cost:
`np.mean()`/`np.partition()` were being called 10,000 times per query on
3-element arrays, and per-call dispatch overhead dwarfed the actual
math. The second fix reshapes and reduces every participant's
similarities in one vectorized call when they share the same
reference-photo count (the common case -- section 5 recommends "3-5"
per participant), falling back to the original per-participant loop
only for a genuine mix of counts. Net result: **5.5x-11.5x faster**
depending on scale, fully backward-compatible (see
`tests/unit/test_face_matching.py`'s uniform-vs-ragged equivalence
tests, which pin that both paths produce identical scores for all four
matching strategies).

### 2. Building the participant index was an N+1 query bug

`_build_participant_index()` (called at the start of every batch run)
fetched all participants, then accessed `.embeddings` on each one --
which triggers a separate SQL query per participant under SQLAlchemy's
default lazy loading. At 5,000 participants:

| Approach | Queries | Time |
|---|---:|---:|
| Lazy load (original) | 5,001 | **19.66s** |
| `selectinload` (fixed) | 2 | **0.51s** |

**38.8x faster**, and the gap only widens with more participants. This
ran before a single photo was even processed -- at the spec's 10,000-
participant target, the original code would have added roughly 40+
seconds to every batch run before any work started. Fixed with one
`selectinload()` in `app/workers/batch_processor.py`; see
`tests/performance/test_database_benchmarks.py::test_eager_loading_beats_lazy_loading_at_scale`
for a runnable, self-contained reproduction of both numbers.

## Real numbers, as measured

### Matching (`--target matching`)
Fully synthetic, safe at any scale, achieved the spec's 1k/10k/50k
targets directly in this sandbox:

| n | Mean | P95 | Peak RSS |
|---:|---:|---:|---:|
| 1,000 | 1.32ms | 1.25ms | 103MB |
| 10,000 | 23.6ms | 41.5ms | 212MB |
| 50,000 | 131ms | 122ms | 699MB |

### Database (`--target database`)
Also synthetic/safe at scale; numbers below are **after** the
`selectinload` fix:

| n | Insert (mean/row) | Query-all (mean, 2 queries) |
|---:|---:|---:|
| 1,000 | 0.91ms | 50.7ms |
| 10,000 | 0.95ms | 1,117ms |

Insert cost stays flat per row as expected (indexed keys). Query-all
still grows with n even with the N+1 fix -- that's now genuine
SQLAlchemy ORM object-hydration cost (building thousands of Python
objects), not query count. Still roughly 20-40x faster than the
unfixed version at any given scale.

### Pipeline (`--target pipeline`) -- the one number with no synthetic substitute

Real face detection + embedding, real disk I/O, on this sandbox's single
CPU core, no GPU:

- **Model load / first-inference time: 7.3 seconds** (one-time per run --
  this is exactly why `warm_up()` exists, so it happens before the
  progress bar starts, not on the first photo).
- **Mean: 2,481ms/image** (0.4 images/sec, 2.4 faces/sec, on a 6-face
  test photo).
- **Peak RSS: 930MB** during inference.

Linearly extrapolated (assumes each image costs the same regardless of
total batch size -- reasonable for independent per-image work, see
`extrapolate_linear()`'s docstring for the caveat):

| Target n | Estimated total time |
|---:|---:|
| 1,000 images | ~41 minutes |
| 5,000 images | ~3.4 hours |
| 10,000 images | ~6.9 hours |

**This is slow**, and it's the honest reason why: single CPU core, no
GPU, no parallelism. This is the actual bottleneck of the whole
application at real scale -- pipeline cost per image (2,481ms) dwarfs
matching cost per face (17.9ms even at 10k participants) by two orders
of magnitude. Optimizing matching further would not move the needle;
optimizing pipeline throughput would.

## What this means for the multiprocessing question

Section 11 says multiprocessing is optional, and section 23 explicitly
says not to add concurrency without benchmarking first. That
benchmarking has now happened, and the evidence is clear: **pipeline
throughput, not matching or database, is where parallelism would
actually help**, since each photo's detection+embedding is completely
independent of every other photo.

This was deliberately **not implemented** in this pass, for the same
reason webcam capture wasn't fully hardware-tested in Phase 2: this
sandbox has exactly one CPU core, so there's no way to measure a
multiprocessing speedup here -- at best I'd be shipping unverified code
on the one piece of infrastructure most likely to hide real bugs (worker
process lifecycle, a model loaded per worker rather than per image,
SQLite's poor concurrent-write story). The concrete plan for whoever
picks this up on real multi-core hardware:

1. `concurrent.futures.ProcessPoolExecutor`, with an **initializer**
   function that loads the InsightFace model once per worker process
   (not once per image -- the 7.3s load cost must be paid per worker,
   not per photo).
2. Workers return `(photo_path, embeddings, bboxes)` results; they do
   **not** write to the database directly -- SQLite handles concurrent
   writes from multiple processes badly. The main process stays the
   only writer, consuming results from the pool and doing all
   `MatchRecord`/`ProcessingCache` writes sequentially, exactly like
   `run_batch()` does today.
3. Worker count should default to `os.cpu_count() - 1` or similar
   (leave a core for the main process/OS), overridable via
   `Settings.worker_count` (already exists, currently unused).
4. Re-run `python -m app.cli benchmark --target pipeline --photos
   <folder> --pipeline-sizes <n>` before and after on the real target
   machine to confirm it actually helps before keeping it -- the same
   discipline this whole document is trying to model.

## Reading these numbers on your own hardware

Every number above came from a single-core, GPU-less sandbox --
treat them as a floor, not a prediction, for real deployment hardware:

- **A GPU changes the pipeline number the most.** `onnxruntime-gpu`
  with a supported NVIDIA GPU (CUDA/TensorRT) should cut the 2,481ms/
  image figure dramatically -- this hasn't been measured anywhere in
  this project, since no GPU has been available in any session so far.
- **More CPU cores help matching/database less than you'd think** (they're
  already fast, sub-25ms even at 10k-50k) but would help pipeline a lot,
  via the multiprocessing plan above.
- Run `python -m app.cli benchmark` yourself on the actual machine this
  will run on, especially `--target pipeline --photos <a real folder>`,
  before trusting any of these numbers for your own deployment.
