"""Migration 066: preserve pre-2.200 behaviour on upgraded installs.

1. Syslog framing: v2.200 introduced ``syslog_framing`` with an automatic
   default of octet-counting (RFC 6587) whenever TLS is enabled — but every
   release before 2.200 always sent line framing. An install that configured
   syslog TCP+TLS under an earlier release therefore silently switched
   framing on upgrade, corrupting the stream for collectors that only speak
   line framing. Seed ``syslog_framing='line'`` for installs that already
   have a syslog configuration but no explicit framing choice; new setups
   keep the (better) automatic default.

2. OCSP response cache: before 2.200, revocation never invalidated cached
   responses (the delete used a key format the cache didn't). Rows cached
   by an earlier release for certificates revoked under that release can
   keep answering ``good`` until they expire (up to 24h after upgrade).
   Purge the cache once; it repopulates on demand.

Dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_CONFIG_TABLE = 'system_config'
_OCSP_CACHE_TABLE = 'ocsp_responses'


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    if _CONFIG_TABLE in tables:
        has_syslog = conn.execute(
            f"SELECT 1 FROM {_CONFIG_TABLE} WHERE key = 'syslog_enabled'"
        ).fetchone()
        has_framing = conn.execute(
            f"SELECT 1 FROM {_CONFIG_TABLE} WHERE key = 'syslog_framing'"
        ).fetchone()
        if has_syslog and not has_framing:
            conn.execute(
                f"INSERT INTO {_CONFIG_TABLE} (key, value) VALUES ('syslog_framing', 'line')"
            )
            logger.info('[066] seeded syslog_framing=line for pre-2.200 syslog config (SQLite)')

    if _OCSP_CACHE_TABLE in tables:
        cur = conn.execute(f'DELETE FROM {_OCSP_CACHE_TABLE}')
        logger.info('[066] purged %s cached OCSP response(s) (SQLite)', cur.rowcount)

    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())

    if _CONFIG_TABLE in tables:
        has_syslog = conn.execute(text(
            f"SELECT 1 FROM {_CONFIG_TABLE} WHERE key = 'syslog_enabled'"
        )).fetchone()
        has_framing = conn.execute(text(
            f"SELECT 1 FROM {_CONFIG_TABLE} WHERE key = 'syslog_framing'"
        )).fetchone()
        if has_syslog and not has_framing:
            conn.execute(text(
                f"INSERT INTO {_CONFIG_TABLE} (key, value) VALUES ('syslog_framing', 'line')"
            ))
            logger.info('[066] seeded syslog_framing=line for pre-2.200 syslog config (PostgreSQL)')

    if _OCSP_CACHE_TABLE in tables:
        result = conn.execute(text(f'DELETE FROM {_OCSP_CACHE_TABLE}'))
        logger.info('[066] purged %s cached OCSP response(s) (PostgreSQL)', result.rowcount)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """The seeded config row simply makes the previous implicit behaviour
    explicit, and the OCSP cache repopulates on demand — nothing to undo."""
    pass
