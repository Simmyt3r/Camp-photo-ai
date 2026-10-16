import base64

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

    def fake_initialize(app, record):
        return {
            "authorization_url": "https://checkout.paystack.test/example",
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
    created = client.post("/api/requests", json=activation_payload())
    assert created.status_code == 200
    body = created.get_json()
    assert body["amount_ngn"] == 10000
    token = body["request_token"]

    verify = client.post(f"/api/requests/{token}/verify")
    assert verify.status_code == 200

    status = client.get(f"/api/requests/{token}")
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
    body = client.post("/api/requests", json=activation_payload()).get_json()
    token = body["request_token"]
    response = client.post(f"/api/requests/{token}/verify")
    assert response.status_code == 409
    status = client.get(f"/api/requests/{token}").get_json()
    assert status["status"] != "licensed"


def test_health_never_exposes_secret_values(app):
    data = app.test_client().get("/health").get_json()
    assert data["status"] == "ok"
    assert data["configuration"]["paystack"] is True
    rendered = str(data)
    assert "sk_test_example" not in rendered
    assert "BEGIN PRIVATE KEY" not in rendered
