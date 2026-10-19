"""Migration 103: SAML responses checked in strict mode.

`pro_sso_saml_message_ids` holds the AuthnRequest ids awaiting a response and
the assertion ids already consumed, shared by every worker. IdP-initiated
logins become an explicit per-provider opt-in, off by default.
"""

import sqlite3

pg_compatible = True

_TABLE_SQLITE = """
    CREATE TABLE IF NOT EXISTS pro_sso_saml_message_ids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind VARCHAR(16) NOT NULL,
        message_id VARCHAR(256) NOT NULL,
        provider_id INTEGER NOT NULL,
        expires_at DATETIME NOT NULL,
        CONSTRAINT uq_saml_message_kind_id UNIQUE (kind, message_id)
    )
"""

_TABLE_PG = """
    CREATE TABLE IF NOT EXISTS pro_sso_saml_message_ids (
        id SERIAL PRIMARY KEY,
        kind VARCHAR(16) NOT NULL,
        message_id VARCHAR(256) NOT NULL,
        provider_id INTEGER NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        CONSTRAINT uq_saml_message_kind_id UNIQUE (kind, message_id)
    )
"""

_INDEX = ("CREATE INDEX IF NOT EXISTS ix_pro_sso_saml_message_ids_expires_at "
          "ON pro_sso_saml_message_ids (expires_at)")


def _upgrade_sqlite(conn):
    conn.execute(_TABLE_SQLITE)
    conn.execute(_INDEX)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'pro_sso_providers' in tables:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pro_sso_providers)")}
        if 'saml_allow_idp_initiated' not in columns:
            conn.execute("ALTER TABLE pro_sso_providers ADD COLUMN "
                         "saml_allow_idp_initiated BOOLEAN NOT NULL DEFAULT 0")
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    conn.execute(text(_TABLE_PG))
    conn.execute(text(_INDEX))
    if 'pro_sso_providers' in inspect(conn).get_table_names():
        conn.execute(text(
            "ALTER TABLE pro_sso_providers ADD COLUMN IF NOT EXISTS "
            "saml_allow_idp_initiated BOOLEAN NOT NULL DEFAULT FALSE"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the table and the column.
    pass
