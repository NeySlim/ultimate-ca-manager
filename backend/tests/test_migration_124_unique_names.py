"""Migration 124 suffixes duplicate names, then makes them unique."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from models.acme_client_account import AcmeClientAccount
from models.acme_models import DnsProvider
from services.webhook_service import WebhookEndpoint

PG_URL = os.getenv('UCM_TEST_PG_URL')

TABLES = (
    (DnsProvider.__tablename__, 'name'),
    (AcmeClientAccount.__tablename__, 'label'),
    (WebhookEndpoint.__tablename__, 'name'),
)

LONG = 'x' * 100
ROWS = [
    (1, 'cf'), (2, 'cf'), (3, 'cf (2)'), (4, 'cf'),
    (5, 'solo'),
    (6, LONG), (7, LONG),
]
# 3 holds "cf (2)" already: 2 and 4 take the next free suffixes.
EXPECTED = {1: 'cf', 2: 'cf (3)', 3: 'cf (2)', 4: 'cf (4)', 5: 'solo',
            6: LONG, 7: 'x' * 96 + ' (2)'}


def _migration():
    return importlib.import_module('migrations.124_unique_provider_account_webhook_names')


def _ddl(table, column):
    return f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, {column} VARCHAR(100) NOT NULL)"


def test_sqlite_suffixes_duplicates_and_enforces_uniqueness():
    conn = sqlite3.connect(':memory:')
    for table, column in TABLES:
        conn.execute(_ddl(table, column))
        conn.executemany(f"INSERT INTO {table} VALUES (?, ?)", ROWS)
    conn.commit()
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    for table, column in TABLES:
        got = dict(conn.execute(f"SELECT id, {column} FROM {table}").fetchall())
        assert got == EXPECTED, table
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"INSERT INTO {table} VALUES (99, 'solo')")


def test_sqlite_without_the_tables_is_a_no_op():
    _migration().upgrade(sqlite3.connect(':memory:'))


def test_a_fresh_schema_holds_the_same_constraint():
    """create_all builds fresh installations: the models carry the index too."""
    engine = create_engine('sqlite://')
    for model in (DnsProvider, AcmeClientAccount, WebhookEndpoint):
        model.__table__.create(engine)
    with engine.connect() as conn:
        for table, column in TABLES:
            indexes = {row[1] for row in conn.execute(text(f"PRAGMA index_list({table})"))}
            assert f'uq_{table}_{column}' in indexes, table
    rows = {
        DnsProvider: dict(name='same', provider_type='manual'),
        AcmeClientAccount: dict(label='same', directory_url='https://a.example/d',
                                email='a@example.com', account_key_algorithm='ES256',
                                is_default=False, proxy_enabled=False, order_poll_timeout_sec=1,
                                order_poll_interval_sec=1, http_timeout_sec=1),
        WebhookEndpoint: dict(name='same', url='https://a.example/h', auth_type='none'),
    }
    for model, values in rows.items():
        with engine.begin() as conn:
            conn.execute(model.__table__.insert().values(**values))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(model.__table__.insert().values(**values))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_suffixes_duplicates_and_enforces_uniqueness():
    schema = f"migtest_124_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for table, column in TABLES:
            conn.execute(text(_ddl(table, column)))
            for row_id, name in ROWS:
                conn.execute(text(f"INSERT INTO {table} VALUES (:i, :n)"), {'i': row_id, 'n': name})
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        for table, column in TABLES:
            got = dict(conn.execute(text(f"SELECT id, {column} FROM {table}")).fetchall())
            assert got == EXPECTED, table
            savepoint = conn.begin_nested()
            with pytest.raises(IntegrityError):
                conn.execute(text(f"INSERT INTO {table} VALUES (99, 'solo')"))
            savepoint.rollback()
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
