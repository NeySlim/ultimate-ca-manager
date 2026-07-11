"""Migration 054: WinRM admin channel for Microsoft CA connections (#185 phase A).

Adds to ``microsoft_cas`` an opt-in WinRM administration channel so UCM can run
CA management operations (revoke, unrevoke, publish CRL, inventory) via
``certutil``/PowerShell remoting. Credentials default to the connection's own,
with optional override fields for a dedicated least-privilege officer account.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_COLUMNS_SQLITE = [
    ("winrm_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
    ("winrm_host", "VARCHAR(500)"),
    ("winrm_port", "INTEGER DEFAULT 5986"),
    ("winrm_use_ssl", "BOOLEAN NOT NULL DEFAULT 1"),
    ("winrm_verify_ssl", "BOOLEAN NOT NULL DEFAULT 1"),
    ("winrm_transport", "VARCHAR(20) DEFAULT 'kerberos'"),
    ("winrm_username", "VARCHAR(500)"),
    ("winrm_password", "TEXT"),
    ("ca_config", "VARCHAR(500)"),
]

_COLUMNS_PG = [
    ("winrm_enabled", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("winrm_host", "VARCHAR(500)"),
    ("winrm_port", "INTEGER DEFAULT 5986"),
    ("winrm_use_ssl", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("winrm_verify_ssl", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("winrm_transport", "VARCHAR(20) DEFAULT 'kerberos'"),
    ("winrm_username", "VARCHAR(500)"),
    ("winrm_password", "TEXT"),
    ("ca_config", "VARCHAR(500)"),
]


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='microsoft_cas'"
    )
    if not cur.fetchone():
        logger.info("[054] microsoft_cas absent, skipping")
        return
    existing = {r[1] for r in conn.execute("PRAGMA table_info(microsoft_cas)").fetchall()}
    for name, ddl in _COLUMNS_SQLITE:
        if name not in existing:
            conn.execute(f"ALTER TABLE microsoft_cas ADD COLUMN {name} {ddl}")
    conn.commit()
    logger.info("[054] msca WinRM admin channel columns added (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'microsoft_cas' not in insp.get_table_names():
        logger.info("[054] microsoft_cas absent, skipping")
        return
    existing = {c['name'] for c in insp.get_columns('microsoft_cas')}
    for name, ddl in _COLUMNS_PG:
        if name not in existing:
            conn.execute(text(f"ALTER TABLE microsoft_cas ADD COLUMN {name} {ddl}"))
    logger.info("[054] msca WinRM admin channel columns added (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    names = [name for name, _ in _COLUMNS_SQLITE]
    if isinstance(conn, sqlite3.Connection):
        for name in names:
            try:
                conn.execute(f"ALTER TABLE microsoft_cas DROP COLUMN {name}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    else:
        from sqlalchemy import text
        for name in names:
            conn.execute(text(f"ALTER TABLE microsoft_cas DROP COLUMN IF EXISTS {name}"))
