"""
Shared loader for InsightFace's FaceAnalysis model.

This loader keeps InsightFace's model files in the application's writable
models directory and performs a reliable first-run download of buffalo_l.

The custom download path avoids InsightFace's console progress output, which
can raise "'NoneType' object has no attribute 'write'" inside a PyInstaller
windowed executable where stdout/stderr may be unavailable.

The buffalo_l model pack is approximately 326 MB extracted and is subject
to InsightFace's model licensing terms.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import sys
import tempfile
import threading
import urllib.request
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable

logger = logging.getLogger("camp_photo_ai.face_model")

_lock = threading.Lock()
_apps: dict[tuple, object] = {}

BUFFALO_L_URL = (
    "https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip"
)

# Official checksum published with the InsightFace model-zoo release.
BUFFALO_L_SHA256 = "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f"

BUFFALO_L_REQUIRED_FILES = {
    "det_10g.onnx",
    "1k3d68.onnx",
    "2d106det.onnx",
    "genderage.onnx",
    "w600k_r50.onnx",
}


class _NullWriter(io.TextIOBase):
    """Safe stdout/stderr replacement for windowed PyInstaller builds."""

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


_NULL_WRITER = _NullWriter()

ModelProgressCallback = Callable[[int, int | None, str], None]


def _emit_progress(callback: ModelProgressCallback | None, downloaded: int, total: int | None, message: str) -> None:
    if callback is None:
        return
    try:
        callback(downloaded, total, message)
    except Exception:
        logger.debug("Model progress callback failed", exc_info=True)


def _safe_stream(stream):
    """Return a usable stream even when PyInstaller sets it to None."""
    return stream if stream is not None and hasattr(stream, "write") else _NULL_WRITER


def _get_model_root(models_dir: str | None, model_name: str) -> Path:
    """Return the concrete model package directory.

    CampPhoto AI's settings.models_dir is the visible `models/` folder, so a
    normal install stores buffalo_l at `models/buffalo_l/`. InsightFace
    itself expects its root one level above that models folder; the loader
    derives that root later when constructing FaceAnalysis.

    _find_existing_model_dir() still recognizes the older accidental
    `models/models/buffalo_l/` layout so existing installs remain usable.
    """
    if models_dir:
        return Path(models_dir).expanduser().resolve() / model_name
    return Path.home() / ".insightface" / "models" / model_name


def _model_is_complete(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False

    return all((model_dir / name).is_file() for name in BUFFALO_L_REQUIRED_FILES)


def _find_existing_model_dir(models_dir: str | None, model_name: str) -> Path | None:
    """
    Check the locations that may already contain the model.

    This also handles installations where the caller supplied either the
    InsightFace root directory or the application's models directory.
    """
    candidates: list[Path] = []

    if models_dir:
        supplied = Path(models_dir).expanduser().resolve()

        candidates.extend(
            [
                supplied / "models" / model_name,
                supplied / model_name,
            ]
        )

    default_root = Path.home() / ".insightface" / "models"
    candidates.append(default_root / model_name)

    seen: set[Path] = set()

    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)

        if _model_is_complete(candidate):
            return candidate

    return None


def _remove_incomplete_model_files(model_root: Path) -> None:
    """Remove failed/partial model downloads."""
    zip_path = model_root.parent / f"{model_root.name}.zip"

    try:
        if zip_path.exists():
            zip_path.unlink()
            logger.warning("Removed incomplete model archive: %s", zip_path)
    except OSError:
        logger.exception("Could not remove incomplete model archive: %s", zip_path)

    if model_root.exists() and not _model_is_complete(model_root):
        try:
            shutil.rmtree(model_root)
            logger.warning("Removed incomplete model directory: %s", model_root)
        except OSError:
            logger.exception("Could not remove incomplete model directory: %s", model_root)


def _download_buffalo_l(model_dir: Path, progress_callback: ModelProgressCallback | None = None) -> Path:
    """
    Download and extract buffalo_l safely.

    The archive is first written to a temporary file. It is never left as a
    zero-byte or partial final archive. Extraction happens into a temporary
    directory and is moved into place only after validation succeeds.
    """
    parent = model_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    zip_path = parent / f"{model_dir.name}.zip"
    temp_zip = parent / f".{model_dir.name}.download"
    temp_extract = Path(
        tempfile.mkdtemp(prefix=f".{model_dir.name}_", dir=str(parent))
    )

    logger.info("Downloading InsightFace model pack %s ...", model_dir.name)
    logger.info("Model download URL: %s", BUFFALO_L_URL)
    _emit_progress(progress_callback, 0, None, "Connecting to InsightFace model server...")

    try:
        request = urllib.request.Request(
            BUFFALO_L_URL,
            headers={
                "User-Agent": "CampPhotoAI/1.0",
                "Accept": "application/octet-stream",
            },
        )

        with urllib.request.urlopen(request, timeout=60) as response, open(
            temp_zip, "wb"
        ) as output:
            content_length = response.headers.get("Content-Length")
            total = int(content_length) if content_length else 0
            downloaded = 0

            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break

                output.write(chunk)
                downloaded += len(chunk)
                _emit_progress(
                    progress_callback,
                    downloaded,
                    total or None,
                    "Downloading buffalo_l face model...",
                )

                if total:
                    percent = downloaded * 100 // total
                    if percent % 10 == 0:
                        logger.info(
                            "buffalo_l download: %d%% (%d/%d MB)",
                            percent,
                            downloaded // (1024 * 1024),
                            total // (1024 * 1024),
                        )

        if not temp_zip.is_file() or temp_zip.stat().st_size < 1024 * 1024:
            raise RuntimeError(
                "The buffalo_l download was incomplete or empty. "
                "Please check the computer's internet connection and try again."
            )

        _emit_progress(
            progress_callback,
            temp_zip.stat().st_size,
            temp_zip.stat().st_size,
            "Verifying buffalo_l download...",
        )

        digest = hashlib.sha256()
        with open(temp_zip, "rb") as downloaded_file:
            for block in iter(lambda: downloaded_file.read(1024 * 1024), b""):
                digest.update(block)
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != BUFFALO_L_SHA256:
            raise RuntimeError(
                "The buffalo_l download failed checksum verification. "
                f"Expected {BUFFALO_L_SHA256}, got {actual_sha256}. "
                "Delete the partial download and try again."
            )

        os.replace(temp_zip, zip_path)

        logger.info(
            "Downloaded buffalo_l archive: %.1f MB",
            zip_path.stat().st_size / (1024 * 1024),
        )

        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(temp_extract)

        # The archive normally contains a buffalo_l directory.
        extracted_model = temp_extract / "buffalo_l"

        if not extracted_model.is_dir():
            possible_dirs = [
                p
                for p in temp_extract.iterdir()
                if p.is_dir()
                and all((p / filename).is_file() for filename in BUFFALO_L_REQUIRED_FILES)
            ]

            if len(possible_dirs) == 1:
                extracted_model = possible_dirs[0]

        if not _model_is_complete(extracted_model):
            missing = sorted(
                BUFFALO_L_REQUIRED_FILES
                - {
                    p.name
                    for p in extracted_model.iterdir()
                    if p.is_file()
                }
            ) if extracted_model.is_dir() else sorted(BUFFALO_L_REQUIRED_FILES)

            raise RuntimeError(
                "buffalo_l was downloaded but the extracted model is incomplete. "
                f"Missing files: {', '.join(missing)}"
            )

        if model_dir.exists():
            shutil.rmtree(model_dir)

        shutil.move(str(extracted_model), str(model_dir))

        if not _model_is_complete(model_dir):
            raise RuntimeError("buffalo_l installation failed validation.")

        logger.info("buffalo_l model installed successfully at %s", model_dir)
        _emit_progress(progress_callback, 1, 1, "buffalo_l model installed successfully.")
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove downloaded model archive: %s", zip_path)
        return model_dir

    except Exception:
        logger.exception("Failed to download/install buffalo_l.")

        try:
            if temp_zip.exists():
                temp_zip.unlink()
        except OSError:
            pass

        try:
            if zip_path.exists() and not _model_is_complete(model_dir):
                zip_path.unlink()
        except OSError:
            pass

        raise

    finally:
        shutil.rmtree(temp_extract, ignore_errors=True)


def _ensure_model_available(
    models_dir: str | None,
    model_name: str,
    progress_callback: ModelProgressCallback | None = None,
) -> Path | None:
    """
    Ensure the requested model is available.

    For buffalo_l, use the application's writable model location and perform
    a controlled download if the model does not already exist.
    """
    if model_name != "buffalo_l":
        return _find_existing_model_dir(models_dir, model_name)

    existing = _find_existing_model_dir(models_dir, model_name)
    if existing:
        logger.info("Using existing buffalo_l model at %s", existing)
        return existing

    model_dir = _get_model_root(models_dir, model_name)

    # Remove any 0-byte/partial archive left by a previous failed attempt.
    _remove_incomplete_model_files(model_dir)

    return _download_buffalo_l(model_dir, progress_callback=progress_callback)


def get_face_analysis_app(
    provider: str = "CPUExecutionProvider",
    model_name: str = "buffalo_l",
    det_size: tuple[int, int] = (640, 640),
    models_dir: str | None = None,
    progress_callback: ModelProgressCallback | None = None,
):
    key = (provider, model_name, models_dir or "")

    with _lock:
        if key in _apps:
            return _apps[key]

        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise RuntimeError(
                "insightface is not installed. Run `pip install insightface "
                "onnxruntime` (or `onnxruntime-gpu` for GPU mode) to enable "
                "face detection/embedding."
            ) from exc

        model_dir = _ensure_model_available(
            models_dir, model_name, progress_callback=progress_callback
        )

        if model_name == "buffalo_l" and model_dir is None:
            raise RuntimeError(
                "The buffalo_l face model is not installed and could not be "
                "prepared. Please check the model directory and internet connection."
            )

        # InsightFace expects root=<parent containing models/<model_name>>.
        if model_dir is not None:
            insightface_root = str(model_dir.parent.parent)
        elif models_dir:
            insightface_root = str(Path(models_dir).expanduser().resolve())
        else:
            insightface_root = None

        kwargs = {
            "name": model_name,
            "providers": [provider],
        }

        if insightface_root:
            kwargs["root"] = insightface_root

        logger.info(
            "Loading FaceAnalysis model=%s provider=%s root=%s",
            model_name,
            provider,
            insightface_root,
        )
        _emit_progress(progress_callback, 1, 1, "Loading face recognition model...")

        # PyInstaller windowed applications can have sys.stdout/sys.stderr=None.
        # InsightFace/tqdm and some dependency code may call .write() on them.
        safe_stdout = _safe_stream(sys.stdout)
        safe_stderr = _safe_stream(sys.stderr)

        old_stdout = sys.stdout
        old_stderr = sys.stderr

        try:
            sys.stdout = safe_stdout
            sys.stderr = safe_stderr

            with redirect_stdout(safe_stdout), redirect_stderr(safe_stderr):
                app = FaceAnalysis(**kwargs)
                app.prepare(
                    ctx_id=0 if provider != "CPUExecutionProvider" else -1,
                    det_size=det_size,
                )

        except Exception as exc:
            raise RuntimeError(
                f"Unable to load the {model_name} face model. "
                f"Model directory: {model_dir or 'not found'}. "
                f"Original error: {exc}"
            ) from exc

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        _apps[key] = app
        logger.info("FaceAnalysis model ready.")
        _emit_progress(progress_callback, 1, 1, "Face model ready.")

        return app
