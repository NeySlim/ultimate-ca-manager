"""Migration 122: strip ':0' from the stored CDP, OCSP and AIA URLs of a CA.

With the HTTP protocol port set to 0 (built-in listener disabled), a CA created
while the Protocol Base URL had no port stored URLs such as
http://pki.example.com:0/cdp/x.crl, and copied them into every certificate it
issued (discussion #433). Dropping ':0' gives the default port, which is what
the fixed URL builder now produces. Certificates already issued are unchanged.
"""
import logging
import sqlite3

from utils.port_zero import strip_port_zero_from_stored

logger = logging.getLogger(__name__)
pg_compatible = True

_COLUMNS = ('cdp_url', 'ocsp_url', 'aia_ca_issuers_url')
_PATTERN = '%:0%'


def _fix_value(value):
    """New column value, or None when nothing changes."""
    new = strip_port_zero_from_stored(value)
    return new if new != value else None


def _fixes(rows):
    for ca_id, *values in rows:
        updates = {}
        for column, value in zip(_COLUMNS, values):
            new = _fix_value(value)
            if new is not None:
                updates[column] = new
        if updates:
            yield ca_id, updates


def _select(placeholder):
    # The pattern is bound: a literal ':0' in text() reads as a bind parameter.
    return (f"SELECT id, {', '.join(_COLUMNS)} FROM certificate_authorities "
            "WHERE " + " OR ".join(f"{c} LIKE {placeholder}" for c in _COLUMNS))


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'certificate_authorities'").fetchone() is None:
        return
    fixed = 0
    for ca_id, updates in _fixes(conn.execute(_select('?'), [_PATTERN] * len(_COLUMNS)).fetchall()):
        sets = ', '.join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE certificate_authorities SET {sets} WHERE id = ?",
                     [*updates.values(), ca_id])
        fixed += 1
    conn.commit()
    if fixed:
        logger.info("Migration 122: removed ':0' from the protocol URLs of %s CA(s)", fixed)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if 'certificate_authorities' not in inspect(conn).get_table_names():
        return
    rows = conn.execute(text(_select(':pattern')), {'pattern': _PATTERN}).fetchall()
    fixed = 0
    for ca_id, updates in _fixes(rows):
        sets = ', '.join(f"{k} = :{k}" for k in updates)
        conn.execute(text(f"UPDATE certificate_authorities SET {sets} WHERE id = :id"),
                     {**updates, 'id': ca_id})
        fixed += 1
    if fixed:
        logger.info("Migration 122: removed ':0' from the protocol URLs of %s CA(s)", fixed)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
