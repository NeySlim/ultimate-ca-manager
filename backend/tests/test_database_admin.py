"""
Tests for database_admin_service: backend switch, bootstrap, migrate.

Covers the bug-class that shipped in #96:
  - SQLite → empty target migration
  - Auth bootstrap on switch-without-migration (no lockout)
  - Refusing to overwrite a non-empty target
  - JSON column handling
  - FK-disabled vs topological fallback
  - PG sequence reset (smoke / mock)
"""
import os
import json
import tempfile

import pytest
from sqlalchemy import create_engine, text, inspect

from services import database_admin_service as svc


# ---------------------------------------------------------------------------
# Fixtures
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
def populated_app(app):
    """App with the auto-created admin user — enough for migration tests."""
    return app


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

def test_connection_rejects_empty_url():
    ok, msg = svc.test_connection('')
    assert not ok
    assert 'required' in msg.lower()


def test_connection_rejects_unknown_scheme():
    ok, msg = svc.test_connection('mysql://x:y@localhost/db')
    assert not ok
    assert 'unsupported' in msg.lower()


def test_connection_succeeds_for_valid_sqlite(sqlite_target):
    # Create the file first by opening it
    create_engine(sqlite_target).connect().close()
    ok, msg = svc.test_connection(sqlite_target)
    assert ok, msg


# ---------------------------------------------------------------------------
# bootstrap_auth_to_target
# ---------------------------------------------------------------------------

def test_bootstrap_copies_users_to_empty_target(populated_app, sqlite_target):
    with populated_app.app_context():
        ok, msg, stats = svc.bootstrap_auth_to_target(sqlite_target)

    assert ok, msg
    assert stats['rows_copied'] >= 1  # admin user at minimum

    # Verify the admin landed on the target
    eng = create_engine(sqlite_target)
    with eng.connect() as c:
        row = c.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin'")).fetchone()
        assert row[0] == 1
    eng.dispose()


def test_bootstrap_skips_when_target_already_has_users(populated_app, sqlite_target):
    # First bootstrap to populate
    with populated_app.app_context():
        svc.bootstrap_auth_to_target(sqlite_target)

    # Second call should be a no-op (skip), not a failure
    with populated_app.app_context():
        ok, msg, stats = svc.bootstrap_auth_to_target(sqlite_target)

    assert ok
    assert 'skipped' in msg.lower()
    assert stats['rows_copied'] == 0


# ---------------------------------------------------------------------------
# migrate_data
# ---------------------------------------------------------------------------

def test_migrate_refuses_non_empty_target(populated_app, sqlite_target):
    # Pre-populate target so the safety check fires
    with populated_app.app_context():
        svc.bootstrap_auth_to_target(sqlite_target)

    with populated_app.app_context():
        ok, msg, stats = svc.migrate_data(sqlite_target)

    assert not ok
    assert 'not empty' in msg.lower()
    assert stats['tables_migrated'] == 0


@pytest.mark.sqlite_only(reason='the session database is the SQLite source of this round trip')
def test_migrate_full_roundtrip_sqlite_to_sqlite(populated_app, sqlite_target):
    with populated_app.app_context():
        ok, msg, stats = svc.migrate_data(sqlite_target)

    assert ok, msg
    assert stats['tables_migrated'] >= 5  # at least users, system_config, ...
    assert stats['rows_migrated'] >= 1
    assert isinstance(stats['dropped_columns'], dict)

    # Spot-check: admin user exists on the target
    eng = create_engine(sqlite_target)
    with eng.connect() as c:
        users = c.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
    eng.dispose()
    assert users >= 1


