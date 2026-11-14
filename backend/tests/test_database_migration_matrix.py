"""The whole migration, end to end, and every way it must refuse to finish.

The gate for this work: the same-backend and cross-backend matrix, a source
that keeps being written to while it is read, a target that holds anything at
all, and a failure of the snapshot, the verification, the bootstrap or the
configuration write — each of which must forbid the switch rather than
produce a half-migrated installation nobody was told about.
"""
import contextlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import Table, create_engine, event, inspect, text
from sqlalchemy.engine import Engine

from config.settings import DATA_DIR
from models import db
from services.database_admin import migration, persistence, snapshot, verify
from services.database_admin.lock import (
    clear_switch_pending,
    switch_pending,
    switch_pending_path,
)
from services.database_admin.verify import VerificationError

pytestmark = pytest.mark.sqlite_only(
    reason='the session database is the migration source, SQLite by design; a PostgreSQL source has its own engine (UCM_TEST_PG_URL)')

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_needs_pg = pytest.mark.skipif(
    not _PG_URL, reason='UCM_TEST_PG_URL not set; skipping PostgreSQL matrix')


def _require_a_dumpable_bench():
    """Skip with the reason that actually applies, evaluated when asked.

    pg_dump refuses to dump a server newer than itself, and a migration away
    from PostgreSQL now requires a verified dump, so on such a host the
    migration refuses by design (that refusal is pinned in
    `tests/test_database_migration_snapshot.py`). What cannot be exercised
    there is the successful path.

    Deliberately not evaluated at import time: this opens a connection, and
    a module-level call would do it during collection, in every xdist worker,
    for a test that may not even be selected.
    """
    import shutil
    import subprocess

    if not shutil.which('pg_dump'):
        pytest.skip('pg_dump is not installed')

    try:
        client = subprocess.run(['pg_dump', '--version'], capture_output=True,
                                text=True, timeout=10).stdout.split()[2]
    except Exception as exc:                     # pragma: no cover - toolchain
        pytest.skip(f'pg_dump --version could not be read: {exc}')

    engine = create_engine(_PG_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            server = conn.execute(text('SHOW server_version')).scalar()
    except Exception as exc:
        pytest.skip(f'the PostgreSQL bench could not be reached: {exc}')
    finally:
        engine.dispose()

    if int(client.split('.')[0]) < int(str(server).split('.')[0]):
        pytest.skip(
            f'pg_dump {client} cannot dump a PostgreSQL {server} server, and '
            'a migration away from PostgreSQL requires a verified dump')


@pytest.fixture(autouse=True)
def _a_source_that_satisfies_its_own_schema(app):
    """These tests read the shared database as a database, not as a fixture.

    Other files write rows through the ORM with foreign keys SQLite never
    enforces, so whether this one sees a consistent source depends on which
    files ran before it on this worker. The migration refuses such a source
    on purpose — that refusal has its own test — so here it is cleaned first.
    """
    from tests.conftest import clean_dangling_rows, clean_unreadable_secrets

    clean_dangling_rows(app)
    clean_unreadable_secrets(app)
    yield


@pytest.fixture
def sqlite_target(tmp_path):
    return f"sqlite:///{tmp_path / 'target.db'}"


@pytest.fixture
def pg_target():
    """An empty PostgreSQL target, dropped and recreated around the test.

    Held exclusively: the bench is one database and three files reset it.
    """
    from tests.conftest import pg_bench_exclusive

    def _reset():
        engine = create_engine(_PG_URL, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.execute(text('DROP SCHEMA public CASCADE'))
            conn.execute(text('CREATE SCHEMA public'))
        engine.dispose()

    with pg_bench_exclusive():
        _reset()
        yield _PG_URL
        _reset()


@pytest.fixture
def restart_signal():
    """The file the watcher polls; absent unless a restart was requested."""
    signal = Path(DATA_DIR) / '.restart_requested'
    signal.unlink(missing_ok=True)
    yield signal
    signal.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def switch_marker():
    """No test inherits another's pending switch."""
    clear_switch_pending()
    yield switch_pending_path()
    clear_switch_pending()


@pytest.fixture
def env_file():
    """The sandboxed ucm.env, as the conftest redirected it."""
    path = Path(persistence.UCM_ENV_PATH)
    before = path.read_text() if path.exists() else None
    yield path
    if before is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(before)


def _counts(url, tables):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {
                name: conn.execute(
                    text(f'SELECT COUNT(*) FROM "{name}"')).scalar()
                for name in tables
            }
    finally:
        engine.dispose()


class TestTheMatrix:
    def test_sqlite_to_sqlite_copies_and_verifies_everything(
            self, app, create_ca, sqlite_target):
        create_ca(cn='Matrix Round Trip CA')

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is True, message
        assert stats['rows_migrated'] > 0
        assert stats['validation']['ok'] is True
        assert set(stats['validation']['checks']) >= {
            'row_counts', 'foreign_keys', 'unique_constraints',
            'sequences', 'schema', 'secrets'}
        assert stats['snapshot']['sha256']
        assert 'snapshot' in stats['source_view']

        copied = _counts(sqlite_target, ['users', 'certificate_authorities'])
        assert copied['users'] == stats['tables']['users']
        assert copied['certificate_authorities'] >= 1

    def test_every_source_table_reaches_the_target(self, app, sqlite_target):
        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)
            source_tables = set(inspect(db.engine).get_table_names())

        assert ok is True, message
        # Nothing is allowed to go missing quietly: what the source has, the
        # plan copied, and the plan is what the statistics report.
        assert source_tables - set(stats['tables']) <= {'alembic_version'}

    @_needs_pg
    def test_sqlite_to_postgresql(self, app, create_ca, pg_target):
        create_ca(cn='Matrix To PostgreSQL CA')

        with app.app_context():
            ok, message, stats = migration.migrate_data(pg_target)

        assert ok is True, message
        assert stats['rows_migrated'] > 0
        copied = _counts(pg_target, ['users', 'certificate_authorities'])
        assert copied['users'] == stats['tables']['users']

    @_needs_pg
    def test_postgresql_to_sqlite(self, app, create_ca, pg_target,
                                  sqlite_target):
        """The other direction, from a PostgreSQL source read under
        REPEATABLE READ rather than from a file."""
        _require_a_dumpable_bench()
        create_ca(cn='Matrix From PostgreSQL CA')
        with app.app_context():
            ok, message, _ = migration.migrate_data(pg_target)
        assert ok is True, message

        pg_engine = create_engine(pg_target, pool_pre_ping=True)
        try:
            with app.app_context():
                # Point the application's own engine at PostgreSQL: the
                # migration reads the database that is connected, which is
                # exactly what this test needs it to do.
                engines = db._app_engines[app]
                original = engines[None]
                engines[None] = pg_engine
                db.session.remove()
                try:
                    ok, message, stats = migration.migrate_data(sqlite_target)
                finally:
                    engines[None] = original
                    db.session.remove()
        finally:
            pg_engine.dispose()

        assert ok is True, message
        assert 'REPEATABLE READ' in stats['source_view']
        assert stats['rows_migrated'] > 0
        assert stats['snapshot']['backend'] == 'postgresql'
        assert 'pg_restore' in stats['snapshot']['verified']

        copied = _counts(sqlite_target, ['certificate_authorities'])
        assert copied['certificate_authorities'] >= 1


def _deleted_last_user(app, auth_client, create_user):
    """The id of an account created and then deleted: the highest ever handed out."""
    made = create_user(username='switch_high_water', role='viewer')
    assert auth_client.delete(f"/api/v2/users/{made['id']}").status_code == 200
    return made['id']


def _next_user_id(url):
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            return conn.execute(text(
                "INSERT INTO users (username, email, password_hash, role, auth_source) "
                "VALUES ('after_switch', 'after@switch', 'x', 'viewer', 'local') RETURNING id")).scalar()
    finally:
        engine.dispose()


class TestAUserIdCrossesTheSwitchUnused:
    """The target hands out ids above every one the source ever handed out."""

    def test_migration_to_sqlite(self, app, auth_client, create_user, sqlite_target):
        gone = _deleted_last_user(app, auth_client, create_user)
        with app.app_context():
            ok, message, _ = migration.migrate_data(sqlite_target)
        assert ok is True, message
        assert _next_user_id(sqlite_target) > gone

    def test_bootstrap_to_sqlite(self, app, auth_client, create_user, sqlite_target):
        gone = _deleted_last_user(app, auth_client, create_user)
        with app.app_context():
            ok, message, _ = migration.bootstrap_auth_to_target(sqlite_target)
        assert ok is True, message
        assert _next_user_id(sqlite_target) > gone

    @_needs_pg
    def test_migration_to_postgresql(self, app, auth_client, create_user, pg_target):
        gone = _deleted_last_user(app, auth_client, create_user)
        with app.app_context():
            ok, message, _ = migration.migrate_data(pg_target)
        assert ok is True, message
        assert _next_user_id(pg_target) > gone

    @_needs_pg
    def test_bootstrap_to_postgresql(self, app, auth_client, create_user, pg_target):
        gone = _deleted_last_user(app, auth_client, create_user)
        with app.app_context():
            ok, message, _ = migration.bootstrap_auth_to_target(pg_target)
        assert ok is True, message
        assert _next_user_id(pg_target) > gone


class TestTheDataKeysCrossTheSwitch:
    """A switch without data carries values under the DEK: it carries the DEK rows too."""

    def _bootstrap(self, app, target):
        from models import EncryptionKey
        from utils.datetime_utils import utc_now
        with app.app_context():
            EncryptionKey.query.delete()
            db.session.add(EncryptionKey(version=7, state='active', kek_id='0' * 16,
                                         wrapped='1:dGVzdA==', created_at=utc_now()))
            db.session.commit()
            try:
                ok, message, _ = migration.bootstrap_auth_to_target(target)
            finally:
                EncryptionKey.query.delete()
                db.session.commit()
        assert ok is True, message
        engine = create_engine(target)
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(
                    'SELECT version, state, wrapped FROM encryption_keys')).fetchall()
        finally:
            engine.dispose()
        assert [tuple(r) for r in rows] == [(7, 'active', '1:dGVzdA==')]

    def test_bootstrap_to_sqlite(self, app, sqlite_target):
        self._bootstrap(app, sqlite_target)

    @_needs_pg
    def test_bootstrap_to_postgresql(self, app, pg_target):
        self._bootstrap(app, pg_target)


