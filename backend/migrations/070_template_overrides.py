"""Migration 070: per-certificate template override tracking.

Adds certificates.template_overrides (TEXT, JSON array of field names).
Populated at issuance when key type / validity / digest explicitly diverge
from the values declared by the linked certificate template. NULL means the
certificate matches its template (or was not issued from one). The value is
frozen at issuance — a template edited later does not retroactively change it.

Dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if 'certificates' not in tables:
        logger.info('[070] certificates absent, skipping (SQLite)')
        return

    columns = {
        row[1] for row in conn.execute(
            'PRAGMA table_info(certificates)'
        ).fetchall()
    }
    if 'template_overrides' not in columns:
        conn.execute(
            'ALTER TABLE certificates ADD COLUMN template_overrides TEXT'
        )
    conn.commit()
    logger.info('[070] added certificates.template_overrides (SQLite)')


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if 'certificates' not in set(inspector.get_table_names()):
        logger.info('[070] certificates absent, skipping (PostgreSQL)')
        return

    columns = {
        column['name'] for column in inspector.get_columns('certificates')
    }
    if 'template_overrides' not in columns:
        conn.execute(text(
            'ALTER TABLE certificates ADD COLUMN template_overrides TEXT'
        ))
    logger.info('[070] added certificates.template_overrides (PostgreSQL)')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Keep the column when rolling application code back."""
    pass
