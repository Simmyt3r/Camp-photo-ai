# Accuracy evaluation framework

Sections 21-22: precision/recall/F1/FAR/FRR/top-1/top-5 accuracy, plus a
threshold-calibration sweep (auto_match_threshold, with review_threshold
and minimum_score_margin held fixed) against a labelled validation
dataset of real, consented photographs.

**Implemented** in `app/services/evaluation.py`, wired up as
`python -m app.cli evaluate --dataset <path>`. See `docs/ACCURACY.md`
for the dataset layout and how to read the output. The classification
and metric logic is unit-tested with deterministic synthetic vectors in
`tests/unit/test_evaluation.py` (23 tests) -- no dataset or model
weights required to verify that logic is correct.

**Not included here**: an actual dataset. Synthetic faces are explicitly
disallowed as the sole benchmark (section 31), and this project doesn't
ship one (bundling real people's photos in a code deliverable isn't
appropriate, and there's no reliable way to generate "the same synthetic
identity under different conditions"). Point `--dataset` at your own
consented photos when you have them -- e.g. a past event's organized
photos, or a small set from a handful of consenting colleagues to start.
