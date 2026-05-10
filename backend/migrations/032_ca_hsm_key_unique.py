"""Migration 032: enforce one-to-one between CA and HSM key.

Closes a TOCTOU race in services/ca/ca_creation.py where two concurrent
CA-create requests could both pass the `CA.query.filter_by(hsm_key_id=...)`
check and end up bound to the same HSM key. Adds a partial unique index
(NULL allowed for local-key CAs).

NOTE: The original (pre-v2.155) version of this migration referenced a
non-existent table name (`cas`); the real table is `certificate_authorities`.
The migration therefore silently no-op'd on every install. Migration 035
(reconcile) creates the correct index. This file remains for tracking
purposes; the upgrade body is now a no-op on both backends.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def upgrade(conn):
    # Intentional no-op. See migration 035 for the actual unique-index
    # creation against the correct `certificate_authorities` table.
    logger.info(
        "[032] no-op (original used wrong table name; healed by migration 035)"
    )


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute("DROP INDEX IF EXISTS uq_ca_hsm_key_id")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("DROP INDEX IF EXISTS uq_ca_hsm_key_id"))