# The child reads neither the host's env file nor its master key, as under conftest
_BOOT_ON_TARGET = '''
import os
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from pathlib import Path
from security import encryption
encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
encryption.key_encryption.reload()
from config import settings
from utils.db_url import sqlalchemy_url
settings.TestingConfig.SQLALCHEMY_DATABASE_URI = sqlalchemy_url(os.environ['DATABASE_URL'])
from app import create_app
create_app('testing')
print('BOOTED')
'''


def _boots(target, tmp_path):
    """The application starts on *target*, in a child that reads nothing of the host."""
    import subprocess
    import sys
    data = tmp_path / 'node'
    data.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(DATA_DIR=str(data), DATABASE_PATH=str(data / 'ucm.db'), DATABASE_URL=target,
               UCM_SKIP_SECRET_VALIDATION='1', UCM_HA='0')
    backend = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, '-c', _BOOT_ON_TARGET], cwd=backend, env=env,
                         capture_output=True, text=True, timeout=180)
    assert run.returncode == 0 and 'BOOTED' in run.stdout, run.stdout[-3000:] + run.stderr[-3000:]


@pytest.fixture
def a_3_0_source(app):
    """The session database carries the registry of a started 3.0 database, as a real source does."""
    import migration_runner
    with app.app_context():
        engine, pg = db.engine, db.engine.dialect.name == 'postgresql'
        created = '_migrations' not in inspect(engine).get_table_names()
        migration_runner._ensure_tracking_table(engine, pg)
        with engine.connect() as conn:
            present = {r[0] for r in conn.execute(text('SELECT name FROM _migrations'))}
        added = [n for n in migration_runner._list_migration_names() if n not in present]
        migration_runner._mark_applied(engine, added, pg)
    yield
    with app.app_context():
        with db.engine.begin() as conn:
            if created:
                conn.execute(text('DROP TABLE _migrations'))
                return
            for name in added:
                conn.execute(text('DELETE FROM _migrations WHERE name = :n'), {'n': name})


