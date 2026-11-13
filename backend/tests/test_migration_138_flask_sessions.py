"""Migration 138 creates the Flask-Session table and its expiry index, on both
backends, with the columns Flask-Session itself would create, and may rerun."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base

TABLE = 'flask_sessions'
PG_URL = os.getenv('UCM_TEST_PG_URL')


def _migration():
    return importlib.import_module('migrations._from_2_254.138_flask_sessions')


def _library_columns():
    """The columns Flask-Session 0.8 creates for the same table name."""
    from flask_sqlalchemy import SQLAlchemy
    from flask_session.sqlalchemy.sqlalchemy import create_session_model

    model = create_session_model(SQLAlchemy(model_class=declarative_base()), TABLE)
    return {c.name: (type(c.type).__name__, c.primary_key) for c in model.__table__.columns}


def _shape(inspector, schema=None):
    """name -> (generic type, is primary key) of the table, backend-neutral."""
    pk = set(inspector.get_pk_constraint(TABLE, schema=schema)['constrained_columns'])
    return {c['name']: (type(c['type'].as_generic()).__name__, c['name'] in pk)
            for c in inspector.get_columns(TABLE, schema=schema)}


def test_sqlite_creates_nothing_and_reruns():
    """SQLite keeps sessions in files: no table, so a PostgreSQL switch is never blocked."""
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name = ?", (TABLE,)).fetchall() == []


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_creates_the_table_beside_one_the_library_made():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_138_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        _migration().upgrade(conn)
        conn.execute(text(f"INSERT INTO {TABLE} (session_id, data, expiry) "
                          "VALUES ('a', '\\x00', '2030-01-01')"))
        _migration().upgrade(conn)
        assert conn.execute(text(f"SELECT session_id FROM {TABLE}")).fetchall() == [('a',)]
        inspector = inspect(conn)
        assert _shape(inspector, schema) == _library_columns()
        assert 'ix_flask_sessions_expiry' in {i['name'] for i in inspector.get_indexes(TABLE, schema=schema)}
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
