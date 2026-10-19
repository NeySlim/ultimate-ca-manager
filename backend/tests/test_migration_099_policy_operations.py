"""Migration 099 on both backends: policy operations backfilled as the old
type behaved, approval requests allowed without a requester."""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

PG_URL = os.getenv('UCM_TEST_PG_URL')

# certificate_policies and approval_requests as create_all built them before 099
SQLITE_SCHEMA = (
    "CREATE TABLE users (id INTEGER NOT NULL, PRIMARY KEY (id))",
    "CREATE TABLE certificate_policies (id INTEGER NOT NULL, name VARCHAR(100) NOT NULL,"
    " policy_type VARCHAR(50), PRIMARY KEY (id))",
    "CREATE TABLE approval_requests (id INTEGER NOT NULL, request_type VARCHAR(50) NOT NULL,"
    " certificate_id INTEGER, request_data TEXT, policy_id INTEGER,"
    " requester_id INTEGER NOT NULL, status VARCHAR(20), PRIMARY KEY (id),"
    " FOREIGN KEY(policy_id) REFERENCES certificate_policies (id),"
    " FOREIGN KEY(requester_id) REFERENCES users (id))",
    "CREATE INDEX ix_approval_requests_status_type ON approval_requests (status, request_type)",
)

PG_SCHEMA = (
    "CREATE TABLE users (id SERIAL PRIMARY KEY)",
    "CREATE TABLE certificate_policies (id SERIAL PRIMARY KEY, name VARCHAR(100) NOT NULL,"
    " policy_type VARCHAR(50))",
    "CREATE TABLE approval_requests (id SERIAL PRIMARY KEY, request_type VARCHAR(50) NOT NULL,"
    " certificate_id INTEGER, request_data TEXT,"
    " policy_id INTEGER REFERENCES certificate_policies (id),"
    " requester_id INTEGER NOT NULL REFERENCES users (id), status VARCHAR(20))",
)

ROWS = (
    "INSERT INTO users (id) VALUES (1)",
    "INSERT INTO certificate_policies (id, name, policy_type) VALUES"
    " (1, 'issue', 'issuance'), (2, 'renew', 'renewal'), (3, 'revoke', 'revocation'), (4, 'none', NULL)",
    "INSERT INTO approval_requests (id, request_type, policy_id, requester_id, status)"
    " VALUES (7, 'csr', 1, 1, 'pending')",
)

EXPECTED = {'issue': ['issuance'], 'renew': [], 'revoke': [], 'none': ['issuance']}


def _migration():
    return importlib.import_module('migrations.099_policy_operations')


def _sqlite():
    conn = sqlite3.connect(':memory:')
    conn.execute("PRAGMA foreign_keys=ON")
    for statement in SQLITE_SCHEMA + ROWS:
        conn.execute(statement)
    conn.commit()
    return conn


def test_sqlite_backfills_and_relaxes_the_requester():
    conn = _sqlite()
    migration = _migration()
    migration.upgrade(conn)
    migration.upgrade(conn)
    ops = {name: json.loads(value) for name, value in
           conn.execute("SELECT name, operations FROM certificate_policies")}
    assert ops == EXPECTED
    cols = {row[1]: row for row in conn.execute("PRAGMA table_info(approval_requests)")}
    assert cols['requester_id'][3] == 0
    # The rows, the index and the foreign keys survive the rebuild
    assert conn.execute("SELECT id, requester_id, status FROM approval_requests").fetchall() == [(7, 1, 'pending')]
    assert 'ix_approval_requests_status_type' in {r[1] for r in conn.execute("PRAGMA index_list('approval_requests')")}
    assert {r[2] for r in conn.execute("PRAGMA foreign_key_list('approval_requests')")} == {'users', 'certificate_policies'}
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.execute("INSERT INTO approval_requests (request_type, status) VALUES ('renewal', 'pending')")


def test_sqlite_leaves_a_nullable_requester_alone():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE approval_requests (id INTEGER PRIMARY KEY, request_type VARCHAR(50) NOT NULL,"
                 " requester_id INTEGER REFERENCES users(id))")
    conn.execute("INSERT INTO approval_requests (request_type) VALUES ('csr')")
    _migration().upgrade(conn)
    assert conn.execute("SELECT sql FROM sqlite_master WHERE name='approval_requests'").fetchone()[0].startswith(
        'CREATE TABLE approval_requests')


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
class TestPostgres:
    @pytest.fixture()
    def connection(self):
        worker = os.getenv('PYTEST_XDIST_WORKER', 'main')
        schema = f'migtest_099_{worker}'
        engine = create_engine(PG_URL)
        conn = engine.connect()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for statement in PG_SCHEMA + ROWS:
            conn.execute(text(statement))
        conn.commit()
        try:
            yield conn
        finally:
            conn.rollback()
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            conn.commit()
            conn.close()
            engine.dispose()

    def test_backfills_and_relaxes_the_requester(self, connection):
        migration = _migration()
        migration.upgrade(connection)
        migration.upgrade(connection)
        ops = {name: json.loads(value) for name, value in connection.execute(
            text("SELECT name, operations FROM certificate_policies"))}
        assert ops == EXPECTED
        connection.execute(text(
            "INSERT INTO approval_requests (request_type, status) VALUES ('renewal', 'pending')"))
        assert connection.execute(text(
            "SELECT count(*) FROM approval_requests WHERE requester_id IS NULL")).scalar() == 1
