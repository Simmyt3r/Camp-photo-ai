# Integration tests (planned)

Exercises full workflows end-to-end against a real (test) database and
real images: registration -> embedding -> scan -> detect -> match ->
output, covering single-person photos, multi-person photos, unknown
faces, low-quality/corrupted photos, duplicates, large batches,
interrupted + resumed batches, manual review corrections, and
participant deletion (spec section 26).

Requires `insightface`/`onnxruntime` installed and a small fixture image
set (not included -- use your own consented test photos; per section 31,
synthetic faces alone are not a valid accuracy benchmark). Not yet
implemented -- the unit tests in `tests/unit/` already cover the
decision/utility logic these workflows depend on.