class TestASwitchedTargetStarts:
    """The target of a switch, with or without its data, is a 3.0 database: its registry
    names every current migration, so the pivot accepts it and the next start goes to the end."""

    def _switch_then_start(self, app, target, tmp_path, monkeypatch,
                           switch=migration.bootstrap_auth_to_target):
        import migration_runner
        from utils.db_url import postgres_connect_args, sqlalchemy_url

        with app.app_context():
            ok, message, _ = switch(target)
        assert ok is True, message

        engine = create_engine(sqlalchemy_url(target), connect_args=postgres_connect_args(target))
        try:
            with engine.connect() as conn:
                registry = sorted(r[0] for r in conn.execute(text('SELECT name FROM _migrations')))
        finally:
            engine.dispose()
        assert registry == migration_runner._list_migration_names()

        monkeypatch.setattr(migration_runner, '_get_db_url', lambda: target)
        assert migration_runner.run_all_migrations() is True
        _boots(target, tmp_path)

    def test_without_data_to_sqlite(self, app, sqlite_target, tmp_path, monkeypatch):
        self._switch_then_start(app, sqlite_target, tmp_path, monkeypatch)

    @_needs_pg
    def test_without_data_to_postgresql(self, app, pg_target, tmp_path, monkeypatch):
        self._switch_then_start(app, pg_target, tmp_path, monkeypatch)

    def test_with_data_to_sqlite(self, app, a_3_0_source, sqlite_target, tmp_path, monkeypatch):
        self._switch_then_start(app, sqlite_target, tmp_path, monkeypatch, migration.migrate_data)

    @_needs_pg
    def test_with_data_to_postgresql(self, app, a_3_0_source, pg_target, tmp_path, monkeypatch):
        self._switch_then_start(app, pg_target, tmp_path, monkeypatch, migration.migrate_data)

    @_needs_pg
    def test_with_data_from_postgresql_to_sqlite(self, app, a_3_0_source, pg_target, sqlite_target,
                                                tmp_path, monkeypatch):
        try:
            _require_a_dumpable_bench()
            dumpable = True
        except pytest.skip.Exception:
            dumpable = False
        with app.app_context():
            ok, message, _ = migration.migrate_data(pg_target)
        assert ok is True, message

        def from_postgresql(target):
            if not dumpable:
                # A PostgreSQL source's dump only restores the source: the target's start never reads it
                monkeypatch.setattr(migration, 'create_source_snapshot', lambda: snapshot.SourceSnapshot(
                    path=tmp_path / 'stub.dump', backend='postgresql', size_bytes=0, sha256='0' * 64,
                    created_at='', verified='stubbed', method='stubbed'))
            pg_engine = create_engine(pg_target, pool_pre_ping=True)
            engines = db._app_engines[app]
            original, engines[None] = engines[None], pg_engine
            db.session.remove()
            try:
                return migration.migrate_data(target)
            finally:
                engines[None] = original
                db.session.remove()
                pg_engine.dispose()

        self._switch_then_start(app, sqlite_target, tmp_path, monkeypatch, from_postgresql)


class TestTheSourceKeepsBeingWrittenTo:
    def test_a_row_written_during_the_copy_is_wholly_in_or_wholly_out(
            self, app, create_ca, create_cert, sqlite_target, monkeypatch):
        """The copy used to read one table at a time from a live database, so
        a certificate issued between the read of its issuer and the read of
        the certificates table arrived on the target without its issuer.

        The write happens from this thread, between the view being fixed and
        the copy running, rather than from a real concurrent writer: what is
        being pinned is that the view precedes the write and covers both
        tables at once, which a second thread would only make harder to
        observe.
        """
        real_copy = migration.copy_tables
        written = {}

        def write_then_copy(source, target_engine, plan, **kwargs):
            if not written:
                ca = create_ca(cn='Written During The Copy CA')
                cert = create_cert(cn='written-during.example.com',
                                   ca_id=ca['id'])
                written.update(ca_refid=ca['refid'], cert_refid=cert['refid'])
            return real_copy(source, target_engine, plan, **kwargs)

        monkeypatch.setattr(migration, 'copy_tables', write_then_copy)

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is True, message
        assert written, 'the concurrent write never happened'

        engine = create_engine(sqlite_target)
        try:
            with engine.connect() as conn:
                has_ca = conn.execute(text(
                    'SELECT COUNT(*) FROM certificate_authorities '
                    'WHERE refid = :r'), {'r': written['ca_refid']}).scalar()
                has_cert = conn.execute(text(
                    'SELECT COUNT(*) FROM certificates WHERE refid = :r'),
                    {'r': written['cert_refid']}).scalar()
        finally:
            engine.dispose()

        # The view being copied was fixed before the write happened, so both
        # rows are outside it. What must never happen is one without the other.
        assert has_ca == has_cert == 0

        # And the operator is told, rather than left to discover it: the two
        # rows exist on the source and not on the target, which nothing else
        # in the pipeline can see (both counts agree about the image copied).
        assert stats['source_drift'], 'the drift must be measured'
        assert stats['source_drift'].get('certificates') == 1
        assert stats['source_drift'].get('certificate_authorities') == 1
        assert 'NOT on the target' in message


