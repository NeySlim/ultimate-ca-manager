"""Migration 103: SAML message-id table and provider options, both backends."""
import importlib.util
import os
import sqlite3
import uuid

import pytest


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', '103_saml_strict.py')
    spec = importlib.util.spec_from_file_location('m103', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PROVIDERS = ('CREATE TABLE pro_sso_providers (id INTEGER PRIMARY KEY, name VARCHAR(100), '
              'provider_type VARCHAR(50), saml_sign_requests BOOLEAN)')


def _provider_columns(conn):
    return {row[1] for row in conn.execute('PRAGMA table_info(pro_sso_providers)')}


def test_sqlite_upgrade_is_idempotent():
    migration = _migration()
    assert migration.pg_compatible is True
    conn = sqlite3.connect(':memory:')
    conn.execute(_PROVIDERS)
    conn.execute("INSERT INTO pro_sso_providers VALUES (1, 'kc', 'saml', 1)")
    migration.upgrade(conn)
    # The sign flag was never applied: reset once, then the operator's choice stays.
    assert conn.execute('SELECT saml_sign_requests FROM pro_sso_providers').fetchone() == (0,)
    conn.execute('UPDATE pro_sso_providers SET saml_sign_requests = 1')
    migration.upgrade(conn)
    assert conn.execute('SELECT saml_sign_requests FROM pro_sso_providers').fetchone() == (1,)
    assert {'saml_allow_idp_initiated', 'saml_name_id_format'} <= _provider_columns(conn)
    assert conn.execute('SELECT saml_allow_idp_initiated FROM pro_sso_providers').fetchone() == (0,)
    conn.execute("INSERT INTO pro_sso_saml_message_ids (kind, message_id, provider_id, expires_at) "
                 "VALUES ('assertion', '_a1', 1, '2030-01-01 00:00:00')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO pro_sso_saml_message_ids (kind, message_id, provider_id, expires_at) "
                     "VALUES ('assertion', '_a1', 1, '2030-01-01 00:00:00')")


def test_sqlite_without_providers_table_creates_only_the_cache():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'pro_sso_saml_message_ids' in tables and 'pro_sso_providers' not in tables


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_postgresql_upgrade_is_idempotent():
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError
    schema = f"m103_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    migration = _migration()
    insert = text("INSERT INTO pro_sso_saml_message_ids (kind, message_id, provider_id, expires_at) "
                  "VALUES ('assertion', '_a1', 1, '2030-01-01 00:00:00')")
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            conn.execute(text(_PROVIDERS))
            conn.execute(text("INSERT INTO pro_sso_providers VALUES (1, 'kc', 'saml', TRUE)"))
        for wanted_sign in (False, True):
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO {schema}'))
                migration.upgrade(conn)
                sign = conn.execute(text('SELECT saml_sign_requests FROM pro_sso_providers')).scalar()
                assert sign is wanted_sign
                conn.execute(text('UPDATE pro_sso_providers SET saml_sign_requests = TRUE'))
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO {schema}'))
            row = conn.execute(text('SELECT saml_allow_idp_initiated, saml_name_id_format '
                                    'FROM pro_sso_providers')).one()
            assert row == (False, None)
            conn.execute(insert)
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(text(f'SET search_path TO {schema}'))
                conn.execute(insert)
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
