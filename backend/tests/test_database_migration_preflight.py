"""
Tests for services/database_admin/preflight.py — the entry control of a
SQLite <-> PostgreSQL migration.

The bugs these pin down all shipped as "successful" migrations:
  - a target holding templates, config or HSM keys accepted because the old
    emptiness probe only looked at `users`, `certificates` and a `cas` table
    that has never existed (it is `certificate_authorities`)
  - a source table absent from the target logged as "Skipping table ..." and
    counted as a success
  - a source column absent from the target recorded in `dropped_columns` and
    counted as a success
  - a target carrying another application's schema, or a partial UCM one,
    never looked at

Every one of those is now a refusal, and every refusal names what blocks it.
"""
import contextlib
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

from services.database_admin import preflight
from services.database_admin.preflight import (
    IGNORED_TABLES,
    INTERNAL_TABLES,
    LEGACY_COLUMNS,
    PreflightError,
    build_copy_plan,
    check_target_is_empty,
    check_target_schema,
    dropped_columns,
    expected_schema,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_target():
    """Empty SQLite file usable as a migration target."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)  # ensure the file does not yet exist
    yield f'sqlite:///{path}'
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sqlite_source():
    """Second SQLite file, used as the migration source in plan tests.

    The plan is built from two engines, and using the session-wide app DB as
    the source would mean mutating a database every other test file shares.
    """
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    yield f'sqlite:///{path}'
    if os.path.exists(path):
        os.unlink(path)


# The applied-migrations ledger, exactly as migration.py creates it on a
# SQLite target: outside db.metadata, and copied.
_MIGRATIONS_DDL = """
    CREATE TABLE _migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(255) NOT NULL UNIQUE,
        applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""

# Alembic's schema stamp: outside db.metadata, and NOT copied.
_ALEMBIC_DDL = """
    CREATE TABLE alembic_version (
        version_num VARCHAR(32) NOT NULL PRIMARY KEY
    )
"""


@contextlib.contextmanager
def _engine(url):
    """Engine that is always disposed, so the temp file can be removed."""
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()


def _create_ucm_schema(app, engine):
    """Leave *engine* with the schema `db.metadata.create_all` would build."""
    with app.app_context():
        from models import db

        expected_schema()  # forces the lazily-imported model modules to register
        db.metadata.create_all(engine)


def _execute(engine, *statements):
    """Run raw DDL/DML on a test database."""
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _table_names(engine):
    return set(inspect(engine).get_table_names())


def _add_legacy_columns(engine, columns_by_table=None):
    """Give a source the columns an upgraded installation still carries."""
    columns_by_table = columns_by_table or LEGACY_COLUMNS
    _execute(engine, *[
        f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT'
        for table, columns in columns_by_table.items()
        for column in columns
    ])


FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def _schema_of(sql):
    """``{table: {column}}`` of a schema script, executed into an in-memory database."""
    conn = sqlite3.connect(':memory:')
    try:
        conn.executescript(sql)
        tables = [
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return {
            table: {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
            for table in tables
        }
    finally:
        conn.close()


def _baseline_schema():
    """The 2.52 baseline every installation upgraded from it still carries, where the legacy
    columns come from (fixture taken from the 2.254 tag by scripts/schema_fixture.py)."""
    return _schema_of((FIXTURES / 'schema_v252_baseline_sqlite.sql').read_text())


def _carried_schema():
    """What a 2.254 database may hold: the baseline's columns and those 2.254 creates."""
    carried = _baseline_schema()
    for table, columns in _schema_of((FIXTURES / 'schema_v2254_sqlite.sql').read_text()).items():
        carried.setdefault(table, set()).update(columns)
    return carried


# ---------------------------------------------------------------------------
# check_target_is_empty — acceptable targets
# ---------------------------------------------------------------------------

def test_blank_sqlite_target_passes(app, sqlite_target):
    with app.app_context(), _engine(sqlite_target) as engine:
        assert check_target_is_empty(engine) == {}


def test_created_but_empty_target_passes_and_reports_every_table(app, sqlite_target):
    """An empty UCM schema is acceptable — and the proof covers all of it."""
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)

        inspected = check_target_is_empty(engine)

    assert set(inspected) == set(expected_schema())
    assert set(inspected.values()) == {0}
    # The tables the old check looked at are in there, but so is everything else.
    for table in ('users', 'certificates', 'certificate_authorities',
                  'certificate_templates', 'system_config'):
        assert inspected[table] == 0


# ---------------------------------------------------------------------------
# check_target_is_empty — refusals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('table, insert_sql', [
    (
        'certificate_templates',
        "INSERT INTO certificate_templates (name, template_type, extensions_template) "
        "VALUES ('Web Server', 'web_server', '{}')",
    ),
    (
        'system_config',
        "INSERT INTO system_config (key, value) VALUES ('smtp_host', 'mail.invalid')",
    ),
])
def test_row_outside_users_and_certificates_is_refused(app, sqlite_target, table, insert_sql):
    """The exact hole: the old check only counted users/certificates/cas."""
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)
        _execute(engine, insert_sql)

        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    message = str(excinfo.value)
    assert table in message
    assert '1 row' in message
    assert 'not empty' in message.lower()


