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
LIVE, EXPIRED, LIVE_2, REVOKED, REPLACED, NEWER = 200, 201, 203, 204, 205, 206
# id, renewal_enabled, status, certificate_id, order_url, last_renewal_at, is_proxy_order, domains
ROWS = [
    (1, True, 'issued', 128, 'u1', RENEWED, False, 'a'),   # the original: keeps the schedule
    (2, True, 'issued', 128, 'u1', None, False, 'a'),      # what its renewal left behind
    (3, True, 'issued', 129, 'u2', None, False, 'b'),      # its own certificate
    (4, True, 'issued', 130, 'u3', RENEWED, False, 'c'),   # holds the certificate, not the URL, of 5
    (5, True, 'issued', 130, 'u4', None, False, 'c'),
    (6, False, 'issued', 131, 'u5', RENEWED, False, 'd'),  # switched off: its copy is all that renews
    (7, True, 'issued', 131, 'u5', None, False, 'd'),
    (8, True, 'issued', 132, 'u6', None, False, 'e'),      # never renewed: the older one proves nothing
    (9, True, 'issued', 132, 'u6', None, False, 'e'),
    (10, True, 'pending', None, 'u7', RENEWED, False, 'f'),
    (11, True, 'pending', None, 'u7', None, False, 'f'),
    (12, True, 'issued', 133, 'u8', None, False, 'g'),     # the renewed one is the younger
    (13, True, 'issued', 133, 'u8', RENEWED, False, 'g'),
    (14, True, 'issued', 134, 'u9', RENEWED, False, 'h'),  # holds the URL, not the certificate, of 15
    (15, True, 'issued', 135, 'u9', None, False, 'h'),
    (16, True, 'issued', 136, 'p1', RENEWED, False, 'i'),  # a proxy order never comes from a renewal
    (17, True, 'issued', 136, 'p1', None, True, 'i'),
    (20, True, 'valid', LIVE, 'v1', None, False, 'j'),     # the status check took it off the schedule
    (21, True, 'valid', EXPIRED, 'v2', None, False, 'k'),  # nobody counts on it any more
    (22, True, 'valid', LIVE, 'v3', None, True, 'l'),      # a proxy order: its client renews it
    (23, True, 'valid', None, 'v4', None, False, 'm'),     # import refused: no certificate to protect
    (24, True, 'valid', 999, 'v5', None, False, 'n'),      # its certificate is gone
    (25, True, 'valid', LIVE, 'v6', None, None, 'o'),      # a proxy column never written counts as false
    (26, True, 'valid', LIVE_2, 'v7', RENEWED, False, 'q'),  # back on the schedule, its leftover goes
    (27, True, 'issued', LIVE_2, 'v7', None, False, 'q'),
    (28, True, 'valid', EXPIRED, 'v8', RENEWED, False, 'r'),  # stays off: its copy is what renews
    (29, True, 'issued', EXPIRED, 'v8', None, False, 'r'),
    (30, True, 'valid', REVOKED, 'v9', None, False, 's'),  # revoked: nothing to keep alive
    (31, True, 'valid', REPLACED, 'w1', None, False, 't'),  # a newer order took the names over
    (32, True, 'issued', NEWER, 'w2', None, False, 't'),
    (33, True, 'valid', LIVE, 'w3', None, False, 'u'),     # a newer order that never finished replaces nothing
    (34, True, 'pending', NEWER, 'w4', None, False, 'u'),
]
CERT_ROWS = [(LIVE, '2099-01-01 00:00:00', False), (EXPIRED, '2001-01-01 00:00:00', False),
             (LIVE_2, '2099-01-01 00:00:00', False), (REVOKED, '2099-01-01 00:00:00', True),
             (REPLACED, '2099-01-01 00:00:00', None), (NEWER, '2099-01-01 00:00:00', False)]
REMOVED = {2, 27}
REISSUED = {20, 25, 26, 33}
DDL = (f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, renewal_enabled BOOLEAN, status TEXT, "
       "certificate_id INTEGER, order_url TEXT, last_renewal_at TIMESTAMP, is_proxy_order BOOLEAN, "
       "domains TEXT, environment TEXT DEFAULT 'production')")
CERT_DDL = f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, valid_to TIMESTAMP, revoked BOOLEAN)"
INSERT = (f"INSERT INTO {TABLE} (id, renewal_enabled, status, certificate_id, order_url, last_renewal_at, "
          "is_proxy_order, domains) VALUES (:id, :on, :status, :cert, :url, :renewed, :proxy, :domains)")
CERT_INSERT = f"INSERT INTO {CERTS} (id, valid_to, revoked) VALUES (:id, :valid_to, :revoked)"
PARAMS = [dict(zip(('id', 'on', 'status', 'cert', 'url', 'renewed', 'proxy', 'domains'), row)) for row in ROWS]
CERT_PARAMS = [dict(zip(('id', 'valid_to', 'revoked'), row)) for row in CERT_ROWS]
SELECT_ALL = f"SELECT id FROM {TABLE}"
SELECT_ISSUED = f"SELECT id FROM {TABLE} WHERE status = 'issued'"


def _migration():
    return importlib.import_module('migrations.121_acme_renewal_order_duplicates')


def _expected_kept():
    return {row[0] for row in ROWS} - REMOVED


def _expected_issued():
    return ({row[0] for row in ROWS if row[2] == 'issued'} | REISSUED) - REMOVED


def test_the_tables_are_the_real_ones():
    assert {'renewal_enabled', 'status', 'certificate_id', 'order_url', 'last_renewal_at', 'is_proxy_order',
            'domains', 'environment'} <= set(AcmeClientOrder.__table__.columns.keys())
    assert {'valid_to', 'revoked'} <= set(Certificate.__table__.columns.keys())


def test_sqlite_repairs_only_what_a_bug_did_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(DDL)
    conn.execute(CERT_DDL)
    conn.executemany(INSERT, PARAMS)
    conn.executemany(CERT_INSERT, CERT_PARAMS)
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[0] for row in conn.execute(SELECT_ALL)} == _expected_kept()
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
            assert {row[0] for row in conn.execute(text(SELECT_ALL))} == _expected_kept()
            assert {row[0] for row in conn.execute(text(SELECT_ISSUED))} == _expected_issued()
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()
