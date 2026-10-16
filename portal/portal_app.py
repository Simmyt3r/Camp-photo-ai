from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

import bcrypt
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import (
    Flask, abort, flash, jsonify, redirect, render_template, request,
    send_file, session, url_for,
)
from sqlalchemy import DateTime, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool
from werkzeug.security import check_password_hash

PORTAL_VERSION = "1.0.0"
ACTIVATION_FEE_NGN = 10_000
ACTIVATION_FEE_KOBO = ACTIVATION_FEE_NGN * 100
LICENSE_VERSION = 1
LICENSE_KIND = "camp_pilot"
ISSUER = "Simeon's Laboratories And Co Technologies Ltd"
PAYSTACK_API = "https://api.paystack.co"
EXPECTED_LICENSE_PUBLIC_KEY_SHA256 = "b5a16e159d90fe0a99dd4c05f5bac03d8d13b1695f870d049a172f30a815c1be"
DEVICE_ID_RE = re.compile(r"^CPA-(?:[A-F0-9]{4}-){3}[A-F0-9]{4}$")
MAX_REQUEST_BODY_BYTES = 64 * 1024


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActivationRequest(Base):
    __tablename__ = "activation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_token: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    camp_name: Mapped[str] = mapped_column(String(240))
    state: Mapped[str] = mapped_column(String(120))
    batch_stream: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(240), index=True)
    phone: Mapped[str] = mapped_column(String(80), default="")
    amount_ngn: Mapped[int] = mapped_column(Integer, default=ACTIVATION_FEE_NGN)
    status: Mapped[str] = mapped_column(String(40), default="created", index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    paystack_access_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    paystack_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    license_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    license_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_on: Mapped[str | None] = mapped_column(String(20), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    activation_request_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(100), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


def _normalise_database_url(value: str) -> str:
    value = value.strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://") and "+psycopg" not in value:
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _private_key_bytes(app: Flask) -> bytes:
    raw_b64 = app.config.get("CAMPPHOTO_LICENSE_PRIVATE_KEY_B64", "").strip()
    raw_pem = app.config.get("CAMPPHOTO_LICENSE_PRIVATE_KEY_PEM", "").strip()
    if raw_b64:
        try:
            return base64.b64decode(raw_b64, validate=True)
        except Exception as exc:
            raise RuntimeError("CAMPPHOTO_LICENSE_PRIVATE_KEY_B64 is not valid base64.") from exc
    if raw_pem:
        return raw_pem.replace("\\n", "\n").encode("utf-8")
    raise RuntimeError("CampPhoto AI private signing key is not configured.")


def _load_signing_key(app: Flask) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(_private_key_bytes(app), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("Configured CampPhoto AI signing key is not Ed25519.")

    public_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = hashlib.sha256(public_der).hexdigest()
    expected = str(
        app.config.get(
            "EXPECTED_LICENSE_PUBLIC_KEY_SHA256",
            EXPECTED_LICENSE_PUBLIC_KEY_SHA256,
        )
    ).strip().lower()
    if not expected or not hmac.compare_digest(fingerprint, expected):
        raise RuntimeError(
            "Configured signing key does not match the public verification key "
            "bundled with the CampPhoto AI desktop application."
        )
    return key


def _sign_payload(app: Flask, payload: dict[str, Any]) -> dict[str, Any]:
    key = _load_signing_key(app)
    signature = key.sign(_canonical_payload(payload))
    return {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}


def _signing_key_ready(app: Flask) -> bool:
    try:
        _load_signing_key(app)
        return True
    except Exception:
        return False


def _parse_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _paystack_headers(secret_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}


def initialize_paystack_transaction(app: Flask, record: ActivationRequest) -> dict[str, Any]:
    secret_key = app.config["PAYSTACK_SECRET_KEY"]
    callback_url = f"{app.config['APP_BASE_URL'].rstrip('/')}/payment/callback"
    payload = {
        "email": record.email,
        "amount": str(ACTIVATION_FEE_KOBO),
        "currency": "NGN",
        "reference": record.payment_reference,
        "callback_url": callback_url,
        "metadata": json.dumps({
            "activation_token": record.public_token,
            "device_id": record.device_id,
            "product": "CampPhoto AI Pilot",
        }),
    }
    response = requests.post(
        f"{PAYSTACK_API}/transaction/initialize",
        headers=_paystack_headers(secret_key),
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("status") or not isinstance(body.get("data"), dict):
        raise RuntimeError(body.get("message") or "Paystack did not initialize the transaction.")
    return body["data"]


def verify_paystack_transaction(app: Flask, reference: str) -> dict[str, Any]:
    response = requests.get(
        f"{PAYSTACK_API}/transaction/verify/{reference}",
        headers=_paystack_headers(app.config["PAYSTACK_SECRET_KEY"]),
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("status") or not isinstance(body.get("data"), dict):
        raise RuntimeError(body.get("message") or "Paystack could not verify the transaction.")
    return body["data"]


def _check_admin_password(stored_hash: str, password: str) -> bool:
    stored_hash = (stored_hash or "").strip()
    if not stored_hash or not password:
        return False

    try:
        if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(
                password.encode("utf-8"),
                stored_hash.encode("utf-8"),
            )
        return check_password_hash(stored_hash, password)
    except (ValueError, TypeError):
        return False


def _configuration(app: Flask) -> dict[str, bool]:
    return {
        "database": bool(app.config.get("DATABASE_URL")),
        "paystack": bool(app.config.get("PAYSTACK_SECRET_KEY")),
        "signing_key": _signing_key_ready(app),
        "app_url": bool(app.config.get("APP_BASE_URL")),
        "flask_secret": bool(os.getenv("FLASK_SECRET_KEY") or app.config.get("TESTING")),
        "admin": bool(app.config.get("ADMIN_EMAIL") and app.config.get("ADMIN_PASSWORD_HASH")),
    }


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "setup-only-not-for-production"),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        PAYSTACK_SECRET_KEY=os.getenv("PAYSTACK_SECRET_KEY", ""),
        CAMPPHOTO_LICENSE_PRIVATE_KEY_B64=os.getenv("CAMPPHOTO_LICENSE_PRIVATE_KEY_B64", ""),
        CAMPPHOTO_LICENSE_PRIVATE_KEY_PEM=os.getenv("CAMPPHOTO_LICENSE_PRIVATE_KEY_PEM", ""),
        APP_BASE_URL=os.getenv("APP_BASE_URL", "").rstrip("/"),
        ADMIN_EMAIL=os.getenv("ADMIN_EMAIL", "").strip().lower(),
        ADMIN_PASSWORD_HASH=os.getenv("ADMIN_PASSWORD_HASH", ""),
        PILOT_LICENSE_DAYS=int(os.getenv("PILOT_LICENSE_DAYS", "45")),
        SUPPORT_PHONE=os.getenv("SUPPORT_PHONE", "09039930006"),
        SUPPORT_EMAIL=os.getenv("SUPPORT_EMAIL", "silabtechnologies@gmail.com"),
        EXPECTED_LICENSE_PUBLIC_KEY_SHA256=EXPECTED_LICENSE_PUBLIC_KEY_SHA256,
        MAX_CONTENT_LENGTH=MAX_REQUEST_BODY_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        SESSION_REFRESH_EACH_REQUEST=False,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get("TESTING"):
        app.config["SESSION_COOKIE_SECURE"] = True

    database_url = app.config.get("DATABASE_URL", "")
    engine = None
    SessionLocal = None
    if database_url:
        engine = create_engine(_normalise_database_url(database_url), poolclass=NullPool, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        Base.metadata.create_all(engine)
    app.extensions["portal_engine"] = engine
    app.extensions["portal_sessionmaker"] = SessionLocal

    def db():
        maker = app.extensions.get("portal_sessionmaker")
        if maker is None:
            abort(503, description="DATABASE_URL is not configured.")
        return maker()

    def audit(database, event: str, record: ActivationRequest | None = None, detail: str = "") -> None:
        database.add(AuditEvent(
            activation_request_id=record.id if record else None,
            event=event,
            detail=detail[:4000],
        ))

    def enforce_rate_limit(
        database,
        *,
        scope: str,
        identity: str,
        limit: int,
        window_minutes: int,
    ) -> None:
        secret = str(app.config["SECRET_KEY"]).encode("utf-8")
        material = f"{scope}|{identity}".encode("utf-8")
        key_hash = hmac.new(secret, material, hashlib.sha256).hexdigest()
        cutoff = utcnow() - timedelta(minutes=window_minutes)
        count = database.scalar(
            select(func.count(SecurityEvent.id)).where(
                SecurityEvent.scope == scope,
                SecurityEvent.key_hash == key_hash,
                SecurityEvent.created_at >= cutoff,
            )
        ) or 0
        if count >= limit:
            abort(429, description="Too many attempts. Try again later.")
        database.add(SecurityEvent(scope=scope, key_hash=key_hash))
        database.commit()

    def require_operational() -> None:
        config = _configuration(app)
        missing = [name for name in ("database", "paystack", "signing_key", "app_url") if not config[name]]
        if missing:
            abort(503, description="Portal setup is incomplete: " + ", ".join(missing))

    def issue_license(database, record: ActivationRequest, *, force: bool = False) -> dict[str, Any]:
        if record.revoked_at is not None or record.status == "revoked":
            raise RuntimeError("This activation has been revoked.")
        if record.license_json and not force:
            return json.loads(record.license_json)
        if record.status not in {"paid", "licensed"}:
            raise RuntimeError("A verified payment is required before issuing a licence.")

        today = date.today()
        expires = today + timedelta(days=int(app.config["PILOT_LICENSE_DAYS"]))
        license_id = "CPA-PILOT-" + uuid.uuid4().hex[:12].upper()
        payload = {
            "version": LICENSE_VERSION,
            "license_kind": LICENSE_KIND,
            "license_id": license_id,
            "device_id": record.device_id.strip().upper(),
            "camp_name": record.camp_name.strip(),
            "state": record.state.strip(),
            "batch_stream": record.batch_stream.strip(),
            "contact_name": record.contact_name.strip(),
            "contact": (record.phone or record.email).strip(),
            "payment_reference": (record.payment_reference or "").strip(),
            "activation_fee_ngn": ACTIVATION_FEE_NGN,
            "issued_on": today.isoformat(),
            "expires_on": expires.isoformat(),
            "issuer": ISSUER,
            "features": ["full_pilot_functionality", "offline_operation"],
        }
        document = _sign_payload(app, payload)
        record.license_id = license_id
        record.license_json = json.dumps(document, indent=2, ensure_ascii=False)
        record.issued_at = utcnow()
        record.expires_on = expires.isoformat()
        record.status = "licensed"
        audit(database, "license_issued", record, license_id)
        database.commit()
        return document

    def accept_verified_payment(database, record: ActivationRequest, data: dict[str, Any]) -> dict[str, Any]:
        if record.status == "revoked" or record.revoked_at is not None:
            raise RuntimeError("This activation has been revoked.")
        if record.status == "licensed" and record.license_json:
            return json.loads(record.license_json)

        if data.get("status") != "success":
            raise RuntimeError(f"Payment is not successful ({data.get('status', 'unknown')}).")
        if int(data.get("amount") or 0) != ACTIVATION_FEE_KOBO:
            raise RuntimeError("Verified payment amount does not match the activation fee.")
        if str(data.get("currency", "")).upper() != "NGN":
            raise RuntimeError("Verified payment currency is not NGN.")
        if str(data.get("reference", "")) != str(record.payment_reference or ""):
            raise RuntimeError("Verified payment reference does not match this activation request.")

        metadata = _parse_metadata(data.get("metadata"))
        token = str(metadata.get("activation_token", ""))
        if token != record.public_token:
            raise RuntimeError("Paystack metadata does not match this activation request.")
        device = str(metadata.get("device_id", "")).strip().upper()
        if device != record.device_id.strip().upper():
            raise RuntimeError("Paystack metadata device does not match this activation request.")

        customer = data.get("customer") or {}
        paystack_email = str(customer.get("email", "")).strip().lower()
        if paystack_email != record.email.strip().lower():
            raise RuntimeError("Paystack customer email does not match this activation request.")

        if record.status not in {"licensed", "revoked"}:
            record.status = "paid"
        record.paystack_status = "success"
        record.paid_at = record.paid_at or utcnow()
        audit(database, "payment_verified", record, record.payment_reference or "")
        database.commit()
        return issue_license(database, record)

    def find_by_reference(
        database,
        reference: str,
        *,
        for_update: bool = False,
    ) -> ActivationRequest | None:
        statement = select(ActivationRequest).where(
            ActivationRequest.payment_reference == reference
        )
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return database.scalar(statement)

    def create_request_from_values(values: dict[str, Any]) -> ActivationRequest:
        required = {
            "device_id": "Device ID", "camp_name": "Camp name", "state": "State",
            "batch_stream": "Batch / Stream", "contact_name": "Contact person", "email": "Email",
        }
        cleaned = {key: str(values.get(key, "")).strip() for key in required}
        missing = [label for key, label in required.items() if not cleaned[key]]
        if missing:
            raise ValueError("Missing: " + ", ".join(missing))
        if len(cleaned["camp_name"]) > 240:
            raise ValueError("Camp name is too long.")
        if len(cleaned["state"]) > 120:
            raise ValueError("State is too long.")
        if len(cleaned["batch_stream"]) > 160:
            raise ValueError("Batch / Stream is too long.")
        if len(cleaned["contact_name"]) > 200:
            raise ValueError("Contact person is too long.")
        if len(cleaned["email"]) > 240:
            raise ValueError("Email is too long.")
        phone = str(values.get("phone", "")).strip()
        if len(phone) > 80:
            raise ValueError("Phone number is too long.")
        if "@" not in cleaned["email"] or "." not in cleaned["email"].split("@")[-1]:
            raise ValueError("Enter a valid email address.")
        device_id = cleaned["device_id"].upper()
        if not DEVICE_ID_RE.fullmatch(device_id):
            raise ValueError(
                "Device ID must match CPA-XXXX-XXXX-XXXX-XXXX using hexadecimal characters."
            )
        return ActivationRequest(
            public_token=secrets.token_urlsafe(32),
            device_id=device_id,
            camp_name=cleaned["camp_name"],
            state=cleaned["state"],
            batch_stream=cleaned["batch_stream"],
            contact_name=cleaned["contact_name"],
            email=cleaned["email"].lower(),
            phone=phone,
            amount_ngn=ACTIVATION_FEE_NGN,
            payment_reference="CPA-" + date.today().strftime("%Y%m%d") + "-" + secrets.token_hex(6).upper(),
            status="created",
        )

    def start_payment(database, record: ActivationRequest) -> str:
        data = initialize_paystack_transaction(app, record)
        authorization_url = str(data.get("authorization_url", "")).strip()
        parsed = urlparse(authorization_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            hostname == "paystack.com" or hostname.endswith(".paystack.com")
        ):
            raise RuntimeError("Paystack returned an invalid authorization URL.")

        record.paystack_access_code = str(data.get("access_code", ""))
        record.payment_reference = str(data.get("reference") or record.payment_reference)
        record.status = "payment_initialized"
        audit(database, "payment_initialized", record, record.payment_reference or "")
        database.commit()
        return authorization_url

    def csrf_token() -> str:
        token = session.get("_csrf")
        if not token:
            token = secrets.token_urlsafe(24)
            session["_csrf"] = token
        return token

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["activation_fee_ngn"] = ACTIVATION_FEE_NGN

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; img-src 'self' data:; "
            "style-src 'self'; script-src 'none'",
        )
        if request.is_secure or str(app.config.get("APP_BASE_URL", "")).startswith("https://"):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        if not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def check_csrf() -> None:
        supplied = request.form.get("_csrf", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(supplied, expected):
            abort(400, description="Invalid form token. Reload the page and try again.")

    def require_desktop_api_request() -> None:
        if request.headers.get("X-CampPhoto-Client", "") != "desktop-v1":
            abort(400, description="Missing CampPhoto AI client header.")

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin_authenticated"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": "CampPhoto AI Licence Portal", "version": PORTAL_VERSION, "configuration": _configuration(app)})

    @app.get("/")
    def home():
        return render_template("index.html", config=_configuration(app), prefill_device=request.args.get("device_id", ""))

    @app.get("/guide")
    def user_guide():
        return render_template("user_guide.html")

    @app.post("/activate")
    def activate():
        check_csrf()
        require_operational()
        try:
            record = create_request_from_values(request.form)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("home"))
        with db() as database:
            enforce_rate_limit(
                database,
                scope="activation-create",
                identity=f"{record.device_id}|{record.email}",
                limit=5,
                window_minutes=15,
            )
            database.add(record)
            database.commit()
            database.refresh(record)
            audit(database, "activation_created", record)
            database.commit()
            try:
                authorization_url = start_payment(database, record)
            except Exception as exc:
                record.status = "payment_error"
                record.payment_error = str(exc)
                audit(database, "payment_initialization_failed", record, str(exc))
                database.commit()
                flash("Payment could not be started. Please try again or contact Silabs.", "error")
                return redirect(url_for("activation_status", token=record.public_token))
        return redirect(authorization_url)

    @app.get("/payment/callback")
    def payment_callback():
        require_operational()
        reference = request.args.get("reference") or request.args.get("trxref")
        if not reference:
            abort(400, description="Missing payment reference.")
        with db() as database:
            record = find_by_reference(database, reference)
            if record is None:
                abort(404)
            try:
                data = verify_paystack_transaction(app, reference)
                record = find_by_reference(database, reference, for_update=True)
                if record is None:
                    abort(404)
                accept_verified_payment(database, record, data)
                flash("Payment verified. Your CampPhoto AI licence is ready.", "success")
            except Exception as exc:
                record.paystack_status = "verification_error"
                record.payment_error = str(exc)
                audit(database, "payment_verification_failed", record, str(exc))
                database.commit()
                flash("Payment has not been verified yet. You can check again below.", "warning")
            return redirect(url_for("activation_status", token=record.public_token))

    @app.post("/webhooks/paystack")
    def paystack_webhook():
        secret_key = app.config.get("PAYSTACK_SECRET_KEY", "")
        if not secret_key:
            return ("", 503)
        raw = request.get_data(cache=False)
        expected = hmac.new(secret_key.encode("utf-8"), raw, hashlib.sha512).hexdigest()
        supplied = request.headers.get("x-paystack-signature", "")
        if not supplied or not hmac.compare_digest(expected, supplied):
            return ("", 401)
        try:
            event = json.loads(raw.decode("utf-8"))
        except Exception:
            return ("", 400)
        if event.get("event") != "charge.success":
            return ("", 200)
        reference = str((event.get("data") or {}).get("reference", ""))
        if not reference:
            return ("", 200)
        try:
            with db() as database:
                record = find_by_reference(database, reference)
                if record is None:
                    return ("", 200)
                verified = verify_paystack_transaction(app, reference)
                record = find_by_reference(database, reference, for_update=True)
                if record is None:
                    return ("", 200)
                accept_verified_payment(database, record, verified)
        except Exception:
            return ("", 500)
        return ("", 200)

    @app.get("/status/<token>")
    def activation_status(token: str):
        with db() as database:
            record = database.scalar(select(ActivationRequest).where(ActivationRequest.public_token == token))
            if record is None:
                abort(404)
            return render_template("status.html", item=record)

    @app.post("/status/<token>/verify")
    def activation_verify(token: str):
        check_csrf()
        require_operational()
        with db() as database:
            record = database.scalar(select(ActivationRequest).where(ActivationRequest.public_token == token))
            if record is None:
                abort(404)
            enforce_rate_limit(
                database,
                scope="payment-recheck",
                identity=record.public_token,
                limit=12,
                window_minutes=15,
            )
            if record.status != "licensed":
                try:
                    verified = verify_paystack_transaction(app, record.payment_reference or "")
                    record = database.scalar(
                        select(ActivationRequest)
                        .where(ActivationRequest.public_token == token)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                    if record is None:
                        abort(404)
                    accept_verified_payment(database, record, verified)
                    flash("Payment verified and licence issued.", "success")
                except Exception as exc:
                    record.payment_error = str(exc)
                    database.commit()
                    flash("Payment is not verified yet.", "warning")
        return redirect(url_for("activation_status", token=token))

    @app.get("/download/<token>")
    def download_license(token: str):
        with db() as database:
            record = database.scalar(select(ActivationRequest).where(ActivationRequest.public_token == token))
            if record is None:
                abort(404)
            if record.status != "licensed" or not record.license_json:
                abort(403)
            return send_file(
                BytesIO(record.license_json.encode("utf-8")),
                mimetype="application/json",
                as_attachment=True,
                download_name=f"{record.license_id or 'CampPhotoAI'}.cpa-license",
            )

    @app.post("/api/requests")
    def api_create_request():
        require_desktop_api_request()
        if not request.is_json:
            return jsonify({"ok": False, "error": "JSON request required."}), 415
        require_operational()
        try:
            record = create_request_from_values(request.get_json(silent=True) or {})
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        with db() as database:
            enforce_rate_limit(
                database,
                scope="activation-create",
                identity=f"{record.device_id}|{record.email}",
                limit=5,
                window_minutes=15,
            )
            database.add(record)
            database.commit()
            database.refresh(record)
            audit(database, "activation_created_api", record)
            database.commit()
            try:
                authorization_url = start_payment(database, record)
            except Exception as exc:
                record.status = "payment_error"
                record.payment_error = str(exc)
                database.commit()
                return jsonify({"ok": False, "error": "Unable to initialize payment."}), 502
            return jsonify({
                "ok": True,
                "request_token": record.public_token,
                "authorization_url": authorization_url,
                "reference": record.payment_reference,
                "amount_ngn": ACTIVATION_FEE_NGN,
            })

    @app.get("/api/requests/<token>")
    def api_request_status(token: str):
        require_desktop_api_request()
        with db() as database:
            record = database.scalar(select(ActivationRequest).where(ActivationRequest.public_token == token))
            if record is None:
                return jsonify({"ok": False, "error": "Activation request not found."}), 404
            payload: dict[str, Any] = {
                "ok": True, "status": record.status, "device_id": record.device_id,
                "camp_name": record.camp_name, "batch_stream": record.batch_stream,
                "reference": record.payment_reference, "expires_on": record.expires_on,
            }
            if record.status == "licensed" and record.license_json:
                payload["license_document"] = json.loads(record.license_json)
            return jsonify(payload)

    @app.post("/api/requests/<token>/verify")
    def api_verify_request(token: str):
        require_desktop_api_request()
        require_operational()
        with db() as database:
            record = database.scalar(select(ActivationRequest).where(ActivationRequest.public_token == token))
            if record is None:
                return jsonify({"ok": False, "error": "Activation request not found."}), 404
            enforce_rate_limit(
                database,
                scope="payment-recheck",
                identity=record.public_token,
                limit=12,
                window_minutes=15,
            )
            if record.status == "licensed" and record.license_json:
                return jsonify({"ok": True, "status": "licensed"})
            try:
                verified = verify_paystack_transaction(app, record.payment_reference or "")
                record = database.scalar(
                    select(ActivationRequest)
                    .where(ActivationRequest.public_token == token)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if record is None:
                    return jsonify({"ok": False, "error": "Activation request not found."}), 404
                accept_verified_payment(database, record, verified)
                return jsonify({"ok": True, "status": "licensed"})
            except Exception as exc:
                record.payment_error = str(exc)
                database.commit()
                return jsonify({"ok": False, "status": record.status, "error": "Payment is not verified yet."}), 409

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        config = _configuration(app)
        if request.method == "POST":
            check_csrf()
            if not config["admin"] or not config["flask_secret"] or not config["database"]:
                flash("Admin login is not configured.", "error")
                return redirect(url_for("admin_login"))
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            with db() as database:
                enforce_rate_limit(
                    database,
                    scope="admin-login",
                    identity=email,
                    limit=10,
                    window_minutes=15,
                )
            email_ok = hmac.compare_digest(email, app.config["ADMIN_EMAIL"])
            password_ok = email_ok and _check_admin_password(
                app.config["ADMIN_PASSWORD_HASH"],
                password,
            )
            if email_ok and password_ok:
                session.clear()
                session.permanent = True
                session["admin_authenticated"] = True
                session["admin_email"] = email
                csrf_token()
                return redirect(url_for("admin_dashboard"))
            flash("Invalid admin credentials.", "error")
        return render_template("admin_login.html", config=config)

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        check_csrf()
        session.clear()
        return redirect(url_for("admin_login"))

    @app.get("/admin/guide")
    @admin_required
    def admin_guide():
        return render_template("admin_guide.html")

    @app.get("/admin/")
    @admin_required
    def admin_dashboard():
        with db() as database:
            items = list(database.scalars(select(ActivationRequest).order_by(ActivationRequest.created_at.desc()).limit(200)))
            counts = {
                "all": len(items),
                "licensed": sum(1 for item in items if item.status == "licensed"),
                "pending": sum(1 for item in items if item.status in {"created", "payment_initialized", "payment_error", "paid"}),
                "revoked": sum(1 for item in items if item.status == "revoked"),
            }
            return render_template("admin_dashboard.html", items=items, counts=counts, config=_configuration(app))

    @app.get("/admin/request/<int:item_id>")
    @admin_required
    def admin_request_detail(item_id: int):
        with db() as database:
            record = database.get(ActivationRequest, item_id)
            if record is None:
                abort(404)
            events = list(database.scalars(
                select(AuditEvent).where(AuditEvent.activation_request_id == item_id).order_by(AuditEvent.created_at.desc())
            ))
            return render_template("admin_detail.html", item=record, events=events)

    @app.post("/admin/request/<int:item_id>/manual-approve")
    @admin_required
    def admin_manual_approve(item_id: int):
        check_csrf()
        with db() as database:
            record = database.get(ActivationRequest, item_id)
            if record is None:
                abort(404)
            if record.status == "revoked":
                flash("Revoked activations cannot be approved.", "error")
                return redirect(url_for("admin_request_detail", item_id=item_id))
            reference = request.form.get("payment_reference", "").strip()
            if not reference:
                flash("Enter the payment reference you personally verified.", "error")
                return redirect(url_for("admin_request_detail", item_id=item_id))
            existing = find_by_reference(database, reference, for_update=True)
            if existing is not None and existing.id != record.id:
                flash("That payment reference is already assigned to another activation.", "error")
                return redirect(url_for("admin_request_detail", item_id=item_id))
            record.payment_reference = reference
            record.paystack_status = "manual_admin_approval"
            record.paid_at = utcnow()
            record.status = "paid"
            audit(database, "manual_payment_approved", record, reference)
            database.commit()
            issue_license(database, record)
            flash("Payment marked verified and licence issued.", "success")
        return redirect(url_for("admin_request_detail", item_id=item_id))

    @app.post("/admin/request/<int:item_id>/reissue")
    @admin_required
    def admin_reissue(item_id: int):
        check_csrf()
        with db() as database:
            record = database.get(ActivationRequest, item_id)
            if record is None:
                abort(404)
            try:
                issue_license(database, record, force=True)
                flash("A new signed licence was issued.", "success")
            except Exception as exc:
                flash(str(exc), "error")
        return redirect(url_for("admin_request_detail", item_id=item_id))

    @app.post("/admin/request/<int:item_id>/revoke")
    @admin_required
    def admin_revoke(item_id: int):
        check_csrf()
        with db() as database:
            record = database.get(ActivationRequest, item_id)
            if record is None:
                abort(404)
            record.status = "revoked"
            record.revoked_at = utcnow()
            audit(database, "activation_revoked", record, "Existing imported offline licences remain valid until expiry.")
            database.commit()
            flash("Portal entitlement revoked. An already imported offline licence cannot be remotely disabled.", "warning")
        return redirect(url_for("admin_request_detail", item_id=item_id))

    @app.errorhandler(429)
    def too_many_requests(error):
        message = getattr(error, "description", "Too many attempts. Try again later.")
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": message}), 429
        return message, 429

    @app.errorhandler(503)
    def setup_required(error):
        return render_template(
            "setup.html", config=_configuration(app),
            message=getattr(error, "description", "Portal setup is incomplete.")
        ), 503

    return app
