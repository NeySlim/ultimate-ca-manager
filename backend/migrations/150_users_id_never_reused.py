"""Migration 150: a user id is never handed out again.

SQLite gave a new account the id of the last one deleted (INTEGER PRIMARY KEY
without AUTOINCREMENT), and every row still holding that id followed it. The
table is rebuilt with AUTOINCREMENT in one transaction, from its own stored DDL
so its columns, constraints and indexes stay as they are. On both backends the
id counter then starts above every id a surviving row still names.
"""
import json
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'users'
SCRATCH = '_users_s150'
# Columns that keep a user id after the account is gone, or until it is purged
REFERENCES = (
    ('user_sessions', 'user_id'), ('api_keys', 'user_id'), ('auth_certificates', 'user_id'),
    ('webauthn_credentials', 'user_id'), ('webauthn_challenges', 'user_id'),
    ('group_members', 'user_id'), ('pro_sso_sessions', 'user_id'),
    ('approval_requests', 'requester_id'), ('hsm_providers', 'created_by'),
    ('acme_eab_credentials', 'created_by_user_id'), ('acme_eab_credentials', 'revoked_by_user_id'),
    ('acme_dns_update_keys', 'created_by_user_id'),
)


def _ids_in_approvals(rows):
    """User ids named in the JSON approval lists of ``approval_requests``."""
    for (approvals,) in rows:
        try:
            entries = json.loads(approvals) if approvals else []
        except (TypeError, ValueError):
            continue
        for entry in entries if isinstance(entries, list) else []:
            value = entry.get('user_id') if isinstance(entry, dict) else None
            if isinstance(value, int) and not isinstance(value, bool):
                yield value


# Above the int4 range PostgreSQL's users sequence cannot take it: not an id it handed out
_MAX_ID = 2 ** 31 - 1


def _ids_in_audit(rows):
    """User ids in ``audit_logs.resource_id``: one id, or a comma list for a bulk delete."""
    for (value,) in rows:
        for part in (value or '').split(','):
            part = part.strip()
            if part.isascii() and part.isdigit() and int(part) <= _MAX_ID:
                yield int(part)


def _highest_named(scalar, rows, has_column):
    """The highest user id the database still names anywhere (0 if none)."""
    highest = scalar(f"SELECT MAX(id) FROM {TABLE}") or 0
    for table, column in REFERENCES:
        if has_column(table, column):
            highest = max(highest, scalar(f"SELECT MAX({column}) FROM {table}") or 0)
    if has_column('approval_requests', 'approvals'):
        highest = max([highest, *_ids_in_approvals(rows("SELECT approvals FROM approval_requests"))])
    if has_column('audit_logs', 'resource_id') and has_column('audit_logs', 'resource_type'):
        highest = max([highest, *_ids_in_audit(rows(
            "SELECT resource_id FROM audit_logs WHERE resource_type = 'user'"))])
    return int(highest)


# --- SQLite -----------------------------------------------------------------

def _split_top_level(body):
    """Split a column list on the commas outside parentheses and quotes."""
    items, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(body):
        if quote:
            if ch == quote:
                quote = None
        elif ch in '\'"`[':
            quote = ']' if ch == '[' else ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            items.append(body[start:i])
            start = i + 1
    items.append(body[start:])
    return items


_ID_COLUMN = re.compile(r'^\s*["`\[]?id["`\]]?\s+INTEGER\b', re.I)
_TABLE_PK = re.compile(r'^\s*(CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*\(\s*["`\[]?id["`\]]?\s*\)\s*$', re.I)


