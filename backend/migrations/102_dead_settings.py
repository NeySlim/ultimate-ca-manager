"""Migration 102: delete settings that nothing reads any more.

Each key below lost its reader or its screen in the same release; leaving the
row would only keep a stale value (some of them secrets) in backups. Policy
rules lose the keys no evaluation ever read.
"""
import json
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


DEAD_RULE_KEYS = ('required_extensions', 'forbidden_extensions')
DEAD_SAN_RULE_KEYS = ('require_approval_for_external',)


def _cleaned_rules(text):
    """The rules without the dead keys, or None when nothing changes."""
    try:
        rules = json.loads(text or '{}')
    except (TypeError, ValueError):
        return None
    if not isinstance(rules, dict):
        return None
    cleaned = {k: v for k, v in rules.items() if k not in DEAD_RULE_KEYS}
    san = cleaned.get('san_restrictions')
    if isinstance(san, dict):
        cleaned['san_restrictions'] = {k: v for k, v in san.items() if k not in DEAD_SAN_RULE_KEYS}
    return None if cleaned == rules else json.dumps(cleaned)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'system_config' in tables:
        conn.executemany("DELETE FROM system_config WHERE key = ?", [(k,) for k in DEAD_KEYS])
    if 'certificate_policies' in tables:
        for pid, rules in conn.execute("SELECT id, rules FROM certificate_policies").fetchall():
            cleaned = _cleaned_rules(rules)
            if cleaned is not None:
                conn.execute("UPDATE certificate_policies SET rules = ? WHERE id = ?", (cleaned, pid))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text

    tables = set(inspect(conn).get_table_names())
    if 'system_config' in tables:
        conn.execute(text("DELETE FROM system_config WHERE key IN :keys").bindparams(
            bindparam('keys', expanding=True)), {'keys': list(DEAD_KEYS)})
    if 'certificate_policies' in tables:
        for pid, rules in conn.execute(text("SELECT id, rules FROM certificate_policies")).fetchall():
            cleaned = _cleaned_rules(rules)
            if cleaned is not None:
                conn.execute(text("UPDATE certificate_policies SET rules = :r WHERE id = :i"),
                             {'r': cleaned, 'i': pid})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Older versions fall back to their defaults for a missing key.
    pass
