"""Migration 062: add fail-closed OIDC ID token verification settings.

Adds the configured issuer, optional explicit JWKS URI, and the explicit
compatibility opt-out. Verification defaults to enabled.

Dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_SQLITE_COLUMNS = (
    ('oauth2_issuer', 'VARCHAR(500)'),
    ('oauth2_jwks_uri', 'VARCHAR(500)'),
    ('id_token_verify', 'BOOLEAN NOT NULL DEFAULT 1'),
)
_PG_COLUMNS = (
    ('oauth2_issuer', 'VARCHAR(500)'),
    ('oauth2_jwks_uri', 'VARCHAR(500)'),
    ('id_token_verify', 'BOOLEAN NOT NULL DEFAULT TRUE'),
)


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if 'pro_sso_providers' not in tables:
        logger.info('[062] pro_sso_providers absent, skipping (SQLite)')
        return

    columns = {
        row[1] for row in conn.execute(
            'PRAGMA table_info(pro_sso_providers)'
        ).fetchall()
    }
    for name, column_type in _SQLITE_COLUMNS:
        if name not in columns:
            conn.execute(
                f'ALTER TABLE pro_sso_providers ADD COLUMN {name} {column_type}'
            )
    conn.commit()
    logger.info('[062] added OIDC verification settings (SQLite)')


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if 'pro_sso_providers' not in set(inspector.get_table_names()):
        logger.info('[062] pro_sso_providers absent, skipping (PostgreSQL)')
        return

    columns = {
        column['name']
        for column in inspector.get_columns('pro_sso_providers')
    }
    for name, column_type in _PG_COLUMNS:
        if name not in columns:
            conn.execute(text(
                f'ALTER TABLE pro_sso_providers ADD COLUMN {name} {column_type}'
            ))
    logger.info('[062] added OIDC verification settings (PostgreSQL)')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Keep security settings when rolling code back."""
    pass
