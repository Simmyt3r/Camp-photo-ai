import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from werkzeug.security import generate_password_hash

import portal_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    db_path = tmp_path / "portal.db"
    public_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    expected_fingerprint = hashlib.sha256(public_der).hexdigest()

    def fake_initialize(app, record):
        return {
            "authorization_url": "https://checkout.paystack.com/example",
            "access_code": "access_test",
            "reference": record.payment_reference,
        }

    def fake_verify(app, reference):
        maker = app.extensions["portal_sessionmaker"]
        with maker() as database:
            record = database.scalar(
                portal_app.select(portal_app.ActivationRequest).where(
                    portal_app.ActivationRequest.payment_reference == reference
                )
            )
            return {
                "status": "success",
                "amount": portal_app.ACTIVATION_FEE_KOBO,
                "currency": "NGN",
                "reference": reference,
                "metadata": {
                    "activation_token": record.public_token,
                    "device_id": record.device_id,
                },
                "customer": {"email": record.email},
            }

    monkeypatch.setattr(portal_app, "initialize_paystack_transaction", fake_initialize)
    monkeypatch.setattr(portal_app, "verify_paystack_transaction", fake_verify)

    return portal_app.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE_URL": f"sqlite:///{db_path}",
            "PAYSTACK_SECRET_KEY": "sk_test_example",
            "CAMPPHOTO_LICENSE_PRIVATE_KEY_B64": base64.b64encode(pem).decode("ascii"),
            "APP_BASE_URL": "https://portal.example.test",
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD_HASH": generate_password_hash("correct horse battery staple"),
            "PILOT_LICENSE_DAYS": 45,
            "EXPECTED_LICENSE_PUBLIC_KEY_SHA256": expected_fingerprint,
        }
    )


def activation_payload():
    return {
        "device_id": "CPA-1111-2222-3333-4444",
        "camp_name": "NYSC Test Camp",
        "state": "Benue",
        "batch_stream": "2026 Batch C Stream I",
        "contact_name": "Test Operator",
        "email": "operator@example.com",
        "phone": "08000000000",
    }


def test_api_payment_to_signed_license(app):
    client = app.test_client()
    headers = {"X-CampPhoto-Client": "desktop-v1"}
    created = client.post("/api/requests", json=activation_payload(), headers=headers)
    assert created.status_code == 200
    body = created.get_json()
    assert body["amount_ngn"] == 10000
    token = body["request_token"]

    verify = client.post(f"/api/requests/{token}/verify", headers=headers)
    assert verify.status_code == 200

    status = client.get(f"/api/requests/{token}", headers=headers)
    data = status.get_json()
    assert data["status"] == "licensed"
    document = data["license_document"]
    assert document["payload"]["device_id"] == activation_payload()["device_id"]
    assert document["payload"]["activation_fee_ngn"] == 10000
    assert document["payload"]["license_kind"] == "camp_pilot"
    assert document["signature"]


def test_wrong_amount_never_issues(app, monkeypatch):
    def wrong_amount(app, reference):
        return {
            "status": "success",
            "amount": 500000,
            "currency": "NGN",
            "reference": reference,
            "metadata": {},
            "customer": {},
        }

    monkeypatch.setattr(portal_app, "verify_paystack_transaction", wrong_amount)
    client = app.test_client()
    headers = {"X-CampPhoto-Client": "desktop-v1"}
    body = client.post("/api/requests", json=activation_payload(), headers=headers).get_json()
    token = body["request_token"]
    response = client.post(f"/api/requests/{token}/verify", headers=headers)
    assert response.status_code == 409
    status = client.get(f"/api/requests/{token}", headers=headers).get_json()
    assert status["status"] != "licensed"


def test_health_never_exposes_secret_values(app):
    data = app.test_client().get("/health").get_json()
    assert data["status"] == "ok"
    assert data["configuration"]["paystack"] is True
    rendered = str(data)
    assert "sk_test_example" not in rendered
    assert "BEGIN PRIVATE KEY" not in rendered


def test_api_requires_desktop_client_header(app):
    client = app.test_client()
    response = client.post("/api/requests", json=activation_payload())
    assert response.status_code == 400


def test_activation_form_requires_csrf(app):
    client = app.test_client()
    response = client.post("/activate", data=activation_payload())
    assert response.status_code == 400

    with client.session_transaction() as sess:
        sess["_csrf"] = "known-token"
    payload = activation_payload()
    payload["_csrf"] = "known-token"
    response = client.post("/activate", data=payload)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("https://checkout.paystack.com/")


def test_security_headers_are_present(app):
    response = app.test_client().get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


def test_invalid_device_id_is_rejected(app):
    client = app.test_client()
    headers = {"X-CampPhoto-Client": "desktop-v1"}
    payload = activation_payload()
    payload["device_id"] = "CPA-NOT-A-REAL-ID"
    response = client.post("/api/requests", json=payload, headers=headers)
    assert response.status_code == 400


def test_payment_metadata_is_required(app, monkeypatch):
    def missing_metadata(app, reference):
        return {
            "status": "success",
            "amount": portal_app.ACTIVATION_FEE_KOBO,
            "currency": "NGN",
            "reference": reference,
            "metadata": {},
            "customer": {"email": "operator@example.com"},
        }

    client = app.test_client()
    headers = {"X-CampPhoto-Client": "desktop-v1"}
    body = client.post("/api/requests", json=activation_payload(), headers=headers).get_json()
    monkeypatch.setattr(portal_app, "verify_paystack_transaction", missing_metadata)
    response = client.post(f"/api/requests/{body['request_token']}/verify", headers=headers)
    assert response.status_code == 409


def test_repeated_verification_is_idempotent(app):
    client = app.test_client()
    headers = {"X-CampPhoto-Client": "desktop-v1"}
    body = client.post("/api/requests", json=activation_payload(), headers=headers).get_json()
    token = body["request_token"]

    first = client.post(f"/api/requests/{token}/verify", headers=headers)
    assert first.status_code == 200
    first_status = client.get(f"/api/requests/{token}", headers=headers).get_json()
    first_id = first_status["license_document"]["payload"]["license_id"]

    second = client.post(f"/api/requests/{token}/verify", headers=headers)
    assert second.status_code == 200
    second_status = client.get(f"/api/requests/{token}", headers=headers).get_json()
    assert second_status["license_document"]["payload"]["license_id"] == first_id


def test_signing_key_mismatch_fails_closed(app):
    app.config["EXPECTED_LICENSE_PUBLIC_KEY_SHA256"] = "0" * 64
    health = app.test_client().get("/health").get_json()
    assert health["configuration"]["signing_key"] is False

    response = app.test_client().post(
        "/api/requests",
        json=activation_payload(),
        headers={"X-CampPhoto-Client": "desktop-v1"},
    )
    assert response.status_code == 503
