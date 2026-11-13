"""Migration 142 makes (caref, serial_number) unique, or lists the duplicates and waits."""
import importlib
import json
import os
import sqlite3
import uuid

import pytest
from sqlalchemy import create_engine, text

from models import Certificate, SystemConfig

PG_URL = os.getenv('UCM_TEST_PG_URL')
CERTS = Certificate.__tablename__
CONFIG = SystemConfig.__tablename__
_DDL = [f"CREATE TABLE {CERTS} (id INTEGER PRIMARY KEY, caref VARCHAR(50), serial_number VARCHAR(100))",
        f"CREATE TABLE {CONFIG} (id INTEGER PRIMARY KEY, key VARCHAR(100) UNIQUE NOT NULL, value TEXT, "
        "encrypted BOOLEAN, description VARCHAR(255), updated_at TIMESTAMP, updated_by VARCHAR(80))"]
# CSR rows carry no serial, imported rows no CA: neither collides
CLEAN = [(1, 'ca-a', '11'), (2, 'ca-a', '12'), (3, 'ca-b', '11'), (4, 'ca-a', None),
         (5, 'ca-a', None), (6, None, '11'), (7, None, '11'), (8, 'ca-a', ''), (9, 'ca-a', '')]
DUPLICATE = CLEAN + [(10, 'ca-b', '11')]


def _migration():
    return importlib.import_module('migrations._from_2_254.142_serial_per_ca_and_proxy_links')


def _pending(rows):
    return [json.loads(value) for (key, value) in rows if key == _migration().PENDING_KEY]


def _sqlite(rows):
    conn = sqlite3.connect(':memory:')
    for ddl in _DDL:
        conn.execute(ddl)
    conn.executemany(f"INSERT INTO {CERTS} VALUES (?, ?, ?)", rows)
    conn.commit()
    return conn


def test_sqlite_clean_table_gets_the_index_twice_over():
    conn = _sqlite(CLEAN)
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {CERTS} VALUES (99, 'ca-a', '11')")
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == []


def test_sqlite_duplicates_are_listed_kept_and_then_resolved():
    conn = _sqlite(DUPLICATE)
    for _ in range(2):
        _migration().upgrade(conn)
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == [
        {'duplicates': [{'caref': 'ca-b', 'serial_number': '11', 'count': 2,
                    'rows': [{'id': 3, 'stored': '11'}, {'id': 10, 'stored': '11'}]}]}]
    assert conn.execute(f"SELECT COUNT(*) FROM {CERTS}").fetchone() == (len(DUPLICATE),)
    conn.execute(f"INSERT INTO {CERTS} VALUES (99, 'ca-a', '11')")  # no index yet
    conn.execute(f"DELETE FROM {CERTS} WHERE id IN (10, 99)")
    _migration().upgrade(conn)
    assert _pending(conn.execute(f"SELECT key, value FROM {CONFIG}")) == []
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {CERTS} VALUES (99, 'ca-b', '11')")


def test_sqlite_without_tables_does_nothing():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)


def test_the_model_declares_the_same_index(app):
    """A fresh install (create_all) refuses the duplicate the migration would."""
    from models import db
    with app.app_context():
        caref = f'ca-{uuid.uuid4().hex[:8]}'
        for refid in ('x1', 'x2'):
            db.session.add(Certificate(refid=f'{refid}-{caref}', descr='dup', caref=caref,
                                       serial_number='42'))
        with pytest.raises(Exception) as caught:
            db.session.commit()
        db.session.rollback()
        from utils.ca_serial_counter import is_serial_collision
        assert is_serial_collision(caught.value)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('rows, pending', [(CLEAN, False), (DUPLICATE, True)])
def test_postgresql(rows, pending):
    schema = f"m142_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with engine.begin() as conn:
            for ddl in _DDL:
                conn.execute(text(ddl.replace('INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY')))
            for row in rows:
                conn.execute(text(f"INSERT INTO {CERTS} VALUES (:i, :c, :s)"),
                             dict(zip('ics', row)))
        for _ in range(2):
            with engine.begin() as conn:
                _migration().upgrade(conn)
        with engine.begin() as conn:
            listed = _pending(conn.execute(text(f"SELECT key, value FROM {CONFIG}")))
            indexes = {r[0] for r in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE schemaname = :s"), {'s': schema})}
        assert (_migration().INDEX in indexes) is not pending
        assert bool(listed) is pending
        if pending:
            assert listed[0]['duplicates'] == [{'caref': 'ca-b', 'serial_number': '11', 'count': 2,
                    'rows': [{'id': 3, 'stored': '11'}, {'id': 10, 'stored': '11'}]}]
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()


def test_sqlite_creates_the_proxy_challenge_links_with_the_orders():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)  # no orders table: nothing to link to
    conn.execute("CREATE TABLE acme_client_orders (id INTEGER PRIMARY KEY)")
    for _ in range(2):
        _migration().upgrade(conn)
    columns = {r[1] for r in conn.execute(f"PRAGMA table_info({_migration().LINKS})")}
    assert columns == {'id', 'key_sha256', 'order_id', 'identifier', 'authz_url', 'created_at'}
    conn.execute(f"INSERT INTO {_migration().LINKS} (key_sha256, order_id, created_at) "
                 "VALUES ('k', 1, CURRENT_TIMESTAMP)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO {_migration().LINKS} (key_sha256, order_id, created_at) "
                     "VALUES ('k', 1, CURRENT_TIMESTAMP)")


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_creates_the_proxy_challenge_links():
    schema = f"m142l_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={schema}'})
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE acme_client_orders (id SERIAL PRIMARY KEY)"))
            conn.execute(text("INSERT INTO acme_client_orders (id) VALUES (1)"))
        for _ in range(2):
            with engine.begin() as conn:
                _migration().upgrade(conn)
        with engine.begin() as conn:
            conn.execute(text(f"INSERT INTO {_migration().LINKS} (key_sha256, order_id, created_at) "
                              "VALUES ('k', 1, now())"))
            conn.execute(text("DELETE FROM acme_client_orders"))
            assert conn.execute(text(f"SELECT COUNT(*) FROM {_migration().LINKS}")).scalar() == 0
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()
