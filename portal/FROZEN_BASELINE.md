# CampPhoto AI Licence Portal v1.0.0 Frozen Baseline

This file defines the production-freeze boundary for the CampPhoto AI licensing portal.

## Frozen scope

The v1.0.0 portal is limited to:

- Camp/device activation requests.
- Fixed NGN 10,000 Paystack checkout.
- Server-side Paystack verification.
- Signed, device-bound offline licence issuance.
- Licence status/download.
- Silabs admin login and activation administration.
- Manual payment fallback approval.
- Reissue, server-side revocation, and audit history.
- Configuration/health diagnostics.

No new product features should be added to this baseline. Changes after freeze should be limited to security fixes, defects, provider compatibility, configuration, tests, and operational reliability.

## Security invariants

1. The CampPhoto AI Ed25519 private key exists only in the server environment.
2. The server derives the public key from that private key and refuses to issue licences unless its SHA-256 fingerprint matches the public key bundled with the desktop application.
3. Browser redirects never grant entitlement by themselves.
4. Successful transactions must be independently verified against Paystack.
5. Amount must equal NGN 10,000 and currency must be NGN.
6. Paystack metadata must match the activation token and Device ID.
7. Paystack customer email must match the activation request email.
8. Webhook bodies must pass Paystack HMAC SHA-512 signature verification.
9. Payment/licence mutation paths use database row locks and idempotent issuance.
10. Payment references are unique and cannot be manually reused across activations.
11. Customer/admin HTML mutations use CSRF protection.
12. Public desktop API mutations require the CampPhoto client header as a browser-CSRF barrier.
13. Activation creation, payment rechecks, and admin login are persistently throttled in PostgreSQL.
14. Session cookies are HttpOnly, SameSite=Lax, Secure in production, and admin sessions expire.
15. Dynamic responses are no-store and include restrictive CSP, frame, referrer, MIME, permissions and HSTS headers.
16. Request bodies are capped at 64 KiB.
17. Input lengths and Device ID format are validated before persistence.

## Expected desktop verification key fingerprint

The frozen portal expects this SHA-256 fingerprint of the DER-encoded Ed25519 public key:

`b5a16e159d90fe0a99dd4c05f5bac03d8d13b1695f870d049a172f30a815c1be`

Changing the desktop licence key pair is a release-breaking operation and requires a coordinated desktop + portal release.

## Known operational constraints

- PostgreSQL is mandatory for production persistence and abuse throttling.
- Paystack test mode must be proven end-to-end before using a live secret key.
- A licence already imported into an intentionally offline desktop cannot be remotely revoked before its signed expiry date.
- Server-side revocation blocks future downloads/reissues and protects subsequent online operations.
- The portal does not store card details; Paystack handles checkout.
- The desktop client header is not an authentication secret. Its purpose is to stop ordinary cross-site browser form abuse of the JSON API.

## Change policy after freeze

Accept only:
- security patches;
- verified defects;
- dependency/provider compatibility fixes;
- operational configuration changes;
- test coverage;
- logging/observability that does not alter the entitlement model;
- user/admin documentation and tutorials that do not alter payment, entitlement, signing, or device-binding behavior.

Anything else belongs in a later version and should not be slipped into v1.0.0 because software has suffered enough from "one tiny feature before release."