def autoincrement_ddl(sql, name):
    """``sql`` (the stored CREATE TABLE of users) renamed to ``name``, id in AUTOINCREMENT.

    Everything else is kept verbatim; a shape this does not recognise raises.
    """
    open_at, close_at = sql.index('('), sql.rindex(')')
    items, seen_id = [], False
    for item in _split_top_level(sql[open_at + 1:close_at]):
        if _TABLE_PK.match(item):
            continue
        if _ID_COLUMN.match(item):
            seen_id = True
            not_null = ' NOT NULL' if re.search(r'\bNOT\s+NULL\b', item, re.I) else ''
            item = f'\n    id INTEGER{not_null} PRIMARY KEY AUTOINCREMENT'
        items.append(item)
    if not seen_id:
        raise RuntimeError(f'[150] no INTEGER id column in the {TABLE} DDL')
    return f'CREATE TABLE {name} (' + ','.join(items) + sql[close_at:]


def _shape(conn, table):
    return [row[1:] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _rebuild_sqlite(conn, sql):
    dependents = [row[0] for row in conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type IN ('index', 'trigger') "
        "AND sql IS NOT NULL ORDER BY type, name", (TABLE,))]
    conn.execute(f'DROP TABLE IF EXISTS {SCRATCH}')
    conn.execute(autoincrement_ddl(sql, SCRATCH))
    if _shape(conn, SCRATCH) != _shape(conn, TABLE):
        raise RuntimeError(f'[150] the rebuilt {TABLE} table would not have the same columns')
    columns = ', '.join(f'"{row[0]}"' for row in _shape(conn, TABLE))
    conn.execute(f'INSERT INTO {SCRATCH} ({columns}) SELECT {columns} FROM {TABLE}')
    conn.execute(f'DROP TABLE {TABLE}')
    conn.execute(f'ALTER TABLE {SCRATCH} RENAME TO {TABLE}')
    _recreate_dependents(conn, dependents)


def _recreate_dependents(conn, statements):
    for statement in statements:
        conn.execute(statement)


def _seed_sqlite(conn):
    def has_column(table, column):
        return any(row[1] == column for row in conn.execute(f'PRAGMA table_info("{table}")'))

    seed = _highest_named(lambda q: conn.execute(q).fetchone()[0], lambda q: conn.execute(q).fetchall(),
                          has_column)
    current = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (TABLE,)).fetchone()
    if current is None:
        conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (TABLE, seed))
    elif current[0] < seed:
        conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (seed, TABLE))


def _upgrade_sqlite(conn):
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)).fetchone()
    if row is None:
        return
    rebuild = 'AUTOINCREMENT' not in row[0].upper()
    # PRAGMA foreign_keys is ignored inside a transaction: switched off before it, so
    # dropping the old table neither cascades nor fails, and put back after it
    if conn.in_transaction:
        conn.commit()
    enforced = conn.execute('PRAGMA foreign_keys').fetchone()[0]
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute('BEGIN IMMEDIATE')
        try:
            if rebuild:
                _rebuild_sqlite(conn, row[0])
            _seed_sqlite(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.execute(f'PRAGMA foreign_keys = {"ON" if enforced else "OFF"}')
    logger.info("[150] users ids never reused (SQLite%s)", ', table rebuilt' if rebuild else '')


# --- PostgreSQL ---------------------------------------------------------------

def _upgrade_pg(conn):
    """A sequence never goes back; it is only moved above the ids rows still name."""
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if TABLE not in tables:
        return
    sequence = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {'t': TABLE}).scalar()
    if not sequence:
        logger.warning("[150] users.id owns no sequence, left as it is (PostgreSQL)")
        return
    columns = {}

    def has_column(table, column):
        if table not in tables:
            return False
        if table not in columns:
            columns[table] = {c['name'] for c in inspector.get_columns(table)}
        return column in columns[table]

    seed = _highest_named(lambda q: conn.execute(text(q)).scalar(),
                          lambda q: conn.execute(text(q)).fetchall(), has_column)
    current = conn.execute(text("SELECT pg_sequence_last_value(CAST(:s AS regclass))"),
                           {'s': sequence}).scalar() or 0
    if seed > current:
        conn.execute(text("SELECT setval(CAST(:s AS regclass), :n, true)"), {'s': sequence, 'n': seed})
    logger.info("[150] users ids never reused (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: going back would hand deleted ids out again."""
    pass
