"""Migration 150: an existing users table stops handing deleted ids out again."""
import importlib
import json
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from models import User

FIXTURES = Path(__file__).parent / 'fixtures'

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = User.__tablename__
SESSIONS = 'user_sessions'
EAB = 'acme_eab_credentials'
APPROVALS = 'approval_requests'
AUDIT = 'audit_logs'

# The users table as SQLite installations hold it before 150: no AUTOINCREMENT
_LEGACY = f"""
CREATE TABLE pro_custom_roles (id INTEGER PRIMARY KEY);
CREATE TABLE {TABLE} (
    id INTEGER NOT NULL,
    username VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL,
    auth_source VARCHAR(20) NOT NULL DEFAULT 'local',
    custom_role_id INTEGER REFERENCES pro_custom_roles(id) ON DELETE SET NULL,
    note TEXT CHECK (note IS NULL OR length(note) < 50),
    PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_users_username ON {TABLE} (username);
CREATE UNIQUE INDEX ix_users_email_local ON {TABLE} (email) WHERE auth_source = 'local';
CREATE TRIGGER users_touch AFTER UPDATE OF email ON {TABLE} BEGIN SELECT 1; END;
CREATE TABLE {SESSIONS} (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL
    REFERENCES {TABLE}(id) ON DELETE CASCADE, session_id TEXT);
CREATE TABLE {EAB} (id INTEGER PRIMARY KEY, created_by_user_id INTEGER, revoked_by_user_id INTEGER);
CREATE TABLE {APPROVALS} (id INTEGER PRIMARY KEY, requester_id INTEGER, approvals TEXT);
CREATE TABLE {AUDIT} (id INTEGER PRIMARY KEY, resource_type VARCHAR(50), resource_id TEXT);
"""
_USERS = [(1, 'admin', 'a@x', 'local', None, None), (2, 'bob', 'b@x', 'ldap', None, 'kept'),
          (5, 'carol', 'c@x', 'local', None, None)]


def _migration():
    return importlib.import_module('migrations._from_2_254.150_users_id_never_reused')


def _legacy_database(enforce_foreign_keys=True):
    conn = sqlite3.connect(':memory:')
    conn.executescript(_LEGACY)
    conn.executemany(f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?, ?, ?)", _USERS)
    conn.executemany(f"INSERT INTO {SESSIONS} (user_id, session_id) VALUES (?, ?)", [(1, 's1'), (5, 's5')])
    conn.commit()
    if enforce_foreign_keys:
        conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _schema(conn):
    """Columns, indexes (with their definition), foreign keys and triggers of users."""
    indexes = sorted((r[1], r[2], r[3], r[4]) for r in conn.execute(f"PRAGMA index_list({TABLE})"))
    index_sql = sorted(r[0] for r in conn.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name = ? AND type = 'index' AND sql IS NOT NULL", (TABLE,)))
    triggers = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE tbl_name = ? AND type = 'trigger'", (TABLE,)))
    return {
        'columns': [r[1:] for r in conn.execute(f"PRAGMA table_info({TABLE})")],
        'indexes': indexes, 'index_sql': index_sql, 'triggers': triggers,
        'foreign_keys': [r[2:] for r in conn.execute(f"PRAGMA foreign_key_list({TABLE})")],
    }


def _table_sql(conn):
    return conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (TABLE,)).fetchone()[0]


def _create(conn, username):
    return conn.execute(f"INSERT INTO {TABLE} (username, email) VALUES (?, ?)",
                        (username, f'{username}@x')).lastrowid


