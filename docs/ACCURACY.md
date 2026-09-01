# Accuracy Evaluation & Threshold Calibration

Sections 21-22 of the original spec. Implemented in
`app/services/evaluation.py`, run via:

```bash
python -m app.cli evaluate --dataset ./your_dataset
```

## Dataset format

```
your_dataset/
├── person_001/
│   ├── photo1.jpg
│   ├── photo2.jpg
│   └── photo3.jpg
├── person_002/
│   ├── photo1.jpg
│   └── photo2.jpg
└── _unknown/                  (optional)
    ├── stranger1.jpg
    └── stranger2.jpg
```

- Each identity folder needs **at least 2 usable photos** (one face,
  clearly detected, per photo). `--gallery-size` (default 3) controls
  how many of each identity's photos become the reference gallery
  (exactly like registration would use); the rest become probes run
  through the real matching pipeline and checked against the known
  answer.
- `_unknown/` is optional but recommended: photos of people who are
  *not* registered anywhere. Without it, the tool can't measure false
  accept rate against genuinely unknown people -- only confusion between
  registered identities.
- **Real, consented photos only.** Per spec section 31, synthetic faces
  are not a valid sole benchmark. Don't point this at AI-generated faces
  or at people who haven't agreed to be part of a test set.

## What it reports

**Recognition accuracy (top-1 / top-5)** -- threshold-independent: for
each probe, is the correct identity even the single highest-scoring
candidate (top-1), or in the 5 highest (top-5)? This measures the
embedding/matching quality itself. Top-5 is close to meaningless with
fewer than 5 registered identities -- it saturates trivially.

**Threshold sweep** -- for each auto-match threshold in the grid
(`--thresholds`, default `0.50,0.55,0.60,0.65,0.70,0.75`, matching the
spec's own example table), with `review_threshold = threshold -
--review-gap` and `minimum_score_margin` held at your configured
setting:

| Column | Meaning |
|---|---|
| Precision | Of everything auto-matched, what fraction was correct |
| Recall | Of everything that *should* have auto-matched, what fraction did |
| F1 | Harmonic mean of the two |
| FAR (False Accept Rate) | Of everything that should NOT have auto-matched (impostors, or known people matched to the wrong person), what fraction incorrectly did -- **the single most important number**, per section 8: a wrong auto-assignment is worse than a missed one |
| FRR (False Reject Rate) | Of everything that should have matched, what fraction was left fully unmatched |
| Review Q | How many probes landed in the review queue at this threshold |

A `threshold_sweep.txt` (plain table) and `threshold_sweep.png` (graph)
are written to `--output-dir` (default `accuracy_report/`).

**Suggested threshold** -- the highest-recall option among those
clearing `--min-precision` (default 98%). This follows section 8's
precision-over-recall priority, but it is a starting point for a human
to weigh against their own risk tolerance, **not a universal answer**
(section 22 is explicit about this). Re-run against your own data before
trusting a number.

## Known limitation found while verifying this

While testing this framework against InsightFace's own bundled sample
images, the face *detector* found **zero faces** in any of 4 test photos
of a person wearing a surgical mask. A masked or otherwise significantly
occluded face isn't just harder to match -- with the current
`buffalo_l` detector, it may not be detected at all, so it never reaches
the matching stage and would land in `Unmatched/` (or simply not be
counted as containing a face), not `Review/`. If your event photos will
include masks, heavy occlusion, or similar, build that into your
validation dataset and expect this to show up as reduced recall, not as
review-queue volume.

## Verification note

This framework was checked against real (if very limited) data: 3
identities built from real face crops of InsightFace's own `t1.jpg`
sample photo, each identity's second "photo" being a disclosed synthetic
augmentation (horizontal flip + brightness jitter) of the same crop --
enough to exercise the gallery/probe split mechanics honestly, but not
independent evidence of real-world accuracy. 3 other, genuinely distinct
real faces from the same photo were used as `_unknown` impostor probes.
At a reasonable threshold (0.50+) the tool correctly reported perfect
precision/recall; at a deliberately unsafe low threshold (0.10-0.20) it
correctly reported degraded precision and a nonzero false-accept rate
instead of always reporting success. The classification/metric logic
itself is also covered by 23 unit tests using deterministic,
hand-computed vectors (`tests/unit/test_evaluation.py`) -- those don't
need a dataset or model weights to verify.

None of this is a substitute for running the tool against your own
event's real, consented photos.
