"""Migration 062 OIDC provider verification fields."""

import importlib
import sqlite3

from sqlalchemy import create_engine, text


def _migration():
    return importlib.import_module('migrations.062_oidc_id_token_verification')


def _create_table(conn):
    conn.execute(text(
        'CREATE TABLE pro_sso_providers ('
        'id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)'
    ))


def test_migration_062_adds_oidc_fields_on_sqlite_idempotently():
    conn = sqlite3.connect(':memory:')
    conn.execute(
        'CREATE TABLE pro_sso_providers ('
        'id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)'
    )
    migration = _migration()

    migration.upgrade(conn)
    migration.upgrade(conn)

    columns = {
        row[1]: row for row in conn.execute(
            'PRAGMA table_info(pro_sso_providers)'
        ).fetchall()
    }
    assert {'oauth2_issuer', 'oauth2_jwks_uri', 'id_token_verify'} <= set(columns)
    conn.execute("INSERT INTO pro_sso_providers (id, name) VALUES (1, 'oidc')")
    assert conn.execute(
        'SELECT id_token_verify FROM pro_sso_providers WHERE id = 1'
    ).fetchone()[0] == 1


def test_migration_062_sqlalchemy_path_uses_supplied_connection():
    engine = create_engine('sqlite:///:memory:')
    migration = _migration()

    with engine.begin() as conn:
        _create_table(conn)
        migration.upgrade(conn)
        migration.upgrade(conn)
        columns = {
            row[1] for row in conn.execute(
                text('PRAGMA table_info(pro_sso_providers)')
            ).fetchall()
        }

    assert {'oauth2_issuer', 'oauth2_jwks_uri', 'id_token_verify'} <= columns
