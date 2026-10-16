# CampPhoto AI Licence Portal

Flask/Vercel control plane for CampPhoto AI pilot monetization.

## Automated flow

1. The customer submits the CampPhoto AI Device ID and camp details.
2. The portal initializes a fixed NGN 10,000 Paystack transaction on the server.
3. Paystack redirects back to the portal and also sends a signed webhook.
4. The portal verifies the transaction against Paystack before granting entitlement.
5. The portal creates the existing Ed25519-signed `.cpa-license`.
6. The customer can download the licence while the Windows app continues to validate it fully offline.
7. Silabs gets an admin dashboard, audit trail, manual fallback approval, reissue, and server-side revocation.

## Required Vercel environment variables

- `DATABASE_URL`: persistent PostgreSQL.
- `PAYSTACK_SECRET_KEY`: start with a Paystack test secret key.
- `CAMPPHOTO_LICENSE_PRIVATE_KEY_B64`: base64 of the same private key whose public key is bundled in CampPhoto AI.
- `APP_BASE_URL`: the production Vercel URL, no trailing slash.
- `FLASK_SECRET_KEY`: long random secret for admin sessions.
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD_HASH`
- Optional: `PILOT_LICENSE_DAYS` (default 45), `SUPPORT_PHONE`, `SUPPORT_EMAIL`.

Generate the password hash:

```bash
python tools/generate_admin_password_hash.py
```

Encode the signing key:

```bash
python tools/encode_private_key.py ../license_keys/CampPhotoAI_PILOT_PRIVATE_KEY.pem
```

Never commit either the private key or its base64 value.

## Paystack

Set the webhook URL in Paystack to:

```text
https://YOUR-PORTAL.vercel.app/webhooks/paystack
```

The portal checks Paystack's `x-paystack-signature` using HMAC SHA-512 and then independently calls the transaction verification endpoint before issuing a licence.

Start with test keys. Only switch to live keys after a complete test transaction produces a licence accepted by the Windows app.

## Local run

```bat
cd portal
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
flask --app app run --debug
```

## Security notes

- Paystack secret keys and the CampPhoto private signing key are server-only.
- A successful browser redirect alone never grants a licence.
- The public activation token is high entropy and acts as a status/download capability.
- Admin state-changing forms use CSRF tokens.
- Server-side revocation cannot invalidate a licence already imported by an intentionally offline desktop. It blocks future downloads/reissues; the signed licence remains valid until expiry.
