"""Migration 142: one certificate per (issuing CA, serial number).

RFC 5280 §4.1.2.2: a CA never issues two certificates with the same serial.
Existing duplicates are listed, never deleted: the index is created only on a
clean table; otherwise the pairs are logged and kept under the SystemConfig key
``serial_unique_index_pending`` until an operator resolves them and runs this again.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'certificates'
CONFIG = 'system_config'
PENDING_KEY = 'serial_unique_index_pending'
INDEX = 'uix_certificates_ca_serial'
# Same name and predicate as the model's index, so create_all and this agree
CREATE_INDEX = (f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (caref, serial_number) "
                "WHERE caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''")
DUPLICATES = (f"SELECT caref, serial_number, COUNT(*) FROM {TABLE} "
              "WHERE caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> '' "
              "GROUP BY caref, serial_number HAVING COUNT(*) > 1 ORDER BY caref, serial_number")
CLEAR_PENDING = f"DELETE FROM {CONFIG} WHERE key = '{PENDING_KEY}'"
SET_PENDING = (f"INSERT INTO {CONFIG} (key, value, encrypted, description, updated_at) "
               "VALUES ('" + PENDING_KEY + "', {value}, {false}, "
               "'Unique serial index per CA waits for duplicate certificates to be resolved', "
               "CURRENT_TIMESTAMP)")


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
    for d in duplicates:
        logger.warning("Migration 142: CA %s holds %s certificates with serial %s",
                       d['caref'], d['count'], d['serial_number'])
    logger.warning("Migration 142: unique serial index not created; resolve the duplicates "
                   "and run migration 142 again")
    if CONFIG in tables:
        execute(SET_PENDING.format(value=value_param, false=false_literal),
                json.dumps({'duplicates': duplicates}))


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    _apply(lambda sql, value: conn.execute(sql) if value is None else conn.execute(sql, (value,)),
           tables, '?', '0')
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())
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
