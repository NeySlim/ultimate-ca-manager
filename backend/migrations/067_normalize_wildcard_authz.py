"""Migration 067: normalize pre-2.200 wildcard ACME authorizations.

Before v2.200 a wildcard authorization was stored with the ``*.`` prefix in
its identifier value and ``wildcard`` left false. v2.200 normalizes new rows
(base domain + wildcard=true) and its authorization-reuse lookup only matches
the normalized form — so every wildcard authorization created before the
upgrade could never be reused, forcing a dns-01 re-validation on the first
renewal (which fails outright for certbot --manual).

Rewrite the legacy rows to the normalized form. JSON identifiers look like
{"type": "dns", "value": "*.example.com"}.

Dual-backend (SQLite + PostgreSQL).
"""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_TABLE = 'acme_authorizations'


def _normalized_rows(rows):
    """Yield (new_identifier_json, id) for rows needing normalization."""
    for row_id, identifier in rows:
        try:
            data = json.loads(identifier)
        except (TypeError, ValueError):
            continue
        value = data.get('value') or ''
        if data.get('type') == 'dns' and value.startswith('*.'):
            data['value'] = value[2:]
            yield json.dumps(data), row_id


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if _TABLE not in tables:
        logger.info('[067] %s absent, skipping (SQLite)', _TABLE)
        return

    rows = conn.execute(
        f"SELECT id, identifier FROM {_TABLE} WHERE identifier LIKE '%*.%'"
    ).fetchall()
    count = 0
    for new_identifier, row_id in _normalized_rows(rows):
        conn.execute(
            f'UPDATE {_TABLE} SET identifier = ?, wildcard = 1 WHERE id = ?',
            (new_identifier, row_id),
        )
        count += 1
    conn.commit()
    logger.info('[067] normalized %s wildcard authorization(s) (SQLite)', count)


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        logger.info('[067] %s absent, skipping (PostgreSQL)', _TABLE)
        return

    rows = conn.execute(text(
        f"SELECT id, identifier FROM {_TABLE} WHERE identifier LIKE '%*.%'"
    )).fetchall()
    count = 0
    for new_identifier, row_id in _normalized_rows(rows):
        conn.execute(
            text(f'UPDATE {_TABLE} SET identifier = :ident, wildcard = TRUE '
                 'WHERE id = :row_id'),
            {'ident': new_identifier, 'row_id': row_id},
        )
        count += 1
    logger.info('[067] normalized %s wildcard authorization(s) (PostgreSQL)', count)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """The normalized form is what current code writes for new rows; there
    is nothing meaningful to restore."""
    pass
