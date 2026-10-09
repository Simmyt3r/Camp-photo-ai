# PyInstaller spec file for CampPhoto AI.
#
# Builds TWO executables:
#   - CampPhotoAI       (app/main.py) -- GUI
#   - camp-photo-ai-cli (app/cli.py)  -- CLI
#
# Run from the project root:
#   pyinstaller pyinstaller.spec --noconfirm --clean

from pathlib import Path

from PIL import Image
from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
)

block_cipher = None
PROJECT_ROOT = Path(SPECPATH)

# Generate a native Windows icon from the verified PNG on every build.
# This avoids relying on a hand-committed ICO, which is easy to corrupt.
ICON_PNG = PROJECT_ROOT / "assets" / "campphoto_logo.png"
ICON_DIR = PROJECT_ROOT / "build" / "branding"
ICON_ICO = ICON_DIR / "campphoto_logo.ico"
ICON_DIR.mkdir(parents=True, exist_ok=True)

with Image.open(ICON_PNG) as logo:
    logo.load()
    logo.convert("RGBA").save(
        ICON_ICO,
        format="ICO",
        # Store frames as Windows DIB/BMP data rather than PNG-compressed
        # icon frames. This is slightly larger, but avoids a Pillow/PyInstaller
        # decoding failure observed on GitHub's Windows runner while embedding
        # the executable icon.
        bitmap_format="bmp",
        sizes=[
            (16, 16),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )

# Do a real decode of every icon size. Image.verify() only validates the
# container and did not catch the malformed/undecodable frame that previously
# failed later inside PyInstaller while copying the icon to the EXE.
with Image.open(ICON_ICO) as icon_file:
    for icon_size in sorted(icon_file.ico.sizes()):
        frame = icon_file.ico.getimage(icon_size)
        frame.load()


# ---------------------------------------------------------------------------
# Dependency collection
# ---------------------------------------------------------------------------
#
# IMPORTANT:
# Do NOT use collect_all("onnxruntime").
#
# collect_all() also returns every discovered hidden import. With the current
# ONNX Runtime/ONNX packages this causes PyInstaller to walk optional tooling
# such as:
#
#   onnx.reference
#   onnxruntime.tools
#   onnxruntime.transformers
#
# Some of those modules are not required by InsightFace inference and one of
# them causes PyInstaller's isolated dependency scanner to crash on Windows
# with exit code 3221225477.
#
# We only collect the ONNX Runtime data and native DLLs that the application
# actually needs. The normal import of onnxruntime is handled by PyInstaller's
# dependency analysis.
#

collected_binaries = []
collected_datas = [
    (str(PROJECT_ROOT / "assets" / "campphoto_logo.png"), "assets"),
    (str(PROJECT_ROOT / "assets" / "license_public_key.pem"), "assets"),
]
collected_hiddenimports = []


# OpenCV: collect its native DLLs/data and hidden modules.
b, d, h = collect_all("cv2")
collected_binaries += b
collected_datas += d
collected_hiddenimports += h


# InsightFace: it performs dynamic imports for model_zoo and related modules,
# so retain its normal collect_all() handling.
b, d, h = collect_all("insightface")
collected_binaries += b
collected_datas += d
collected_hiddenimports += h


# ONNX Runtime: collect ONLY data files and native libraries.
collected_binaries += collect_dynamic_libs("onnxruntime")
collected_datas += collect_data_files("onnxruntime")


COMMON_HIDDEN_IMPORTS = collected_hiddenimports + [
    "sqlalchemy.dialects.sqlite",
    "PIL.Image",
    "imagehash",
]


COMMON_EXCLUDES = [
    # Optional/test-only packages.
    "matplotlib.tests",
    "numpy.tests",

    # Qt modules not used by this application.
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",

    # ONNX Runtime optional tooling. The application uses ONNX Runtime for
    # inference, not model conversion/optimization tooling.
    "onnxruntime.tools",
    "onnxruntime.transformers",

    # ONNX reference implementation is not required by InsightFace inference.
    # Excluding it also prevents PyInstaller from importing the problematic
    # onnx.reference package during binary dependency analysis.
    "onnx.reference",
    "onnx.reference.ops",
    "onnx.reference.ops.aionnxml",
    "onnx.reference.ops.experimental",
    "onnx.reference.ops.aionnx_preview",
    "onnx.reference.ops.aionnx_preview_training",
    "onnx.reference.ops_optimized",
]


# ---------------------------------------------------------------------------
# GUI executable
# ---------------------------------------------------------------------------

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

gui_pyz = PYZ(
    gui_analysis.pure,
    gui_analysis.zipped_data,
    cipher=block_cipher,
)

gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    [],
    exclude_binaries=True,
    name="CampPhotoAI",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON_ICO),
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


# ---------------------------------------------------------------------------
# CLI executable
# ---------------------------------------------------------------------------

cli_analysis = Analysis(
    [str(PROJECT_ROOT / "app" / "cli.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=collected_binaries,
    datas=collected_datas,
    hiddenimports=COMMON_HIDDEN_IMPORTS + ["click"],
    hookspath=[],
    excludes=COMMON_EXCLUDES + [
        "PySide6",
    ],
    noarchive=False,
    cipher=block_cipher,
)

cli_pyz = PYZ(
    cli_analysis.pure,
    cli_analysis.zipped_data,
    cipher=block_cipher,
)

cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    [],
    exclude_binaries=True,
    name="camp-photo-ai-cli",
    debug=False,
    strip=False,
    upx=False,
    console=True,
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