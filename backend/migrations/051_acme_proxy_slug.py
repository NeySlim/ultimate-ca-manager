"""Migration 051: Per-CA ACME proxy slug (multi-path proxy endpoints).

Adds ``proxy_slug`` and ``proxy_enabled`` on ``acme_client_accounts`` and
backfills the account referenced by ``acme.proxy.acme_account_id``.
"""
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

PROXY_ACCOUNT_ID_KEY = "acme.proxy.acme_account_id"

PROXY_RESERVED_SLUGS = frozenset({
    'directory', 'new-nonce', 'new-account', 'new-order',
    'acct', 'authz', 'challenge', 'order', 'cert',
    'revoke-cert', 'key-change',
})


def _slugify(label: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', (label or 'ca').lower()).strip('-')
    return (slug[:63] or 'ca')


def _unique_slug(conn, base_slug, *, sqlite=True, exclude_id=None):
    slug = base_slug
    n = 2
    while slug in PROXY_RESERVED_SLUGS or _slug_taken(conn, slug, sqlite=sqlite, exclude_id=exclude_id):
        suffix = f'-{n}'
        slug = f'{base_slug[: max(1, 63 - len(suffix))]}{suffix}'
        n += 1
    return slug


def _slug_taken(conn, slug, *, sqlite=True, exclude_id=None):
    if sqlite:
        cur = conn.execute(
            "SELECT id FROM acme_client_accounts WHERE proxy_slug = ?",
            (slug,),
        )
    else:
        from sqlalchemy import text
        cur = conn.execute(
            text("SELECT id FROM acme_client_accounts WHERE proxy_slug = :s"),
            {"s": slug},
        )
    row = cur.fetchone()
    if not row:
        return False
    if exclude_id is not None and row[0] == exclude_id:
        return False
    return True


def _column_exists(conn, table, column, *, sqlite=True):
    if sqlite:
        cur = conn.execute(f"PRAGMA table_info({table})")
        return any(r[1] == column for r in cur.fetchall())
    from sqlalchemy import inspect
    return column in [c['name'] for c in inspect(conn).get_columns(table)]


def _add_columns_sqlite(conn):
    if not _column_exists(conn, 'acme_client_accounts', 'proxy_slug', sqlite=True):
        conn.execute("ALTER TABLE acme_client_accounts ADD COLUMN proxy_slug VARCHAR(63)")
    if not _column_exists(conn, 'acme_client_accounts', 'proxy_enabled', sqlite=True):
        conn.execute(
            "ALTER TABLE acme_client_accounts ADD COLUMN proxy_enabled BOOLEAN NOT NULL DEFAULT 0"
        )
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_acme_client_accounts_proxy_slug "
            "ON acme_client_accounts (proxy_slug)"
        )
    except sqlite3.OperationalError:
        pass


def _backfill_sqlite(conn):
    cur = conn.execute(
        "SELECT value FROM system_config WHERE key = ?",
        (PROXY_ACCOUNT_ID_KEY,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return
    try:
        account_id = int(row[0])
    except (TypeError, ValueError):
        return
    cur = conn.execute(
        "SELECT id, label, proxy_slug FROM acme_client_accounts WHERE id = ?",
        (account_id,),
    )
    acct = cur.fetchone()
    if not acct:
        return
    _id, label, existing_slug = acct
    slug = existing_slug or _unique_slug(conn, _slugify(label), sqlite=True, exclude_id=_id)
    conn.execute(
        "UPDATE acme_client_accounts SET proxy_enabled = 1, proxy_slug = ? WHERE id = ?",
        (slug, _id),
    )
    logger.info("[051] Enabled proxy slug %r for account id=%s", slug, _id)


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='acme_client_accounts'"
    )
    if not cur.fetchone():
        logger.info("[051] acme_client_accounts absent, skipping")
        return
    _add_columns_sqlite(conn)
    _backfill_sqlite(conn)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
        return

    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'acme_client_accounts' not in insp.get_table_names():
        logger.info("[051] acme_client_accounts absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('acme_client_accounts')}
    if 'proxy_slug' not in cols:
        conn.execute(text("ALTER TABLE acme_client_accounts ADD COLUMN proxy_slug VARCHAR(63)"))
    if 'proxy_enabled' not in cols:
        conn.execute(text(
            "ALTER TABLE acme_client_accounts ADD COLUMN proxy_enabled BOOLEAN NOT NULL DEFAULT FALSE"
        ))
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_acme_client_accounts_proxy_slug "
        "ON acme_client_accounts (proxy_slug)"
    ))

    row = conn.execute(
        text("SELECT value FROM system_config WHERE key = :k"),
        {"k": PROXY_ACCOUNT_ID_KEY},
    ).fetchone()
    if not row or not row[0]:
        return
    try:
        account_id = int(row[0])
    except (TypeError, ValueError):
        return
    acct = conn.execute(
        text("SELECT id, label, proxy_slug FROM acme_client_accounts WHERE id = :id"),
        {"id": account_id},
    ).fetchone()
    if not acct:
        return
    slug = acct.proxy_slug or _unique_slug(
        conn, _slugify(acct.label), sqlite=False, exclude_id=acct.id
    )
    conn.execute(
        text(
            "UPDATE acme_client_accounts SET proxy_enabled = TRUE, proxy_slug = :s WHERE id = :id"
        ),
        {"s": slug, "id": acct.id},
    )
    logger.info("[051] Enabled proxy slug %r for account id=%s", slug, acct.id)
