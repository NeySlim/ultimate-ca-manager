"""Migration 063 coverage for ACME ARI replacement identifiers."""
import importlib
import sqlite3

from sqlalchemy import create_engine, text


def _migration():
    return importlib.import_module('migrations.063_acme_order_replaces')


def test_migration_063_adds_replaces_on_sqlite_idempotently():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE acme_orders (id INTEGER PRIMARY KEY)')
    migration = _migration()

    migration.upgrade(conn)
    migration.upgrade(conn)

    columns = {
        row[1] for row in conn.execute('PRAGMA table_info(acme_orders)')
    }
    assert 'replaces' in columns
    indexes = {
        row[1] for row in conn.execute("PRAGMA index_list('acme_orders')")
    }
    assert 'ix_acme_orders_replaces' in indexes


def test_migration_063_sqlalchemy_path_uses_supplied_connection():
    engine = create_engine('sqlite:///:memory:')
    migration = _migration()

    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE acme_orders (id INTEGER PRIMARY KEY)'))
        migration.upgrade(conn)
        migration.upgrade(conn)
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info('acme_orders')"))
        }
        indexes = {
            row[1]
            for row in conn.execute(text("PRAGMA index_list('acme_orders')"))
        }

    assert 'replaces' in columns
    assert 'ix_acme_orders_replaces' in indexes
