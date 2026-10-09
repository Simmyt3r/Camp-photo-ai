# CampPhoto AI - Phase One Pilot Monetization

## Commercial offer

CampPhoto AI Pilot Activation: N10,000.

Scope: one Windows device, one camp, one batch/stream cycle, full pilot functionality, offline operation after activation, and basic pilot support. The N10,000 amount is an activation fee for the pilot, not a lifetime software purchase.

## Customer payment and activation flow

1. Install and open CampPhoto AI.
2. Accept the user agreement.
3. The activation screen displays the Device ID.
4. Obtain the current Silabs bank-transfer details through the official support contacts shown in the app.
5. Pay N10,000.
6. Enter camp, state, batch/stream, contact details, and the bank/payment reference.
7. Click Copy activation request and send the copied text to Silabs.
8. Silabs confirms the transfer manually.
9. Silabs issues a signed .cpa-license file using the admin tool.
10. Import the licence file. CampPhoto AI validates the signature, Device ID, issue date, and expiry date completely offline.

## Private issuing key

The application contains only assets/license_public_key.pem. The matching private key must never be committed to GitHub, bundled in a Windows build, sent to a customer, or pasted into support chats.

Store the private key locally at:

    license_keys/CampPhotoAI_PILOT_PRIVATE_KEY.pem

The license_keys directory is ignored by Git.

## Issue a licence

After manually confirming payment, run:

    python scripts/license_admin.py issue --device-id CPA-XXXX-XXXX-XXXX-XXXX --camp "NYSC Benue Orientation Camp" --state "Benue" --batch "2026 Batch C Stream I" --contact-name "Camp Operator" --contact "08000000000" --payment-reference "BANK-REFERENCE" --expires-on "2026-12-31" --output "Benue-Batch-C.cpa-license"

Send only the resulting .cpa-license file to the customer.

## Reissuing

If the licensed computer genuinely fails, collect the replacement computer's new Device ID, verify the customer and camp, and issue a replacement licence. The old licence remains bound to the old Device ID.

## Security model

Ed25519 signatures prevent a customer from editing the camp, device, or expiry without invalidating the licence signature. The private signing key stays with Silabs. The customer application can verify licences with the public key but cannot mint new valid licences.

Phase one intentionally uses manual payment verification. Automated payment and entitlement issuance belong to a later phase after the pilot proves demand.
