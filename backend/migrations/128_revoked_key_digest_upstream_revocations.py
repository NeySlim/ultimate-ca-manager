"""Migration 128: a revocation record keeps its key, an ACME order the revocations its CA still owes.

`revoked_serials.public_key_sha256` is the SHA-256 of the revoked certificate's
SubjectPublicKeyInfo: a key revoked as compromised stays known once its certificate row is
deleted. `acme_client_orders.upstream_revocations` lists, as JSON, the replaced certificates
whose revocation the CA has not confirmed yet, retried by the renewal task.
"""
import sqlite3

pg_compatible = True

_COLUMNS = {
    'revoked_serials': {'public_key_sha256': ('VARCHAR(64)', 'VARCHAR(64)')},
    'acme_client_orders': {'upstream_revocations': ('TEXT', 'TEXT')},
}
_INDEX = ('CREATE INDEX IF NOT EXISTS ix_revoked_serials_public_key_sha256 '
          'ON revoked_serials (public_key_sha256)')


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, (sqlite_type, _pg_type) in columns.items():
            if column not in present:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sqlite_type}")
    if 'revoked_serials' in tables:
        conn.execute(_INDEX)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        present = {c['name'] for c in inspector.get_columns(table)}
        for column, (_sqlite_type, pg_type) in columns.items():
            if column not in present:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {pg_type}"))
    if 'revoked_serials' in tables:
        conn.execute(text(_INDEX))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the columns.
    pass
