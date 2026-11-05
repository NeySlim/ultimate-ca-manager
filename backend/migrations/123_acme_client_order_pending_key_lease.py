"""Migration 123: an ACME client order keeps its pending key and its renewal lease.

`pending_key` holds, stored like a certificate's key, the private key sent to the CA in
a finalize request until the certificate is imported: a restart or a failed import no
longer loses it. `renewal_claimed_at` is the lease of the renewal or finalization running
on the order, so a manual and a scheduled renewal never run at once. `renewal_of_order_id`
names, on the order a renewal opens, the order it renews.
"""
import sqlite3

pg_compatible = True

_TABLE = 'acme_client_orders'
_COLUMNS = {
    'pending_key': ('TEXT', 'TEXT'),
    'renewal_claimed_at': ('DATETIME', 'TIMESTAMP'),
    'renewal_of_order_id': (f'INTEGER REFERENCES {_TABLE}(id) ON DELETE SET NULL',
                            f'INTEGER REFERENCES {_TABLE}(id) ON DELETE SET NULL'),
}
_INDEX = f'CREATE INDEX IF NOT EXISTS ix_{_TABLE}_renewal_of_order_id ON {_TABLE} (renewal_of_order_id)'


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = ?", (_TABLE,)).fetchone() is None:
        return
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({_TABLE})")}
    for column, (sqlite_type, _pg_type) in _COLUMNS.items():
        if column not in present:
            conn.execute(f"ALTER TABLE {_TABLE} ADD COLUMN {column} {sqlite_type}")
    conn.execute(_INDEX)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return
    present = {c['name'] for c in inspector.get_columns(_TABLE)}
    for column, (_sqlite_type, pg_type) in _COLUMNS.items():
        if column not in present:
            conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {column} {pg_type}"))
    conn.execute(text(_INDEX))


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions ignore the columns.
    pass