class TestTheSwitchIsAsCheckedAsTheMigration:
    """Every failure mode of the bootstrap used to be pinned by a single test
    that replaced the whole function with a stub returning False: it proved
    the route handles a False, and nothing about how one is produced."""

    def test_the_bootstrap_verifies_what_it_copied(
            self, populated_app, sqlite_target, monkeypatch):
        from services.database_admin import migration as migration_module
        from services.database_admin.verify import VerificationError

        def refuse(*args, **kwargs):
            raise VerificationError('users: 3 rows copied, 2 on the target')

        monkeypatch.setattr(migration_module, 'verify_migration', refuse)

        with populated_app.app_context():
            ok, message, stats = svc.bootstrap_auth_to_target(sqlite_target)

        assert ok is False
        assert '2 on the target' in message
        assert stats['refusal'] == 'verification'

    def test_a_target_without_a_single_user_aborts_the_switch(
            self, populated_app, sqlite_target, monkeypatch):
        """The anti-lockout guard: an administrator who lands on a backend
        holding no account cannot get back in."""
        from services.database_admin import migration as migration_module

        real_copy = migration_module.copy_tables

        def copy_without_users(source, target_engine, plan, **kwargs):
            plan = [entry for entry in plan if entry.name != 'users']
            return real_copy(source, target_engine, plan, **kwargs)

        monkeypatch.setattr(migration_module, 'copy_tables', copy_without_users)

        with populated_app.app_context():
            ok, message, stats = svc.bootstrap_auth_to_target(sqlite_target)

        assert ok is False
        assert 'lockout' in message
        assert stats['refusal'] == 'verification'

    def test_a_target_that_cannot_be_read_is_treated_as_provisioned(
            self, populated_app, sqlite_target, monkeypatch):
        """Fail-closed: bootstrapping over an installation already in use is
        the one outcome that has no undo."""
        from services.database_admin import migration as migration_module

        def unreadable(engine):
            raise RuntimeError('permission denied on relation "users"')

        monkeypatch.setattr(migration_module, 'inspect', unreadable)

        with populated_app.app_context():
            ok, message, _ = svc.bootstrap_auth_to_target(sqlite_target)

        assert ok is False
        assert 'users table could not be read' in message

    def test_the_source_is_read_in_one_transaction(self, populated_app):
        """`users` and `group_members` read at two different moments can
        bootstrap a target with a membership pointing at an account that was
        never copied."""
        from services.database_admin.copy import consistent_live_source

        with populated_app.app_context():
            with consistent_live_source() as (conn, description, _is_pg):
                assert conn.in_transaction(), 'the read is not isolated'
                assert 'transaction' in description


class TestStatusDescribesTheConnectedDatabase:
    """`get_status` reports the size and the version of a database. Reading
    the module-level configuration instead of the engine meant describing
    whatever that configuration named, which under the test suite is the
    machine's own installation rather than the database in use."""

    def test_the_status_describes_the_engine_in_use(self, app):
        from models import db

        with app.app_context():
            status = svc.get_status()
            connected = str(db.engine.url)

        assert status['healthy'] is True
        assert status['backend'] == (
            'postgresql' if connected.startswith('postgresql') else 'sqlite')
        assert status['table_count'] > 10
        # The redacted URI is the one that is connected, not the configured one.
        assert status['uri_redacted'].startswith(connected.split('://')[0])

    def test_the_status_route_answers(self, auth_client):
        response = auth_client.get('/api/v2/database/status')

        assert response.status_code == 200, response.data
        data = json.loads(response.data)['data']
        assert data['healthy'] is True
        assert data['backend'] in ('sqlite', 'postgresql')

    def test_the_status_never_carries_a_password(self, app, monkeypatch):
        from sqlalchemy.engine import make_url
        from services.database_admin import status as status_module

        monkeypatch.setattr(
            status_module, '_live_database_url',
            lambda: make_url('postgresql://ucm:S3cret-For-Review@db.example/ucm'))

        with app.app_context():
            reported = svc.get_status()

        assert 'S3cret-For-Review' not in json.dumps(reported)


