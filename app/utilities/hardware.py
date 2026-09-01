"""Hardware detection (section 12): CPU, RAM, GPU, disk space, and the
resulting recommended processing mode."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

import psutil

logger = logging.getLogger("camp_photo_ai.hardware")


@dataclass
class HardwareProfile:
    cpu_count: int
    ram_total_gb: float
    ram_available_gb: float
    disk_free_gb: float
    gpu_available: bool
    gpu_provider: str | None
    recommended_mode: str  # "cpu" | "gpu"


def _detect_gpu_provider() -> str | None:
    """Checks which ONNX Runtime execution providers are actually usable.
    Returns None if only CPUExecutionProvider is available, so the caller
    falls back to CPU mode automatically."""
    try:
        import onnxruntime as ort
    except ImportError:
        logger.warning("onnxruntime not installed -- defaulting to CPU mode")
        return None

    available = ort.get_available_providers()
    for provider in ("CUDAExecutionProvider", "TensorrtExecutionProvider", "DmlExecutionProvider"):
        if provider in available:
            return provider
    return None


def detect_hardware(output_dir: str = ".") -> HardwareProfile:
    gpu_provider = _detect_gpu_provider()
    disk_free_gb = shutil.disk_usage(output_dir).free / (1024 ** 3)

    profile = HardwareProfile(
        cpu_count=psutil.cpu_count(logical=True) or 1,
        ram_total_gb=round(psutil.virtual_memory().total / (1024 ** 3), 1),
        ram_available_gb=round(psutil.virtual_memory().available / (1024 ** 3), 1),
        disk_free_gb=round(disk_free_gb, 1),
        gpu_available=gpu_provider is not None,
        gpu_provider=gpu_provider,
        recommended_mode="gpu" if gpu_provider else "cpu",
    )
    logger.info(
        "Hardware detected: %d CPUs, %.1fGB RAM, GPU=%s (%s), %.1fGB free disk",
        profile.cpu_count, profile.ram_total_gb, profile.gpu_available,
        profile.gpu_provider or "none", profile.disk_free_gb,
    )
    return profile


def resolve_processing_mode(configured_mode: str, profile: HardwareProfile) -> str:
    """configured_mode is the user's setting: 'auto' | 'cpu' | 'gpu'."""
    if configured_mode == "auto":
        return profile.recommended_mode
    if configured_mode == "gpu" and not profile.gpu_available:
        logger.warning("GPU mode requested but no GPU provider found -- falling back to CPU")
        return "cpu"
    return configured_mode
