"""Migration 104: group permissions stored as JSON lists.

The default groups were seeded with their permissions as a JSON string, which
the API returned as text and the Groups panel crashed on. Each row becomes a
list of the scopes a group may grant.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)

pg_compatible = True

ADMIN_GROUP_SEEDED = 'Full system administrators with all permissions'
ADMIN_GROUP_NOW = 'Membership grants no rights: assign the Administrator role for full access'


def _grantable():
    """The scopes a group may grant, or None to fall back on the structural filter."""
    try:
        from auth.permissions import GROUP_GRANTABLE_PERMISSIONS
        return set(GROUP_GRANTABLE_PERMISSIONS)
    except ImportError as e:
        logger.warning("Migration 104: %s; keeping only scoped, non-admin permissions", e)
        return None


def _grantable_list(value, grantable=None):
    """*value* (list, JSON text, or JSON text of JSON text) as a list of the
    scopes a group may hold, or None when it is not a list."""
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, list):
        return None
    return [p for p in value
            if isinstance(p, str) and ':' in p and '*' not in p and not p.startswith('admin:')
            and (grantable is None or p in grantable)]


def _stored_list(raw, sqlite):
    """What the ORM reads back from *raw*: SQLite stores JSON text, PostgreSQL
    hands over the decoded value."""
    if sqlite and isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return raw


def _fixes(rows, sqlite):
    """(id, permissions JSON, description) for each row that needs rewriting."""
    out, grantable = [], _grantable()
    for gid, raw, description in rows:
        fixed = _grantable_list(raw, grantable)
        if fixed is None or fixed == _stored_list(raw, sqlite):
            continue
        if description == ADMIN_GROUP_SEEDED and not fixed:
            description = ADMIN_GROUP_NOW
        out.append((gid, json.dumps(fixed), description))
    return out


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'groups' not in tables:
        return
    rows = conn.execute("SELECT id, permissions, description FROM groups").fetchall()
    for gid, perms, description in _fixes(rows, sqlite=True):
        conn.execute("UPDATE groups SET permissions = ?, description = ? WHERE id = ?",
                     (perms, description, gid))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'groups' not in inspect(conn).get_table_names():
        return
    data_type = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'groups' "
        "AND column_name = 'permissions'")).scalar()
    value = 'CAST(:p AS jsonb)' if data_type == 'jsonb' else (
        'CAST(:p AS json)' if data_type == 'json' else ':p')
    rows = conn.execute(text("SELECT id, permissions, description FROM groups")).fetchall()
    for gid, perms, description in _fixes(rows, sqlite=data_type not in ('json', 'jsonb')):
        conn.execute(text(f"UPDATE groups SET permissions = {value}, description = :d WHERE id = :i"),
                     {'p': perms, 'd': description, 'i': gid})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # A list reads fine in older versions.
    pass
