"""Migration 050: Link ACME proxy upstream to acme_client_accounts.

Stores ``acme.proxy.acme_account_id`` and backfills from legacy proxy
SystemConfig keys (upstream URL/mode, account key/url, EAB, contact email).

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

LE_STAGING = "https://acme-staging-v02.api.letsencrypt.org/directory"
LE_PRODUCTION = "https://acme-v02.api.letsencrypt.org/directory"
PROXY_ACCOUNT_ID_KEY = "acme.proxy.acme_account_id"


def _get_cfg(conn, key, default=None, *, sqlite=True):
    if sqlite:
        cur = conn.execute("SELECT value FROM system_config WHERE key = ?", (key,))
    else:
        from sqlalchemy import text
        cur = conn.execute(text("SELECT value FROM system_config WHERE key = :k"), {"k": key})
    row = cur.fetchone()
    if not row or row[0] is None:
        return default
    return row[0]


def _set_cfg(conn, key, value, description, *, sqlite=True):
    if sqlite:
        cur = conn.execute("SELECT 1 FROM system_config WHERE key = ?", (key,))
        if cur.fetchone():
            conn.execute(
                "UPDATE system_config SET value = ? WHERE key = ?",
                (str(value), key),
            )
        else:
            conn.execute(
                "INSERT INTO system_config (key, value, description) VALUES (?, ?, ?)",
                (key, str(value), description),
            )
    else:
        from sqlalchemy import text
        cur = conn.execute(text("SELECT 1 FROM system_config WHERE key = :k"), {"k": key})
        if cur.fetchone():
            conn.execute(
                text("UPDATE system_config SET value = :v WHERE key = :k"),
                {"v": str(value), "k": key},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO system_config (key, value, description) "
                    "VALUES (:k, :v, :d)"
                ),
                {"k": key, "v": str(value), "d": description},
            )


def _legacy_upstream_url(conn, *, sqlite=True):
    custom = _get_cfg(conn, "acme.proxy.upstream_url", "", sqlite=sqlite)
    if custom and str(custom).strip():
        return str(custom).strip()
    mode = _get_cfg(conn, "acme.proxy.upstream_mode", "staging", sqlite=sqlite) or "staging"
    if mode == "production":
        return LE_PRODUCTION
    return LE_STAGING


def _find_account_id_by_url(conn, directory_url, *, sqlite=True):
    if sqlite:
        cur = conn.execute(
            "SELECT id FROM acme_client_accounts WHERE directory_url = ?",
            (directory_url,),
        )
    else:
        from sqlalchemy import text
        cur = conn.execute(
            text("SELECT id FROM acme_client_accounts WHERE directory_url = :u"),
            {"u": directory_url},
        )
    row = cur.fetchone()
    return row[0] if row else None


def _insert_account_sqlite(conn, directory_url, label, email, account_url, account_key,
                           algorithm, eab_kid, eab_hmac_key, is_default):
    if _find_account_id_by_url(conn, directory_url, sqlite=True):
        return _find_account_id_by_url(conn, directory_url, sqlite=True)
    import datetime as _dt
    now = _dt.datetime.utcnow().isoformat(sep=' ', timespec='seconds')
    conn.execute(
        """INSERT INTO acme_client_accounts
           (directory_url, label, email, account_url, account_key, account_key_algorithm,
            eab_kid, eab_hmac_key, is_default, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            directory_url,
            label,
            email or "admin@localhost",
            account_url,
            account_key,
            algorithm or "ES256",
            eab_kid,
            eab_hmac_key,
            1 if is_default else 0,
            now,
            now,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='acme_client_accounts'"
    )
    if not cur.fetchone():
        logger.info("[050] acme_client_accounts absent, skipping")
        return

    if _get_cfg(conn, PROXY_ACCOUNT_ID_KEY, sqlite=True):
        logger.info("[050] proxy account id already set, skipping backfill")
        return

    directory_url = _legacy_upstream_url(conn, sqlite=True)
    account_id = _find_account_id_by_url(conn, directory_url, sqlite=True)

    proxy_key = _get_cfg(conn, "acme.proxy.account_key", sqlite=True)
    proxy_url = _get_cfg(conn, "acme.proxy.account_url", sqlite=True)
    proxy_email = _get_cfg(conn, "acme.proxy_email", sqlite=True)
    proxy_eab_kid = _get_cfg(conn, "acme.proxy.eab_kid", sqlite=True)
    proxy_eab_hmac = _get_cfg(conn, "acme.proxy.eab_hmac_key", sqlite=True)

    if account_id is None and proxy_key:
        label = "Proxy upstream"
        if "letsencrypt" in directory_url:
            label = "Let's Encrypt Staging (proxy)" if "staging" in directory_url else "Let's Encrypt Production (proxy)"
        account_id = _insert_account_sqlite(
            conn,
            directory_url,
            label,
            proxy_email or "admin@localhost",
            proxy_url,
            proxy_key,
            "RS256",
            proxy_eab_kid,
            proxy_eab_hmac,
            False,
        )
        logger.info("[050] Created acme_client_accounts row id=%s from legacy proxy creds", account_id)
    elif account_id is not None and proxy_key:
        # Merge legacy proxy creds into existing row only when row has no key yet
        cur = conn.execute(
            "SELECT account_key FROM acme_client_accounts WHERE id = ?",
            (account_id,),
        )
        row = cur.fetchone()
        if row and not row[0]:
            conn.execute(
                """UPDATE acme_client_accounts
                   SET account_key = ?, account_url = COALESCE(?, account_url),
                       email = COALESCE(?, email),
                       eab_kid = COALESCE(?, eab_kid),
                       eab_hmac_key = COALESCE(?, eab_hmac_key),
                       account_key_algorithm = 'RS256'
                   WHERE id = ?""",
                (
                    proxy_key,
                    proxy_url,
                    proxy_email,
                    proxy_eab_kid,
                    proxy_eab_hmac,
                    account_id,
                ),
            )
            logger.info("[050] Merged legacy proxy creds into account id=%s", account_id)

    if account_id is None:
        account_id = _find_account_id_by_url(conn, directory_url, sqlite=True)
    if account_id is None:
        default_cur = conn.execute(
            "SELECT id FROM acme_client_accounts WHERE is_default = 1 ORDER BY id LIMIT 1"
        )
        row = default_cur.fetchone()
        account_id = row[0] if row else None

    if account_id is not None:
        _set_cfg(
            conn,
            PROXY_ACCOUNT_ID_KEY,
            account_id,
            "AcmeClientAccount id used as ACME proxy upstream",
            sqlite=True,
        )
        logger.info("[050] Set %s = %s", PROXY_ACCOUNT_ID_KEY, account_id)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
        return

    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if "acme_client_accounts" not in insp.get_table_names():
        logger.info("[050] acme_client_accounts absent, skipping")
        return

    if _get_cfg(conn, PROXY_ACCOUNT_ID_KEY, sqlite=False):
        logger.info("[050] proxy account id already set, skipping backfill")
        return

    directory_url = _legacy_upstream_url(conn, sqlite=False)
    account_id = _find_account_id_by_url(conn, directory_url, sqlite=False)

    proxy_key = _get_cfg(conn, "acme.proxy.account_key", sqlite=False)
    proxy_url = _get_cfg(conn, "acme.proxy.account_url", sqlite=False)
    proxy_email = _get_cfg(conn, "acme.proxy_email", sqlite=False)
    proxy_eab_kid = _get_cfg(conn, "acme.proxy.eab_kid", sqlite=False)
    proxy_eab_hmac = _get_cfg(conn, "acme.proxy.eab_hmac_key", sqlite=False)

    if account_id is None and proxy_key:
        label = "Proxy upstream"
        if "letsencrypt" in directory_url:
            label = (
                "Let's Encrypt Staging (proxy)"
                if "staging" in directory_url
                else "Let's Encrypt Production (proxy)"
            )
        import datetime as _dt
        now = _dt.datetime.utcnow().isoformat(sep=' ', timespec='seconds')
        result = conn.execute(
            text(
                """INSERT INTO acme_client_accounts
                   (directory_url, label, email, account_url, account_key,
                    account_key_algorithm, eab_kid, eab_hmac_key, is_default,
                    created_at, updated_at)
                   VALUES (:u, :l, :e, :au, :ak, :alg, :kid, :hmac, FALSE, :now, :now)
                   RETURNING id"""
            ),
            {
                "u": directory_url,
                "l": label,
                "e": proxy_email or "admin@localhost",
                "au": proxy_url,
                "ak": proxy_key,
                "alg": "RS256",
                "kid": proxy_eab_kid,
                "hmac": proxy_eab_hmac,
                "now": now,
            },
        )
        account_id = result.scalar()
        if account_id is None:
            account_id = _find_account_id_by_url(conn, directory_url, sqlite=False)
        logger.info("[050] Created acme_client_accounts row id=%s from legacy proxy creds", account_id)
    elif account_id is not None and proxy_key:
        row = conn.execute(
            text("SELECT account_key FROM acme_client_accounts WHERE id = :id"),
            {"id": account_id},
        ).fetchone()
        if row and not row[0]:
            conn.execute(
                text(
                    """UPDATE acme_client_accounts
                       SET account_key = :ak,
                           account_url = COALESCE(:au, account_url),
                           email = COALESCE(:e, email),
                           eab_kid = COALESCE(:kid, eab_kid),
                           eab_hmac_key = COALESCE(:hmac, eab_hmac_key),
                           account_key_algorithm = 'RS256'
                       WHERE id = :id"""
                ),
                {
                    "ak": proxy_key,
                    "au": proxy_url,
                    "e": proxy_email,
                    "kid": proxy_eab_kid,
                    "hmac": proxy_eab_hmac,
                    "id": account_id,
                },
            )
            logger.info("[050] Merged legacy proxy creds into account id=%s", account_id)

    if account_id is None:
        account_id = _find_account_id_by_url(conn, directory_url, sqlite=False)
    if account_id is None:
        row = conn.execute(
            text("SELECT id FROM acme_client_accounts WHERE is_default = TRUE ORDER BY id LIMIT 1")
        ).fetchone()
        account_id = row[0] if row else None

    if account_id is not None:
        _set_cfg(
            conn,
            PROXY_ACCOUNT_ID_KEY,
            account_id,
            "AcmeClientAccount id used as ACME proxy upstream",
            sqlite=False,
        )
        logger.info("[050] Set %s = %s", PROXY_ACCOUNT_ID_KEY, account_id)
