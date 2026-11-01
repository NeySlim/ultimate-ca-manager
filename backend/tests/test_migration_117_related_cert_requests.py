"""Migration 117 creates related_cert_requests, idempotently, with its unique request hash."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations.117_related_cert_requests')


def test_sqlite_creates_the_table():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(related_cert_requests)")}
    assert {'request_sha256', 'spki_sha256', 'request_time', 'created_at'} <= columns
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(related_cert_requests)")}
    assert 'ix_related_cert_requests_request_time' in indexes
    conn.execute("INSERT INTO related_cert_requests (request_sha256, spki_sha256, request_time) "
                 "VALUES ('r', 'k', '2026-11-01 00:00:00')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO related_cert_requests (request_sha256, spki_sha256, request_time) "
                     "VALUES ('r', 'other', '2026-11-01 00:00:00')")


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table():
    schema = f"migtest_117_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        inspector = inspect(conn)
        columns = {c['name'] for c in inspector.get_columns('related_cert_requests', schema=schema)}
        assert {'request_sha256', 'spki_sha256', 'request_time', 'created_at'} <= columns
        assert 'ix_related_cert_requests_request_time' in {
            i['name'] for i in inspector.get_indexes('related_cert_requests', schema=schema)}
        insert = text("INSERT INTO related_cert_requests (request_sha256, spki_sha256, request_time) "
                      "VALUES ('r', :key, '2026-11-01 00:00:00')")
        conn.execute(insert, {'key': 'k'})
        with pytest.raises(IntegrityError):
            conn.execute(insert, {'key': 'other'})
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_model_matches_the_migration(app):
    from models import db
    from models.related_cert_request import RelatedCertRequestUse
    with app.app_context():
        columns = {c['name'] for c in inspect(db.engine).get_columns('related_cert_requests')}
        assert columns == {c.name for c in RelatedCertRequestUse.__table__.columns}
