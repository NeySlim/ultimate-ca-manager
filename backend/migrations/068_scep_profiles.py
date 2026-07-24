"""Migration 068: scep_profiles table (issue #228).

Named SCEP endpoints: each profile is served at /scep/<url_slug>/pkiclient.exe
and binds its own CA, optional certificate template, challenge password
(encrypted at rest) and approval policy. The unlabelled /scep endpoints keep
serving the global SystemConfig-based configuration.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS scep_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    url_slug VARCHAR(64) NOT NULL UNIQUE,
    description VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT 1,
    ca_refid VARCHAR(36) NOT NULL REFERENCES certificate_authorities(refid),
    template_id INTEGER,
    challenge_password TEXT,
    challenge_generated_at DATETIME,
    auto_approve BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME,
    created_by VARCHAR(80),
    updated_at DATETIME,
    updated_by VARCHAR(80)
)
"""

_PG_DDL = """
CREATE TABLE IF NOT EXISTS scep_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    url_slug VARCHAR(64) NOT NULL UNIQUE,
    description VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ca_refid VARCHAR(36) NOT NULL REFERENCES certificate_authorities(refid),
    template_id INTEGER,
    challenge_password TEXT,
    challenge_generated_at TIMESTAMP,
    auto_approve BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP,
    created_by VARCHAR(80),
    updated_at TIMESTAMP,
    updated_by VARCHAR(80)
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_scep_profiles_url_slug ON scep_profiles(url_slug)",
    "CREATE INDEX IF NOT EXISTS ix_scep_profiles_ca_refid ON scep_profiles(ca_refid)",
)


def _upgrade_sqlite(conn):
    conn.execute(_SQLITE_DDL)
    for ddl in _INDEXES:
        conn.execute(ddl)
    conn.commit()
    logger.info("[068] created scep_profiles (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import text
    conn.execute(text(_PG_DDL))
    for ddl in _INDEXES:
        conn.execute(text(ddl))
    logger.info("[068] created scep_profiles (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute("DROP TABLE IF EXISTS scep_profiles")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("DROP TABLE IF EXISTS scep_profiles"))
