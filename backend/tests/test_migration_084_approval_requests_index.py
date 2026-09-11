"""Migration 084 coverage: index on approval_requests (status, request_type)."""
import importlib
import sqlite3

from sqlalchemy import create_engine, text


def _migration():
    return importlib.import_module('migrations.084_approval_requests_index')


def test_migration_084_adds_the_index_on_sqlite_idempotently():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE approval_requests (id INTEGER PRIMARY KEY, status VARCHAR(20), request_type VARCHAR(50))')
    migration = _migration()
    migration.upgrade(conn)
    migration.upgrade(conn)
    indexes = {row[1] for row in conn.execute("PRAGMA index_list('approval_requests')")}
    assert 'ix_approval_requests_status_type' in indexes


def test_migration_084_sqlalchemy_path_uses_supplied_connection():
    engine = create_engine('sqlite:///:memory:')
    migration = _migration()
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE approval_requests (id INTEGER PRIMARY KEY, status VARCHAR(20), request_type VARCHAR(50))'))
        migration.upgrade(conn)
        migration.upgrade(conn)
        indexes = {row[1] for row in conn.execute(text("PRAGMA index_list('approval_requests')"))}
    assert 'ix_approval_requests_status_type' in indexes
