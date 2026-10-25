"""Migration 111 creates the DNS UPDATE listener tables."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models.acme_dns_update import AcmeDnsUpdateKey, AcmeProxyDnsChallenge

PG_URL = os.getenv('UCM_TEST_PG_URL')
KEYS = AcmeDnsUpdateKey.__tablename__
CHALLENGES = AcmeProxyDnsChallenge.__tablename__
TABLES = {KEYS, CHALLENGES}
KEYS_TABLE = AcmeDnsUpdateKey.__table__
CHALLENGES_TABLE = AcmeProxyDnsChallenge.__table__
INDEXES = {
    'ix_acme_dns_update_keys_acme_client_account_id',
    'ix_acme_dns_update_keys_eab_credential_id',
    'ix_acme_dns_update_keys_status',
    'ix_acme_proxy_dns_challenges_order_id',
    'ix_acme_proxy_dns_challenges_acme_client_account_id',
    'ix_acme_proxy_dns_challenges_record_name',
    'ix_acme_proxy_dns_challenges_zone_name',
    'idx_acme_proxy_dns_status_expires',
    'idx_acme_proxy_dns_expires',
}


def _migration():
    return importlib.import_module('migrations.111_acme_dns_update')


def _sqlite():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE acme_client_accounts (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE acme_eab_credentials (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE acme_client_orders (id INTEGER PRIMARY KEY)")
    return conn


def _names(conn, kind):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = ?", (kind,))}


def test_is_pg_compatible():
    assert _migration().pg_compatible is True


def test_sqlite_creates_tables_and_indexes():
    conn = _sqlite()
    _migration().upgrade(conn)
    assert TABLES <= _names(conn, 'table')
    assert INDEXES <= _names(conn, 'index')
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({CHALLENGES})")}
    assert 'zone_name' in cols
    info = {r[1]: r for r in conn.execute(f"PRAGMA table_info({KEYS})")}
    assert 'eab_bound' in info
    assert info['eab_bound'][3] == 1  # NOT NULL
    conn.execute("INSERT INTO acme_client_accounts (id) VALUES (1)")
    conn.execute(f"INSERT INTO {KEYS} (acme_client_account_id, name, secret) "
                 "VALUES (1, 'k.', 's')")
    assert conn.execute(f"SELECT eab_bound FROM {KEYS}").fetchone()[0] == 0


def test_sqlite_unique_constraints():
    conn = _sqlite()
    _migration().upgrade(conn)
    conn.execute("INSERT INTO acme_client_orders (id) VALUES (1)")
    ins = (f"INSERT INTO {CHALLENGES} (order_id, client_jwk_thumbprint, "
           "identifier, record_name, txt_value, zone_name, expires_at) "
           "VALUES (1, 't', 'x', 'n.', ?, 'z.', CURRENT_TIMESTAMP)")
    conn.execute(ins, ('a',))
    conn.execute(ins, ('b',))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(ins, ('a',))
    k = (f"INSERT INTO {KEYS} (acme_client_account_id, name, secret) "
         "VALUES (1, ?, 's')")
    conn.execute(k, ('k.example.',))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(k, ('k.example.',))
    row = conn.execute(f"SELECT algorithm, status FROM {KEYS}").fetchone()
    assert row == ('hmac-sha256', 'active')


def test_sqlite_second_run_is_idempotent():
    conn = _sqlite()
    _migration().upgrade(conn)
    conn.execute(f"INSERT INTO {KEYS} (acme_client_account_id, name, secret) "
                 "VALUES (1, 'k.', 's')")
    _migration().upgrade(conn)
    assert conn.execute(f"SELECT COUNT(*) FROM {KEYS}").fetchone()[0] == 1


def test_sqlite_downgrade_drops_tables():
    conn = _sqlite()
    _migration().upgrade(conn)
    _migration().downgrade(conn)
    assert not (TABLES & _names(conn, 'table'))
    assert not (INDEXES & _names(conn, 'index'))
    _migration().downgrade(conn)


def test_expires_index_pos():
    conn = _sqlite()
    _migration().upgrade(conn)
    cols = [r[2] for r in conn.execute("PRAGMA index_info(idx_acme_proxy_dns_expires)")]
    assert cols == ['expires_at']
    composite = [r[2] for r in conn.execute(
        "PRAGMA index_info(idx_acme_proxy_dns_status_expires)")]
    assert composite == ['status', 'expires_at']


def _plan(conn):
    # The filter of the row snapshot of the listener (records.ActiveRecordCache._load).
    return ' '.join(str(r[-1]) for r in conn.execute(
        f"EXPLAIN QUERY PLAN SELECT id FROM {CHALLENGES} WHERE expires_at > ?",
        ('2026-01-01 00:00:00',)))


def test_expires_index_serves_the_snapshot_query_pos():
    conn = _sqlite()
    _migration().upgrade(conn)
    plan = _plan(conn)
    assert plan.startswith('SEARCH') and 'idx_acme_proxy_dns_expires' in plan


def test_snapshot_query_scans_without_the_expires_index_neg():
    conn = _sqlite()
    _migration().upgrade(conn)
    conn.execute('DROP INDEX idx_acme_proxy_dns_expires')
    # The composite index starts with status: it can only be scanned, not searched.
    plan = _plan(conn)
    assert plan.startswith('SCAN') and 'SEARCH' not in plan


def test_model_and_migration_index_names_match_pos():
    model = {i.name for i in CHALLENGES_TABLE.indexes} | {
        i.name for t in (KEYS_TABLE,) for i in t.indexes}
    assert model == INDEXES


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_upgrade_twice_and_downgrade():
    schema = f"migtest_111_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for t in ('acme_client_accounts', 'acme_eab_credentials', 'acme_client_orders'):
            conn.execute(text(f"CREATE TABLE {t} (id SERIAL PRIMARY KEY)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        tables = {r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = :s"), {'s': schema})}
        assert TABLES <= tables
        col = conn.execute(text(
            "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
            f"WHERE table_schema = :s AND table_name = '{KEYS}' "
            "AND column_name = 'eab_bound'"), {'s': schema}).fetchone()
        assert col is not None and col[0] == 'boolean' and col[1] == 'NO'
        assert 'false' in col[2].lower()
        indexes = {r[0] for r in conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = :s"), {'s': schema})}
        assert INDEXES <= indexes
        _migration().downgrade(conn)
        tables = {r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = :s"), {'s': schema})}
        assert not (TABLES & tables)
        indexes = {r[0] for r in conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = :s"), {'s': schema})}
        assert not (INDEXES & indexes)
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