class TestBootstrapPlanOnAnUpgradedInstallation:
    """The test database is built from the models, so it never carries the
    columns an installation upgraded from an older version still has. Those
    have to be built by hand, or nothing here sees them."""

    @staticmethod
    def _schemas(app, source_url, target_url):
        from models import db
        from services.database_admin.preflight import LEGACY_COLUMNS, expected_schema

        source = create_engine(source_url)
        target = create_engine(target_url)
        with app.app_context():
            expected_schema()  # registers the lazily-imported model modules
            db.metadata.create_all(source)
            db.metadata.create_all(target)
        with source.begin() as conn:
            for table, columns in LEGACY_COLUMNS.items():
                for column in columns:
                    conn.execute(text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column}" TEXT'))
        return source, target

    def test_a_legacy_column_does_not_block_the_switch(
            self, populated_app, sqlite_target, tmp_path):
        """`group_members` is one of the bootstrapped tables and carries
        `created_at` on any upgraded installation: refusing it would make the
        backend switch impossible on every real deployment."""
        from services.database_admin.migration import _bootstrap_plan

        source, target = self._schemas(
            populated_app, f"sqlite:///{tmp_path / 'src.db'}", sqlite_target)
        try:
            plan = _bootstrap_plan(source, target)
        finally:
            source.dispose()
            target.dispose()

        members = next(entry for entry in plan if entry.name == 'group_members')
        assert 'created_at' not in members.columns
        assert 'joined_at' in members.columns

    def test_an_unapproved_missing_column_still_blocks_it(
            self, populated_app, sqlite_target, tmp_path):
        from services.database_admin.migration import _bootstrap_plan
        from services.database_admin.preflight import PreflightError

        source, target = self._schemas(
            populated_app, f"sqlite:///{tmp_path / 'src2.db'}", sqlite_target)
        try:
            with source.begin() as conn:
                conn.execute(text(
                    'ALTER TABLE "users" ADD COLUMN "device_label" TEXT'))
            with pytest.raises(PreflightError, match='device_label'):
                _bootstrap_plan(source, target)
        finally:
            source.dispose()
            target.dispose()

    def test_the_parents_are_copied_before_the_children(
            self, populated_app, sqlite_target, tmp_path):
        """`users` is a child of `pro_custom_roles` and `pro_sso_providers`;
        the hand-written order put it first, which a PostgreSQL role that
        cannot disable constraints refuses."""
        from services.database_admin.migration import _bootstrap_plan

        source, target = self._schemas(
            populated_app, f"sqlite:///{tmp_path / 'src3.db'}", sqlite_target)
        try:
            order = [entry.name for entry in _bootstrap_plan(source, target)]
        finally:
            source.dispose()
            target.dispose()

        assert order.index('pro_custom_roles') < order.index('users')
        assert order.index('pro_sso_providers') < order.index('users')
        assert order.index('users') < order.index('group_members')


# ---------------------------------------------------------------------------
# FK-disable fallback for non-superuser PostgreSQL roles (#126, #305)
# ---------------------------------------------------------------------------

def test_disable_fks_refusal_keeps_bulk_load_transaction_usable(sqlite_target):
    """A refused ``SET LOCAL session_replication_role`` must only roll back its
    savepoint: the enclosing ``engine.begin()`` transaction stays open and the
    rows loaded afterwards are committed (#305 regression: the connection was
    rolled back instead, closing the context-managed transaction, and every
    later INSERT raised "Can't operate on closed transaction").

    SQLite rejects the PostgreSQL SET syntax, which reproduces the refusal
    without needing a PostgreSQL server."""
    eng = create_engine(sqlite_target)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE t (x INTEGER)"))
    with eng.begin() as conn:
        # First statement of the block, exactly as in migrate_data()
        assert svc._try_disable_fks(conn, target_is_pg=True) is False
        conn.execute(text("INSERT INTO t (x) VALUES (1)"))
        conn.execute(text("INSERT INTO t (x) VALUES (2)"))
    with eng.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM t")).scalar() == 2
    eng.dispose()


_PG_URL = os.environ.get('UCM_TEST_PG_URL')


