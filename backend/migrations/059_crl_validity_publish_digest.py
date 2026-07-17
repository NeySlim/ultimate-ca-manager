"""Migration 059: per-CA CRL validity / publish / digest + next_publish metadata.

Discussion #207 — decouple full-CRL nextUpdate (validity) from publish schedule,
allow configurable CRL digest, and expose next_publish on CRLMetadata.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_CA_COLS_SQLITE = [
    ('crl_validity_days', 'INTEGER DEFAULT 7'),
    ('crl_publish_interval_hours', 'INTEGER DEFAULT 168'),
    ('crl_digest', "TEXT DEFAULT 'sha256'"),
]
_CA_COLS_PG = [
    ('crl_validity_days', 'INTEGER DEFAULT 7'),
    ('crl_publish_interval_hours', 'INTEGER DEFAULT 168'),
    ('crl_digest', "VARCHAR(20) DEFAULT 'sha256'"),
]


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='certificate_authorities'"
    )
    if cur.fetchone():
        existing = {row[1] for row in conn.execute('PRAGMA table_info(certificate_authorities)')}
        for name, ddl in _CA_COLS_SQLITE:
            if name in existing:
                continue
            conn.execute(f'ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}')
            logger.info(f'[059] added certificate_authorities.{name} (SQLite)')

    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='crl_metadata'"
    )
    if cur.fetchone():
        existing = {row[1] for row in conn.execute('PRAGMA table_info(crl_metadata)')}
        if 'next_publish' not in existing:
            conn.execute('ALTER TABLE crl_metadata ADD COLUMN next_publish DATETIME')
            logger.info('[059] added crl_metadata.next_publish (SQLite)')

    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    tables = set(insp.get_table_names())

    if 'certificate_authorities' in tables:
        existing = {c['name'] for c in insp.get_columns('certificate_authorities')}
        for name, ddl in _CA_COLS_PG:
            if name in existing:
                continue
            conn.execute(text(
                f'ALTER TABLE certificate_authorities ADD COLUMN {name} {ddl}'
            ))
            logger.info(f'[059] added certificate_authorities.{name} (PostgreSQL)')

    if 'crl_metadata' in tables:
        existing = {c['name'] for c in insp.get_columns('crl_metadata')}
        if 'next_publish' not in existing:
            conn.execute(text(
                'ALTER TABLE crl_metadata ADD COLUMN next_publish TIMESTAMP'
            ))
            logger.info('[059] added crl_metadata.next_publish (PostgreSQL)')


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    cols_ca = ['crl_validity_days', 'crl_publish_interval_hours', 'crl_digest']
    if isinstance(conn, sqlite3.Connection):
        for c in cols_ca + ['next_publish']:
            try:
                if c == 'next_publish':
                    conn.execute(f'ALTER TABLE crl_metadata DROP COLUMN {c}')
                else:
                    conn.execute(
                        f'ALTER TABLE certificate_authorities DROP COLUMN {c}'
                    )
            except Exception:
                pass
        conn.commit()
    else:
        from sqlalchemy import text
        for c in cols_ca:
            conn.execute(text(
                f'ALTER TABLE certificate_authorities DROP COLUMN IF EXISTS {c}'
            ))
        conn.execute(text(
            'ALTER TABLE crl_metadata DROP COLUMN IF EXISTS next_publish'
        ))
