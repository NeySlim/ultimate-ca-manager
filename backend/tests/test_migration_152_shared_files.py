"""Migration 152: shared_files on both backends, idempotent, matching the model."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import SharedFile

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = SharedFile.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.152_shared_files')


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    conn.execute(f"INSERT INTO {TABLE} (name, content) VALUES ('kerberos.keytab', 'x')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {TABLE} (name, content) VALUES ('kerberos.keytab', 'y')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {TABLE} (name) VALUES ('no content')")


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    schema = f"migtest_152_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        conn.execute(text(f"INSERT INTO {TABLE} (name, content) VALUES ('kerberos.keytab', 'x')"))
        cols = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert cols['content']['nullable'] is False and cols['updated_by']['nullable'] is True
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_matches_the_migration(app):
    from models import db
    with app.app_context():
        assert {'name', 'content', 'updated_at', 'updated_by'} == {
            c['name'] for c in inspect(db.engine).get_columns(TABLE)}
