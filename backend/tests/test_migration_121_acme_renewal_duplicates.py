"""Migration 121 repairs the renewal schedule of ACME client orders, and touches nothing else."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from models import Certificate
from models.acme_models import AcmeClientOrder

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = AcmeClientOrder.__tablename__
CERTS = Certificate.__tablename__
RENEWED = '2026-07-06 16:53:53'
LIVE, EXPIRED = 200, 201
# id, renewal_enabled, status, certificate_id, order_url, last_renewal_at, is_proxy_order
ROWS = [
    (1, True, 'issued', 128, 'u1', RENEWED, False),   # the original: keeps the schedule
    (2, True, 'issued', 128, 'u1', None, False),      # what its renewal left behind
    (3, True, 'issued', 129, 'u2', None, False),      # same names perhaps, its own certificate
    (4, True, 'issued', 130, 'u3', RENEWED, False),   # holds the certificate, not the URL, of 5
    (5, True, 'issued', 130, 'u4', None, False),
    (6, False, 'issued', 131, 'u5', RENEWED, False),  # switched off: its copy is all that renews
    (7, True, 'issued', 131, 'u5', None, False),
    (8, True, 'issued', 132, 'u6', None, False),      # never renewed: the older one proves nothing
    (9, True, 'issued', 132, 'u6', None, False),
    (10, True, 'pending', None, 'u7', RENEWED, False),
    (11, True, 'pending', None, 'u7', None, False),
    (12, True, 'issued', 133, 'u8', None, False),     # the renewed one is the younger
    (13, True, 'issued', 133, 'u8', RENEWED, False),
    (14, True, 'issued', 134, 'u9', RENEWED, False),  # holds the URL, not the certificate, of 15
    (15, True, 'issued', 135, 'u9', None, False),
    (20, True, 'valid', LIVE, 'v1', None, False),     # the status check took it off the schedule
    (21, True, 'valid', EXPIRED, 'v2', None, False),  # nobody counts on it any more
    (22, True, 'valid', LIVE, 'v3', None, True),      # a proxy order: its client renews it
    (23, True, 'valid', None, 'v4', None, False),     # import refused: no certificate to protect
    (24, True, 'valid', 999, 'v5', None, False),      # its certificate is gone
    (25, True, 'valid', LIVE, 'v6', None, None),      # a proxy column never written counts as false
    (26, True, 'valid', 203, 'v7', RENEWED, False),   # back on the schedule, and its leftover comes off
    (27, True, 'issued', 203, 'v7', None, False),
    (28, True, 'valid', EXPIRED, 'v8', RENEWED, False),  # stays off the schedule: its copy is what renews
    (29, True, 'issued', EXPIRED, 'v8', None, False),
]
CERT_ROWS = [(LIVE, '2099-01-01 00:00:00'), (EXPIRED, '2001-01-01 00:00:00'), (203, '2099-01-01 00:00:00')]
TAKEN_OFF = {2, 27}
REISSUED = {20, 25, 26}
DDL = (f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, renewal_enabled BOOLEAN, status TEXT, "
       "certificate_id INTEGER, order_url TEXT, last_renewal_at TIMESTAMP, is_proxy_order BOOLEAN)")
CERT_DDL = f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, valid_to TIMESTAMP)"
INSERT = (f"INSERT INTO {TABLE} (id, renewal_enabled, status, certificate_id, order_url, last_renewal_at, "
          "is_proxy_order) VALUES (:id, :on, :status, :cert, :url, :renewed, :proxy)")
CERT_INSERT = f"INSERT INTO {CERTS} (id, valid_to) VALUES (:id, :valid_to)"
PARAMS = [dict(zip(('id', 'on', 'status', 'cert', 'url', 'renewed', 'proxy'), row)) for row in ROWS]
CERT_PARAMS = [dict(zip(('id', 'valid_to'), row)) for row in CERT_ROWS]
SELECT_ON = f"SELECT id FROM {TABLE} WHERE renewal_enabled"
SELECT_ISSUED = f"SELECT id FROM {TABLE} WHERE status = 'issued'"


def _migration():
    return importlib.import_module('migrations.121_acme_renewal_order_duplicates')


def _expected_on():
    return {row[0] for row in ROWS if row[1]} - TAKEN_OFF


def _expected_issued():
    return {row[0] for row in ROWS if row[2] == 'issued'} | REISSUED


def test_the_tables_are_the_real_ones():
    assert {'renewal_enabled', 'status', 'certificate_id', 'order_url', 'last_renewal_at', 'is_proxy_order'} \
        <= set(AcmeClientOrder.__table__.columns.keys())
    assert 'valid_to' in Certificate.__table__.columns


def test_sqlite_repairs_only_what_a_bug_did_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(DDL)
    conn.execute(CERT_DDL)
    conn.executemany(INSERT, PARAMS)
    conn.executemany(CERT_INSERT, CERT_PARAMS)
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[0] for row in conn.execute(SELECT_ON)} == _expected_on()
    assert {row[0] for row in conn.execute(SELECT_ISSUED)} == _expected_issued()
    _migration().downgrade(conn)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_repairs_only_what_a_bug_did_and_is_idempotent():
    schema = f"migtest_121_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {schema}"))
            conn.execute(text(f"SET search_path TO {schema}"))
            conn.execute(text(DDL))
            conn.execute(text(CERT_DDL))
            conn.execute(text(INSERT), PARAMS)
            conn.execute(text(CERT_INSERT), CERT_PARAMS)
            _migration().upgrade(conn)
            _migration().upgrade(conn)
            assert {row[0] for row in conn.execute(text(SELECT_ON))} == _expected_on()
            assert {row[0] for row in conn.execute(text(SELECT_ISSUED))} == _expected_issued()
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()