class TestEachStepIsActuallyWired:
    """A function that refuses correctly and is never called refuses nothing.
    These pin the call sites rather than the functions."""

    def test_a_schema_that_did_not_come_out_complete_stops_the_migration(
            self, app, sqlite_target, monkeypatch):
        """create_all reports nothing when it cannot create a table: an
        existing object of the same name, a revoked privilege. The copy would
        be the thing to find out, one table at a time, halfway through."""
        from models import db as _db

        real_create = migration._create_target_schema

        def create_then_lose_one(target_engine, target_is_pg):
            real_create(target_engine, target_is_pg)
            with target_engine.begin() as conn:
                conn.execute(text('DROP TABLE certificate_templates'))

        monkeypatch.setattr(
            migration, '_create_target_schema', create_then_lose_one)

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is False
        assert 'certificate_templates' in message
        assert 'incomplete after creation' in message
        assert stats['rows_migrated'] == 0

    def test_what_is_left_behind_reaches_the_statistics(
            self, app, sqlite_target, monkeypatch):
        """The count is computed, carried to the API and shown; a call site
        that dropped it would leave the operator with the sentence alone."""
        sentinel = {'group_members': {'created_at': {'reason': 'r', 'values': 7}}}
        monkeypatch.setattr(
            migration, 'dropped_columns', lambda source, target: sentinel)

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is True, message
        assert stats['dropped_columns'] == sentinel

    def test_the_target_carries_the_applied_migrations_ledger(
            self, app, sqlite_target):
        """`_migrations` is created by the migration runner, not by a model,
        so create_all knows nothing about it. A target without it re-runs
        every schema migration on first boot against data that has them."""
        with app.app_context():
            ok, message, _ = migration.migrate_data(sqlite_target)

        assert ok is True, message
        engine = create_engine(sqlite_target)
        try:
            assert '_migrations' in inspect(engine).get_table_names()
        finally:
            engine.dispose()

    def test_a_copy_that_fails_partway_leaves_the_target_empty(
            self, app, sqlite_target, monkeypatch):
        """One transaction for the whole copy: a target holding half a
        migration is a target someone has to reason about."""
        from services.database_admin import copy as copy_module

        real_copy_one = copy_module._copy_one
        seen = []

        def fail_on_certificates(source, dst, entry, **kwargs):
            seen.append(entry.name)
            if entry.name == 'certificates':
                raise RuntimeError('the disk went away')
            return real_copy_one(source, dst, entry, **kwargs)

        monkeypatch.setattr(copy_module, '_copy_one', fail_on_certificates)

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is False
        assert stats['refusal'] == 'copy'
        assert 'users' in seen, 'the test never reached a later table'

        engine = create_engine(sqlite_target)
        try:
            with engine.connect() as conn:
                assert conn.execute(
                    text('SELECT COUNT(*) FROM users')).scalar() == 0
        finally:
            engine.dispose()


class TestASourceThatBreaksItsOwnRules:
    def test_an_orphan_row_in_the_source_stops_the_migration(
            self, app, sqlite_target):
        """SQLite enforces no foreign key unless asked to, and UCM's
        connections never have, so an installation accumulates orphan rows
        for years. PostgreSQL does enforce them: copying those rows either
        produces a database that contradicts its own schema, or kills the
        migration halfway through on a driver error naming one row."""
        with app.app_context():
            db.session.execute(text(
                'INSERT INTO group_members (group_id, user_id, role) '
                'VALUES (987654, 987655, :role)'), {'role': 'member'})
            db.session.commit()
            try:
                ok, message, stats = migration.migrate_data(sqlite_target)
            finally:
                db.session.execute(text(
                    'DELETE FROM group_members WHERE group_id = 987654'))
                db.session.commit()

        assert ok is False
        assert stats['refusal'] == 'preflight'
        assert 'group_members' in message
        assert 'the current database' in message
        assert stats['snapshot'] is None, \
            'the refusal must come before an hour of dumping'


class TestATargetThatHoldsAnything:
    def _prepare(self, app, url, table, statement):
        engine = create_engine(url)
        try:
            with app.app_context():
                db.metadata.create_all(engine)
            with engine.begin() as conn:
                conn.execute(text(statement))
        finally:
            engine.dispose()

    def test_a_row_in_a_table_nobody_used_to_check_is_refused(
            self, app, sqlite_target):
        """The check counted users, certificates and a table called 'cas'
        which has not existed under that name for years."""
        self._prepare(
            app, sqlite_target, 'system_config',
            "INSERT INTO system_config (key, value) "
            "VALUES ('leftover', 'from another installation')")

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is False
        assert stats['refusal'] == 'preflight'
        assert 'system_config' in message
        assert stats['snapshot'] is None, 'nothing should have been snapshotted'

    def test_a_table_from_another_application_is_refused(
            self, app, sqlite_target):
        engine = create_engine(sqlite_target)
        try:
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE some_other_app (id INTEGER)'))
        finally:
            engine.dispose()

        with app.app_context():
            ok, message, stats = migration.migrate_data(sqlite_target)

        assert ok is False
        assert stats['refusal'] == 'preflight'
        assert 'some_other_app' in message


