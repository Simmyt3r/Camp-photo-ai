"""Offline pilot licensing for CampPhoto AI.

The desktop application contains only an Ed25519 PUBLIC key. Silabs keeps the
matching private issuing key outside the repository. A copied application
therefore cannot create its own valid licences.

Phase-one licences are:
- bound to one device
- scoped to one camp/batch
- validated fully offline
- time-limited
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.config.settings import APP_ROOT
from app.ui.branding import COMPANY_NAME, SUPPORT_EMAIL, SUPPORT_PHONE

PILOT_ACTIVATION_FEE_NGN = 10_000
LICENSE_VERSION = 1
LICENSE_KIND = "camp_pilot"
LICENSE_PATH = APP_ROOT / "data" / "license.cpa-license"


@dataclass(frozen=True)
class LicenseValidation:
    valid: bool
    reason: str
    payload: dict[str, Any] | None = None


def _asset_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parents[2] / "assets"


def public_key_path() -> Path:
    return _asset_root() / "license_public_key.pem"


def _machine_seed() -> str:
    """Return a stable local machine identifier source without exposing it."""
    if platform.system().lower() == "windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                if value:
                    return f"windows-machine-guid:{value}"
        except (OSError, ImportError):
            pass

    parts = [
        platform.system(),
        platform.machine(),
        platform.node(),
        str(uuid.getnode()),
    ]
    return "|".join(parts)


def get_device_id() -> str:
    """Return a privacy-preserving device ID suitable for licence binding."""
    digest = hashlib.sha256(
        ("CampPhotoAI|v1|" + _machine_seed()).encode("utf-8")
    ).hexdigest().upper()[:16]
    return "CPA-" + "-".join(digest[i : i + 4] for i in range(0, 16, 4))


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_license_payload(
    payload: dict[str, Any],
    private_key_pem: bytes,
) -> dict[str, Any]:
    """Create a signed licence document. Intended for the Silabs admin tool."""
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None,
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("The licence private key is not an Ed25519 private key.")

    signature = private_key.sign(_canonical_payload(payload))
    return {
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def verify_license_document(
    document: dict[str, Any],
    *,
    public_key_pem: bytes | None = None,
    expected_device_id: str | None = None,
    today: date | None = None,
) -> LicenseValidation:
    try:
        payload = document["payload"]
        signature_text = document["signature"]
        if not isinstance(payload, dict) or not isinstance(signature_text, str):
            return LicenseValidation(False, "Licence file format is invalid.")

        if payload.get("version") != LICENSE_VERSION:
            return LicenseValidation(False, "Unsupported licence version.")

        if payload.get("license_kind") != LICENSE_KIND:
            return LicenseValidation(False, "This licence is not a Camp Pilot licence.")

        required = (
            "license_id",
            "device_id",
            "camp_name",
            "state",
            "batch_stream",
            "issued_on",
            "expires_on",
            "issuer",
        )
        missing = [name for name in required if not str(payload.get(name, "")).strip()]
        if missing:
            return LicenseValidation(
                False,
                "Licence is missing required field(s): " + ", ".join(missing),
            )

        key_bytes = public_key_pem
        if key_bytes is None:
            key_path = public_key_path()
            if not key_path.is_file():
                return LicenseValidation(False, "Licence verification key is missing.")
            key_bytes = key_path.read_bytes()

        public_key = serialization.load_pem_public_key(key_bytes)
        if not isinstance(public_key, Ed25519PublicKey):
            return LicenseValidation(False, "Licence verification key is invalid.")

        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(signature, _canonical_payload(payload))

        device_id = expected_device_id or get_device_id()
        if payload["device_id"].strip().upper() != device_id.strip().upper():
            return LicenseValidation(
                False,
                f"Licence belongs to another device ({payload['device_id']}).",
                payload,
            )

        current_date = today or date.today()
        expires_on = date.fromisoformat(payload["expires_on"])
        issued_on = date.fromisoformat(payload["issued_on"])
        if issued_on > current_date:
            return LicenseValidation(False, "Licence is not active yet.", payload)
        if current_date > expires_on:
            return LicenseValidation(
                False,
                f"Licence expired on {expires_on.isoformat()}.",
                payload,
            )

        return LicenseValidation(True, "Licence is valid.", payload)

    except InvalidSignature:
        return LicenseValidation(False, "Licence signature is invalid or the file was modified.")
    except (ValueError, TypeError, KeyError, binascii.Error) as exc:
        return LicenseValidation(False, f"Licence could not be read: {exc}")


def read_license_document(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_installed_license() -> LicenseValidation:
    if not LICENSE_PATH.is_file():
        return LicenseValidation(False, "CampPhoto AI has not been activated on this device.")
    try:
        document = read_license_document(LICENSE_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return LicenseValidation(False, f"Installed licence could not be read: {exc}")
    return verify_license_document(document)


def install_license(source: Path) -> LicenseValidation:
    try:
        document = read_license_document(source)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return LicenseValidation(False, f"Licence file could not be read: {exc}")

    validation = verify_license_document(document)
    if not validation.valid:
        return validation

    LICENSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_PATH.write_text(
        json.dumps(document, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return validation


def format_activation_request(
    *,
    camp_name: str,
    state: str,
    batch_stream: str,
    contact_name: str,
    contact: str,
    payment_reference: str,
) -> str:
    return (
        "CAMP PHOTO AI - PILOT ACTIVATION REQUEST\n"
        f"Activation fee: NGN {PILOT_ACTIVATION_FEE_NGN:,}\n"
        f"Device ID: {get_device_id()}\n"
        f"Camp: {camp_name.strip()}\n"
        f"State: {state.strip()}\n"
        f"Batch / Stream: {batch_stream.strip()}\n"
        f"Contact person: {contact_name.strip()}\n"
        f"Phone / Email: {contact.strip()}\n"
        f"Payment reference: {payment_reference.strip()}\n\n"
        f"Issue licence after payment is manually verified by {COMPANY_NAME}.\n"
        f"Support: {SUPPORT_PHONE} | {SUPPORT_EMAIL}"
    )