@pytest.fixture
def pg_target():
    """Empty PostgreSQL target (schema reset before and after), opt-in via
    UCM_TEST_PG_URL. The role should NOT be superuser so that the
    session_replication_role refusal path is exercised."""
    if not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    eng = create_engine(_PG_URL)

    def _reset():
        with eng.begin() as c:
            c.execute(text('DROP SCHEMA public CASCADE'))
            c.execute(text('CREATE SCHEMA public'))

    # The bench is one database; another file resets the same schema.
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        _reset()
        yield _PG_URL
        _reset()
    eng.dispose()


def test_migrate_sqlite_to_pg_non_superuser_falls_back_to_topological_order(
        populated_app, pg_target):
    """#305: the whole migration failed ('Can't operate on closed transaction
    inside context manager', 0 rows migrated) as soon as the PostgreSQL role
    could not disable FK checks."""
    with populated_app.app_context():
        ok, msg, stats = svc.migrate_data(pg_target)

    assert ok, msg
    # Nothing is reported as an error any more: anything that cannot be
    # copied refuses the migration outright.
    assert stats['validation']['ok'] is True
    assert stats['rows_migrated'] >= 1

    eng = create_engine(pg_target)
    with eng.connect() as c:
        assert c.execute(text('SELECT COUNT(*) FROM users')).scalar() >= 1
    # The _migrations table is created on the target outside the metadata
    # (test app sources carry no applied-migration rows to copy).
    assert '_migrations' in inspect(eng).get_table_names()
    eng.dispose()


def test_a_row_pointing_at_a_later_row_of_its_table_is_copied(populated_app, pg_target):
    """A role inheriting from one created after it: without the constraints
    turned off, the row went in before its parent and the copy was refused."""
    from models import db
    from models.rbac import CustomRole

    with populated_app.app_context():
        heir = CustomRole(name='Forward Heir', permissions=['read:cas'])
        db.session.add(heir)
        db.session.flush()
        parent = CustomRole(name='Forward Parent', permissions=['read:crl'])
        db.session.add(parent)
        db.session.flush()
        heir.inherits_from = parent.id
        db.session.commit()
        heir_id, parent_id = heir.id, parent.id
        try:
            ok, msg, _stats = svc.migrate_data(pg_target)
        finally:
            CustomRole.query.filter(CustomRole.id.in_([heir_id, parent_id])).update(
                {'inherits_from': None}, synchronize_session=False)
            CustomRole.query.filter(CustomRole.id.in_([heir_id, parent_id])).delete(
                synchronize_session=False)
            db.session.commit()

    assert ok, msg
    eng = create_engine(pg_target)
    with eng.connect() as c:
        assert c.execute(text('SELECT inherits_from FROM pro_custom_roles WHERE id = :i'),
                         {'i': heir_id}).scalar() == parent_id
    eng.dispose()


def test_bootstrap_to_pg_non_superuser_copies_users(populated_app, pg_target):
    """Same failure class on the switch-without-migration path: a refused
    FK-disable poisoned the per-table transaction and every table was skipped,
    leaving the target without any user (admin lockout)."""
    with populated_app.app_context():
        ok, msg, stats = svc.bootstrap_auth_to_target(pg_target)

    assert ok, msg
    assert stats['rows_copied'] >= 1
    # A table that cannot be copied is a refusal, so a success means every
    # one of them landed — users included.
    assert stats['tables']['users'] >= 1

    eng = create_engine(pg_target)
    with eng.connect() as c:
        assert c.execute(text('SELECT COUNT(*) FROM users')).scalar() >= 1
    eng.dispose()


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------

def test_normalize_row_pg_to_sqlite_serializes_dicts():
    out = svc._normalize_row(
        {"a": {"x": 1}, "b": [1, 2], "c": "plain"},
        source_is_pg=True,
        target_is_pg=False,
    )
    assert out["a"] == json.dumps({"x": 1})
    assert out["b"] == json.dumps([1, 2])
    assert out["c"] == "plain"


