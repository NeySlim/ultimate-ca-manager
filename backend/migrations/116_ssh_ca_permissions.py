"""Migration 116: SSH CA scopes split out of the SSH scopes.

The SSH CA routes now check ``read|write|delete:ssh_cas``. Every custom role,
group and API key that held ``X:ssh`` receives ``X:ssh_cas`` beside it, so no
one loses a right on upgrade. Wildcards (``*``, ``read:*``) need nothing.

Multi-backend convention: runs on both SQLite and PostgreSQL.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

# CustomRole, Group and APIKey, by their __tablename__
TABLES = ('pro_custom_roles', 'groups', 'api_keys')

# Frozen here: a migration must not follow later edits of auth.permissions
SSH_CA_SCOPES = {'read:ssh': 'read:ssh_cas', 'write:ssh': 'write:ssh_cas',
                 'delete:ssh': 'delete:ssh_cas'}


def with_ssh_ca_scopes(perms) -> list:
    """``perms`` with ``X:ssh_cas`` added right after each ``X:ssh`` it holds."""
    out = []
    for perm in perms:
        if perm not in out:
            out.append(perm)
        added = SSH_CA_SCOPES.get(perm) if isinstance(perm, str) else None
        if added and added not in perms and added not in out:
            out.append(added)
    return out


def _decode(raw):
    """The stored list, JSON text decoded (twice at most), or None."""
    value = raw
    for _ in range(2):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, list) else None


def _updates(rows):
    """(id, new JSON list) for each row that holds an SSH scope without its CA twin."""
    out = []
    for row_id, raw in rows:
        perms = _decode(raw)
        if perms is None:
            continue
        widened = with_ssh_ca_scopes(perms)
        if [p for p in widened if p not in perms]:
            out.append((row_id, json.dumps(widened)))
    return out


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for table in TABLES:
        if table not in tables:
            continue
        rows = conn.execute(f"SELECT id, permissions FROM {table}").fetchall()
        for row_id, perms in _updates(rows):
            conn.execute(f"UPDATE {table} SET permissions = ? WHERE id = ?", (perms, row_id))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    present = set(inspect(conn).get_table_names())
    for table in TABLES:
        if table not in present:
            continue
        # create_all makes a json column, the SQL baseline a text one
        data_type = conn.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :t "
            "AND column_name = 'permissions'"), {'t': table}).scalar()
        value = f'CAST(:p AS {data_type})' if data_type in ('json', 'jsonb') else ':p'
        rows = conn.execute(text(f"SELECT id, permissions FROM {table}")).fetchall()
        for row_id, perms in _updates(rows):
            conn.execute(text(f"UPDATE {table} SET permissions = {value} WHERE id = :i"),
                         {'p': perms, 'i': row_id})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)
    logger.info("Migration 116: SSH CA scopes granted beside the SSH scopes")


def downgrade(conn):
    # An older version ignores the ssh_cas scopes.
    pass