def test_row_in_the_internal_migrations_ledger_is_refused(app, sqlite_target):
    """`_migrations` rows mean the target is already somebody's database."""
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)
        _execute(
            engine,
            _MIGRATIONS_DDL,
            "INSERT INTO _migrations (name) VALUES ('300_upgrade_from_2_254')",
        )

        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    assert '_migrations' in str(excinfo.value)


def test_foreign_table_is_refused_even_when_empty(app, sqlite_target):
    """A table that is not UCM's means the target belongs to something else."""
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)
        _execute(
            engine,
            "CREATE TABLE some_other_app (id INTEGER PRIMARY KEY, payload TEXT)",
        )

        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    message = str(excinfo.value)
    assert 'some_other_app' in message
    assert 'not part of ucm' in message.lower()


def test_foreign_database_without_any_ucm_table_is_refused(app, sqlite_target):
    with app.app_context(), _engine(sqlite_target) as engine:
        _execute(
            engine,
            "CREATE TABLE billing_invoices (id INTEGER PRIMARY KEY, amount INTEGER)",
        )

        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    assert 'billing_invoices' in str(excinfo.value)


def test_ucm_table_missing_a_column_is_refused(app, sqlite_target):
    """A partial/outdated UCM schema would silently drop what it cannot hold."""
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)
        _execute(engine, "ALTER TABLE system_config DROP COLUMN description")

        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    message = str(excinfo.value)
    assert 'system_config' in message
    assert 'description' in message
    assert 'partial' in message.lower()


def test_unreadable_target_is_refused_without_leaking_the_path(app, sqlite_target):
    """Fail-closed: a database we cannot inspect is never assumed empty."""
    path = sqlite_target[len('sqlite:///'):]
    with open(path, 'wb') as handle:
        handle.write(b'this is not a database' * 64)

    with app.app_context(), _engine(sqlite_target) as engine:
        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    message = str(excinfo.value)
    assert 'refusing' in message.lower()
    assert path not in message  # API-bound message: no filesystem path


def test_count_failure_is_refused(app, sqlite_target, monkeypatch):
    """Fail-closed: a table whose rows cannot be counted blocks the migration."""
    real_count = preflight._table_row_count

    def failing_count(conn, table):
        if table == 'certificates':
            raise OperationalError(
                'SELECT 1 FROM "certificates" LIMIT 1', {},
                Exception('database is locked'),
            )
        return real_count(conn, table)

    monkeypatch.setattr(preflight, '_table_row_count', failing_count)

    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)

        with pytest.raises(PreflightError) as excinfo:
            check_target_is_empty(engine)

    message = str(excinfo.value)
    assert 'certificates' in message
    assert 'could not verify' in message.lower()


# ---------------------------------------------------------------------------
# check_target_schema
# ---------------------------------------------------------------------------

