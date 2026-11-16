"""Upgrade step 166: an account may be opened by several providers, one row each.

``users.sso_provider_id``, ``sso_external_id`` and ``sso_orphan_of`` become rows of
``user_sso_identities``, and ``users.auth_source`` goes: an account is local when it has
no row. Each account keeps the access it had. An account 2.254 treated as SSO (a source other
than local) gets one row; one older than migration 024 (local, no password, owing no change)
gets one only where 024 or a provider deletion recorded its provider, and otherwise stays the
legacy account the first provider to open it by name records itself on.
"""
import logging
import re
import sqlite3

from utils.sso_identity_upgrade import identity_rows

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'user_sso_identities'
USERS = 'users'
PROVIDERS = 'pro_sso_providers'
SCRATCH = '_users_s166'
DROPPED = ('auth_source', 'sso_provider_id', 'sso_external_id', 'sso_orphan_of')
LEGACY_INDEXES = ('ix_users_email_local', 'ix_users_sso_identity')

_COLUMNS = """
    user_id INTEGER NOT NULL,
    provider_id INTEGER,
    orphan_of VARCHAR(600),
    external_id VARCHAR(255),
    created_at {ts},
    bound_at {ts},
    created_by VARCHAR(80),
    PRIMARY KEY (id),
    CONSTRAINT uq_user_sso_identities_provider_identity UNIQUE (provider_id, external_id),
    CONSTRAINT uq_user_sso_identities_user_provider UNIQUE (user_id, provider_id),
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY(provider_id) REFERENCES pro_sso_providers (id) ON DELETE SET NULL
)"""
SQLITE_DDL = f"CREATE TABLE {TABLE} (\n    id INTEGER NOT NULL," + _COLUMNS.format(ts='DATETIME')
PG_DDL = f"CREATE TABLE {TABLE} (\n    id SERIAL NOT NULL," + _COLUMNS.format(ts='TIMESTAMP WITHOUT TIME ZONE')
INDEXES = (
    f"CREATE INDEX IF NOT EXISTS ix_user_sso_identities_orphan ON {TABLE} (orphan_of, external_id)",
    f"CREATE INDEX IF NOT EXISTS ix_user_sso_identities_user_id ON {TABLE} (user_id)",
)


# --- SQLite -----------------------------------------------------------------

def _columns_sqlite(conn, table):
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]


def _names(text):
    return {name.lower() for name in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text)}


def users_ddl_without(sql, name):
    """``sql`` (the stored CREATE TABLE of users) renamed to ``name``, without the dropped
    columns nor a table constraint naming one; everything else verbatim."""
    from migrations._from_2_254 import step
    split = step('150_users_id_never_reused')._split_top_level
    open_at, close_at = sql.index('('), sql.rindex(')')
    dropped = set(DROPPED)
    kept = []
    for item in split(sql[open_at + 1:close_at]):
        words = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', item)
        first = words[0].lower() if words else ''
        if first in dropped:
            continue
        if first in ('constraint', 'primary', 'unique', 'check', 'foreign') and _names(item) & dropped:
            continue
        kept.append(item)
    return f'CREATE TABLE {name} (' + ','.join(kept) + sql[close_at:]


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if USERS not in tables:
        conn.commit()
        return
    if conn.in_transaction:
        conn.commit()
    # PRAGMA foreign_keys is ignored inside a transaction: off before it, back after it
    enforced = conn.execute('PRAGMA foreign_keys').fetchone()[0]
    conn.execute('PRAGMA foreign_keys = OFF')
    try:
        conn.execute('BEGIN IMMEDIATE')
        try:
            if TABLE not in tables:
                conn.execute(SQLITE_DDL)
            for statement in INDEXES:
                conn.execute(statement)
            columns = set(_columns_sqlite(conn, USERS))
            if set(DROPPED) <= columns:
                _copy_sqlite(conn, tables)
            if columns & set(DROPPED):
                _drop_sqlite(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.execute(f'PRAGMA foreign_keys = {"ON" if enforced else "OFF"}')
    logger.info("[166] SSO identities per account (SQLite)")


def _copy_sqlite(conn, tables):
    provider_ids = ({row[0] for row in conn.execute(f"SELECT id FROM {PROVIDERS}")}
                    if PROVIDERS in tables else set())
    users = conn.execute(
        f"SELECT id, auth_source, sso_provider_id, sso_external_id, sso_orphan_of, password_hash, "
        f"force_password_change FROM {USERS} u WHERE NOT EXISTS "
        f"(SELECT 1 FROM {TABLE} i WHERE i.user_id = u.id) ORDER BY id").fetchall()
    conn.executemany(
        f"INSERT INTO {TABLE} (user_id, provider_id, orphan_of, external_id, created_at, bound_at) "
        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CASE WHEN ? IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END)",
        [(uid, pid, orphan, ext, ext) for uid, pid, orphan, ext in identity_rows(users, provider_ids)])


