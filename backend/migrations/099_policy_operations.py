"""Migration 099: the operations a policy applies to, scheduler-made requests.

``certificate_policies.operations`` lists the operations (issuance, renewal,
revocation) a policy governs. Existing rows keep what they did: an issuance
policy stays one, a renewal or revocation type, never enforced, governs nothing.
``approval_requests.requester_id`` becomes nullable: the renewal scheduler
queues requests nobody made.
"""

import json
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_POLICIES = 'certificate_policies'
_REQUESTS = 'approval_requests'


def legacy_operations(policy_type):
    """The operations a policy of the old single type actually governed."""
    if policy_type in (None, '', 'issuance'):
        return ['issuance']
    return []


def _backfill(rows):
    for row_id, policy_type in rows:
        yield json.dumps(legacy_operations(policy_type)), row_id


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if _POLICIES in tables:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({_POLICIES})")}
        if 'operations' not in cols:
            conn.execute(f"ALTER TABLE {_POLICIES} ADD COLUMN operations TEXT")
        rows = conn.execute(
            f"SELECT id, policy_type FROM {_POLICIES} WHERE operations IS NULL").fetchall()
        conn.executemany(f"UPDATE {_POLICIES} SET operations = ? WHERE id = ?",
                         list(_backfill(rows)))
    conn.commit()
    if _REQUESTS in tables:
        _sqlite_requester_nullable(conn)


def _sqlite_requester_nullable(conn):
    """SQLite has no ALTER COLUMN: the table is rebuilt from its own DDL."""
    cols = {r[1]: r for r in conn.execute(f"PRAGMA table_info({_REQUESTS})")}
    if 'requester_id' not in cols or cols['requester_id'][3] == 0:
        return
    ddl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                       (_REQUESTS,)).fetchone()[0]
    new_ddl, n = re.subn(r'(\brequester_id\s+INTEGER)\s+NOT\s+NULL', r'\1', ddl,
                         count=1, flags=re.IGNORECASE)
    new_ddl, m = re.subn(r'CREATE\s+TABLE\s+"?approval_requests"?',
                         'CREATE TABLE _approval_requests_new', new_ddl,
                         count=1, flags=re.IGNORECASE)
    if n != 1 or m != 1:
        raise RuntimeError('099: unexpected approval_requests schema, requester_id left NOT NULL')
    indexes = [r[0] for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (_REQUESTS,))]
    fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.executescript(
            f"BEGIN;\n{new_ddl};\n"
            f"INSERT INTO _approval_requests_new SELECT * FROM {_REQUESTS};\n"
            f"DROP TABLE {_REQUESTS};\n"
            f"ALTER TABLE _approval_requests_new RENAME TO {_REQUESTS};\n"
            + ''.join(f"{sql};\n" for sql in indexes)
            + "COMMIT;")
    finally:
        conn.execute(f"PRAGMA foreign_keys={'ON' if fk_on else 'OFF'}")
    logger.info("099: approval_requests.requester_id made nullable (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if insp.has_table(_POLICIES):
        cols = {c['name'] for c in insp.get_columns(_POLICIES)}
        if 'operations' not in cols:
            conn.execute(text(f"ALTER TABLE {_POLICIES} ADD COLUMN operations TEXT"))
        rows = conn.execute(text(
            f"SELECT id, policy_type FROM {_POLICIES} WHERE operations IS NULL")).fetchall()
        for value, row_id in _backfill(rows):
            conn.execute(text(f"UPDATE {_POLICIES} SET operations = :v WHERE id = :id"),
                         {'v': value, 'id': row_id})
    if insp.has_table(_REQUESTS):
        cols = {c['name']: c for c in insp.get_columns(_REQUESTS)}
        if 'requester_id' in cols and not cols['requester_id'].get('nullable', True):
            conn.execute(text(f"ALTER TABLE {_REQUESTS} ALTER COLUMN requester_id DROP NOT NULL"))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the column and accept a nullable requester.
    pass
