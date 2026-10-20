"""Cross-backend transfer helpers: sequence realignment, value normalisation,
foreign-key handling and load order. PostgreSQL cases are opt-in through
UCM_TEST_PG_URL and take the bench exclusively."""
import json
import os

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.dialects import postgresql

from services.database_admin import helpers

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_EVIL = "x'; DROP TABLE users; --"


@pytest.fixture
def pg():
    if not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    from tests.conftest import pg_bench_exclusive
    eng = create_engine(_PG_URL)

    def _reset():
        with eng.begin() as c:
            c.execute(text('DROP SCHEMA public CASCADE'))
            c.execute(text('CREATE SCHEMA public'))

    with pg_bench_exclusive():
        _reset()
        try:
            yield eng
        finally:
            _reset()
            eng.dispose()


def _next_id(eng, quoted_table, quoted_col):
    with eng.begin() as c:
        return c.execute(text(
            f'INSERT INTO {quoted_table} DEFAULT VALUES RETURNING {quoted_col}')).scalar()


# ---------------------------------------------------------------------------
# Sequences (PostgreSQL)
# ---------------------------------------------------------------------------

class TestResetSequences:
    @pytest.mark.postgres
    def test_unusual_but_legal_identifiers_are_realigned(self, pg):
        with pg.begin() as c:
            c.execute(text('CREATE TABLE "My Table" ("Row Id" SERIAL PRIMARY KEY)'))
            c.execute(text('CREATE TABLE "dotted.Name" (id SERIAL PRIMARY KEY)'))
            c.execute(text('INSERT INTO "My Table" ("Row Id") VALUES (5), (9)'))
            c.execute(text('INSERT INTO "dotted.Name" (id) VALUES (41)'))

        helpers._reset_pg_sequences(pg)

        assert _next_id(pg, '"My Table"', '"Row Id"') == 10
        assert _next_id(pg, '"dotted.Name"', 'id') == 42

    @pytest.mark.postgres
    def test_an_adversarial_column_name_runs_nothing_but_setval(self, pg):
        with pg.begin() as c:
            c.execute(text('CREATE TABLE users (id SERIAL PRIMARY KEY)'))
            c.execute(text(f'CREATE TABLE evil ("{_EVIL}" SERIAL PRIMARY KEY)'))
            c.execute(text(f'INSERT INTO evil ("{_EVIL}") VALUES (7)'))

        statements = []

        def record(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(pg, 'before_cursor_execute', record)
        try:
            helpers._reset_pg_sequences(pg)
        finally:
            event.remove(pg, 'before_cursor_execute', record)

        work = [s for s in statements
                if not s.lstrip().upper().startswith(('SAVEPOINT', 'RELEASE', 'ROLLBACK'))
                and 'information_schema' not in s]
        assert len(work) == 2 and all(s.lstrip().startswith('SELECT setval(') for s in work)
        assert 'users' in inspect(pg).get_table_names()
        assert _next_id(pg, 'evil', f'"{_EVIL}"') == 8

    @pytest.mark.postgres
    def test_an_empty_table_hands_out_one(self, pg):
        with pg.begin() as c:
            c.execute(text('CREATE TABLE empty_one (id SERIAL PRIMARY KEY)'))
            c.execute(text("SELECT setval('empty_one_id_seq', 50)"))

        helpers._reset_pg_sequences(pg)

        assert _next_id(pg, 'empty_one', 'id') == 1

    @pytest.mark.postgres
    def test_one_refused_reset_does_not_stop_the_others(self, pg):
        with pg.begin() as c:
            c.execute(text('CREATE TABLE a_bounded (id SERIAL PRIMARY KEY)'))
            c.execute(text('ALTER SEQUENCE a_bounded_id_seq MAXVALUE 5'))
            c.execute(text('INSERT INTO a_bounded (id) VALUES (10)'))
            c.execute(text('CREATE TABLE b_good (id SERIAL PRIMARY KEY)'))
            c.execute(text('INSERT INTO b_good (id) VALUES (3)'))

        helpers._reset_pg_sequences(pg)

        assert _next_id(pg, 'b_good', 'id') == 4

    @pytest.mark.postgres
    def test_the_serial_column_query_names_owned_and_unowned_sequences(self, pg):
        with pg.begin() as c:
            c.execute(text('CREATE TABLE "Owned T" ("Id" SERIAL PRIMARY KEY, n INT)'))
            c.execute(text('CREATE SEQUENCE shared_seq'))
            c.execute(text("CREATE TABLE borrowed (id INT DEFAULT nextval('shared_seq'))"))
            c.execute(text('CREATE TABLE plain (id INT)'))
            rows = c.execute(helpers._PG_SERIAL_COLUMNS_SQL).fetchall()

        assert sorted(tuple(r) for r in rows) == [
            ('public', 'Owned T', 'Id', 'public."Owned T_Id_seq"'),
            ('public', 'borrowed', 'id', None),
        ]


def test_setval_statement_quotes_metadata_and_binds_the_sequence():
    stmt = helpers._pg_setval_stmt('public', 'My Table', _EVIL)
    compiled = stmt.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert f'"{_EVIL}"' in sql and '"My Table"' in sql and 'public.' in sql
    assert sql.count(_EVIL) == sql.count(f'"{_EVIL}"')
    assert 'seq' in compiled.params


def test_reset_is_a_no_op_off_postgresql(tmp_path):
    eng = create_engine(f'sqlite:///{tmp_path / "s.db"}')
    helpers._reset_pg_sequences(eng)
    eng.dispose()


# ---------------------------------------------------------------------------
# Value normalisation
# ---------------------------------------------------------------------------

def test_type_detection_is_exact(tmp_path):
    eng = create_engine(f'sqlite:///{tmp_path / "types.db"}')
    with eng.begin() as c:
        c.execute(text('CREATE TABLE t (a BOOLEAN, b BOOL, c TINYINT, d SMALLINT, '
                       'e JSON, f TEXT, g INTEGER)'))
    insp = inspect(eng)
    assert helpers._detect_boolean_columns(insp, ['t']) == {'t': {'a', 'b'}}
    assert helpers._detect_json_columns(insp, ['t']) == {'t': {'e'}}
    eng.dispose()


def test_a_table_that_cannot_be_reflected_is_skipped(tmp_path):
    eng = create_engine(f'sqlite:///{tmp_path / "r.db"}')
    with eng.begin() as c:
        c.execute(text('CREATE TABLE good (flag BOOLEAN)'))
    real = inspect(eng)

    class Flaky:
        def get_columns(self, table):
            if table == 'broken':
                raise RuntimeError('reflection failed')
            return real.get_columns(table)

    assert helpers._detect_boolean_columns(Flaky(), ['broken', 'good']) == {'good': {'flag'}}
    eng.dispose()


def test_raw_text_in_a_json_column_stays_valid_json():
    out = helpers._normalize_row({'meta': 'not json', 'n': 3}, False, True,
                                 target_json_cols={'meta', 'n'})
    assert json.loads(out['meta']) == 'not json'
    assert json.loads(out['n']) == 3


def test_an_empty_string_in_a_json_column_becomes_null():
    out = helpers._normalize_row({'meta': '', 'name': ''}, False, True,
                                 target_json_cols={'meta'})
    assert out['meta'] is None and out['name'] == ''


def test_only_zero_one_and_known_strings_become_booleans():
    values = {'two': 2, 'minus': -1, 'half': 0.5, 'odd': 'maybe',
              'one': 1, 'zero': 0.0, 'yes': 'Yes'}
    out = helpers._normalize_row(values, False, True, target_bool_cols=set(values))
    assert (out['two'], out['minus'], out['half'], out['odd']) == (2, -1, 0.5, 'maybe')
    assert out['one'] is True and out['zero'] is False and out['yes'] is True


@pytest.mark.postgres
def test_sqlite_json_reaches_postgresql_as_the_same_object(pg, tmp_path):
    original = {'perms': ['read:certs', 'write:cas'], 'nested': {'k': [1, None, True]}}
    src = create_engine(f'sqlite:///{tmp_path / "src.db"}')
    with src.begin() as c:
        c.execute(text('CREATE TABLE doc (id INTEGER PRIMARY KEY, body JSON, live BOOLEAN)'))
        c.execute(text('INSERT INTO doc VALUES (1, :b, 1)'), {'b': json.dumps(original)})
    with pg.begin() as c:
        c.execute(text('CREATE TABLE doc (id INTEGER PRIMARY KEY, body JSONB, live BOOLEAN)'))

    insp = inspect(pg)
    json_cols = helpers._detect_json_columns(insp, ['doc'])['doc']
    bool_cols = helpers._detect_boolean_columns(insp, ['doc'])['doc']
    with src.connect() as c:
        row = dict(c.execute(text('SELECT id, body, live FROM doc')).mappings().one())
    values = helpers._normalize_row(row, False, True, json_cols, bool_cols)
    # A typed read hands over the parsed object rather than the text.
    typed = helpers._normalize_row({'id': 2, 'body': original, 'live': 0},
                                   False, True, json_cols, bool_cols)
    with pg.begin() as c:
        c.execute(text('INSERT INTO doc (id, body, live) VALUES (:id, :body, :live)'),
                  [values, typed])
        rows = c.execute(text('SELECT body, live FROM doc ORDER BY id')).all()

    assert [tuple(r) for r in rows] == [(original, True), (original, False)]
    body, live = rows[0]

    # And back: PostgreSQL's parsed dict lands in SQLite as the same JSON.
    back = create_engine(f'sqlite:///{tmp_path / "back.db"}')
    with back.begin() as c:
        c.execute(text('CREATE TABLE doc (id INTEGER PRIMARY KEY, body JSON, live BOOLEAN)'))
        c.execute(text('INSERT INTO doc VALUES (:id, :body, :live)'),
                  helpers._normalize_row({'id': 1, 'body': body, 'live': live}, True, False))
        stored, flag = c.execute(text('SELECT body, live FROM doc')).one()
    assert json.loads(stored) == original and flag == 1
    src.dispose()
    back.dispose()


# ---------------------------------------------------------------------------
# Foreign keys and load order
# ---------------------------------------------------------------------------

def _fk_engine(path):
    eng = create_engine(f'sqlite:///{path}')

    @event.listens_for(eng, 'connect')
    def _on(dbapi_conn, record):
        dbapi_conn.execute('PRAGMA foreign_keys=ON')

    with eng.begin() as c:
        c.execute(text('CREATE TABLE z_parent (id INTEGER PRIMARY KEY)'))
        c.execute(text('CREATE TABLE a_child (id INTEGER PRIMARY KEY, '
                       'parent_id INTEGER REFERENCES z_parent(id))'))
    return eng


def _fks_on(eng):
    with eng.connect() as c:
        return c.exec_driver_sql('PRAGMA foreign_keys').scalar()


class TestSqliteForeignKeys:
    def test_a_load_against_the_natural_order_succeeds(self, tmp_path):
        eng = _fk_engine(tmp_path / 'fk.db')
        conn = eng.connect()
        try:
            disabled = helpers._try_disable_fks(conn, False)
            with conn.begin():
                conn.execute(text('INSERT INTO a_child VALUES (1, 1)'))
                conn.execute(text('INSERT INTO z_parent VALUES (1)'))
            helpers._try_reenable_fks(conn, False, disabled)
            assert disabled is True
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        finally:
            conn.close()
        eng.dispose()

    def test_refused_inside_a_transaction(self, tmp_path):
        eng = _fk_engine(tmp_path / 'fk.db')
        with eng.connect() as conn:
            conn.begin()
            assert helpers._try_disable_fks(conn, False) is False
            assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
            conn.rollback()
        eng.dispose()

    def test_a_failed_load_does_not_leave_the_checks_off(self, tmp_path):
        eng = _fk_engine(tmp_path / 'fk.db')
        conn = eng.connect()
        dbapi_id = id(conn.connection.dbapi_connection)
        try:
            assert helpers._try_disable_fks(conn, False) is True
            with pytest.raises(RuntimeError):
                with conn.begin():
                    conn.execute(text('INSERT INTO a_child VALUES (1, 99)'))
                    raise RuntimeError('copy failed')
        finally:
            conn.close()

        with eng.connect() as again:
            assert id(again.connection.dbapi_connection) == dbapi_id
            assert again.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        eng.dispose()


def test_topo_sort_parents_first_and_cycles_do_not_abort(tmp_path):
    eng = create_engine(f'sqlite:///{tmp_path / "topo.db"}')
    with eng.begin() as c:
        c.execute(text('CREATE TABLE c_leaf (id INTEGER PRIMARY KEY, b_id INTEGER REFERENCES b_mid(id))'))
        c.execute(text('CREATE TABLE b_mid (id INTEGER PRIMARY KEY, a_id INTEGER REFERENCES z_root(id))'))
        c.execute(text('CREATE TABLE z_root (id INTEGER PRIMARY KEY, me INTEGER REFERENCES z_root(id))'))
        c.execute(text('CREATE TABLE x_loop (id INTEGER PRIMARY KEY, y INTEGER REFERENCES y_loop(id))'))
        c.execute(text('CREATE TABLE y_loop (id INTEGER PRIMARY KEY, x INTEGER REFERENCES x_loop(id))'))
    order = helpers._topo_sort_tables(inspect(eng))
    assert sorted(order) == ['b_mid', 'c_leaf', 'x_loop', 'y_loop', 'z_root']
    assert order.index('z_root') < order.index('b_mid') < order.index('c_leaf')
    eng.dispose()


def test_topo_sort_falls_back_to_alphabetical():
    class Broken:
        def get_table_names(self):
            return ['b', 'a']

        def get_foreign_keys(self, table):
            raise RuntimeError('no reflection')

    assert helpers._topo_sort_tables(Broken()) == ['a', 'b']


@pytest.mark.postgres
def test_pg_refused_replication_role_keeps_the_load_alive(pg):
    with pg.connect() as c:
        if c.execute(text('SELECT rolsuper FROM pg_roles WHERE rolname = current_user')).scalar():
            pytest.skip('the bench role is a superuser; the refusal cannot happen')
    with pg.begin() as c:
        c.execute(text('CREATE TABLE z_parent (id INTEGER PRIMARY KEY)'))
        c.execute(text('CREATE TABLE a_child (id INTEGER PRIMARY KEY, '
                       'parent_id INTEGER REFERENCES z_parent(id))'))

    rows = {'z_parent': [{'id': 1}], 'a_child': [{'id': 1, 'parent_id': 1}]}
    with pg.connect() as conn:
        with conn.begin():
            disabled = helpers._try_disable_fks(conn, True)
            for table in helpers._topo_sort_tables(inspect(pg)):
                cols = list(rows[table][0])
                conn.execute(text(
                    f'INSERT INTO {table} ({", ".join(cols)}) '
                    f'VALUES ({", ".join(":" + c for c in cols)})'), rows[table])
            helpers._try_reenable_fks(conn, True, disabled)

    assert disabled is False
    with pg.connect() as c:
        assert c.execute(text('SELECT COUNT(*) FROM a_child')).scalar() == 1