def test_check_target_schema_passes_after_create_all(app, sqlite_target):
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)

        assert check_target_schema(engine) is None


def test_check_target_schema_refuses_a_dropped_table(app, sqlite_target):
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)
        _execute(engine, "DROP TABLE api_keys")

        with pytest.raises(PreflightError) as excinfo:
            check_target_schema(engine)

    message = str(excinfo.value)
    assert 'api_keys' in message
    assert 'incomplete' in message.lower()


def test_check_target_schema_refuses_a_dropped_column(app, sqlite_target):
    with app.app_context(), _engine(sqlite_target) as engine:
        _create_ucm_schema(app, engine)
        _execute(engine, "ALTER TABLE system_config DROP COLUMN description")

        with pytest.raises(PreflightError) as excinfo:
            check_target_schema(engine)

    message = str(excinfo.value)
    assert 'system_config' in message
    assert 'description' in message


# ---------------------------------------------------------------------------
# build_copy_plan
# ---------------------------------------------------------------------------

def test_copy_plan_covers_the_whole_schema_parents_first(app, sqlite_source, sqlite_target):
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _create_ucm_schema(app, target)

        plan = build_copy_plan(source, target)

    names = [entry.name for entry in plan]
    assert len(names) == len(set(names))  # no table planned twice
    assert set(names) == set(expected_schema())
    # FK order: a certificate cannot be inserted before its issuing CA.
    assert names.index('certificate_authorities') < names.index('certificates')
    assert names.index('certificate_templates') < names.index('certificates')

    columns = {entry.name: entry.columns for entry in plan}
    assert isinstance(columns['system_config'], tuple)
    # Every source column is copied — nothing is dropped along the way.
    assert set(columns['system_config']) == expected_schema()['system_config']


def test_copy_plan_includes_migrations_and_excludes_alembic_version(
        app, sqlite_source, sqlite_target):
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _execute(source, _MIGRATIONS_DDL, _ALEMBIC_DDL)
        _create_ucm_schema(app, target)
        _execute(target, _MIGRATIONS_DDL)

        plan = build_copy_plan(source, target)

    names = [entry.name for entry in plan]
    assert '_migrations' in names
    assert '_migrations' in INTERNAL_TABLES
    # alembic_version is on the source and absent from the target, and that is
    # approved: it is the one case that does not refuse the migration.
    assert 'alembic_version' not in names
    assert 'alembic_version' in IGNORED_TABLES

    ledger = next(entry for entry in plan if entry.name == '_migrations')
    assert ledger.columns == ('id', 'name', 'applied_at')


def test_copy_plan_refuses_a_source_table_absent_from_the_target(
        app, sqlite_source, sqlite_target):
    """Used to be `logger.warning("Skipping table ...")` plus a success."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _create_ucm_schema(app, target)
        _execute(target, "DROP TABLE crls")

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    message = str(excinfo.value)
    assert 'crls' in message
    assert 'dropped without a trace' in message.lower()


def test_copy_plan_refuses_an_extra_source_table_absent_from_the_target(
        app, sqlite_source, sqlite_target):
    """Operator data outside db.metadata still cannot vanish silently."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _execute(source, "CREATE TABLE legacy_notes (id INTEGER PRIMARY KEY, note TEXT)")
        _create_ucm_schema(app, target)

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    assert 'legacy_notes' in str(excinfo.value)


