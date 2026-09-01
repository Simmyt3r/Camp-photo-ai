# Installation

Two ways to run CampPhoto AI: from source (any OS, needs Python), or as
a pre-built Windows distributable (no Python needed, Windows only).

## From source

### Prerequisites

- Python 3.11 or newer
- ~2GB free disk space (dependencies + the InsightFace model pack,
  which downloads on first use)
- Windows, macOS, or Linux

### Quick start

```bash
# macOS/Linux
bash scripts/setup_dev_env.sh

# Windows
scripts\setup_dev_env.bat
```

This creates a virtual environment and installs everything in
`requirements.txt`. Then:

```bash
python -m app.main          # GUI
python -m app.cli --help    # CLI
```

### Manual installation

If you'd rather not use the setup script:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
```

### First run: the model download

The first time you run `register`, `process`, or open the Registration/
Processing screen, InsightFace downloads its `buffalo_l` model pack
(~350MB) into `models/`. This is the **only** network call this app
makes (see `docs/PRIVACY.md`) -- after that, everything runs fully
offline. If you're behind a restrictive firewall, this download needs
to succeed once before the app is usable; there's currently no way to
manually pre-seed the model files short of copying an existing
`models/` folder from another working install.

### GPU setup (optional)

By default, `requirements.txt` installs the CPU build of ONNX Runtime.
For a supported NVIDIA GPU (CUDA or TensorRT):

```bash
pip uninstall onnxruntime
pip install onnxruntime-gpu
```

Set `processing_mode` to `auto` (the default) or `gpu` in Settings --
`app/utilities/hardware.py` detects which ONNX Runtime execution
providers are actually available at startup and falls back to CPU
automatically if no GPU provider is found, so switching the pip package
back later doesn't require any config changes.

**Honest caveat**: no GPU has been available in any development session
for this project. GPU support is implemented and the fallback logic is
tested, but the actual speedup on real GPU hardware has never been
measured -- see `docs/PERFORMANCE.md`'s closing section. Please report
back what you see.

### Verifying the install

```bash
pip install pytest
pytest tests/unit -v
```

Should show 105 passing tests, all without needing a GPU or the model
weights (they use synthetic data -- see `docs/TESTING.md`).

## Windows distributable (no Python required)

If someone has already built `CampPhotoAI.exe` for you (see "Building
it yourself" below), using it needs no Python installation at all:

1. Unzip/copy the whole `CampPhotoAI` folder somewhere you have write
   access -- **Desktop, Documents, or a dedicated folder. Not Program
   Files.** The app stores its own `data/`, `logs/`, `models/`, and
   `output/` folders right next to the `.exe`, and standard Windows
   accounts can't write to Program Files without admin rights.
2. Double-click `CampPhotoAI.exe`.
3. First launch downloads the model pack (~350MB, one time, needs
   internet) -- same as the source install above.

The CLI equivalent (`camp-photo-ai-cli.exe`) works the same way from a
terminal: `camp-photo-ai-cli.exe --help`.

### Building it yourself

```bat
scripts\build_windows.bat
```

This must be run **on Windows** -- PyInstaller does not cross-compile,
so running it on macOS/Linux produces a macOS/Linux binary, not a
Windows `.exe`. It installs `pyinstaller` and everything in
`requirements.txt`, then builds from `pyinstaller.spec`. Output lands in
`dist/CampPhotoAI/` and `dist/camp-photo-ai-cli/`.

This has been validated by actually building both targets *on Linux*
during development and running the resulting binaries -- which caught
and fixed a real bug (default paths resolved incorrectly inside a
frozen bundle; see `pyinstaller.spec`'s header comment and
`app/config/settings.py::_detect_app_root()`). What Linux testing
*can't* validate is anything Windows-specific -- if the real Windows
build hits something new, it's likely in that category. Expect the
build to take several minutes and the output folder to be large
(the Linux test build was ~630-770MB per target, dominated by
onnxruntime/insightface/OpenCV/PySide6) -- normal for this dependency
stack, not a sign something went wrong.

No Windows installer (`.msi`/setup wizard) is built here -- just the
`--onedir` PyInstaller output, which is a complete, runnable folder you
can zip and share as-is. [Inno Setup](https://jrsoftware.org/isinfo.php)
or similar is a reasonable next step if a polished installer experience
matters more than "unzip and run."