class TestNothingSwitchesUnlessEverythingPassed:
    def _post(self, auth_client, route, payload):
        return auth_client.post(f'/api/v2/database/{route}',
                                data=json.dumps(payload),
                                content_type='application/json')

    def test_a_snapshot_that_failed_forbids_the_switch(
            self, auth_client, sqlite_target, env_file, restart_signal,
            monkeypatch):
        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: None)
        before = env_file.read_text()

        response = self._post(auth_client, 'migrate',
                              {'database_url': sqlite_target})

        assert response.status_code == 409, response.data
        assert env_file.read_text() == before
        assert not restart_signal.exists()

    def test_a_verification_that_failed_forbids_the_switch(
            self, auth_client, sqlite_target, env_file, restart_signal,
            monkeypatch):
        def refuse(*args, **kwargs):
            raise VerificationError('users: 12 rows copied, 11 on the target')

        monkeypatch.setattr(migration, 'verify_migration', refuse)
        before = env_file.read_text()

        response = self._post(auth_client, 'migrate',
                              {'database_url': sqlite_target})

        assert response.status_code == 500, response.data
        assert '11 on the target' in json.loads(response.data)['message']
        assert env_file.read_text() == before
        assert not restart_signal.exists()

    def test_a_bootstrap_that_failed_forbids_the_switch(
            self, auth_client, sqlite_target, env_file, restart_signal,
            monkeypatch):
        import api.v2.database as route_module

        monkeypatch.setattr(
            route_module.svc, 'bootstrap_auth_to_target',
            lambda url: (False, 'group_members: no counterpart on the target',
                         {'refusal': 'preflight'}))
        before = env_file.read_text()

        response = self._post(auth_client, 'switch',
                              {'database_url': sqlite_target})

        assert response.status_code == 409, response.data
        assert env_file.read_text() == before
        assert not restart_signal.exists()

    @pytest.mark.parametrize('refusal,advice', [
        ('error', 'Retrying on the same target resumes the switch.'),
        ('copy', 'Retrying on the same target resumes the switch.'),
        ('verification', 'failed its verification; reset the target before retrying.'),
    ])
    def test_a_bootstrap_cut_short_says_how_to_retry(
            self, auth_client, sqlite_target, env_file, refusal, advice, monkeypatch):
        import api.v2.database as route_module

        monkeypatch.setattr(
            route_module.svc, 'bootstrap_auth_to_target',
            lambda url: (False, 'Bootstrap failed: stopped',
                         {'refusal': refusal, 'target_written': True}))

        response = self._post(auth_client, 'switch', {'database_url': sqlite_target})

        assert response.status_code == 500, response.data
        message = json.loads(response.data)['message']
        assert message.endswith(advice), message
        assert 'carries a schema' not in message

    def test_a_refused_plan_does_not_promise_a_resume(self, auth_client, sqlite_target, monkeypatch):
        """A table or column the plan refuses is refused again by a retry."""
        import api.v2.database as route_module

        monkeypatch.setattr(
            route_module.svc, 'bootstrap_auth_to_target',
            lambda url: (False, "Bootstrap failed: Column 'users.x' has no counterpart on the target",
                         {'refusal': 'preflight', 'target_written': True}))

        response = self._post(auth_client, 'switch', {'database_url': sqlite_target})

        message = json.loads(response.data)['message']
        assert message.endswith('has no counterpart on the target'), message

    def test_a_configuration_that_could_not_be_written_forbids_the_restart(
            self, auth_client, sqlite_target, restart_signal, monkeypatch):
        import api.v2.database as route_module

        called = []

        def refuse(url):
            called.append(url)
            return False, 'Permission denied writing the configuration', None

        monkeypatch.setattr(
            route_module.svc, 'persist_database_url_with_backup', refuse)

        response = self._post(auth_client, 'migrate',
                              {'database_url': sqlite_target})

        assert response.status_code == 500, response.data
        # Named, so the test cannot pass on any other 500: the data did
        # migrate, and it is the configuration write that stopped the switch.
        assert called == [sqlite_target], 'the configuration was never written'
        message = json.loads(response.data)['message']
        assert 'could not persist config' in message
        assert not restart_signal.exists()

    def test_a_restart_that_cannot_be_requested_puts_the_configuration_back(
            self, auth_client, sqlite_target, env_file, restart_signal,
            monkeypatch):
        """A configuration naming a backend the service was never restarted
        onto moves the instance hours later, with nobody watching."""
        import api.v2.database as route_module

        monkeypatch.setattr(
            route_module, 'restart_ucm_service',
            lambda: (False, 'the restart signal could not be written'))
        before = env_file.read_text()

        response = self._post(auth_client, 'migrate',
                              {'database_url': sqlite_target})

        assert response.status_code == 500, response.data
        assert 'put back' in json.loads(response.data)['message']
        assert env_file.read_text() == before
        assert 'DATABASE_URL' not in env_file.read_text()