class TestSQLite:
    def test_keeps_every_row_index_trigger_and_foreign_key(self):
        conn = _legacy_database()
        before = _schema(conn)
        _migration().upgrade(conn)
        _migration().upgrade(conn)

        assert 'AUTOINCREMENT' in _table_sql(conn).upper()
        assert _schema(conn) == before
        assert conn.execute(f"SELECT * FROM {TABLE} ORDER BY id").fetchall() == _USERS
        assert conn.execute(f"SELECT user_id FROM {SESSIONS} ORDER BY user_id").fetchall() == [(1,), (5,)]
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = '_users_s150'").fetchone() is None
        # The sessions were not cascaded away and still point at the same account
        assert conn.execute(f"PRAGMA foreign_key_check({SESSIONS})").fetchall() == []

    def test_a_deleted_last_id_is_not_handed_out_again(self):
        conn = _legacy_database()
        _migration().upgrade(conn)
        conn.execute(f"DELETE FROM {SESSIONS} WHERE user_id = 5")
        conn.execute(f"DELETE FROM {TABLE} WHERE id = 5")
        assert _create(conn, 'dave') == 6
        conn.execute(f"DELETE FROM {TABLE}")
        assert _create(conn, 'erin') == 7

    def test_the_counter_starts_above_ids_surviving_rows_still_name(self):
        conn = _legacy_database()
        conn.execute(f"INSERT INTO {EAB} (created_by_user_id, revoked_by_user_id) VALUES (8, 9)")
        conn.execute(f"INSERT INTO {APPROVALS} (requester_id, approvals) VALUES (?, ?)",
                     (7, json.dumps([{'user_id': 12, 'username': 'gone'}, {'user_id': True}])))
        conn.commit()
        _migration().upgrade(conn)
        assert _create(conn, 'dave') == 13

    @pytest.mark.parametrize('resource_id, expected', [('7', 8), ('3,9,4', 10), (' 11 ', 12)])
    def test_the_counter_starts_above_user_ids_the_audit_trail_names(self, resource_id, expected):
        conn = _legacy_database()
        conn.executemany(f"INSERT INTO {AUDIT} (resource_type, resource_id) VALUES (?, ?)",
                         [('user', resource_id), ('user', 'bob'), ('user', None), ('user', ''),
                          ('user', '99999999999'), ('certificate', '40')])
        conn.commit()
        _migration().upgrade(conn)
        assert _create(conn, 'dave') == expected

    def test_an_empty_table_is_ready_too(self):
        conn = sqlite3.connect(':memory:')
        conn.executescript(_LEGACY)
        _migration().upgrade(conn)
        assert _create(conn, 'first') == 1

    def test_a_failure_halfway_leaves_the_table_untouched_and_a_rerun_completes(self, monkeypatch):
        conn = _legacy_database()
        before, legacy_sql = _schema(conn), _table_sql(conn)

        def _crash(_conn, _statements):
            raise RuntimeError('interrupted')

        monkeypatch.setattr(_migration(), '_recreate_dependents', _crash)
        with pytest.raises(RuntimeError, match='interrupted'):
            _migration().upgrade(conn)
        assert _table_sql(conn) == legacy_sql
        assert _schema(conn) == before
        assert conn.execute(f"SELECT * FROM {TABLE} ORDER BY id").fetchall() == _USERS
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = '_users_s150'").fetchone() is None
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1

        monkeypatch.undo()
        _migration().upgrade(conn)
        assert 'AUTOINCREMENT' in _table_sql(conn).upper()
        assert _schema(conn) == before

    def test_a_scratch_table_left_by_a_killed_run_is_replaced(self):
        conn = _legacy_database(enforce_foreign_keys=False)
        conn.execute("CREATE TABLE _users_s150 (id INTEGER)")
        conn.commit()
        _migration().upgrade(conn)
        assert 'AUTOINCREMENT' in _table_sql(conn).upper()
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 0

    def test_a_ddl_it_does_not_recognise_is_refused(self):
        with pytest.raises(RuntimeError):
            _migration().autoincrement_ddl('CREATE TABLE users (uid INTEGER PRIMARY KEY)', 'x')


def _create_all_users_schema(without_autoincrement=False):
    """The users table create_all builds from the model, or as it was before 150."""
    table, options = User.__table__, User.__table__.dialect_options['sqlite']
    saved = options['autoincrement']
    if without_autoincrement:
        options['autoincrement'] = False
    try:
        dialect = sqlite_dialect.dialect()
        statements = [str(CreateTable(table).compile(dialect=dialect))]
        statements += [str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes]
    finally:
        options['autoincrement'] = saved
    conn = sqlite3.connect(':memory:')
    for statement in statements:
        conn.execute(statement)
    return conn


def test_a_fresh_install_and_an_upgraded_one_have_the_same_users_table():
    fresh = _create_all_users_schema()
    assert 'AUTOINCREMENT' in _table_sql(fresh).upper()
    upgraded = _create_all_users_schema(without_autoincrement=True)
    assert 'AUTOINCREMENT' not in _table_sql(upgraded).upper()
    _migration().upgrade(upgraded)
    assert 'AUTOINCREMENT' in _table_sql(upgraded).upper()
    assert _schema(upgraded) == _schema(fresh)


