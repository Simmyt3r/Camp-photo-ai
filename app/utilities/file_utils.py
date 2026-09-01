"""
Filesystem helpers: safe filenames, path-traversal protection, file
hashing, perceptual hashing.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import imagehash
from PIL import Image

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Turns an arbitrary participant name/ID into a safe filesystem
    component. Strips path separators and traversal sequences so a
    participant name can never be used to write outside the output
    directory (section 28: "Protection against directory traversal
    through participant names")."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = _UNSAFE_CHARS.sub("_", name).strip(" .")
    name = name.replace("..", "_")
    if not name:
        name = "unnamed"
    return name[:max_length]


def ensure_within_root(root: Path, candidate: Path) -> Path:
    """Raises ValueError if `candidate` (once resolved) is not `root` or
    inside it. This is the actual boundary check, kept separate from
    safe_output_path and independently testable: safe_output_path also
    sanitizes each path component before calling this (which neutralizes
    most traversal attempts on its own), but this function still catches
    an escape even if a future change to sanitize_filename ever had a
    gap, or if a candidate path is built some other way."""
    root = root.resolve()
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Refusing to write outside root directory: {candidate}")
    return candidate


def safe_output_path(output_root: Path, *parts: str) -> Path:
    """Joins sanitized parts under output_root and verifies the result is
    still inside output_root (section 28: directory-traversal protection)."""
    output_root = output_root.resolve()
    candidate = output_root.joinpath(*[sanitize_filename(p) for p in parts])
    return ensure_within_root(output_root, candidate)


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def perceptual_hash(path: Path) -> imagehash.ImageHash:
    with Image.open(path) as img:
        return imagehash.phash(img)


def hashes_are_near_duplicate(a: imagehash.ImageHash, b: imagehash.ImageHash, threshold: int = 6) -> bool:
    return (a - b) <= threshold


def unique_destination(path: Path) -> Path:
    """If `path` already exists, appends _1, _2, ... before the extension
    until a free path is found. Used when duplicate_policy == 'rename' so
    an existing photo is never silently overwritten (section 15)."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
