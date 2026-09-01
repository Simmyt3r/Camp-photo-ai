"""Image validation, EXIF-orientation correction, thumbnailing, and safe
loading that never lets one bad file crash a batch (sections 10, 30)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger("camp_photo_ai.image_processing")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif"}


@dataclass
class LoadResult:
    success: bool
    image: np.ndarray | None  # BGR, EXIF-corrected
    error: str | None


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def safe_load_image(path: Path, max_dimension: int = 4096) -> LoadResult:
    """Loads an image, applies EXIF orientation correction, and downsizes
    if it exceeds max_dimension on its longest side. Never raises --
    always returns a LoadResult so the batch pipeline can log a specific,
    actionable error and move on (section 30: never crash the batch on
    one bad photo)."""
    if not path.exists():
        return LoadResult(False, None, f"{path.name} could not be found (it may have been moved or deleted).")
    if not is_supported(path):
        return LoadResult(False, None, f"{path.name} has an unsupported file type ({path.suffix}).")

    try:
        with Image.open(path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)  # respects EXIF rotation
            pil_img = pil_img.convert("RGB")
            w, h = pil_img.size
            longest = max(w, h)
            if longest > max_dimension:
                scale = max_dimension / longest
                pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            rgb = np.array(pil_img)
    except Exception as exc:
        return LoadResult(
            False, None,
            f"{path.name} could not be processed because the image file is corrupted "
            f"or unreadable ({exc.__class__.__name__}). The file was skipped."
        )

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return LoadResult(True, bgr, None)


def generate_thumbnail(image: np.ndarray, max_size: int = 256) -> np.ndarray:
    h, w = image.shape[:2]
    scale = max_size / max(h, w)
    if scale >= 1:
        return image
    return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def encode_thumbnail_jpeg(image: np.ndarray, max_size: int = 200, quality: int = 80) -> bytes:
    """Downscales and JPEG-encodes an image (BGR numpy array) to bytes,
    for storing alongside a reference embedding so the review screen can
    show what a participant looks like without keeping the full-size
    original reference photo file (see docs/PRIVACY.md)."""
    thumb = generate_thumbnail(image, max_size=max_size)
    ok, buf = cv2.imencode(".jpg", thumb, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("Failed to encode thumbnail")
    return buf.tobytes()
