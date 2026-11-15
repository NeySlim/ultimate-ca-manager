"""Upgrade step 163: an HSM key backs one X.509 CA and one SSH CA at most; an SSH CA can keep its key on an HSM token.

``ssh_cas.key_source`` ('software' on every existing row) and ``ssh_cas.hsm_key_id`` (NULL),
a foreign key to ``hsm_keys.id``; the unique index ``uq_ssh_cas_hsm_key_id`` binds a key to
one SSH CA at most (NULLs stay distinct on both backends). 2.254 has no HSM SSH CA: no row moves.

``uq_ca_hsm_key_id`` does the same for X.509 CAs. 2.x created it (partial) only on the databases its
migration 035 upgraded: it is created, or replaced by the definition of a fresh install, on every one.
Two X.509 CAs on one key refuse the upgrade before migration 300 writes anything (``refusal``).
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'ssh_cas'
INDEX = ('CREATE UNIQUE INDEX IF NOT EXISTS uq_ssh_cas_hsm_key_id '
         'ON ssh_cas (hsm_key_id)')
_COLUMNS = (
    ('key_source', "VARCHAR(20) NOT NULL DEFAULT 'software'"),
    ('hsm_key_id', 'INTEGER REFERENCES hsm_keys (id)'),
)

X509 = 'certificate_authorities'
X509_INDEX = 'uq_ca_hsm_key_id'
_X509_DDL = (f'DROP INDEX IF EXISTS {X509_INDEX}', f'CREATE UNIQUE INDEX {X509_INDEX} ON {X509} (hsm_key_id)')
_SHARED = (f"SELECT c.hsm_key_id, k.label, c.id, c.descr FROM {X509} c "
           f"LEFT JOIN hsm_keys k ON k.id = c.hsm_key_id "
           f"WHERE c.hsm_key_id IN (SELECT hsm_key_id FROM {X509} WHERE hsm_key_id IS NOT NULL "
           f"GROUP BY hsm_key_id HAVING COUNT(*) > 1) ORDER BY c.hsm_key_id, c.id")


def _refusal_text(rows):
    if not rows:
        return None
    keys = {}
    for key_id, label, ca_id, descr in rows:
        keys.setdefault((key_id, label), []).append(f"'{descr}' (#{ca_id})")
    named = '; '.join(f"HSM key '{label or ''}' (#{key_id}) backs {len(cas)} X.509 CAs: {', '.join(cas)}"
                      for (key_id, label), cas in keys.items())
    return (f"Upgrade refused: {named}. An HSM key backs one CA only: start 2.254 again, keep one CA on "
            f"each key and delete the others, then upgrade. Nothing was changed: 2.254 still starts on "
            f"this database.")


def _tables(conn):
    if isinstance(conn, sqlite3.Connection):
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    from sqlalchemy import inspect
    return set(inspect(conn).get_table_names())


def refusal(conn):
    """The message that stops the upgrade when two X.509 CAs share an HSM key, else None. Reads only."""
    if not {X509, 'hsm_keys'} <= _tables(conn):
        return None
    if isinstance(conn, sqlite3.Connection):
        return _refusal_text(conn.execute(_SHARED).fetchall())
    from sqlalchemy import text
    return _refusal_text([tuple(r) for r in conn.execute(text(_SHARED))])


def _upgrade_sqlite(conn):
    tables = _tables(conn)
    if TABLE not in tables and X509 not in tables:
        logger.info("163: no ssh_cas table, nothing to do (SQLite)")
        return
    message = refusal(conn)
    if message:
        raise RuntimeError(message)
    if TABLE in tables:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
        for name, ddl in _COLUMNS:
            if name not in columns:
                conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}")
        conn.execute(INDEX)
    if X509 in tables:
        for ddl in _X509_DDL:
            conn.execute(ddl)
    conn.commit()
    logger.info("163: one CA per HSM key, ssh_cas can name one (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text
    tables = _tables(conn)
    if TABLE not in tables and X509 not in tables:
        logger.info("163: no ssh_cas table, nothing to do (PostgreSQL)")
        return
    message = refusal(conn)
    if message:
        raise RuntimeError(message)
    if TABLE in tables:
        columns = {c['name'] for c in inspect(conn).get_columns(TABLE)}
        for name, ddl in _COLUMNS:
            if name not in columns:
                conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}"))
        conn.execute(text(INDEX))
    if X509 in tables:
        for ddl in _X509_DDL:
            conn.execute(text(ddl))
    logger.info("163: one CA per HSM key, ssh_cas can name one (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: 2.254 never reads the two columns, and keeps the index of its migration 035."""
    pass
