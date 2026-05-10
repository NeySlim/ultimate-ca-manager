"""Migration 031: ACME client accounts table.

Replaces 6 SystemConfig keys (acme.client.{staging,production}.account_{key,url}
+ acme.client.{environment,directory_url}) with a relational table where URL is
the source of truth and credentials cannot drift from the directory.

Legacy keys are NOT deleted; they remain for 1 release for rollback safety.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS acme_client_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    directory_url VARCHAR(500) NOT NULL UNIQUE,
    label VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    account_url VARCHAR(500),
    account_key TEXT,
    account_key_algorithm VARCHAR(20) NOT NULL DEFAULT 'ES256',
    eab_kid VARCHAR(255),
    eab_hmac_key TEXT,
    is_default BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_acme_client_accounts_default ON acme_client_accounts(is_default);
"""

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS acme_client_accounts (
    id SERIAL PRIMARY KEY,
    directory_url VARCHAR(500) NOT NULL UNIQUE,
    label VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    account_url VARCHAR(500),
    account_key TEXT,
    account_key_algorithm VARCHAR(20) NOT NULL DEFAULT 'ES256',
    eab_kid VARCHAR(255),
    eab_hmac_key TEXT,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_acme_client_accounts_default ON acme_client_accounts(is_default);
"""

LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"


# -------- SQLite path (legacy behaviour preserved) --------

def _get_cfg_sqlite(conn, key, default=None):
    cur = conn.execute("SELECT value FROM system_config WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else default


def _has_account_sqlite(conn, directory_url):
    cur = conn.execute("SELECT 1 FROM acme_client_accounts WHERE directory_url = ?", (directory_url,))
    return cur.fetchone() is not None


def _insert_account_sqlite(conn, directory_url, label, email, account_url, account_key,
                           algorithm, eab_kid, eab_hmac_key, is_default):
    if _has_account_sqlite(conn, directory_url):
        return
    conn.execute(
        """INSERT INTO acme_client_accounts
           (directory_url, label, email, account_url, account_key, account_key_algorithm,
            eab_kid, eab_hmac_key, is_default)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (directory_url, label, email, account_url, account_key, algorithm,
         eab_kid, eab_hmac_key, 1 if is_default else 0)
    )
    logger.info(f"[031] Backfilled account: {label} ({directory_url})")


def _upgrade_sqlite(conn):
    conn.executescript(SQLITE_SCHEMA)
    conn.commit()

    active_env = _get_cfg_sqlite(conn, 'acme.client.environment', 'staging')
    email = _get_cfg_sqlite(conn, 'acme.client.email', 'admin@localhost') or 'admin@localhost'
    algorithm = _get_cfg_sqlite(conn, 'acme.client.account_key_type', 'ES256') or 'ES256'
    eab_kid = _get_cfg_sqlite(conn, 'acme.client.eab_kid')
    eab_hmac_key = _get_cfg_sqlite(conn, 'acme.client.eab_hmac_key')
    custom_dir = _get_cfg_sqlite(conn, 'acme.client.directory_url')

    for env in ('staging', 'production'):
        account_key = _get_cfg_sqlite(conn, f'acme.client.{env}.account_key')
        if not account_key:
            continue
        account_url = _get_cfg_sqlite(conn, f'acme.client.{env}.account_url')
        url = LE_STAGING if env == 'staging' else LE_PRODUCTION
        label = "Let's Encrypt Staging" if env == 'staging' else "Let's Encrypt Production"
        is_def = (env == active_env)
        attach_eab = is_def
        _insert_account_sqlite(
            conn, url, label, email, account_url, account_key, algorithm,
            eab_kid if attach_eab else None,
            eab_hmac_key if attach_eab else None,
            is_def,
        )

    if custom_dir and custom_dir not in (LE_STAGING, LE_PRODUCTION):
        account_key = _get_cfg_sqlite(conn, f'acme.client.{active_env}.account_key')
        account_url = _get_cfg_sqlite(conn, f'acme.client.{active_env}.account_url')
        if account_key:
            _insert_account_sqlite(
                conn, custom_dir, f"Custom ({custom_dir[:40]}...)", email,
                account_url, account_key, algorithm, eab_kid, eab_hmac_key, True
            )
        conn.execute(
            "UPDATE acme_client_accounts SET is_default = 0 WHERE directory_url != ?",
            (custom_dir,)
        )

    conn.commit()
    logger.info("[031] ACME client accounts migration complete (SQLite)")


