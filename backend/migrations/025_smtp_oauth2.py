"""
Migration 025: Add OAuth2 (XOAUTH2) authentication columns to ``smtp_config``

Adds optional OAuth2 fields so SMTP can authenticate against providers that
no longer permit basic auth (Gmail, Microsoft 365 / Outlook.com).

Auth flow: Authorization Code + Refresh Token. The admin runs an interactive
consent once (UI button), the resulting refresh_token is stored encrypted,
and short-lived access tokens are minted on demand via ``services.smtp_oauth``.

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

# (column_name, sqlite_type, default_clause)
NEW_COLUMNS = [
    ("smtp_auth_method", "VARCHAR(20) NOT NULL DEFAULT 'password'", None),
    ("smtp_oauth_provider", "VARCHAR(20)", None),         # google | microsoft | custom
    ("smtp_oauth_tenant_id", "VARCHAR(100)", None),       # microsoft only
    ("smtp_oauth_client_id", "VARCHAR(255)", None),
    ("smtp_oauth_client_secret", "VARCHAR(1024)", None),  # encrypted at rest
    ("smtp_oauth_refresh_token", "VARCHAR(4096)", None),  # encrypted at rest
    ("smtp_oauth_authorize_url", "VARCHAR(512)", None),   # custom only
    ("smtp_oauth_token_url", "VARCHAR(512)", None),       # custom only
    ("smtp_oauth_scope", "VARCHAR(512)", None),           # custom only
    ("smtp_oauth_redirect_uri", "VARCHAR(512)", None),    # optional override
]

PG_TYPE_MAP = {
    "VARCHAR(20) NOT NULL DEFAULT 'password'": "VARCHAR(20) NOT NULL DEFAULT 'password'",
    "VARCHAR(20)": "VARCHAR(20)",
    "VARCHAR(100)": "VARCHAR(100)",
    "VARCHAR(255)": "VARCHAR(255)",
    "VARCHAR(512)": "VARCHAR(512)",
    "VARCHAR(1024)": "VARCHAR(1024)",
    "VARCHAR(4096)": "VARCHAR(4096)",
}


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='smtp_config'"
    )
    if not cur.fetchone():
        logger.info("Migration 025: smtp_config table absent, skipping")
        return

    for name, sqlite_type, _ in NEW_COLUMNS:
        if not _column_exists_sqlite(conn, 'smtp_config', name):
            conn.execute(f"ALTER TABLE smtp_config ADD COLUMN {name} {sqlite_type}")
            logger.info(f"Migration 025: added smtp_config.{name}")

    conn.commit()


def _upgrade_pg(engine):
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if 'smtp_config' not in set(insp.get_table_names()):
        logger.info("Migration 025: smtp_config table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('smtp_config')}
    with engine.begin() as conn:
        for name, sqlite_type, _ in NEW_COLUMNS:
            if name not in cols:
                pg_type = PG_TYPE_MAP.get(sqlite_type, sqlite_type)
                conn.execute(text(
                    f"ALTER TABLE smtp_config ADD COLUMN {name} {pg_type}"
                ))
                logger.info(f"Migration 025: added smtp_config.{name}")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op."""
    pass
