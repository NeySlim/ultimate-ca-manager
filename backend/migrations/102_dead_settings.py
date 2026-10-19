"""Migration 102: delete settings that nothing reads any more.

Each key below lost its reader or its screen in the same release; leaving the
row would only keep a stale value (some of them secrets) in backups.
"""
import sqlite3

pg_compatible = True

DEAD_KEYS = (
    'admin_bypass_password_policy',
    'acme.proxy_enabled',
    'acme.proxy.eab_kid',
    'acme.proxy.eab_hmac_key',
    'acme.proxy.account_url',
    'acme.proxy.account_key',
)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'system_config' not in tables:
        return
    conn.executemany("DELETE FROM system_config WHERE key = ?", [(k,) for k in DEAD_KEYS])
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text

    if 'system_config' not in inspect(conn).get_table_names():
        return
    conn.execute(text("DELETE FROM system_config WHERE key IN :keys").bindparams(
        bindparam('keys', expanding=True)), {'keys': list(DEAD_KEYS)})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Older versions fall back to their defaults for a missing key.
    pass
