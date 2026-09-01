"""Database engine/session management."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.database.models import Base

logger = logging.getLogger("camp_photo_ai.database")

_engine = None
_SessionLocal = None


def _auto_migrate_add_missing_columns(engine) -> None:
    """Lightweight, additive-only schema sync for SQLite: adds any column
    that's declared on a model but missing from the actual table. Not a
    real migration system -- it can't rename/drop/retype columns, and it
    skips any new column that's NOT NULL with no default (adding that
    safely to a table that may already have rows isn't possible without
    knowing what value to backfill, so it's logged and left alone rather
    than guessed at). Covers the common early-development case of adding
    a new nullable column to an existing table, e.g. so a `data/
    camp_photo_ai.db` created under Phase 1 keeps working after Phase 2
    added MatchRecord.bbox_* and ReferenceEmbedding.thumbnail."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table -- create_all() already handled it
            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                if not column.nullable and column.default is None:
                    logger.warning(
                        "Column %s.%s is new, NOT NULL, and has no default -- "
                        "skipping auto-migration. If this causes errors, delete "
                        "the database file and let it be recreated fresh.",
                        table.name, column.name,
                    )
                    continue
                col_type = column.type.compile(engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}'))
                logger.info("Auto-migrated: added column %s.%s", table.name, column.name)


def init_engine(database_path: str | None = None):
    global _engine, _SessionLocal
    settings = get_settings()
    db_path = Path(database_path or settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)

    # SQLite disables foreign-key enforcement by default. Without this,
    # ON DELETE CASCADE (participant -> embeddings/match records) silently
    # does nothing, which would leave orphaned biometric data behind on
    # deletion -- see docs/PRIVACY.md.
    @event.listens_for(_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(_engine)
    _auto_migrate_add_missing_columns(_engine)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    logger.info("Database initialised at %s", db_path)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


@contextmanager
def get_session() -> Session:
    if _SessionLocal is None:
        init_engine()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