def _drop_sqlite(conn):
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                       (USERS,)).fetchone()[0]
    dropped = set(DROPPED)
    dependents = [row[0] for row in conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type IN ('index', 'trigger') "
        "AND sql IS NOT NULL ORDER BY type, name", (USERS,)) if not _names(row[0]) & dropped]
    conn.execute(f'DROP TABLE IF EXISTS {SCRATCH}')
    conn.execute(users_ddl_without(sql, SCRATCH))
    kept = [c for c in _columns_sqlite(conn, USERS) if c not in dropped]
    if _columns_sqlite(conn, SCRATCH) != kept:
        raise RuntimeError(f'[166] the rebuilt {USERS} table would not have the expected columns')
    columns = ', '.join(f'"{c}"' for c in kept)
    conn.execute(f'INSERT INTO {SCRATCH} ({columns}) SELECT {columns} FROM {USERS}')
    sequence = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (USERS,)).fetchone() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone() else None
    conn.execute(f'DROP TABLE {USERS}')
    conn.execute(f'ALTER TABLE {SCRATCH} RENAME TO {USERS}')
    if sequence is not None:
        # The id counter of step 150 follows the table: no deleted id is handed out again
        now = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (USERS,)).fetchone()
        if now is None:
            conn.execute("INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (USERS, sequence[0]))
        elif now[0] < sequence[0]:
            conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (sequence[0], USERS))
    for statement in dependents:
        conn.execute(statement)


# --- PostgreSQL ---------------------------------------------------------------

def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if USERS not in tables:
        return
    if TABLE not in tables:
        conn.execute(text(PG_DDL))
    for statement in INDEXES:
        conn.execute(text(statement))
    columns = {c['name'] for c in inspector.get_columns(USERS)}
    if set(DROPPED) <= columns:
        provider_ids = ({row[0] for row in conn.execute(text(f"SELECT id FROM {PROVIDERS}"))}
                        if PROVIDERS in tables else set())
        users = conn.execute(text(
            f"SELECT id, auth_source, sso_provider_id, sso_external_id, sso_orphan_of, password_hash, "
            f"force_password_change FROM {USERS} u WHERE NOT EXISTS "
            f"(SELECT 1 FROM {TABLE} i WHERE i.user_id = u.id) ORDER BY id")).fetchall()
        for uid, pid, orphan, ext in identity_rows(users, provider_ids):
            conn.execute(text(
                f"INSERT INTO {TABLE} (user_id, provider_id, orphan_of, external_id, created_at, bound_at) "
                "VALUES (:u, :p, :o, :e, timezone('utc', now()), "
                "CASE WHEN CAST(:e AS VARCHAR) IS NULL THEN NULL ELSE timezone('utc', now()) END)"),
                {'u': uid, 'p': pid, 'o': orphan, 'e': ext})
    for index in LEGACY_INDEXES:
        conn.execute(text(f"DROP INDEX IF EXISTS {index}"))
    for column in DROPPED:
        if column in columns:
            conn.execute(text(f"ALTER TABLE {USERS} DROP COLUMN {column}"))
    logger.info("[166] SSO identities per account (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: 2.254 restores a backup taken before the upgrade."""
