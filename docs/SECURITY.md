# Security

## Path traversal

Participant names/IDs become folder names. Two layers prevent a crafted
name from writing outside the output directory:

1. `sanitize_filename()` strips path separators (`/`, `\`), null bytes,
   and `..` sequences from any name before it's used as a folder/file
   component.
2. `safe_output_path()` re-resolves the final path and raises
   `ValueError` if it isn't actually inside the configured output root --
   defense in depth that doesn't rely on step 1 alone.

Both are unit-tested in `tests/unit/test_file_utils.py`.

## SQL injection

All database access goes through SQLAlchemy's ORM query API
(`session.query(...)`, `select(...)`, `session.get(...)`) or the ORM's
own parameter binding -- there is no raw SQL string built from user input
anywhere in this codebase. The one raw SQL statement that exists
(`PRAGMA foreign_keys=ON` in `app/database/db.py`) is a fixed string with
no interpolated input. The Participants screen's search box (Phase 5,
`app/services/participant_management.py::search_participants`) is the
first place free-form user text reaches a query directly -- it uses
`Column.ilike()`, which parameter-binds the search text rather than
interpolating it, so `%`/`_` wildcards work as LIKE wildcards but
anything SQL-metacharacter-like (`'`, `;`, `--`) is just treated as
literal text. Verified directly with injection-style inputs (`'; DROP
TABLE participants; --` etc.) against a real database -- all correctly
returned zero results without affecting the table.

## Logging

- Structured logs at DEBUG/INFO/WARNING/ERROR/CRITICAL
  (`app/utilities/logging_config.py`).
- A dedicated `camp_photo_ai.audit` logger records registration,
  processing start/completion, every match decision's reason, every
  human review action (confirm/reject/reassign), and participant
  deletion, to `logs/audit.log`.
- `RedactBiometricFilter` scans every log line for anything that looks
  like a long float vector and replaces it with `[REDACTED_VECTOR]`
  before it's written -- a safety net against an embedding accidentally
  ending up in a log call, on top of the coding convention of never
  logging `.vector`/`.embedding` fields directly.

## Deletion

`delete_participant` uses a single transaction with `ON DELETE CASCADE`
foreign keys, so a participant and their embeddings/match records are
removed atomically -- there's no window where a crash could leave
orphaned embeddings behind after the parent participant row is gone.

## No telemetry

The app makes no network calls in this build (see `docs/PRIVACY.md`).
There is no analytics/telemetry code path to disable, because none
exists.

## What isn't hardened yet

- **No database encryption at rest.** `data/camp_photo_ai.db` is a plain
  SQLite file. Protect it with OS-level file permissions and disk
  encryption in the meantime.
- **No in-app access-control layer** (e.g. per-operator logins) -- this
  build assumes one trusted operator per machine, consistent with the
  CLI-only interface so far. Worth revisiting once the multi-user GUI
  exists.
- **No fuzz/adversarial-input test pass yet** -- `tests/security/` is
  scoped but not implemented (see `tests/security/README.md`).

Report issues by opening them against this project directly -- there's no
separate disclosure process set up yet.
