"""Migration 105 deletes the legacy ``ldap_*`` settings, on both backends."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('UCM_TEST_PG_URL')

# The 20 keys of the specification, spelled out so a key dropped from the
# migration's list fails here.
LEGACY = (
    'ldap_server', 'ldap_port', 'ldap_use_ssl', 'ldap_use_starttls', 'ldap_base_dn',
    'ldap_bind_dn', 'ldap_bind_password', 'ldap_user_filter', 'ldap_username_attribute',
    'ldap_email_attribute', 'ldap_display_name_attribute', 'ldap_group_filter',
    'ldap_group_attribute', 'ldap_sync_enabled', 'ldap_sync_interval', 'ldap_default_role',
    'ldap_enabled', 'ldap_timeout', 'ldap_verify_ssl', 'ldap_ca_cert',
)
ENCRYPTED = 'ENC:gAAAAABmZm9vYmFyYmF6cXV4'
SCENARIO = {
    'ldap_server': ('ldap.example.test', False),
    'ldap_bind_password': (ENCRYPTED, True),
    'ldap_enabled': ('true', False),
    'system_name': ('UCM lab', False),
    'ldap_custom': ('kept', False),
}
KEPT = {'system_name': 'UCM lab', 'ldap_custom': 'kept'}
NEAR_MISSES = ('ldap', 'ldap_', 'LDAP_SERVER', 'ldap_server ', 'ldapxserver', 'ldap_bind_password_old',
               'sso.ldap_bind_password', 'ldap_ca_bundle')

SQLITE_SCHEMA = (
    'CREATE TABLE system_config (id INTEGER PRIMARY KEY, "key" VARCHAR(100) NOT NULL UNIQUE, '
    'value TEXT, encrypted BOOLEAN, description VARCHAR(255))',
    'CREATE TABLE pro_sso_providers (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, '
    'provider_type VARCHAR(50) NOT NULL, ldap_server VARCHAR(500), ldap_bind_dn VARCHAR(500), '
    'ldap_bind_password VARCHAR(500))',
)
PG_SCHEMA = (
    'CREATE TABLE system_config (id SERIAL PRIMARY KEY, "key" VARCHAR(100) NOT NULL UNIQUE, '
    'value TEXT, encrypted BOOLEAN, description VARCHAR(255))',
    'CREATE TABLE pro_sso_providers (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL, '
    'provider_type VARCHAR(50) NOT NULL, ldap_server VARCHAR(500), ldap_bind_dn VARCHAR(500), '
    'ldap_bind_password VARCHAR(500))',
)
SSO_ROW = ('Corp LDAP', 'ldap', 'ldap.example.test', 'cn=bind,dc=example,dc=test', ENCRYPTED)


def _migration():
    return importlib.import_module('migrations.105_legacy_ldap_settings')


def _seed_sqlite(conn, config):
    for stmt in SQLITE_SCHEMA:
        conn.execute(stmt)
    conn.executemany('INSERT INTO system_config ("key", value, encrypted) VALUES (?, ?, ?)',
                     [(k, v, enc) for k, (v, enc) in config.items()])
    conn.execute('INSERT INTO pro_sso_providers (name, provider_type, ldap_server, ldap_bind_dn, '
                 'ldap_bind_password) VALUES (?, ?, ?, ?, ?)', SSO_ROW)
    conn.commit()


def _config_sqlite(conn):
    return dict(conn.execute('SELECT "key", value FROM system_config').fetchall())


def _sso_sqlite(conn):
    return conn.execute('SELECT name, provider_type, ldap_server, ldap_bind_dn, ldap_bind_password '
                        'FROM pro_sso_providers').fetchall()


def test_sqlite_scenario_keeps_only_unlisted_keys():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    _seed_sqlite(conn, SCENARIO)
    m.upgrade(conn)
    assert _config_sqlite(conn) == KEPT
    assert _sso_sqlite(conn) == [SSO_ROW]
    m.upgrade(conn)
    assert _config_sqlite(conn) == KEPT
    assert _sso_sqlite(conn) == [SSO_ROW]


def test_sqlite_deletes_every_listed_key_whatever_its_value():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    values = ('', None, 'plain', ENCRYPTED)
    config = {k: (values[i % len(values)], i % len(values) == 3) for i, k in enumerate(LEGACY)}
    config.update({k: ('x', False) for k in NEAR_MISSES})
    _seed_sqlite(conn, config)
    m.upgrade(conn)
    assert set(_config_sqlite(conn)) == set(NEAR_MISSES)


def test_sqlite_change_is_committed():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    _seed_sqlite(conn, SCENARIO)
    m.upgrade(conn)
    conn.rollback()
    assert _config_sqlite(conn) == KEPT


def test_sqlite_without_system_config_is_a_no_op():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute(SQLITE_SCHEMA[1])
    conn.execute('INSERT INTO pro_sso_providers (name, provider_type, ldap_server, ldap_bind_dn, '
                 'ldap_bind_password) VALUES (?, ?, ?, ?, ?)', SSO_ROW)
    m.upgrade(conn)
    m.upgrade(conn)
    assert _sso_sqlite(conn) == [SSO_ROW]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {'pro_sso_providers'}


def test_sqlite_on_an_empty_database_is_a_no_op():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    m.upgrade(conn)
    m.upgrade(conn)
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_downgrade_is_a_no_op():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    _seed_sqlite(conn, SCENARIO)
    m.upgrade(conn)
    m.downgrade(conn)
    assert _config_sqlite(conn) == KEPT


def _pg_schema_conn(suffix):
    schema = f"migtest_105{suffix}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    conn.execute(text(f"CREATE SCHEMA {schema}"))
    conn.execute(text(f"SET search_path TO {schema}"))
    return engine, conn, schema


def _pg_drop(engine, conn, schema):
    conn.rollback()
    conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    conn.commit()
    conn.close()
    engine.dispose()


def _seed_pg(conn, config):
    for stmt in PG_SCHEMA:
        conn.execute(text(stmt))
    for k, (v, enc) in config.items():
        conn.execute(text('INSERT INTO system_config ("key", value, encrypted) VALUES (:k, :v, :e)'),
                     {'k': k, 'v': v, 'e': enc})
    conn.execute(text('INSERT INTO pro_sso_providers (name, provider_type, ldap_server, ldap_bind_dn, '
                      'ldap_bind_password) VALUES (:n, :t, :s, :d, :p)'),
                 dict(zip('ntsdp', SSO_ROW)))


def _config_pg(conn):
    return dict(conn.execute(text('SELECT "key", value FROM system_config')).fetchall())


def _sso_pg(conn):
    return [tuple(r) for r in conn.execute(text(
        'SELECT name, provider_type, ldap_server, ldap_bind_dn, ldap_bind_password '
        'FROM pro_sso_providers')).fetchall()]


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_scenario_keeps_only_unlisted_keys():
    m = _migration()
    engine, conn, schema = _pg_schema_conn('s')
    try:
        _seed_pg(conn, SCENARIO)
        m.upgrade(conn)
        assert _config_pg(conn) == KEPT
        assert _sso_pg(conn) == [SSO_ROW]
        m.upgrade(conn)
        assert _config_pg(conn) == KEPT
        assert _sso_pg(conn) == [SSO_ROW]
    finally:
        _pg_drop(engine, conn, schema)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_deletes_every_listed_key_whatever_its_value():
    m = _migration()
    engine, conn, schema = _pg_schema_conn('v')
    try:
        values = ('', None, 'plain', ENCRYPTED)
        config = {k: (values[i % len(values)], i % len(values) == 3) for i, k in enumerate(LEGACY)}
        config.update({k: ('x', False) for k in NEAR_MISSES})
        _seed_pg(conn, config)
        m.upgrade(conn)
        assert set(_config_pg(conn)) == set(NEAR_MISSES)
    finally:
        _pg_drop(engine, conn, schema)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_without_system_config_is_a_no_op():
    m = _migration()
    engine, conn, schema = _pg_schema_conn('n')
    try:
        conn.execute(text(PG_SCHEMA[1]))
        m.upgrade(conn)
        m.upgrade(conn)
        assert conn.execute(text("SELECT to_regclass('system_config')")).scalar() is None
    finally:
        _pg_drop(engine, conn, schema)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_runs_inside_the_runner_transaction():
    """The runner owns the transaction: a rollback after upgrade undoes it."""
    m = _migration()
    engine, conn, schema = _pg_schema_conn('t')
    try:
        _seed_pg(conn, SCENARIO)
        conn.commit()
        conn.execute(text(f"SET search_path TO {schema}"))
        m.upgrade(conn)
        conn.rollback()
        conn.execute(text(f"SET search_path TO {schema}"))
        assert set(_config_pg(conn)) == set(SCENARIO)
    finally:
        _pg_drop(engine, conn, schema)


def test_sqlite_runner_applies_105_on_a_file(tmp_path):
    import migration_runner

    db = tmp_path / 'ucm.db'
    conn = sqlite3.connect(db)
    _seed_sqlite(conn, SCENARIO)
    conn.close()
    assert migration_runner._run_pending_sqlite(['105_legacy_ldap_settings'], False, db_path=str(db))
    conn = sqlite3.connect(db)
    try:
        assert _config_sqlite(conn) == KEPT
        assert _sso_sqlite(conn) == [SSO_ROW]
        assert conn.execute("SELECT name FROM _migrations").fetchall() == [('105_legacy_ldap_settings',)]
    finally:
        conn.close()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_runner_applies_105():
    import migration_runner

    engine, conn, schema = _pg_schema_conn('r')
    try:
        _seed_pg(conn, SCENARIO)
        conn.execute(text("CREATE TABLE _migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT NOW())"))
        conn.commit()
        runner_engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={schema}'})
        try:
            assert migration_runner._run_pending_pg(runner_engine, ['105_legacy_ldap_settings'], False)
        finally:
            runner_engine.dispose()
        assert _config_pg(conn) == KEPT
        assert _sso_pg(conn) == [SSO_ROW]
        assert conn.execute(text("SELECT name FROM _migrations")).scalars().all() == ['105_legacy_ldap_settings']
    finally:
        _pg_drop(engine, conn, schema)
