"""Migration 111: tables for the DNS UPDATE (RFC 2136) listener.

``acme_dns_update_keys`` holds TSIG keys bound to an ACME proxy account
(``secret`` is encrypted by the application). ``acme_proxy_dns_challenges``
holds the TXT values a client may publish for a proxy order.

Multi-backend convention: runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLES = ('acme_proxy_dns_challenges', 'acme_dns_update_keys')

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_acme_dns_update_keys_acme_client_account_id "
    "ON acme_dns_update_keys (acme_client_account_id)",
    "CREATE INDEX IF NOT EXISTS ix_acme_dns_update_keys_eab_credential_id "
    "ON acme_dns_update_keys (eab_credential_id)",
    "CREATE INDEX IF NOT EXISTS ix_acme_dns_update_keys_status "
    "ON acme_dns_update_keys (status)",
    "CREATE INDEX IF NOT EXISTS ix_acme_proxy_dns_challenges_order_id "
    "ON acme_proxy_dns_challenges (order_id)",
    "CREATE INDEX IF NOT EXISTS ix_acme_proxy_dns_challenges_acme_client_account_id "
    "ON acme_proxy_dns_challenges (acme_client_account_id)",
    "CREATE INDEX IF NOT EXISTS ix_acme_proxy_dns_challenges_record_name "
    "ON acme_proxy_dns_challenges (record_name)",
    "CREATE INDEX IF NOT EXISTS ix_acme_proxy_dns_challenges_zone_name "
    "ON acme_proxy_dns_challenges (zone_name)",
    "CREATE INDEX IF NOT EXISTS idx_acme_proxy_dns_status_expires "
    "ON acme_proxy_dns_challenges (status, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_acme_proxy_dns_expires "
    "ON acme_proxy_dns_challenges (expires_at)",
)


def _tables(pk, ts, false):
    keys = f"""
    CREATE TABLE IF NOT EXISTS acme_dns_update_keys (
        id {pk},
        acme_client_account_id INTEGER NOT NULL
            REFERENCES acme_client_accounts (id) ON DELETE CASCADE,
        eab_credential_id INTEGER
            REFERENCES acme_eab_credentials (id) ON DELETE CASCADE,
        eab_bound BOOLEAN NOT NULL DEFAULT {false},
        name VARCHAR(255) NOT NULL UNIQUE,
        algorithm VARCHAR(32) NOT NULL DEFAULT 'hmac-sha256',
        secret TEXT NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'active',
        created_at {ts} DEFAULT CURRENT_TIMESTAMP,
        created_by_user_id INTEGER,
        last_used_at {ts},
        revoked_at {ts},
        notes TEXT
    )"""
    challenges = f"""
    CREATE TABLE IF NOT EXISTS acme_proxy_dns_challenges (
        id {pk},
        order_id INTEGER NOT NULL
            REFERENCES acme_client_orders (id) ON DELETE CASCADE,
        acme_client_account_id INTEGER,
        account_id VARCHAR(64),
        client_jwk_thumbprint VARCHAR(128) NOT NULL,
        identifier VARCHAR(255) NOT NULL,
        record_name VARCHAR(255) NOT NULL,
        txt_value VARCHAR(64) NOT NULL,
        zone_name VARCHAR(255) NOT NULL,
        upstream_challenge_url TEXT,
        status VARCHAR(16) NOT NULL DEFAULT 'pending',
        created_at {ts} DEFAULT CURRENT_TIMESTAMP,
        expires_at {ts} NOT NULL,
        client_confirmed_at {ts},
        CONSTRAINT uq_acme_proxy_dns_challenge
            UNIQUE (order_id, record_name, txt_value)
    )"""
    return (keys, challenges)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        for stmt in _tables('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME', '0') + _INDEXES:
            conn.execute(stmt)
        conn.commit()
        logger.info("Migration 111: ensured DNS UPDATE tables (SQLite)")
    else:
        from sqlalchemy import text
        for stmt in _tables('SERIAL PRIMARY KEY', 'TIMESTAMP', 'FALSE') + _INDEXES:
            conn.execute(text(stmt))
        logger.info("Migration 111: ensured DNS UPDATE tables (PostgreSQL)")


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        for t in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.commit()
    else:
        from sqlalchemy import text
        for t in TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
