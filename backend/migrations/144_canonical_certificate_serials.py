"""Migration 144: one stored spelling per certificate serial (RFC 5280 §4.1.2.2).

certificates.serial_number and revoked_serials.serial_number become the decimal string
of the integer (utils/serial_format.py), read back from the row's certificate when the
text is ambiguous, so the unique (caref, serial_number) index of migration 142 sees one
spelling per serial. Rows of one CA that would end up sharing a serial are left as they
are and listed under ``serial_unique_index_pending``, as migration 142 does, with any row
whose decimal is still a held row's spelling; no row is ever deleted. Running it again
changes nothing.
"""
import json
import logging
import sqlite3

from utils.serial_duplicates import CLEANUP, DUPLICATES, PENDING_KEY, describe_pending, stored_rows
from utils.serial_format import canonical_serial, canonical_stored_serial

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'certificates'
REVOKED = 'revoked_serials'
CONFIG = 'system_config'
INDEX = 'uix_certificates_ca_serial'
CREATE_INDEX = (f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (caref, serial_number) "
                "WHERE caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''")
CLEAR_PENDING = f"DELETE FROM {CONFIG} WHERE key = '{PENDING_KEY}'"
SET_PENDING = (f"INSERT INTO {CONFIG} (key, value, encrypted, description, updated_at) "
               "VALUES ('" + PENDING_KEY + "', {value}, {false}, "
               "'Migrations 142/144 pending: certificates of one CA share a serial number', "
               "CURRENT_TIMESTAMP)")
_CERTS = (f"SELECT id, caref, serial_number, crt FROM {TABLE} "
          "WHERE serial_number IS NOT NULL AND serial_number <> '' ORDER BY id")
_REVOKED = f"SELECT id, serial_number, certificate_id FROM {REVOKED} ORDER BY id"


def plan(cert_rows, revoked_rows):
    """(certificate updates, revoked_serials updates, pending pairs) for the rows read.

    *cert_rows*: (id, caref, serial_number, crt); *revoked_rows*: (id, serial_number, certificate_id).
    A CA's rows that share a canonical serial are all left unconverted and listed, and so
    is any row whose target is the spelling a held row of its CA keeps (to a fixed point).
    """
    target, raw, ca, groups = {}, {}, {}, {}
    for row_id, caref, serial, crt in cert_rows:
        raw[row_id] = serial
        ca[row_id] = caref
        target[row_id] = canonical_stored_serial(serial, crt)
        if caref is not None:
            groups.setdefault((caref, target[row_id]), []).append(row_id)
    shared = {key: ids for key, ids in groups.items() if len(ids) > 1}
    held = {row_id for ids in shared.values() for row_id in ids}
    waiting = {}
    kept = {(ca[row_id], raw[row_id]) for row_id in held}
    while kept:
        blocked = [row_id for row_id in target if row_id not in held and ca[row_id] is not None
                   and target[row_id] != raw[row_id] and (ca[row_id], target[row_id]) in kept]
        held.update(blocked)
        waiting.update((row_id, target[row_id]) for row_id in blocked)
        kept = {(ca[row_id], raw[row_id]) for row_id in blocked}
    cert_updates = [(row_id, new) for row_id, new in target.items()
                    if new != raw[row_id] and row_id not in held]
    revoked_updates = []
    for row_id, serial, certificate_id in revoked_rows:
        # The record of the row's own serial takes the spelling its certificate settled
        new = (target[certificate_id] if certificate_id in raw and raw[certificate_id] == serial
               else canonical_serial(serial))
        if new != serial:
            revoked_updates.append((row_id, new))
    pending = [{'caref': caref, 'serial_number': serial, 'count': len(ids), 'rows': stored_rows(ids, raw)}
               for (caref, serial), ids in shared.items()]
    # A waiting row is listed with the rows of its CA that keep the spelling it waits for
    spelled = {}
    if waiting:
        for i, text in raw.items():
            spelled.setdefault((ca[i], text), []).append(i)
    pending += [{'caref': ca[row_id], 'serial_number': raw[row_id], 'count': 1, 'waits_for': new,
                 'rows': stored_rows([row_id] + spelled.get((ca[row_id], new), []), raw)}
                for row_id, new in waiting.items()]
    pending.sort(key=lambda d: (str(d['caref']), d['serial_number']))
    return cert_updates, revoked_updates, pending


def _apply(execute, executemany, stream, tables, value_param, false_literal):
    if TABLE not in tables:
        return
    revoked_rows = execute(_REVOKED, None).fetchall() if REVOKED in tables else []
    # Streamed: only the ids and serials stay in memory, never every certificate's PEM
    cert_updates, revoked_updates, pending = plan(stream(_CERTS), revoked_rows)
    # Two passes: a target spelling may still be another converted row's current one
    executemany(f"UPDATE {TABLE} SET serial_number = {{p}}s WHERE id = {{p}}i",
                [{'s': f'm144-{row_id}', 'i': row_id} for row_id, _ in cert_updates])
    executemany(f"UPDATE {TABLE} SET serial_number = {{p}}s WHERE id = {{p}}i",
                [{'s': new, 'i': row_id} for row_id, new in cert_updates])
    executemany(f"UPDATE {REVOKED} SET serial_number = {{p}}s WHERE id = {{p}}i",
                [{'s': new, 'i': row_id} for row_id, new in revoked_updates])
    if cert_updates or revoked_updates:
        logger.info("Migration 144: %d certificate and %d revocation serial(s) rewritten in decimal",
                    len(cert_updates), len(revoked_updates))
    if not execute(DUPLICATES, None).fetchall():
        execute(CREATE_INDEX, None)
    if CONFIG in tables:
        execute(CLEAR_PENDING, None)
    if not pending:
        return
    for d in pending:
        logger.warning("Migration 144: %s (left as stored)", describe_pending(d))
    logger.warning("Migration 144: these serials stay outside the unique index. %s", CLEANUP)
    if CONFIG in tables:
        execute(SET_PENDING.format(value=value_param, false=false_literal),
                json.dumps({'duplicates': pending}))


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def executemany(sql, params):
        if params:
            conn.executemany(sql.format(p=':'), params)
    _apply(lambda sql, value: conn.execute(sql) if value is None else conn.execute(sql, (value,)),
           executemany, conn.execute, tables, '?', '0')
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())

    def executemany(sql, params):
        if params:
            conn.execute(text(sql.format(p=':')), params)
    _apply(lambda sql, value: conn.execute(text(sql)) if value is None
           else conn.execute(text(sql), {'v': value}),
           executemany, lambda sql: conn.execute(text(sql), execution_options={'yield_per': 500}),
           tables, ':v', 'FALSE')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
