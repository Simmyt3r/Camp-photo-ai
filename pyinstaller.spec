# PyInstaller spec file for CampPhoto AI (spec section 36).
#
# Builds TWO executables from one spec, matching the app's two real
# entry points:
#   - CampPhotoAI       (app/main.py)  -- the GUI
#   - camp-photo-ai-cli (app/cli.py)   -- the CLI
#
# Run from the project root:
#   pyinstaller pyinstaller.spec --noconfirm
#
# Output goes to dist/CampPhotoAI/ and dist/camp-photo-ai-cli/ (--onedir
# mode -- see docs/INSTALLATION.md for why --onefile is deliberately NOT
# used here: this app's dependencies, especially onnxruntime and
# insightface, are large and slow to self-extract on every launch).
#
# IMPORTANT: PyInstaller does not cross-compile. Building on Linux
# produces a Linux binary, not a Windows .exe. This spec file has been
# validated by actually building BOTH targets on Linux in development --
# not just checked by inspection -- and running the resulting binaries.
# That process found and fixed a real bug: app/config/settings.py computed
# its base directory from Path(__file__), which resolves to a meaningless
# location inside a frozen bundle, so every default path (database,
# output, models, logs) was wrong under a frozen build until fixed (see
# app/config/settings.py::_detect_app_root() and app/bootstrap.py). The
# real Windows .exe still needs to be built BY RUNNING THIS ON WINDOWS --
# Linux testing validates the bundling and the app's own path-handling
# logic, not Windows-specific behavior. See docs/INSTALLATION.md.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
PROJECT_ROOT = Path(SPECPATH)

# opencv, onnxruntime, and insightface have no built-in PyInstaller hook
# (unlike PySide6/numpy/sqlalchemy, which do) -- collect_all() pulls in
# their binaries, data files, and hidden submodule imports that
# PyInstaller's static bytecode analysis alone would miss. insightface
# in particular does internal dynamic imports based on model pack names,
# which static analysis cannot see coming.
collected_binaries = []
collected_datas = []
collected_hiddenimports = []
for pkg in ("cv2", "onnxruntime", "insightface"):
    b, d, h = collect_all(pkg)
    collected_binaries += b
    collected_datas += d
    collected_hiddenimports += h

COMMON_HIDDEN_IMPORTS = collected_hiddenimports + [
    "sqlalchemy.dialects.sqlite",
    "PIL.Image",
    "imagehash",
]

COMMON_EXCLUDES = [
    # Reduces bundle size: these are pulled in transitively by some
    # dependencies' optional code paths but nothing in this app uses
    # them. Remove from this list if a build ever fails looking for one.
    "matplotlib.tests",
    "numpy.tests",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
]

# --- GUI executable ---------------------------------------------------

gui_analysis = Analysis(
    [str(PROJECT_ROOT / "app" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=collected_binaries,
    datas=collected_datas,
    hiddenimports=COMMON_HIDDEN_IMPORTS,
    hookspath=[],
    excludes=COMMON_EXCLUDES,
    noarchive=False,
    cipher=block_cipher,
)
gui_pyz = PYZ(gui_analysis.pure, gui_analysis.zipped_data, cipher=block_cipher)
gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name="CampPhotoAI",
    debug=False,
    strip=False,
    upx=False,  # UPX compression saves space but has caused false-positive
                # antivirus flags on PyInstaller binaries before -- not
                # worth it for a first distributable.
    console=False,  # no terminal window behind the GUI
    icon=None,  # add an .ico here once one exists -- see docs/INSTALLATION.md
)
gui_collect = COLLECT(
    gui_exe,
    gui_analysis.binaries,
    gui_analysis.zipfiles,
    gui_analysis.datas,
    strip=False,
    upx=False,
    name="CampPhotoAI",
)

# --- CLI executable -----------------------------------------------------

cli_analysis = Analysis(
    [str(PROJECT_ROOT / "app" / "cli.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=collected_binaries,
    datas=collected_datas,
    hiddenimports=COMMON_HIDDEN_IMPORTS + ["click"],
    hookspath=[],
    excludes=COMMON_EXCLUDES + ["PySide6"],  # the CLI never imports app.ui, but
                                               # exclude explicitly in case a
                                               # future change adds an accidental
                                               # import -- keeps the CLI build
                                               # from silently bloating with Qt.
    noarchive=False,
    cipher=block_cipher,
)
cli_pyz = PYZ(cli_analysis.pure, cli_analysis.zipped_data, cipher=block_cipher)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="camp-photo-ai-cli",
    debug=False,
    strip=False,
    upx=False,
    console=True,  # CLI needs its terminal output
    icon=None,
)
cli_collect = COLLECT(
    cli_exe,
    cli_analysis.binaries,
    cli_analysis.zipfiles,
    cli_analysis.datas,
    strip=False,
    upx=False,
    name="camp-photo-ai-cli",
)