class TestNothingElseSwitchesUntilTheRestart:
    """The lock is released when the request returns, but the restart it
    asked for happens afterwards: a watcher unit picks up a signal file. A
    second migration in that window would rewrite the configuration again and
    the service would come up on whichever one wrote last."""

    def _migrate(self, auth_client, target):
        return auth_client.post(
            '/api/v2/database/migrate',
            data=json.dumps({'database_url': target}),
            content_type='application/json')

    def test_a_switch_that_has_not_been_applied_refuses_the_next_one(
            self, auth_client, tmp_path, env_file, restart_signal):
        first = self._migrate(auth_client, f"sqlite:///{tmp_path / 'one.db'}")
        assert first.status_code == 200, first.data
        assert restart_signal.exists()
        assert switch_pending() is not None

        second = self._migrate(auth_client, f"sqlite:///{tmp_path / 'two.db'}")

        assert second.status_code == 409, second.data
        message = json.loads(second.data)['message']
        assert 'has not restarted yet' in message
        assert 'DATABASE_URL' in env_file.read_text()

    def test_the_marker_carries_no_password(
            self, auth_client, tmp_path, env_file, restart_signal, monkeypatch):
        import api.v2.database as route_module

        monkeypatch.setattr(route_module.svc, 'migrate_data',
                            lambda url: (True, 'ok', {'tables': {}}))
        target = 'postgresql://ucm:S3cret-For-Review@db.example:5432/ucm'
        assert self._migrate(auth_client, target).status_code == 200

        assert 'S3cret-For-Review' not in switch_pending_path().read_text()
        assert 'ucm' in switch_pending()['backend']

    def test_a_restore_is_refused_until_the_restart(
            self, auth_client, tmp_path, env_file, restart_signal):
        """Between the configuration being written and the service restarting
        onto it, this instance still runs on the backend being left behind:
        a restore landing here would be discarded by the restart."""
        import io

        assert self._migrate(
            auth_client, f"sqlite:///{tmp_path / 'one.db'}").status_code == 200

        response = auth_client.post(
            '/api/v2/system/restore',
            data={'password': 'Correct-Horse-Battery-9',
                  'file': (io.BytesIO(b'not read'), 'b.ucmbkp')},
            content_type='multipart/form-data')

        assert response.status_code == 409, response.data
        assert 'has not restarted yet' in json.loads(response.data)['message']

    def test_a_restart_clears_the_marker(self, auth_client, tmp_path,
                                         env_file, restart_signal):
        assert self._migrate(
            auth_client, f"sqlite:///{tmp_path / 'one.db'}").status_code == 200
        assert switch_pending() is not None

        clear_switch_pending()  # what app startup does

        assert switch_pending() is None


class TestTheProofIsReturnedEitherWay:
    def test_docker_gets_the_same_validation_as_the_native_path(
            self, auth_client, sqlite_target, monkeypatch):
        """The manual restart deserves the same evidence as the automatic
        one: under Docker the operator is the one taking the decision."""
        import api.v2.database as route_module

        monkeypatch.setattr(route_module, 'is_docker', lambda: True)

        response = auth_client.post(
            '/api/v2/database/migrate',
            data=json.dumps({'database_url': sqlite_target}),
            content_type='application/json')

        assert response.status_code == 200, response.data
        data = json.loads(response.data)['data']
        assert data['docker'] is True
        assert data['restart_initiated'] is False
        proof = data['proof']
        assert proof['snapshot']['sha256']
        assert proof['validation']
        assert proof['rows'] > 0


def _provision(url, registry, with_user=True):
    """A target that already holds the schema, an account unless told otherwise, and
    *registry* as its `_migrations` (None: no registry table at all)."""
    import migration_runner
    from utils.db_url import postgres_connect_args, sqlalchemy_url

    migration._force_register_all_models()
    is_pg = url.startswith('postgresql')
    engine = create_engine(sqlalchemy_url(url), connect_args=postgres_connect_args(url))
    try:
        db.metadata.create_all(engine)
        if with_user:
            with engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO users (username, email, password_hash, role, auth_source) "
                    "VALUES ('target_owner', 'owner@target', 'x', 'admin', 'local')"))
        if registry is not None:
            migration_runner._ensure_tracking_table(engine, is_pg)
            migration_runner._mark_applied(engine, sorted(registry), is_pg)
    finally:
        engine.dispose()


def _registry_of(url):
    """The target's registry, or None when it has no `_migrations` table."""
    from utils.db_url import postgres_connect_args, sqlalchemy_url
    engine = create_engine(sqlalchemy_url(url), connect_args=postgres_connect_args(url))
    try:
        if '_migrations' not in inspect(engine).get_table_names():
            return None
        with engine.connect() as conn:
            return sorted(r[0] for r in conn.execute(text('SELECT name FROM _migrations')))
    finally:
        engine.dispose()


def _starts(url, monkeypatch):
    import migration_runner
    monkeypatch.setattr(migration_runner, '_get_db_url', lambda: url)
    return migration_runner.run_all_migrations()


def _pivot_registry_but(missing):
    from migrations._from_2_254 import PIVOT_NAMES
    return set(PIVOT_NAMES) - {missing}


def _the_3_0_registry():
    import migration_runner
    return set(migration_runner._list_migration_names())


