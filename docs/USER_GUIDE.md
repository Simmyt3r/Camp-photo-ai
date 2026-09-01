# User Guide

CampPhoto AI has two interfaces that share the same underlying data --
use whichever fits, or mix both (e.g. register participants in the GUI,
run a big batch overnight from the CLI).

- **GUI** (`python -m app.main`): point-and-click, good for day-to-day
  operation by someone who isn't a developer.
- **CLI** (`python -m app.cli --help`): scriptable, good for large
  unattended batches, automation, or servers without a display.

## Typical end-to-end workflow

1. **Register participants** -- 3-5 reference photos each, different
   angles/lighting where possible.
2. **Process a folder of event photos** -- sorts them into per-
   participant folders automatically.
3. **Review** anything the system wasn't confident about.
4. **Export/report** as needed.

## The GUI, screen by screen

Launch with `python -m app.main`. The sidebar (or the Dashboard's
action buttons) reaches all seven screens.

### Dashboard
Live counts: registered participants, photos processed, faces
detected, auto-matched, needs review, unmatched. Refreshes every time
you navigate back to it.

### Register Participant
Fill in Participant ID and Full Name (required); Registration Number
and Category are optional. Add reference photos via **Import Photos**
(file picker) or **Open Camera** (webcam, if one's available -- gracefully
tells you if none is found rather than failing). Each photo is
validated before registration: photos with zero faces or more than one
face are rejected with a reason, shown in the list once you click
**Register Participant**. 3-5 good photos is the sweet spot -- more
isn't necessarily better if the extra photos are low quality.

### Process Photos
Pick an input folder (where the event photos are) and an output folder
(where sorted results go), then **Start Processing**. Progress, speed,
and live auto-matched/review/unmatched/error counts update as it runs,
on a background thread so the window stays responsive. Unchanged
photos from a previous run in the same input folder are skipped
automatically (resumable batches -- see `docs/PERFORMANCE.md` for what
this costs at scale).

### Review Matches
The queue on the left lists everything that needs a human decision.
Selecting an item shows the full photo, a cropped detected-face
thumbnail, the suggested participant's reference photo, the
score/margin/reason, and three actions:
- **Confirm** -- accepts the suggested participant, copies the photo
  into their folder.
- **Reject** -- marks it rejected, assigns nobody.
- **Reassign & Confirm** -- pick a different participant from the
  dropdown if the suggestion was wrong.

### Participants
Search by name, ID, registration number, or category. Selecting a
result shows their reference photo thumbnails, matched-photo count, and
an editable form (name/registration number/category -- **Save Changes**
to persist). Three further actions:
- **Export Photos...** -- zips everything matched to them so far.
- **Reprocess...** -- re-scans a chosen folder matching against *only*
  this person (useful after improving their reference photos, or if
  they were missed the first time). This always re-evaluates every
  photo in the folder, even ones already processed before -- that's the
  point of reprocessing.
- **Delete Participant** -- permanent, cascades to their reference
  embeddings (see `docs/PRIVACY.md`). Confirmed via a dialog first.

### Reports
Browse every past processing run, see full details (photo/face counts,
speed, thresholds used), export as JSON or CSV.

### Settings
Every configurable value from `app/config/settings.py` in one form --
paths, matching thresholds, match strategy, processing mode, duplicate
policy, cache behavior, log level. Path changes (database, models
folder) need an app restart to take effect; everything else applies to
the next `process`/`evaluate`/`benchmark` run in the same session.
**Restore Defaults** resets the form (not saved until you click **Save
Settings** afterward).

## The CLI, command by command

```bash
# Register a participant from 3-5 reference photos
python -m app.cli register --id P001 --name "John Doe" \
  --photos ref1.jpg --photos ref2.jpg --photos ref3.jpg

# Sort a folder of event photos
python -m app.cli process --input ./event_photos --output ./sorted

# Review queue
python -m app.cli review-queue
python -m app.cli review-confirm 14
python -m app.cli review-confirm 14 --participant-db-id 7   # reassign instead
python -m app.cli review-reject 14

# Clear the cache so the next `process` reprocesses everything
python -m app.cli rebuild-cache

# Export a report for the most recent run
python -m app.cli report --format json

# Calibrate thresholds against a labelled validation dataset
python -m app.cli evaluate --dataset ./validation_photos

# Benchmark performance
python -m app.cli benchmark --target matching --sizes 1000,10000
```

Every command has `--help` with its full option list.

## Threshold calibration workflow

The default thresholds (`auto_match_threshold=0.62`,
`review_threshold=0.45`, `minimum_score_margin=0.08`) are starting
points, not validated numbers -- see `docs/ACCURACY.md`. Before relying
on this for a real event:

1. Build a labelled dataset: a folder per known person, 2+ real photos
   each, plus an optional `_unknown/` folder of people who should never
   match (see `docs/ACCURACY.md`'s dataset format).
2. `python -m app.cli evaluate --dataset ./your_dataset` -- reports
   recognition accuracy, a full threshold sweep (table + graph), and a
   suggested starting threshold.
3. Update `auto_match_threshold`/`review_threshold`/
   `minimum_score_margin` in Settings (GUI) or `data/settings.json`
   directly, based on what you measured -- not on the shipped defaults.

## Performance benchmarking workflow

If processing feels slow, or before committing to a deployment machine
for a real event:

```bash
# Fast, synthetic, safe at any scale
python -m app.cli benchmark --target matching --sizes 1000,10000
python -m app.cli benchmark --target database --sizes 1000,10000,50000

# Real inference speed -- no synthetic substitute, start small
python -m app.cli benchmark --target pipeline --photos ./sample_photos --pipeline-sizes 20,50
```

See `docs/PERFORMANCE.md` for what the numbers mean, real measurements
from development (single CPU core, no GPU -- treat as a floor, not a
prediction, for your hardware), and two real performance bugs that were
found and fixed this way.
