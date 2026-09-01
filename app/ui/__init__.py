"""PySide6 desktop GUI (sections 17-19).

Seven screens: dashboard, participant registration (with webcam
capture), photo processing with live progress, the human-review queue,
participant search/edit/delete/export/reprocess, past-run reports, and
a settings editor -- see app/main.py to launch. No pipeline logic lives
here: pages call straight into app.workers.batch_processor.run_batch(),
app.services.review_service, and app.services.participant_management,
wrapped in QThread workers (app/ui/workers.py) so the UI thread never
blocks.

Not yet built: any UI for the accuracy/calibration (`evaluate`) or
performance (`benchmark`) CLI commands -- those stay CLI-only for now."""