def test_copy_plan_refuses_a_source_column_absent_from_the_target(
        app, sqlite_source, sqlite_target):
    """Used to be recorded in stats["dropped_columns"] plus a success."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _execute(source, "ALTER TABLE system_config ADD COLUMN legacy_note TEXT")
        _create_ucm_schema(app, target)

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    message = str(excinfo.value)
    assert 'system_config' in message
    assert 'legacy_note' in message


def test_copy_plan_refuses_a_source_missing_an_expected_table(
        app, sqlite_source, sqlite_target):
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _execute(source, "DROP TABLE crls")
        _create_ucm_schema(app, target)

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    message = str(excinfo.value)
    assert 'crls' in message
    assert 'source' in message.lower()


def test_copy_plan_refuses_an_unreadable_source(app, sqlite_source, sqlite_target):
    path = sqlite_source[len('sqlite:///'):]
    with open(path, 'wb') as handle:
        handle.write(b'this is not a database' * 64)

    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, target)

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    message = str(excinfo.value)
    assert 'source' in message.lower()
    assert path not in message


# ---------------------------------------------------------------------------
# LEGACY_COLUMNS — the only approved loss
# ---------------------------------------------------------------------------

def test_copy_plan_accepts_a_source_carrying_the_legacy_columns(
        app, sqlite_source, sqlite_target):
    """An upgraded installation still has them; the migration must not stop."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _add_legacy_columns(source)
        _create_ucm_schema(app, target)

        plan = build_copy_plan(source, target)

    columns = {entry.name: set(entry.columns) for entry in plan}
    schema = expected_schema()
    for table, legacy in LEGACY_COLUMNS.items():
        assert not set(legacy) & columns[table]      # dropped, as approved
        assert columns[table] == schema[table]       # and nothing else is


def test_copy_plan_still_refuses_an_unapproved_extra_column(
        app, sqlite_source, sqlite_target):
    """The approval covers the listed columns and nothing else."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _add_legacy_columns(source)
        _execute(source, 'ALTER TABLE "user_sessions" ADD COLUMN "device_label" TEXT')
        _create_ucm_schema(app, target)

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    message = str(excinfo.value)
    assert 'device_label' in message
    assert 'last_active' not in message  # the approved one is not what blocks


def test_a_name_that_cannot_be_quoted_refuses_the_migration(
        app, sqlite_source, sqlite_target):
    """A column or a table this code cannot address is one it cannot copy.
    The old code filtered such names out of the column list and carried on,
    which is the silent-data-loss path this module exists to close."""
    with app.app_context(), _engine(sqlite_source) as source, \
            _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _create_ucm_schema(app, target)
        # Present on both sides, so it is the name itself that has to refuse.
        for engine in (source, target):
            _execute(engine, 'CREATE TABLE "odd-name" (id INTEGER)')

        with pytest.raises(PreflightError) as excinfo:
            build_copy_plan(source, target)

    assert 'odd-name' in str(excinfo.value)
    assert 'identifier' in str(excinfo.value)


def test_dropped_columns_reports_only_what_the_source_really_has(
        app, sqlite_source, sqlite_target):
    partial = {
        'user_sessions': {'last_active': ''},
        'approval_requests': {'data': ''},
    }
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _add_legacy_columns(source, partial)
        _create_ucm_schema(app, target)

        report = dropped_columns(source, target)

    assert set(report) == {'user_sessions', 'approval_requests'}
    assert report['user_sessions']['last_active']['reason'] == \
        LEGACY_COLUMNS['user_sessions']['last_active']
    assert report['approval_requests']['data']['reason'] == \
        LEGACY_COLUMNS['approval_requests']['data']
    # The count is what turns a standing approval into a measured loss.
    assert all(entry['values'] == 0
               for columns in report.values() for entry in columns.values())
    assert all(entry['reason'].strip()
               for columns in report.values() for entry in columns.values())


def test_dropped_columns_counts_the_values_it_leaves_behind(
        app, sqlite_source, sqlite_target):
    """An operator deserves "12 values", not a sentence: three of these
    columns were replaced by a column that was added empty, so on an old
    installation they are the only copy of what they hold."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _add_legacy_columns(source, {'group_members': {'created_at': ''}})
        _execute(source, 'INSERT INTO "groups" (id, name) VALUES (1, \'g\')')
        _execute(source,
                 'INSERT INTO "users" (id, username, email, password_hash, role, '
                 'auth_source) VALUES (1, \'u\', \'u@x.test\', \'x\', \'viewer\', \'local\')')
        _execute(source,
                 'INSERT INTO "group_members" (group_id, user_id, created_at) '
                 'VALUES (1, 1, \'2020-01-01\')')
        _create_ucm_schema(app, target)

        report = dropped_columns(source, target)

    assert report['group_members']['created_at']['values'] == 1


