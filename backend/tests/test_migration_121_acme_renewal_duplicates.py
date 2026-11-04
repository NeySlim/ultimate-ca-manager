"""Migration 121 takes a renewal's leftover order off the schedule, and nothing else."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models.acme_models import AcmeClientOrder

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = AcmeClientOrder.__tablename__
RENEWED = '2026-07-06 16:53:53'
# id, renewal_enabled, status, certificate_id, order_url, last_renewal_at
ROWS = [
    (1, True, 'issued', 128, 'u1', RENEWED),   # the original: keeps the schedule
    (2, True, 'issued', 128, 'u1', None),      # what its renewal left behind
    (3, True, 'issued', 129, 'u2', None),      # same names perhaps, its own certificate
    (4, True, 'issued', 130, 'u3', RENEWED),   # holds the certificate, not the URL, of 5
    (5, True, 'issued', 130, 'u4', None),
    (6, False, 'issued', 131, 'u5', RENEWED),  # switched off: its copy is all that still renews
    (7, True, 'issued', 131, 'u5', None),
    (8, True, 'issued', 132, 'u6', None),      # never renewed: the older one proves nothing
    (9, True, 'issued', 132, 'u6', None),
    (10, True, 'pending', None, 'u7', RENEWED),
    (11, True, 'pending', None, 'u7', None),
    (12, True, 'issued', 133, 'u8', None),     # the renewed one is the younger: neither is a leftover
    (13, True, 'issued', 133, 'u8', RENEWED),
    (14, True, 'issued', 134, 'u9', RENEWED),  # holds the URL, not the certificate, of 15
    (15, True, 'issued', 135, 'u9', None),
]
TAKEN_OFF = {2}
DDL = (f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, renewal_enabled BOOLEAN, status TEXT, "
       "certificate_id INTEGER, order_url TEXT, last_renewal_at TIMESTAMP)")
INSERT = (f"INSERT INTO {TABLE} (id, renewal_enabled, status, certificate_id, order_url, last_renewal_at) "
          "VALUES (:id, :on, :status, :cert, :url, :renewed)")
PARAMS = [dict(zip(('id', 'on', 'status', 'cert', 'url', 'renewed'), row)) for row in ROWS]


def _migration():
    return importlib.import_module('migrations.121_acme_renewal_order_duplicates')


def _expected_on():
    return {row[0] for row in ROWS if row[1]} - TAKEN_OFF


def test_sqlite_takes_off_only_the_leftover_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(DDL)
    conn.executemany(INSERT, PARAMS)
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    on = {row[0] for row in conn.execute(f"SELECT id FROM {TABLE} WHERE renewal_enabled")}
    assert on == _expected_on()
    _migration().downgrade(conn)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_takes_off_only_the_leftover_and_is_idempotent():
    schema = f"migtest_121_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}"))
            conn.execute(text(DDL))
            conn.execute(text(INSERT), PARAMS)
            _migration().upgrade(conn)
            _migration().upgrade(conn)
            on = {row[0] for row in conn.execute(text(f"SELECT id FROM {TABLE} WHERE renewal_enabled"))}
            assert on == _expected_on()
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()
