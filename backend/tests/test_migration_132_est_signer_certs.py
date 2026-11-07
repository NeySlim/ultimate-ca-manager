"""Migration 132 creates est_signer_certs, one EST key generator per CA."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

TABLE = 'est_signer_certs'
PG_URL = os.getenv('UCM_TEST_PG_URL')
COLUMNS = {'id', 'ca_id', 'certificate_id', 'serial_number', 'issuer_fingerprint', 'created_at'}


def _migration():
    return importlib.import_module('migrations.132_est_signer_certs')


def test_sqlite_creates_the_table_with_one_row_per_ca_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE certificate_authorities (id INTEGER PRIMARY KEY, refid VARCHAR(36))")
    conn.execute("CREATE TABLE certificates (id INTEGER PRIMARY KEY, refid VARCHAR(36))")
    conn.execute("INSERT INTO certificate_authorities VALUES (1, 'ca-1')")
    conn.execute("INSERT INTO certificates VALUES (1, 'cert-1')")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert {row[1] for row in conn.execute(f'PRAGMA table_info({TABLE})')} == COLUMNS
    insert = (f"INSERT INTO {TABLE} (ca_id, certificate_id, serial_number, issuer_fingerprint) "
              "VALUES (1, 1, '7', 'f')")
    conn.execute(insert)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert)
    # With foreign keys enforced, the pointer goes with its certificate
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM certificates WHERE id = 1")
    assert conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_cascades_with_the_ca():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_132_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text("CREATE TABLE certificate_authorities (id SERIAL PRIMARY KEY, refid VARCHAR(36))"))
        conn.execute(text("CREATE TABLE certificates (id SERIAL PRIMARY KEY, refid VARCHAR(36))"))
        conn.execute(text("INSERT INTO certificate_authorities (refid) VALUES ('ca-1')"))
        conn.execute(text("INSERT INTO certificates (refid) VALUES ('cert-1')"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert {c['name'] for c in inspect(conn).get_columns(TABLE, schema=schema)} == COLUMNS
        insert = text(f"INSERT INTO {TABLE} (ca_id, certificate_id, serial_number, issuer_fingerprint) "
                      "VALUES (1, 1, '7', 'f')")
        conn.execute(insert)
        conn.execute(text("DELETE FROM certificate_authorities"))
        assert conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 0
        conn.execute(text("INSERT INTO certificate_authorities (id, refid) VALUES (1, 'ca-1')"))
        conn.execute(insert)
        conn.execute(text("DELETE FROM certificates"))
        assert conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar() == 0
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_carries_the_table(app):
    from models import db
    with app.app_context():
        assert COLUMNS <= {c['name'] for c in inspect(db.engine).get_columns(TABLE)}
