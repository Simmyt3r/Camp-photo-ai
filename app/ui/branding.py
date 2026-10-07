"""CampPhoto AI product identity and asset helpers."""
from __future__ import annotations

import sys
from pathlib import Path

PRODUCT_NAME = "CampPhoto AI"
COMPANY_NAME = "Simeon's Laboratories And Co Technologies Ltd"
SUPPORT_PHONE = "09039930006"
SUPPORT_EMAIL = "silabtechnologies@gmail.com"
AGREEMENT_VERSION = "2026-10-07-v1"


def asset_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"


def app_logo_path() -> Path:
    return asset_root() / "campphoto_logo.png"
