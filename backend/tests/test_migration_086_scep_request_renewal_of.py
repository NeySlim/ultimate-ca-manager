"""Migration 086 coverage: scep_requests.renewal_of."""
import importlib
import sqlite3

from sqlalchemy import create_engine, text


def _migration():
    return importlib.import_module('migrations.086_scep_request_renewal_of')


def test_migration_086_adds_the_column_on_sqlite_idempotently():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE scep_requests (id INTEGER PRIMARY KEY, transaction_id VARCHAR(100))')
    migration = _migration()
    migration.upgrade(conn)
    migration.upgrade(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info('scep_requests')")}
    assert 'renewal_of' in columns


def test_migration_086_sqlalchemy_path_uses_supplied_connection():
    engine = create_engine('sqlite:///:memory:')
    migration = _migration()
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE scep_requests (id INTEGER PRIMARY KEY, transaction_id VARCHAR(100))'))
        migration.upgrade(conn)
        migration.upgrade(conn)
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info('scep_requests')"))}
    assert 'renewal_of' in columns