class TestASwitchNeverNamesATargetTheStartRefuses:
    """The switch reads the target's registry before ucm.env is written: a target the
    pivot would refuse at start is refused here, with the pivot's own message."""

    def _post_switch(self, auth_client, url):
        return auth_client.post('/api/v2/database/switch',
                                data=json.dumps({'database_url': url}),
                                content_type='application/json')

    def _refused(self, auth_client, url, env_file, restart_signal, monkeypatch, expected):
        before = env_file.read_text()
        registry = _registry_of(url)

        response = self._post_switch(auth_client, url)

        assert response.status_code == 409, response.data
        assert expected in json.loads(response.data)['message']
        assert env_file.read_text() == before
        assert not restart_signal.exists()
        assert switch_pending() is None
        assert _registry_of(url) == registry, 'the refused target was written to'

    @pytest.mark.parametrize('backend', ['sqlite', pytest.param('pg', marks=_needs_pg)])
    def test_accounts_without_a_registry(self, request, backend, auth_client, env_file,
                                         restart_signal, monkeypatch):
        url = request.getfixturevalue(f'{backend}_target')
        _provision(url, None)
        assert _starts(url, monkeypatch) is False
        self._refused(auth_client, url, env_file, restart_signal, monkeypatch,
                      'it has no migration registry')

    @pytest.mark.parametrize('backend', ['sqlite', pytest.param('pg', marks=_needs_pg)])
    def test_accounts_with_a_registry_short_of_2_254(self, request, backend, auth_client,
                                                     env_file, restart_signal, monkeypatch):
        url = request.getfixturevalue(f'{backend}_target')
        _provision(url, _pivot_registry_but('001_fix_dn_format'))
        assert _starts(url, monkeypatch) is False
        self._refused(auth_client, url, env_file, restart_signal, monkeypatch,
                      '001_fix_dn_format')

    @pytest.mark.parametrize('backend', ['sqlite', pytest.param('pg', marks=_needs_pg)])
    def test_a_2_254_database_without_accounts(self, request, backend, auth_client,
                                               env_file, restart_signal, monkeypatch):
        """Its upgrade has not run: recording a 3.0 registry over it would skip it."""
        url = request.getfixturevalue(f'{backend}_target')
        _provision(url, _pivot_registry_but(None), with_user=False)
        self._refused(auth_client, url, env_file, restart_signal, monkeypatch,
                      'without user accounts')

    @pytest.mark.parametrize('backend', ['sqlite', pytest.param('pg', marks=_needs_pg)])
    def test_a_3_0_database_with_accounts_is_taken_as_it_is(self, request, backend, app,
                                                            monkeypatch):
        url = request.getfixturevalue(f'{backend}_target')
        _provision(url, _the_3_0_registry())
        with app.app_context():
            ok, message, stats = migration.bootstrap_auth_to_target(url)
        assert ok is True, message
        assert 'skipped' in message
        assert stats['target_written'] is False
        assert _counts(url, ['users']) == {'users': 1}
        assert _starts(url, monkeypatch) is True


def _source_highest_ids(app):
    """{copied table: its highest id on the source}, for the tables that hold rows."""
    with app.app_context():
        with db.engine.connect() as conn:
            insp = inspect(conn)
            highest = {}
            for table in migration.BOOTSTRAP_AUTH_TABLES:
                if 'id' in {c['name'] for c in insp.get_columns(table)}:
                    top = conn.execute(text(f'SELECT MAX(id) FROM "{table}"')).scalar()
                    if top is not None:
                        highest[table] = top
    assert set(highest) - {'users'}, 'no copied table but users holds a row'
    return highest


def _assert_new_ids_above(url, highest, gone):
    """A new account takes an id above every one the source handed out, and on PostgreSQL
    every copied table's next id is above the source's highest."""
    assert _next_user_id(url) > max(gone, highest['users'])
    if not url.startswith('postgresql'):
        return
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            for table, top in highest.items():
                nxt = conn.execute(text("SELECT nextval(pg_get_serial_sequence(:t, 'id'))"),
                                   {'t': table}).scalar()
                assert nxt > top, f'{table}: next id {nxt}, source reached {top}'
    finally:
        engine.dispose()


def _cut_points():
    """Before and after every step the switch runs, and inside the two that write in bulk."""
    points = [(step.__name__, where) for step in migration._BOOTSTRAP_STEPS
              for where in ('before', 'after')]
    return points + [('_step_schema', 'during'), ('_step_schema', 'index'), ('_step_copy', 'during')]


@contextlib.contextmanager
def _cut(step_name, where):
    """One failure armed at that point of the attempt run inside; yields the list it fills."""
    from services.database_admin import copy as copy_module
    fired = []

    def stop():
        fired.append(f'{where} {step_name}')
        raise RuntimeError('the service stopped here')

    with pytest.MonkeyPatch.context() as patch:
        if where == 'during' and step_name == '_step_schema':
            created = []

            def on_create(table, connection, **kwargs):
                created.append(table.name)
                if len(created) == 3:      # some tables exist, the others do not
                    stop()
            event.listen(Table, 'after_create', on_create)
            try:
                yield fired
            finally:
                event.remove(Table, 'after_create', on_create)
            return
        if where == 'index':
            def on_execute(conn, cursor, statement, *rest):
                # SQLite commits each statement: the table is there, its index is not
                if not fired and statement.lstrip().startswith('CREATE UNIQUE INDEX'):
                    stop()
            event.listen(Engine, 'before_cursor_execute', on_execute)
            try:
                yield fired
            finally:
                event.remove(Engine, 'before_cursor_execute', on_execute)
            return
        if where == 'during':
            assert step_name == '_step_copy', step_name
            real_copy_one, calls = copy_module._copy_one, []

            def copy_one(*args, **kwargs):
                calls.append(real_copy_one(*args, **kwargs))
                if len(calls) == 2:        # the DEKs and the accounts are in, uncommitted
                    stop()
                return calls[-1]
            patch.setattr(copy_module, '_copy_one', copy_one)
        else:
            steps = list(migration._BOOTSTRAP_STEPS)
            index = [step.__name__ for step in steps].index(step_name)
            real = steps[index]

            def cut_step(run):
                if where == 'after':
                    real(run)
                stop()
            steps[index] = cut_step
            patch.setattr(migration, '_BOOTSTRAP_STEPS', tuple(steps))
        yield fired


