"""Upgrade step 168: a non-zero SSH certificate serial is held once under its CA (PROTOCOL.krl §2.2).

2.254 could issue one serial twice. Such rows keep their number, which their signature carries:
``ssh_certificates.serial_duplicate`` marks them, which takes them out of the unique index
``uq_ssh_certificates_ca_serial``; each pair is logged and listed under
``ssh_serial_duplicates_marked``, which the next start turns into audit entries
(utils/ssh_serials.report_marked_duplicates). Every counter then moves past the serials its CA
holds. Running it again changes nothing.
"""
import logging
import sqlite3

from utils.ssh_serials import CREATE_INDEX, FLAG, describe, list_for_next_start, mark_duplicates, raise_counters

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'ssh_certificates'
CONFIG = 'system_config'


def _apply(run, tables, columns, add_column):
    if TABLE not in tables:
        return
    if FLAG not in columns:
        run(add_column)
    groups = mark_duplicates(run)
    for entry in groups:
        logger.warning("Upgrade step 168: %s", describe(entry))
    if CONFIG in tables:
        list_for_next_start(run, groups)
    run(CREATE_INDEX)
    if 'ssh_cas' in tables:
        raise_counters(run)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({TABLE})")}
        _apply(lambda sql, params=None: conn.execute(sql, params or {}), tables, columns,
               f"ALTER TABLE {TABLE} ADD COLUMN {FLAG} BOOLEAN DEFAULT 0 NOT NULL")
        conn.commit()
        return
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    columns = {c['name'] for c in inspector.get_columns(TABLE)} if TABLE in tables else set()
    _apply(lambda sql, params=None: conn.execute(text(sql), params or {}), tables, columns,
           f"ALTER TABLE {TABLE} ADD COLUMN {FLAG} BOOLEAN DEFAULT false NOT NULL")


def downgrade(conn):
    """No downgrade: 2.254 restores a backup taken before the upgrade."""