def test_normalize_row_sqlite_to_pg_parses_json_columns():
    # JSON-typed target column → JSON-encoded text (PG parses on insert).
    # Strings that are already JSON pass through verbatim.
    out = svc._normalize_row(
        {"perms": '["read:certs","write:cas"]', "name": "alice"},
        source_is_pg=False,
        target_is_pg=True,
        target_json_cols={"perms"},
    )
    assert out["perms"] == '["read:certs","write:cas"]'
    assert out["name"] == "alice"  # untouched


def test_normalize_row_sqlite_to_pg_leaves_non_json_strings_alone():
    out = svc._normalize_row(
        {"name": "alice", "perms": "[1,2]"},
        source_is_pg=False,
        target_is_pg=True,
        target_json_cols=set(),  # no JSON columns
    )
    assert out["name"] == "alice"
    assert out["perms"] == "[1,2]"  # not parsed


def test_normalize_row_handles_memoryview():
    out = svc._normalize_row(
        {"blob": memoryview(b"hello")},
        source_is_pg=True,
        target_is_pg=False,
    )
    assert out["blob"] == b"hello"


def test_normalize_row_sqlite_to_pg_coerces_int_to_bool():
    """SQLite stores bools as INTEGER; PG BOOLEAN refuses int — must coerce."""
    out = svc._normalize_row(
        {"active": 1, "deleted": 0, "name": "alice"},
        source_is_pg=False,
        target_is_pg=True,
        target_bool_cols={"active", "deleted"},
    )
    assert out["active"] is True
    assert out["deleted"] is False
    assert out["name"] == "alice"


def test_normalize_row_sqlite_to_pg_coerces_str_bool_variants():
    out = svc._normalize_row(
        {"a": "true", "b": "false", "c": "1", "d": "0", "e": ""},
        source_is_pg=False,
        target_is_pg=True,
        target_bool_cols={"a", "b", "c", "d", "e"},
    )
    assert out["a"] is True
    assert out["b"] is False
    assert out["c"] is True
    assert out["d"] is False
    assert out["e"] is False


def test_normalize_row_preserves_real_bools():
    out = svc._normalize_row(
        {"active": True, "deleted": False},
        source_is_pg=False,
        target_is_pg=True,
        target_bool_cols={"active", "deleted"},
    )
    assert out["active"] is True
    assert out["deleted"] is False


def test_normalize_row_pg_to_sqlite_leaves_bool_alone():
    # SQLite accepts True/False (stored as 1/0). No need to mangle.
    out = svc._normalize_row(
        {"active": True},
        source_is_pg=True,
        target_is_pg=False,
        target_bool_cols={"active"},
    )
    assert out["active"] is True


def test_normalize_row_sqlite_to_pg_encodes_dict_list_for_json_column():
    """SQLAlchemy auto-deserializes SQLite JSON to dict/list. psycopg2 would
    send a Python list as PostgreSQL text[], breaking a real json column.
    """
    out = svc._normalize_row(
        {"perms": ["read:certs", "write:cas"], "meta": {"key": "val"}},
        source_is_pg=False,
        target_is_pg=True,
        target_json_cols={"perms", "meta"},
    )
    # Both must end up as JSON-encoded strings (PG parses them on insert).
    assert out["perms"] == '["read:certs", "write:cas"]'
    assert out["meta"] == '{"key": "val"}'


def test_topo_sort_puts_parents_before_children(populated_app):
    from models import db
    with populated_app.app_context():
        order = svc._topo_sort_tables(inspect(db.engine))
    # users must come before user_sessions (FK)
    if 'user_sessions' in order and 'users' in order:
        assert order.index('users') < order.index('user_sessions')
    # certificate_authorities must come before certificates (FK)
    if 'certificates' in order and 'certificate_authorities' in order:
        assert order.index('certificate_authorities') < order.index('certificates')


def test_redact_uri_hides_password():
    redacted = svc._redact_uri('postgresql://user:secret@host:5432/db')
    assert 'secret' not in redacted
    assert '***' in redacted


def test_human_size_formats_bytes():
    assert svc._human_size(0) == '0 B'
    assert svc._human_size(1024) == '1.0 KB'
    assert 'MB' in svc._human_size(1024 * 1024 * 5)
