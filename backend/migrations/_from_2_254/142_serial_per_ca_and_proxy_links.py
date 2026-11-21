"""Upgrade step 142: one certificate per (issuing CA, serial number); proxy challenge links.

RFC 5280 §4.1.2.2: a CA never issues two certificates with the same serial.
Existing duplicates are listed, never deleted: the index is created only on a
clean table; otherwise the pairs are logged and kept under the SystemConfig key
``serial_unique_index_pending``. While that key is set, every start runs step 144
again (migration_runner), which holds raw duplicates too, so a restart after the
cleanup creates the index.

``acme_proxy_challenge_links`` records which proxy order a challenge belongs to, so
any worker or node answers the challenge POST that another one's authz fetch prepared.
"""
import json
import logging
import sqlite3

# The query a backend migration and a restore run on their source too
from utils.serial_duplicates import CLEANUP, DUPLICATES, PENDING_KEY, ROWS_OF_COVERED, describe_pending, stored_rows

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'certificates'
CONFIG = 'system_config'
INDEX = 'uix_certificates_ca_serial'
# Same name and predicate as the model's index, so create_all and this agree
CREATE_INDEX = (f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (caref, serial_number) "
                "WHERE caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''")
CLEAR_PENDING = f"DELETE FROM {CONFIG} WHERE key = '{PENDING_KEY}'"
SET_PENDING = (f"INSERT INTO {CONFIG} (key, value, encrypted, description, updated_at) "
               "VALUES ('" + PENDING_KEY + "', {value}, {false}, "
               "'Upgrade step 142 pending: the unique serial index per CA waits for duplicate certificates to be resolved', "
               "CURRENT_TIMESTAMP)")

LINKS = 'acme_proxy_challenge_links'
ORDERS = 'acme_client_orders'


def _links_ddl(pk, ts):
    return [f"""CREATE TABLE IF NOT EXISTS {LINKS} (
        id {pk},
        key_sha256 VARCHAR(64) NOT NULL UNIQUE,
        order_id INTEGER NOT NULL REFERENCES {ORDERS} (id) ON DELETE CASCADE,
        identifier VARCHAR(255),
        authz_url TEXT,
        created_at {ts} NOT NULL
    )""",
            f"CREATE INDEX IF NOT EXISTS ix_{LINKS}_order_id ON {LINKS} (order_id)",
            f"CREATE INDEX IF NOT EXISTS ix_{LINKS}_created_at ON {LINKS} (created_at)"]


def _apply(execute, tables, value_param, false_literal):
    """Shared body: *execute(sql, params)* returns a cursor-like result."""
    if TABLE not in tables:
        return
    duplicates = [{'caref': r[0], 'serial_number': r[1], 'count': int(r[2])}
                  for r in execute(DUPLICATES, None).fetchall()]
    if CONFIG in tables:
        execute(CLEAR_PENDING, None)
    if not duplicates:
        execute(CREATE_INDEX, None)
        return
    ids = {}
    for row_id, caref, serial in execute(ROWS_OF_COVERED, None).fetchall():
        ids.setdefault((caref, serial), []).append(row_id)
    for d in duplicates:
        held = ids.get((d['caref'], d['serial_number']), [])
        d['rows'] = stored_rows(held, dict.fromkeys(held, d['serial_number']))
        logger.warning("Upgrade step 142: %s", describe_pending(d))
    logger.warning("Upgrade step 142: unique serial index not created. %s", CLEANUP)
    if CONFIG in tables:
        execute(SET_PENDING.format(value=value_param, false=false_literal),
                json.dumps({'duplicates': duplicates}))


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if ORDERS in tables:
        for ddl in _links_ddl('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME'):
            conn.execute(ddl)
    _apply(lambda sql, value: conn.execute(sql) if value is None else conn.execute(sql, (value,)),
           tables, '?', '0')
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())
    if ORDERS in tables:
        for ddl in _links_ddl('SERIAL PRIMARY KEY', 'TIMESTAMP WITHOUT TIME ZONE'):
            conn.execute(text(ddl))
    _apply(lambda sql, value: conn.execute(text(sql)) if value is None
           else conn.execute(text(sql), {'v': value}),
           tables, ':v', 'FALSE')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