def test_dropped_columns_is_empty_when_nothing_is_left_behind(
        app, sqlite_source, sqlite_target):
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _create_ucm_schema(app, target)

        assert dropped_columns(source, target) == {}


def test_dropped_columns_ignores_an_entry_the_source_does_not_have(
        app, sqlite_source, sqlite_target):
    """A recent installation has none of the old tables' extra columns."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _add_legacy_columns(source)
        _execute(source, 'DROP TABLE "user_sessions"')
        _create_ucm_schema(app, target)

        report = dropped_columns(source, target)

    assert 'user_sessions' not in report
    assert 'data' in report['approval_requests']
    assert report['approval_requests']['data']['values'] == 0


def test_legacy_columns_are_not_declared_by_any_model(app):
    """A column a model declares again is not a legacy column."""
    schema = expected_schema()
    for table, columns in LEGACY_COLUMNS.items():
        assert table in schema, f"{table} is not a UCM table"
        for column, reason in columns.items():
            assert column not in schema[table], f"{table}.{column} is a model column"
            assert reason.strip(), f"{table}.{column} has no written reason"


def test_legacy_columns_match_the_baseline_schema(app):
    """The list is exactly what an upgraded installation carries and the
    models dropped.

    Same contract as `tests/test_backup_manifest.py` for the archive: the day
    a column is removed from a model without a line in LEGACY_COLUMNS, the
    migration would drop it silently — this fails first.
    """
    baseline = _baseline_schema()
    schema = expected_schema()

    unapproved = {}
    for table, columns in _carried_schema().items():
        if table not in schema:
            continue
        extra = columns - schema[table] - set(LEGACY_COLUMNS.get(table, {}))
        if extra:
            unapproved[table] = sorted(extra)

    assert unapproved == {}, (
        "columns a 2.254 database may carry, dropped from the models, and "
        f"not approved in LEGACY_COLUMNS: {unapproved}"
    )

    # And the reverse: an approval for a column no schema ever had is a typo.
    for table, columns in LEGACY_COLUMNS.items():
        for column in columns:
            assert column in baseline.get(table, set()), f"{table}.{column}"


def test_no_unapproved_extra_column_in_the_test_database(app):
    """The same check against the database the suite actually runs on."""
    with app.app_context():
        from models import db

        inspector = inspect(db.engine)
        schema = expected_schema()
        unapproved = {}
        for table in inspector.get_table_names():
            if table not in schema:
                continue
            extra = {c['name'] for c in inspector.get_columns(table)} - schema[table]
            extra -= set(LEGACY_COLUMNS.get(table, {}))
            if extra:
                unapproved[table] = sorted(extra)

    assert unapproved == {}, (
        f"columns held by the database and by no model, unapproved: {unapproved}"
    )


def test_copy_plan_leaves_both_databases_untouched(app, sqlite_source, sqlite_target):
    """Preflight only reads: a refusal must not have started anything."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _create_ucm_schema(app, target)
        before_source = _table_names(source)
        before_target = _table_names(target)

        build_copy_plan(source, target)
        check_target_schema(target)

        assert _table_names(source) == before_source
        assert _table_names(target) == before_target


def test_copy_plan_ignores_the_session_store_table(app, sqlite_source, sqlite_target):
    """Live sessions are never copied, and their table never blocks a switch."""
    with app.app_context(), _engine(sqlite_source) as source, _engine(sqlite_target) as target:
        _create_ucm_schema(app, source)
        _execute(source, "CREATE TABLE flask_sessions (id INTEGER PRIMARY KEY, "
                         "session_id VARCHAR(255), data BLOB, expiry DATETIME)",
                 "INSERT INTO flask_sessions (session_id) VALUES ('live')")
        _create_ucm_schema(app, target)

        plan = build_copy_plan(source, target)

    assert 'flask_sessions' not in [entry.name for entry in plan]
    assert 'flask_sessions' in IGNORED_TABLES
