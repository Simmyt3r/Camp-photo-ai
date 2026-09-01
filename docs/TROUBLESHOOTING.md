# Troubleshooting

## Installation

**`pip install -r requirements.txt` fails on OpenCV or PySide6**
These have real system-library dependencies on Linux (X11/Wayland libs
for PySide6, libGL for OpenCV) that pip can't install for you. On
Debian/Ubuntu: `sudo apt install libgl1 libxkbcommon0 libegl1`. Windows
and macOS wheels are typically self-contained and shouldn't hit this.

**`pip install` fails with a permissions error**
You're likely installing outside a virtual environment into a
system-managed Python. Use `scripts/setup_dev_env.sh` /
`setup_dev_env.bat`, or create your own venv first (see
`docs/INSTALLATION.md`) -- don't `pip install --break-system-packages`
outside of a throwaway/CI environment.

**The model download hangs or fails**
This is the one network call the app makes (see `docs/PRIVACY.md`) --
InsightFace downloading its `buffalo_l` pack (~350MB) on first
`register`/`process`. Check your internet connection and any
firewall/proxy that might block the download host. There's currently no
built-in way to resume a partial download or point at a mirror -- if it
fails partway, delete the partial `models/` contents and try again.

## Running the app

**"No such column" / database errors after updating**
The auto-migration (`app/database/db.py::_auto_migrate_add_missing_columns`)
handles new nullable columns automatically, but can't safely add a
required column with no default to a table that might already have
rows -- it logs a warning and skips instead of guessing. If you see a
column-related error after pulling an update, check the logs for an
"auto-migration...skipping" warning; if there isn't one, back up
`data/camp_photo_ai.db` and delete it to let it be recreated fresh
(you'll need to re-register participants).

**Processing is very slow**
Expected on CPU-only hardware -- see `docs/PERFORMANCE.md` for real
measured numbers (2.5 seconds/image on a single CPU core in
development) and what would actually help (a GPU, or multiprocessing --
not yet implemented, see that doc's plan). Run `python -m app.cli
benchmark --target pipeline --photos <folder>` on your own machine to
see what to actually expect before assuming something's wrong.

**GPU isn't being used even though I installed `onnxruntime-gpu`**
Check the status bar in the GUI (or `Processing mode: ...` in the CLI's
`process` output) -- it shows which execution provider was actually
selected. `app/utilities/hardware.py::_detect_gpu_provider()` only
picks a GPU if `CUDAExecutionProvider`, `TensorrtExecutionProvider`, or
`DmlExecutionProvider` shows up in `onnxruntime.get_available_providers()`;
if none do, it silently falls back to CPU rather than erroring. Run
`python -c "import onnxruntime; print(onnxruntime.get_available_providers())"`
directly to see what your `onnxruntime` install actually detected --
if your GPU provider isn't listed, the issue is in the ONNX Runtime /
CUDA driver setup, not this app.

## GUI-specific

**"No camera found" when trying to use webcam capture**
The Registration screen degrades gracefully rather than crashing --
this message means `cv2.VideoCapture(0)` couldn't open a device.
Confirm no other application is holding the camera, and that camera
permissions are granted (macOS/Windows both gate camera access per-app).
Import Photos from disk works regardless. Note: the webcam path has
never been tested against real hardware in development (no camera in
any development sandbox) -- if something's subtly wrong beyond "no
camera found," that's the most likely place.

**GUI won't start / crashes immediately on Linux**
If running headless (a server, CI, over SSH without X forwarding), Qt
needs a display. For automated/headless use, set
`QT_QPA_PLATFORM=offscreen` -- though at that point you likely want the
CLI instead, since a fully headless GUI can't be interacted with
anyway.

**Settings changes don't seem to take effect**
Path changes (database location, models folder) need an app restart --
the Settings screen says this, but it's easy to miss. Everything else
(thresholds, duplicate policy, cache, log level) applies to the next
`process`/`evaluate`/`benchmark` run within the same session.

## Windows distributable specifically

**The app creates `data`/`logs`/`output`/`models` folders somewhere
unexpected, or fails to write them**
By design, these live right next to `CampPhotoAI.exe` (see
`docs/INSTALLATION.md`) -- if the `.exe` is under `C:\Program Files\...`,
standard Windows accounts can't write there without admin rights, and
the app will fail on startup. Move the whole folder somewhere you have
write access (Desktop, Documents, a dedicated folder).

**Antivirus flags or quarantines the `.exe`**
Common for PyInstaller-built executables in general, especially
unsigned ones (this build isn't code-signed). If you built it yourself
and trust your own build, add an exclusion. This is also why UPX
compression is deliberately disabled in `pyinstaller.spec` -- it's
sometimes associated with more false positives, not fewer.

**Something Windows-specific is broken that isn't listed here**
Genuinely possible -- every development session for this project has
run on Linux, and while the frozen build was validated by actually
building and running it (see `pyinstaller.spec`'s header comment for
the real bug that caught), that was Linux-only testing of the app's own
logic, not a real Windows environment. See `docs/DEVELOPER_GUIDE.md`'s
closing section for the full list of what's genuinely unverified.

## Still stuck?

Check the logs: `logs/camp_photo_ai.log` for general activity,
`logs/audit.log` for registration/processing/review/deletion actions
specifically (see `docs/SECURITY.md`). Both use plain structured text,
one line per event, and never contain raw embedding vectors (filtered
before writing, not just by convention).
