"""Migration 122 strips ':0' from the stored CDP, OCSP and AIA URLs of a CA (discussion #433)."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('UCM_TEST_PG_URL')

DDL = ("CREATE TABLE certificate_authorities (id INTEGER PRIMARY KEY, "
       "cdp_url VARCHAR(512), ocsp_url VARCHAR(512), aia_ca_issuers_url VARCHAR(512), "
       "sia_urls TEXT)")

ROWS = [
    # plain string form
    (1, 'http://pki.example.com:0/cdp/a.crl', 'http://pki.example.com:0/ocsp', 'http://pki.example.com:0/ca/a.cer', None),
    # JSON list form, one clean and one broken URL, plus a duplicate once stripped
    (2, json.dumps(['http://pki.example.com:0/cdp/b.crl', 'http://pki.example.com/cdp/b.crl']),
     json.dumps(['http://pki.example.com:0/ocsp']), json.dumps(['https://pki.example.com:0/ca/b.cer']), None),
    # nothing to change: other ports, ':0' as a prefix of a longer port, ':0' inside a path
    (3, 'http://pki.example.com:8080/cdp/c.crl', 'http://pki.example.com:08080/ocsp', 'http://pki.example.com/x:0/ca.cer', None),
    # IPv6 literal, bare host with ':0' and a user-supplied SIA that is left alone
    (4, 'http://[2001:db8::1]:0/cdp/d.crl', 'http://pki.example.com:0', None, json.dumps(['http://x.example.com:0/repo'])),
    # empty
    (5, None, None, None, None),
    # the scheme keeps the case it was stored in
    (6, 'HTTP://pki.example.com:0/cdp/e.crl', None, None, None),
    # the port ends at a query or a fragment too, and ':0' before an '@' is a password
    (7, 'http://pki.example.com:0?x=1', 'http://pki.example.com:0#y', 'http://user:0@pki.example.com/ca.cer', None),
    # a URL carrying credentials is the operator's own: left alone
    (8, 'http://user:p@pki.example.com:0/f.crl', None, None, None),
]

EXPECTED = {
    1: ('http://pki.example.com/cdp/a.crl', 'http://pki.example.com/ocsp', 'http://pki.example.com/ca/a.cer', None),
    2: (json.dumps(['http://pki.example.com/cdp/b.crl']), json.dumps(['http://pki.example.com/ocsp']),
        json.dumps(['https://pki.example.com/ca/b.cer']), None),
    3: ('http://pki.example.com:8080/cdp/c.crl', 'http://pki.example.com:08080/ocsp', 'http://pki.example.com/x:0/ca.cer', None),
    4: ('http://[2001:db8::1]/cdp/d.crl', 'http://pki.example.com', None, json.dumps(['http://x.example.com:0/repo'])),
    5: (None, None, None, None),
    6: ('HTTP://pki.example.com/cdp/e.crl', None, None, None),
    7: ('http://pki.example.com?x=1', 'http://pki.example.com#y', 'http://user:0@pki.example.com/ca.cer', None),
    8: ('http://user:p@pki.example.com:0/f.crl', None, None, None),
}


def _migration():
    return importlib.import_module('migrations.122_strip_port_zero_protocol_urls')


def test_sqlite_strips_port_zero_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute(DDL)
    conn.executemany("INSERT INTO certificate_authorities VALUES (?, ?, ?, ?, ?)", ROWS)
    conn.commit()
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    got = {r[0]: r[1:] for r in conn.execute(
        "SELECT id, cdp_url, ocsp_url, aia_ca_issuers_url, sia_urls FROM certificate_authorities")}
    assert got == EXPECTED


def test_sqlite_without_the_table_is_a_no_op():
    _migration().upgrade(sqlite3.connect(':memory:'))


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_strips_port_zero_and_is_idempotent():
    schema = f"migtest_122_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(DDL))
        for row in ROWS:
            conn.execute(text("INSERT INTO certificate_authorities VALUES "
                              "(:i, :c, :o, :a, :s)"),
                         dict(zip('icoas', row)))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        got = {r[0]: tuple(r[1:]) for r in conn.execute(text(
            "SELECT id, cdp_url, ocsp_url, aia_ca_issuers_url, sia_urls FROM certificate_authorities"))}
        assert got == EXPECTED
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