def _missing_indexes(url):
    """The indexes the models declare that the target does not have."""
    from utils.db_url import postgres_connect_args, sqlalchemy_url
    engine = create_engine(sqlalchemy_url(url), connect_args=postgres_connect_args(url))
    try:
        inspector = inspect(engine)
        return sorted(index.name for table in db.metadata.sorted_tables for index in table.indexes
                      if index.name not in {i['name'] for i in inspector.get_indexes(table.name)})
    finally:
        engine.dispose()


def _usernames(url):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return sorted(r[0] for r in conn.execute(text('SELECT username FROM users')))
    finally:
        engine.dispose()


class TestASwitchCutShortCanBeResumed:
    """Every step of a switch without data is idempotent: cut short at any of them, the next
    attempt on the same target succeeds, and the target starts with counters past the source's."""

    @pytest.mark.parametrize('backend', ['sqlite', pytest.param('pg', marks=_needs_pg)])
    @pytest.mark.parametrize('step_name,where', _cut_points(),
                             ids=[f'{w}{s[5:]}' for s, w in _cut_points()])
    def test_a_cut_is_resumed(self, request, backend, step_name, where, app, auth_client,
                              create_user, tmp_path, monkeypatch):
        url = request.getfixturevalue(f'{backend}_target')
        gone = _deleted_last_user(app, auth_client, create_user)
        highest = _source_highest_ids(app)
        with app.app_context():
            source_names = sorted(r[0] for r in db.session.execute(text('SELECT username FROM users')))

        with app.app_context():
            with _cut(step_name, where) as fired:
                ok, _, _ = migration.bootstrap_auth_to_target(url)
            assert fired and ok is False
            ok, message, _ = migration.bootstrap_auth_to_target(url)
        assert ok is True, message

        assert _starts(url, monkeypatch) is True
        _boots(url, tmp_path)
        assert _usernames(url) == source_names
        assert _missing_indexes(url) == []
        _assert_new_ids_above(url, highest, gone)

    @_needs_pg
    def test_a_target_in_use_keeps_counters_above_its_data(self, app, pg_target, monkeypatch):
        """The replay on a target that already holds accounts never moves a counter down."""
        _provision(pg_target, _the_3_0_registry())
        engine = create_engine(pg_target)
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT setval(pg_get_serial_sequence('users', 'id'), 1000)"))
        finally:
            engine.dispose()
        with app.app_context():
            ok, message, _ = migration.bootstrap_auth_to_target(pg_target)
        assert ok is True and 'skipped' in message, message
        assert _next_user_id(pg_target) > 1000


    @pytest.mark.parametrize('backend', ['sqlite', pytest.param('pg', marks=_needs_pg)])
    def test_a_2_254_target_with_accounts_is_left_as_it_is(self, request, backend, app,
                                                            auth_client, create_user):
        """Not a copy of this switch, its upgrade has not run: registry and counters stay as they were."""
        from migrations._from_2_254 import PIVOT_NAMES
        url = request.getfixturevalue(f'{backend}_target')
        _provision(url, set(PIVOT_NAMES))
        before = _registry_of(url), _counters(url)
        assert _deleted_last_user(app, auth_client, create_user) > 1    # past the target's one account

        with app.app_context():
            ok, message, _ = migration.bootstrap_auth_to_target(url)

        assert ok is True and 'skipped' in message, message
        assert (_registry_of(url), _counters(url)) == before


def _counters(url):
    """What the target recorded as the last id each table handed out."""
    from utils.db_url import postgres_connect_args, sqlalchemy_url
    engine = create_engine(sqlalchemy_url(url), connect_args=postgres_connect_args(url))
    try:
        with engine.connect() as conn:
            if url.startswith('postgresql'):
                return conn.execute(text(
                    "SELECT sequencename, last_value FROM pg_sequences "
                    "WHERE schemaname = current_schema() ORDER BY 1")).fetchall()
            return conn.execute(text("SELECT name, seq FROM sqlite_sequence ORDER BY 1")).fetchall()
    finally:
        engine.dispose()


class TestARevertNeverNamesAFileTheStartRefuses:
    """Back to SQLite means the file at DATABASE_PATH, possibly left by an older release."""

    def _post_revert(self, auth_client):
        return auth_client.post('/api/v2/database/switch', data=json.dumps({}),
                                content_type='application/json')

    def test_a_file_older_than_2_254_is_refused(self, auth_client, tmp_path, env_file,
                                                restart_signal, monkeypatch):
        from config.settings import Config
        path = tmp_path / 'ucm.db'
        _provision(f'sqlite:///{path}', None)
        monkeypatch.setattr(Config, 'DATABASE_PATH', path)
        before = env_file.read_text()

        response = self._post_revert(auth_client)

        assert response.status_code == 409, response.data
        assert 'it has no migration registry' in json.loads(response.data)['message']
        assert env_file.read_text() == before
        assert not restart_signal.exists()

    def test_a_3_0_file_is_accepted(self, auth_client, tmp_path, env_file, restart_signal,
                                    monkeypatch):
        from config.settings import Config
        path = tmp_path / 'ucm.db'
        _provision(f'sqlite:///{path}', _the_3_0_registry())
        monkeypatch.setattr(Config, 'DATABASE_PATH', path)

        response = self._post_revert(auth_client)

        assert response.status_code == 200, response.data
        assert restart_signal.exists()

    def test_no_file_yet_is_accepted_and_not_created(self, auth_client, tmp_path, env_file,
                                                     restart_signal, monkeypatch):
        from config.settings import Config
        path = tmp_path / 'ucm.db'
        monkeypatch.setattr(Config, 'DATABASE_PATH', path)

        assert self._post_revert(auth_client).status_code == 200
        assert not path.exists()
