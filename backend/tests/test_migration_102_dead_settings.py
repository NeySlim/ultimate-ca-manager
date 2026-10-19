"""Migration 102 deletes the settings nothing reads any more, on both backends."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
KEPT = ('session_timeout', 'acme.enabled', 'system_name')


def _migration():
    return importlib.import_module('migrations.102_dead_settings')


def test_sqlite_deletes_only_the_dead_keys():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE system_config (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO system_config VALUES (?, 'x')", [(k,) for k in m.DEAD_KEYS + KEPT])
    m.upgrade(conn)
    m.upgrade(conn)
    left = {r[0] for r in conn.execute("SELECT key FROM system_config")}
    assert left == set(KEPT)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_deletes_only_the_dead_keys():
    m = _migration()
    schema = f"migtest_102_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)"))
        for k in m.DEAD_KEYS + KEPT:
            conn.execute(text("INSERT INTO system_config VALUES (:k, 'x')"), {'k': k})
        m.upgrade(conn)
        m.upgrade(conn)
        left = {r[0] for r in conn.execute(text("SELECT key FROM system_config"))}
        assert left == set(KEPT)
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


RULES = json.dumps({'max_validity_days': 90, 'required_extensions': ['keyUsage'],
                    'forbidden_extensions': [],
                    'san_restrictions': {'max_dns_names': 5, 'dns_pattern': '',
                                         'require_approval_for_external': True}})
CLEAN = {'max_validity_days': 90, 'san_restrictions': {'max_dns_names': 5, 'dns_pattern': ''}}


def test_sqlite_drops_the_dead_policy_rules():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE certificate_policies (id INTEGER PRIMARY KEY, rules TEXT)")
    conn.execute("INSERT INTO certificate_policies VALUES (1, ?)", (RULES,))
    conn.execute("INSERT INTO certificate_policies VALUES (2, 'not json')")
    m.upgrade(conn)
    m.upgrade(conn)
    assert json.loads(conn.execute("SELECT rules FROM certificate_policies WHERE id = 1").fetchone()[0]) == CLEAN
    assert conn.execute("SELECT rules FROM certificate_policies WHERE id = 2").fetchone()[0] == 'not json'


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_drops_the_dead_policy_rules():
    m = _migration()
    schema = f"migtest_102p_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE certificate_policies (id INTEGER PRIMARY KEY, rules TEXT NOT NULL)"))
        conn.execute(text("INSERT INTO certificate_policies VALUES (1, :r)"), {'r': RULES})
        m.upgrade(conn)
        m.upgrade(conn)
        stored = conn.execute(text("SELECT rules FROM certificate_policies WHERE id = 1")).scalar()
        assert json.loads(stored) == CLEAN
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_sqlite_adds_the_discovery_notify_email_column():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE discovery_scan_profiles (id INTEGER PRIMARY KEY, name TEXT)")
    m.upgrade(conn)
    m.upgrade(conn)
    assert 'notify_email' in {r[1] for r in conn.execute("PRAGMA table_info(discovery_scan_profiles)")}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_adds_the_discovery_notify_email_column():
    m = _migration()
    schema = f"migtest_102d_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE discovery_scan_profiles (id INTEGER PRIMARY KEY, name TEXT)"))
        m.upgrade(conn)
        m.upgrade(conn)
        columns = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = 'discovery_scan_profiles'"), {'s': schema})}
        assert 'notify_email' in columns
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


LEGACY = {'report_expiry_enabled': 'true', 'report_expiry_recipients': '["ops@example.test"]',
          'report_compliance_enabled': 'true', 'report_compliance_recipients': '[]'}


def _check_legacy_reports(config):
    assert not any(k in config for k in LEGACY)
    sched = json.loads(config['report_schedule_expiring_certificates'])
    assert sched['enabled'] is True and sched['frequency'] == 'daily'
    assert sched['recipients'] == ['ops@example.test']
    # Switched on without recipients: it never sent anything, nothing to keep
    assert 'report_schedule_compliance_status' not in config


def test_sqlite_converts_the_legacy_report_switches():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE system_config (id INTEGER PRIMARY KEY NOT NULL, key VARCHAR(100) NOT NULL, value TEXT)")
    conn.executemany("INSERT INTO system_config (key, value) VALUES (?, ?)", list(LEGACY.items()))
    m.upgrade(conn)
    m.upgrade(conn)
    _check_legacy_reports(dict(conn.execute("SELECT key, value FROM system_config").fetchall()))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_converts_the_legacy_report_switches():
    m = _migration()
    schema = f"migtest_102r_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE system_config (id SERIAL PRIMARY KEY, key VARCHAR(100) NOT NULL, value TEXT)"))
        for k, v in LEGACY.items():
            conn.execute(text("INSERT INTO system_config (key, value) VALUES (:k, :v)"), {'k': k, 'v': v})
        m.upgrade(conn)
        m.upgrade(conn)
        _check_legacy_reports(dict(conn.execute(text("SELECT key, value FROM system_config")).fetchall()))
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


SITE = {'site_name': 'pki-site', 'system_name': ''}


def _check_site_name(config):
    assert 'site_name' not in config
    assert config['system_name'] == 'pki-site'


def test_sqlite_carries_site_name_into_system_name():
    m = _migration()
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE system_config (id INTEGER PRIMARY KEY NOT NULL, key VARCHAR(100) NOT NULL, value TEXT)")
    conn.executemany("INSERT INTO system_config (key, value) VALUES (?, ?)", list(SITE.items()))
    m.upgrade(conn)
    m.upgrade(conn)
    rows = conn.execute("SELECT key, value FROM system_config").fetchall()
    assert len(rows) == 1
    _check_site_name(dict(rows))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_carries_site_name_into_system_name():
    m = _migration()
    schema = f"migtest_102s_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE system_config (id SERIAL PRIMARY KEY, key VARCHAR(100) NOT NULL, value TEXT)"))
        for k, v in SITE.items():
            conn.execute(text("INSERT INTO system_config (key, value) VALUES (:k, :v)"), {'k': k, 'v': v})
        m.upgrade(conn)
        m.upgrade(conn)
        rows = conn.execute(text("SELECT key, value FROM system_config")).fetchall()
        assert len(rows) == 1
        _check_site_name(dict(rows))
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
