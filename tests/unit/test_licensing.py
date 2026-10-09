from datetime import date, timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.licensing import (
    LICENSE_KIND,
    LICENSE_VERSION,
    sign_license_payload,
    verify_license_document,
)


def _keypair():
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _payload(device_id="CPA-AAAA-BBBB-CCCC-DDDD"):
    today = date(2026, 10, 9)
    return {
        "version": LICENSE_VERSION,
        "license_kind": LICENSE_KIND,
        "license_id": "CPA-PILOT-TEST1234",
        "device_id": device_id,
        "camp_name": "Test Orientation Camp",
        "state": "Benue",
        "batch_stream": "2026 Batch C Stream I",
        "contact_name": "Test Operator",
        "contact": "operator@example.com",
        "payment_reference": "PAY-123",
        "activation_fee_ngn": 10000,
        "issued_on": today.isoformat(),
        "expires_on": (today + timedelta(days=30)).isoformat(),
        "issuer": "Simeon's Laboratories And Co Technologies Ltd",
        "features": ["full_pilot_functionality", "offline_operation"],
    }


def test_valid_signed_licence_is_accepted():
    private_pem, public_pem = _keypair()
    payload = _payload()
    document = sign_license_payload(payload, private_pem)

    result = verify_license_document(
        document,
        public_key_pem=public_pem,
        expected_device_id=payload["device_id"],
        today=date(2026, 10, 9),
    )

    assert result.valid
    assert result.payload["camp_name"] == "Test Orientation Camp"


def test_tampered_licence_is_rejected():
    private_pem, public_pem = _keypair()
    payload = _payload()
    document = sign_license_payload(payload, private_pem)
    document["payload"]["expires_on"] = "2099-12-31"

    result = verify_license_document(
        document,
        public_key_pem=public_pem,
        expected_device_id=payload["device_id"],
        today=date(2026, 10, 9),
    )

    assert not result.valid
    assert "signature" in result.reason.lower()


def test_wrong_device_is_rejected():
    private_pem, public_pem = _keypair()
    payload = _payload()
    document = sign_license_payload(payload, private_pem)

    result = verify_license_document(
        document,
        public_key_pem=public_pem,
        expected_device_id="CPA-1111-2222-3333-4444",
        today=date(2026, 10, 9),
    )

    assert not result.valid
    assert "another device" in result.reason.lower()


def test_expired_licence_is_rejected():
    private_pem, public_pem = _keypair()
    payload = _payload()
    payload["issued_on"] = "2026-08-01"
    payload["expires_on"] = "2026-09-30"
    document = sign_license_payload(payload, private_pem)

    result = verify_license_document(
        document,
        public_key_pem=public_pem,
        expected_device_id=payload["device_id"],
        today=date(2026, 10, 9),
    )

    assert not result.valid
    assert "expired" in result.reason.lower()
