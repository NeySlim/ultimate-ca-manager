"""Migration 096: store certificate_templates.key_type as its registry label.

The template API accepted legacy spellings ('ec:p384', 'rsa:4096') and stored
them as given: XCEP then announced those templates as RSA 2048 and issuance
from them failed. Spellings the key registry does not know are left as they are.
"""

import sqlite3

pg_compatible = True

_TABLE = 'certificate_templates'
_SELECT = f"SELECT id, key_type FROM {_TABLE} WHERE key_type IS NOT NULL"


def _changes(rows):
    from utils.key_algorithms import normalize_label
    for row_id, current in rows:
        label = normalize_label(current)
        if label and label != current:
            yield label, row_id


def _upgrade_sqlite(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (_TABLE,)).fetchone():
        return
    rows = conn.execute(_SELECT).fetchall()
    conn.executemany(f"UPDATE {_TABLE} SET key_type = ? WHERE id = ?", list(_changes(rows)))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    if not inspect(conn).has_table(_TABLE):
        return
    rows = conn.execute(text(_SELECT)).fetchall()
    for label, row_id in _changes(rows):
        conn.execute(text(f"UPDATE {_TABLE} SET key_type = :label WHERE id = :id"),
                     {'label': label, 'id': row_id})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Kept: older versions accept the canonical labels.
    pass
