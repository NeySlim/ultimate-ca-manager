"""Migration 034: add offline columns to certificate_authorities.

Adds `offline`, `offline_reason`, `offline_mode` for offline-CA support.

Dual-backend (SQLite + PostgreSQL). Idempotent: per-column existence check
before each ADD COLUMN.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_COLUMNS_SQLITE = [
    ("offline", "BOOLEAN DEFAULT 0"),
    ("offline_reason", "TEXT"),
    ("offline_mode", "TEXT"),
]

_COLUMNS_PG = [
    ("offline", "BOOLEAN DEFAULT FALSE"),
    ("offline_reason", "TEXT"),
    ("offline_mode", "TEXT"),
]


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='certificate_authorities'"
    )
    if not cur.fetchone():
        logger.info("[034] certificate_authorities absent, skipping (fresh)")
        return

    cur = conn.execute("PRAGMA table_info(certificate_authorities)")
    existing = {row[1] for row in cur.fetchall()}
    for name, ddl in _COLUMNS_SQLITE:
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}")
        logger.info(f"[034] added column {name} (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'certificate_authorities' not in set(insp.get_table_names()):
        logger.info("[034] certificate_authorities absent, skipping (fresh PG)")
        return

    existing = {c['name'] for c in insp.get_columns('certificate_authorities')}
    for name, ddl in _COLUMNS_PG:
        if name in existing:
            continue
        conn.execute(text(f"ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}"))
        logger.info(f"[034] added column {name} (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    cols = ["offline", "offline_reason", "offline_mode"]
    if isinstance(conn, sqlite3.Connection):
        for c in cols:
            try:
                conn.execute(f"ALTER TABLE certificate_authorities DROP COLUMN {c}")
            except Exception:
                pass
        conn.commit()
    else:
        from sqlalchemy import text
        for c in cols:
            conn.execute(text(f"ALTER TABLE certificate_authorities DROP COLUMN IF EXISTS {c}"))