# -------- PostgreSQL path --------

def _get_cfg_pg(conn, key, default=None):
    from sqlalchemy import text
    row = conn.execute(text("SELECT value FROM system_config WHERE key = :k"), {"k": key}).fetchone()
    return row[0] if row and row[0] is not None else default


def _has_account_pg(conn, directory_url):
    from sqlalchemy import text
    return conn.execute(
        text("SELECT 1 FROM acme_client_accounts WHERE directory_url = :u"),
        {"u": directory_url},
    ).fetchone() is not None


def _insert_account_pg(conn, directory_url, label, email, account_url, account_key,
                       algorithm, eab_kid, eab_hmac_key, is_default):
    from sqlalchemy import text
    if _has_account_pg(conn, directory_url):
        return
    conn.execute(
        text(
            """INSERT INTO acme_client_accounts
               (directory_url, label, email, account_url, account_key, account_key_algorithm,
                eab_kid, eab_hmac_key, is_default)
               VALUES (:du, :lb, :em, :au, :ak, :alg, :kid, :hmac, :def)"""
        ),
        {"du": directory_url, "lb": label, "em": email, "au": account_url,
         "ak": account_key, "alg": algorithm, "kid": eab_kid, "hmac": eab_hmac_key,
         "def": is_default},
    )
    logger.info(f"[031] Backfilled account: {label} ({directory_url})")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    # CREATE TABLE / INDEX (idempotent)
    for stmt in [s.strip() for s in PG_SCHEMA.split(";") if s.strip()]:
        conn.execute(text(stmt))

    insp = inspect(conn)
    if 'system_config' not in set(insp.get_table_names()):
        logger.info("[031] system_config absent, skipping backfill (PG fresh)")
        return

    active_env = _get_cfg_pg(conn, 'acme.client.environment', 'staging')
    email = _get_cfg_pg(conn, 'acme.client.email', 'admin@localhost') or 'admin@localhost'
    algorithm = _get_cfg_pg(conn, 'acme.client.account_key_type', 'ES256') or 'ES256'
    eab_kid = _get_cfg_pg(conn, 'acme.client.eab_kid')
    eab_hmac_key = _get_cfg_pg(conn, 'acme.client.eab_hmac_key')
    custom_dir = _get_cfg_pg(conn, 'acme.client.directory_url')

    for env in ('staging', 'production'):
        account_key = _get_cfg_pg(conn, f'acme.client.{env}.account_key')
        if not account_key:
            continue
        account_url = _get_cfg_pg(conn, f'acme.client.{env}.account_url')
        url = LE_STAGING if env == 'staging' else LE_PRODUCTION
        label = "Let's Encrypt Staging" if env == 'staging' else "Let's Encrypt Production"
        is_def = (env == active_env)
        attach_eab = is_def
        _insert_account_pg(
            conn, url, label, email, account_url, account_key, algorithm,
            eab_kid if attach_eab else None,
            eab_hmac_key if attach_eab else None,
            is_def,
        )

    if custom_dir and custom_dir not in (LE_STAGING, LE_PRODUCTION):
        account_key = _get_cfg_pg(conn, f'acme.client.{active_env}.account_key')
        account_url = _get_cfg_pg(conn, f'acme.client.{active_env}.account_url')
        if account_key:
            _insert_account_pg(
                conn, custom_dir, f"Custom ({custom_dir[:40]}...)", email,
                account_url, account_key, algorithm, eab_kid, eab_hmac_key, True
            )
        conn.execute(
            text("UPDATE acme_client_accounts SET is_default = FALSE WHERE directory_url != :u"),
            {"u": custom_dir},
        )

    logger.info("[031] ACME client accounts migration complete (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute("DROP TABLE IF EXISTS acme_client_accounts")
        conn.commit()
    else:
        from sqlalchemy import text
        conn.execute(text("DROP TABLE IF EXISTS acme_client_accounts"))
