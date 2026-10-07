"""Bundle a locally supplied InsightFace buffalo_l model into Windows builds.

This intentionally does not download or commit pretrained weights. It copies
a model the operator already possesses into the frozen app folders so the
result can run offline.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REQUIRED_FILES = {
    "det_10g.onnx",
    "1k3d68.onnx",
    "2d106det.onnx",
    "genderage.onnx",
    "w600k_r50.onnx",
}


def model_is_complete(path: Path) -> bool:
    return path.is_dir() and all(
        (path / name).is_file() and (path / name).stat().st_size > 0
        for name in REQUIRED_FILES
    )


def locate_model(root: Path) -> Path | None:
    if model_is_complete(root):
        return root

    named = root / "buffalo_l"
    if model_is_complete(named):
        return named

    for anchor in root.rglob("w600k_r50.onnx"):
        candidate = anchor.parent
        if model_is_complete(candidate):
            return candidate

    return None


def resolve_source(source: Path, temp_root: Path) -> Path | None:
    if source.is_dir():
        return locate_model(source)

    if source.is_file() and source.suffix.lower() == ".zip":
        extracted = temp_root / "extracted"
        extracted.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source, "r") as archive:
            archive.extractall(extracted)
        return locate_model(extracted)

    return None


def copy_model(model_dir: Path, destination_root: Path) -> None:
    destination = destination_root / "models" / "buffalo_l"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    for name in sorted(REQUIRED_FILES):
        shutil.copy2(model_dir / name, destination / name)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a local buffalo_l model into CampPhoto AI Windows build folders."
    )
    parser.add_argument(
        "--source",
        default="models/buffalo_l",
        help="Folder containing buffalo_l ONNX files, or a buffalo_l.zip archive.",
    )
    parser.add_argument(
        "--required",
        action="store_true",
        help="Fail if a complete local model is not available.",
    )
    parser.add_argument(
        "--gui-target",
        default="dist/CampPhotoAI",
        help="PyInstaller GUI output folder.",
    )
    parser.add_argument(
        "--cli-target",
        default="dist/camp-photo-ai-cli",
        help="PyInstaller CLI output folder.",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()

    with tempfile.TemporaryDirectory(prefix="camp-photo-model-bundle-") as temp_dir:
        model_dir = resolve_source(source, Path(temp_dir))

        if model_dir is None:
            message = (
                f"No complete buffalo_l model was found at {source}. "
                "Expected the five ONNX files or a buffalo_l.zip archive."
            )
            if args.required:
                print(f"ERROR: {message}", file=sys.stderr)
                return 2
            print(f"Skipping model bundle: {message}")
            return 0

        targets = [Path(args.gui_target), Path(args.cli_target)]
        missing_targets = [str(target) for target in targets if not target.is_dir()]
        if missing_targets:
            print(
                "ERROR: Build output folder(s) missing: " + ", ".join(missing_targets),
                file=sys.stderr,
            )
            return 3

        for target in targets:
            copy_model(model_dir, target.resolve())
            print(f"Bundled buffalo_l into {target / 'models' / 'buffalo_l'}")

    print("Offline buffalo_l bundle complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
