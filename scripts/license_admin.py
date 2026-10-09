"""Silabs-only command-line tool for issuing CampPhoto AI pilot licences.

Keep the Ed25519 private key OUT of Git and OUT of customer computers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.licensing import (
    LICENSE_KIND,
    LICENSE_VERSION,
    PILOT_ACTIVATION_FEE_NGN,
    sign_license_payload,
)


def _private_key_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("CAMPPHOTO_LICENSE_PRIVATE_KEY")
    if env:
        return Path(env)
    return REPO_ROOT / "license_keys" / "CampPhotoAI_PILOT_PRIVATE_KEY.pem"


def issue(args: argparse.Namespace) -> int:
    key_path = _private_key_path(args.private_key)
    if not key_path.is_file():
        print(
            "Private issuing key not found. Put it at "
            f"{key_path} or set CAMPPHOTO_LICENSE_PRIVATE_KEY.",
            file=sys.stderr,
        )
        return 2

    issued_on = date.today()
    expires_on = date.fromisoformat(args.expires_on)
    if expires_on < issued_on:
        print("Expiry date cannot be before today.", file=sys.stderr)
        return 2

    payload = {
        "version": LICENSE_VERSION,
        "license_kind": LICENSE_KIND,
        "license_id": "CPA-PILOT-" + uuid.uuid4().hex[:12].upper(),
        "device_id": args.device_id.strip().upper(),
        "camp_name": args.camp.strip(),
        "state": args.state.strip(),
        "batch_stream": args.batch.strip(),
        "contact_name": args.contact_name.strip(),
        "contact": args.contact.strip(),
        "payment_reference": args.payment_reference.strip(),
        "activation_fee_ngn": PILOT_ACTIVATION_FEE_NGN,
        "issued_on": issued_on.isoformat(),
        "expires_on": expires_on.isoformat(),
        "issuer": "Simeon's Laboratories And Co Technologies Ltd",
        "features": ["full_pilot_functionality", "offline_operation"],
    }

    document = sign_license_payload(payload, key_path.read_bytes())
    output = Path(args.output) if args.output else Path(
        f"{payload['license_id']}.cpa-license"
    )
    output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Issued: {payload['license_id']}")
    print(f"Camp: {payload['camp_name']}")
    print(f"Device: {payload['device_id']}")
    print(f"Valid through: {payload['expires_on']}")
    print(f"Licence file: {output.resolve()}")
    return 0


def inspect(args: argparse.Namespace) -> int:
    document = json.loads(Path(args.license).read_text(encoding="utf-8"))
    print(json.dumps(document.get("payload", {}), indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CampPhoto AI pilot licence administration."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    issue_parser = sub.add_parser("issue", help="Issue one signed pilot licence.")
    issue_parser.add_argument("--device-id", required=True)
    issue_parser.add_argument("--camp", required=True)
    issue_parser.add_argument("--state", required=True)
    issue_parser.add_argument("--batch", required=True)
    issue_parser.add_argument("--contact-name", required=True)
    issue_parser.add_argument("--contact", required=True)
    issue_parser.add_argument("--payment-reference", required=True)
    issue_parser.add_argument("--expires-on", required=True, help="YYYY-MM-DD")
    issue_parser.add_argument("--private-key")
    issue_parser.add_argument("--output")
    issue_parser.set_defaults(func=issue)

    inspect_parser = sub.add_parser(
        "inspect",
        help="Display the payload of a licence file.",
    )
    inspect_parser.add_argument("license")
    inspect_parser.set_defaults(func=inspect)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
