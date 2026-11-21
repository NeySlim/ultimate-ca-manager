"""Migration 164: file_removals on both backends, idempotent, matching the model."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import FileRemoval

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = FileRemoval.__tablename__


def _migration():
    return importlib.import_module('migrations._from_2_254.164_file_removals')


def test_the_step_is_part_of_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert '164_file_removals' in STEPS


def test_sqlite_creates_the_table_and_is_idempotent():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    conn.execute(f"INSERT INTO {TABLE} (generation, path) VALUES (1, '/a')")
    conn.execute(f"INSERT INTO {TABLE} (generation, path) VALUES (1, '/a')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {TABLE} (generation) VALUES (2)")
    indexed = {row[2] for name in ('ix_file_removals_path', 'ix_file_removals_generation')
               for row in conn.execute(f"PRAGMA index_info({name})")}
    assert indexed == {'path', 'generation'}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_and_is_idempotent():
    schema = f"migtest_164_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        conn.execute(text(f"INSERT INTO {TABLE} (generation, path) VALUES (1, '/a')"))
        cols = {c['name']: c for c in inspect(conn).get_columns(TABLE, schema=schema)}
        assert cols['path']['nullable'] is False and cols['generation']['nullable'] is False
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_matches_the_migration(app):
    from models import db
    with app.app_context():
        assert {'id', 'generation', 'path'} == {
            c['name'] for c in inspect(db.engine).get_columns(TABLE)}