def test_the_baseline_table_shape_is_accepted():
    """The 2.52 baseline declares the id inline (``id INTEGER PRIMARY KEY NOT NULL``)."""
    conn = sqlite3.connect(':memory:')
    conn.executescript((FIXTURES / 'schema_v252_baseline_sqlite.sql').read_text())
    conn.execute(f"INSERT INTO {TABLE} (id, username, email, password_hash, role) VALUES (3, 'a', 'a@x', 'h', 'admin')")
    conn.commit()
    before = _schema(conn)
    _migration().upgrade(conn)
    assert 'AUTOINCREMENT' in _table_sql(conn).upper()
    assert _schema(conn) == before
    conn.execute(f"DELETE FROM {TABLE}")
    assert conn.execute(f"INSERT INTO {TABLE} (username, email, password_hash, role) "
                        "VALUES ('b', 'b@x', 'h', 'admin')").lastrowid == 4


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_never_reused_an_id_and_the_counter_passes_surviving_references():
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    schema = f"migtest_150_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    with _a_schema_of_our_own(schema) as url:
        engine = create_engine(url)
        try:
            with engine.begin() as conn:
                conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, username VARCHAR(80))"))
                conn.execute(text(f"CREATE TABLE {EAB} (id SERIAL PRIMARY KEY, created_by_user_id INTEGER, "
                                  "revoked_by_user_id INTEGER)"))
                for name in ('a', 'b', 'c'):
                    conn.execute(text(f"INSERT INTO {TABLE} (username) VALUES (:n)"), {'n': name})
                conn.execute(text(f"DELETE FROM {TABLE} WHERE id = 3"))

                def _next(name):
                    return conn.execute(text(f"INSERT INTO {TABLE} (username) VALUES (:n) RETURNING id"),
                                        {'n': name}).scalar()

                # Without the migration already: the highest deleted id is not reused
                assert _next('d') == 4
                _migration().upgrade(conn)
                _migration().upgrade(conn)
                assert _next('e') == 5
                # A sequence realigned on MAX(id) by an earlier backend switch is moved past the references
                conn.execute(text(f"DELETE FROM {TABLE} WHERE id >= 4"))
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{TABLE}', 'id'), 2)"))
                conn.execute(text(f"INSERT INTO {EAB} (created_by_user_id, revoked_by_user_id) VALUES (9, NULL)"))
                _migration().upgrade(conn)
                assert _next('f') == 10
                assert [r[0] for r in conn.execute(text(f"SELECT id FROM {TABLE} ORDER BY id"))] == [1, 2, 10]
                # A bulk delete recorded in the audit trail names ids no other row keeps
                conn.execute(text(f"CREATE TABLE {AUDIT} (id SERIAL PRIMARY KEY, resource_type VARCHAR(50), "
                                  "resource_id TEXT)"))
                conn.execute(text(f"INSERT INTO {AUDIT} (resource_type, resource_id) VALUES ('user', '14,12')"))
                _migration().upgrade(conn)
                assert _next('g') == 15
        finally:
            engine.dispose()


def test_the_runner_applies_it_to_a_database_file(tmp_path):
    import migration_runner
    path = tmp_path / 'ucm.db'
    conn = _legacy_database(enforce_foreign_keys=False)
    conn.execute(f"VACUUM INTO '{path}'")
    conn.close()
    assert migration_runner._run_pending_sqlite(['300_upgrade_from_2_254'], False, db_path=str(path))
    conn = sqlite3.connect(path)
    assert 'AUTOINCREMENT' in _table_sql(conn).upper()
    assert conn.execute(f"SELECT * FROM {TABLE} ORDER BY id").fetchall() == _USERS
    assert conn.execute("SELECT name FROM _migrations").fetchall() == [('300_upgrade_from_2_254',)]


def test_a_2254_install_upgraded_by_the_runner_never_reuses_an_id(tmp_path):
    """The 2.254 schema with its registry, upgraded as a start upgrades it."""
    import migration_runner
    path = tmp_path / 'ucm2254.db'
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / 'schema_v2254_sqlite.sql').read_text())
    conn.execute(f"INSERT INTO {TABLE} (id, username, email, password_hash, role, auth_source) "
                 "VALUES (4, 'a', 'a@x', 'h', 'admin', 'local')")
    conn.commit()
    conn.close()
    assert migration_runner._run_pending_sqlite(['300_upgrade_from_2_254'], False, db_path=str(path))

    conn, fresh = sqlite3.connect(path), _schema(_create_all_users_schema())
    upgraded = _schema(conn)
    assert 'AUTOINCREMENT' in _table_sql(conn).upper()
    for part in ('indexes', 'index_sql', 'triggers'):
        assert upgraded[part] == fresh[part]
    assert [c for c in upgraded['columns'] if c[0] == 'id'] == [c for c in fresh['columns'] if c[0] == 'id']
    conn.execute(f"DELETE FROM {TABLE}")
    assert conn.execute(f"INSERT INTO {TABLE} (username, email, password_hash, role, auth_source) "
                        "VALUES ('b', 'b@x', 'h', 'admin', 'local')").lastrowid == 5
