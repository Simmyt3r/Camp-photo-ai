# Privacy

CampPhoto AI processes biometric data (face embeddings) as its core
function. This document describes what's collected, why, and what
controls exist in this build.

## What's collected

- **Photographs**: never modified or moved. The app only ever *copies*
  matched photos into output folders; originals are untouched.
- **Reference photos** (registration): read once to generate an
  embedding. The app does not keep a separate copy of reference photos
  itself -- operators may still have their own copies wherever the
  source files came from.
- **Face embeddings**: a 512-number vector per reference photo, stored as
  an opaque binary blob in the local SQLite database
  (`reference_embeddings.vector`). This is the primary long-term
  biometric representation the app keeps.
- **Reference-photo thumbnails** (added for the Phase 2 review screen): a
  small (~200px, JPEG-compressed) copy of each reference photo, stored
  alongside its embedding (`reference_embeddings.thumbnail`). This exists
  so a human reviewer can see who a suggested participant actually is
  without the app retaining the original, full-resolution reference
  photo file. It's a deliberate, scoped exception to "we don't keep
  reference photos" -- weigh whether a low-res thumbnail is acceptable
  for your deployment; it's deleted by the same cascade as everything
  else when a participant is deleted.
- **Participant metadata**: ID, name, optional registration
  number/category -- stored in plain text in the local database.
- **Match records**: which photo, which participant, what score, and why
  -- kept so the false-positive-protection logic and any human
  correction is auditable later.

## Local by default, always

Nothing in this codebase makes an HTTP request to send a photo or an
embedding anywhere. `Settings.allow_external_api` exists as a switch for
a *future* integration and defaults to `False`; no code currently checks
or acts on it, because no cloud code path exists yet. If a cloud
integration is ever added, it must require this flag plus a separate,
explicit per-run confirmation -- never on by default.

## Consent

`register` (CLI) and the Registration screen (GUI) both set
`Participant.consent_given = True` at creation time -- neither actually
captures or verifies consent, they just record that the operator
confirmed it happened. This build assumes the operator has already
obtained the participant's consent before registering them (e.g.
verbally at a physical registration desk, or via a paper/digital form)
-- there's still no in-app consent-capture UI (e.g. a signature/checkbox
step with a timestamp) in either interface. Don't register someone's
photos without having actually asked them.

## Deletion

`delete_participant` deletes the participant row and, via `ON DELETE
CASCADE` foreign keys, every `ReferenceEmbedding` and `MatchRecord` that
points to them, in the same transaction. There is no "soft delete" --
once a participant is deleted, their embeddings are gone from the
database. The one thing deletion does *not* touch is photos already
copied into their output folder before deletion; those are ordinary
files at that point and need to be removed separately if required.

## Treat embeddings as sensitive, not as "just numbers"

A face embedding is a biometric identifier, not an anonymous data point
-- it can be compared against other embeddings to re-identify someone,
which is exactly what this app is for. It's stored as an opaque blob and
is filtered out of every log line (`RedactBiometricFilter` in
`app/utilities/logging_config.py`), but the SQLite database file itself
is **not encrypted at rest** in this build. Give `data/camp_photo_ai.db`
the same access controls you'd give any sensitive personal-data file
(disk encryption, restricted file permissions, no cloud-synced folders)
until database-level encryption is added. The same applies to the
reference-photo thumbnails described above -- they're a smaller,
lower-resolution artifact than the original photos, but they're still
personally identifying images of registered participants.

## Participant IDs over personal info

Internally, matching and file operations key off `participant_id`
wherever possible (folder names are `{participant_id}_{name}`, not name
alone) so renaming a participant doesn't silently orphan their photos,
and so the name field is the only place personal-name text actually
lives in the pipeline.

## What isn't built yet

- In-app consent capture UI (a real signature/checkbox-with-timestamp step, not just the `consent_given` flag)
- Configurable, automatic retention/expiry (e.g. "delete all data 30
  days after the event")
- Database encryption at rest
- A full "what does the app know about me" export -- the Participants
  screen (Phase 5) can export a participant's *matched photos* as a zip,
  but not a structured export of their stored metadata/registration
  info together in one place (their embedding vectors themselves should
  never be exposed regardless -- see "Avoid exposing biometric
  embeddings through the UI" in the original spec).
- Automatic cleanup of webcam captures: the registration screen's camera
  capture button (Phase 2) saves each snapshot as a JPEG under
  `data/captures/` so it can be treated like any imported photo. These
  files are not deleted automatically, including for photos that get
  rejected (no face / multiple faces) or that belong to a participant
  who's later deleted -- clear out `data/captures/` periodically by hand
  for now.

These are reasonable next additions once further GUI/backend work continues.
