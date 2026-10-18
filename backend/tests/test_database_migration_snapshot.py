"""A migration does not start without a rollback point it has read back.

``_backup_current_db()`` reports "the dump failed" and "there was nothing to
dump" the same way: it returns None. The migration stored that in its
statistics and carried on, so an installation could be copied onto another
backend, have its configuration rewritten and be restarted with no way back.
"""
import json
import os
import sqlite3
from pathlib import Path

import pytest

from services.database_admin import helpers, snapshot
from services.database_admin.snapshot import SnapshotError, create_source_snapshot


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
def snapshots_dir(tmp_path, monkeypatch):
    """Snapshots land in a directory of this test's own."""
    directory = tmp_path / 'db_migration'
    directory.mkdir()
    monkeypatch.setattr(helpers, 'BACKUP_DIR', directory)
    return directory


class TestASnapshotIsTakenAndRead:
    def test_the_source_is_snapshotted_and_verified(self, app, snapshots_dir):
        with app.app_context():
            result = create_source_snapshot()

        assert result.path.exists()
        assert result.backend == 'sqlite'
        assert result.size_bytes > 0
        assert len(result.sha256) == 64
        assert 'quick_check ok' in result.verified

    def test_the_snapshot_holds_the_tables_the_source_holds(self, app, snapshots_dir):
        with app.app_context():
            result = create_source_snapshot()

        copy = sqlite3.connect(f"file:{result.path}?mode=ro", uri=True)
        try:
            names = {
                row[0] for row in copy.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        finally:
            copy.close()

        assert 'users' in names and 'certificate_authorities' in names

    def test_the_proof_names_no_directory_and_is_serialisable(
            self, app, snapshots_dir):
        with app.app_context():
            proof = create_source_snapshot().as_proof()

        assert json.loads(json.dumps(proof)) == proof
        assert str(snapshots_dir) not in json.dumps(proof)
        assert set(proof) == {
            'name', 'backend', 'method', 'size_bytes', 'sha256', 'created_at',
            'verified'}
        # Never a raw file copy: on SQLite the migration reads this very
        # file, so torn pages would seed the target.
        assert proof['method'].startswith('online backup')

    def test_two_snapshots_never_claim_the_same_name(self, app, snapshots_dir):
        with app.app_context():
            first = create_source_snapshot()
            second = create_source_snapshot()

        assert first.path != second.path
        assert first.path.exists() and second.path.exists()

    def test_a_claimed_name_is_refused_rather_than_overwritten(
            self, snapshots_dir):
        """Exclusive creation is what makes the claim; a unique-looking name
        is only what makes the claim succeed."""
        free = snapshots_dir / 'ucm-sqlite-free.db'
        helpers._reserve(free)
        assert free.exists()
        assert oct(free.stat().st_mode)[-3:] == '600'

        with pytest.raises(FileExistsError):
            helpers._reserve(free)

    @pytest.mark.parametrize('backend_url', [
        None,  # the configured SQLite database
        'postgresql://ucm:pw@db.example:5432/ucm',
    ])
    def test_a_name_owned_by_another_migration_is_never_discarded(
            self, app, snapshots_dir, monkeypatch, backend_url):
        """The failure path used to unlink the name it had just failed to
        claim, which is the other migration's rollback point.

        Asserting on an unrelated file proves nothing, since the name being
        claimed is a UUID this test never sees: what is watched is that the
        removal is not called at all, on both backends, since each has its
        own handler for a name that is taken.
        """
        from sqlalchemy.engine import make_url

        if backend_url:
            monkeypatch.setattr(helpers, '_live_database_url',
                                lambda: make_url(backend_url))

        def already_claimed(path):
            raise FileExistsError(17, 'File exists', str(path))

        discarded = []
        monkeypatch.setattr(helpers, '_reserve', already_claimed)
        monkeypatch.setattr(helpers, '_discard', discarded.append)

        with app.app_context():
            assert helpers._backup_current_db() is None

        assert discarded == [], 'the claim of another migration was removed'


class TestTheSnapshotIsReadTheWayARollbackWould:
    def test_a_snapshot_with_torn_pages_is_refused(
            self, app, snapshots_dir, monkeypatch):
        """The failure quick_check exists for: a file that opens, lists its
        tables and is internally broken. A copy taken while the database was
        being written looks exactly like this, and on SQLite the migration
        reads the snapshot, so those pages would seed the target."""
        import sqlite3

        torn = snapshots_dir / 'ucm-sqlite-torn-pages.db'
        with app.app_context():
            from models import db as _db

            raw = _db.engine.raw_connection()
            try:
                source = getattr(raw, 'driver_connection', None) or raw.connection
                target = sqlite3.connect(str(torn))
                try:
                    source.backup(target)
                finally:
                    target.close()
            finally:
                raw.close()

        # Corrupt a page well past the header, so sqlite_master still reads.
        data = bytearray(torn.read_bytes())
        for offset in range(8192, min(len(data), 65536)):
            data[offset] ^= 0xFF
        torn.write_bytes(bytes(data))

        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: torn)

        with app.app_context():
            with pytest.raises(SnapshotError) as refused:
                create_source_snapshot()

        assert 'integrity' in str(refused.value) or 'read back' in str(refused.value)
        assert not torn.exists()

    def test_the_snapshot_is_opened_read_only(self, app, snapshots_dir):
        """The copy must not be able to write to the artefact it would be
        rolled back to, not even by accident."""
        from sqlalchemy import create_engine, text
        from services.database_admin.copy import consistent_source
        from services.database_admin.snapshot import read_only_uri

        with app.app_context():
            result = create_source_snapshot()

            assert 'mode=ro' in read_only_uri(result.path)
            with consistent_source(result) as (src, _view, _is_pg):
                with pytest.raises(Exception) as denied:
                    src.execute(text(
                        "INSERT INTO system_config (key, value) "
                        "VALUES ('written-through-the-snapshot', '1')"))

        assert 'readonly' in str(denied.value).lower()


class TestAFailedSnapshotStopsTheMigration:
    def test_a_snapshot_that_could_not_be_taken_is_a_refusal(
            self, app, monkeypatch):
        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: None)

        with app.app_context():
            with pytest.raises(SnapshotError) as refused:
                create_source_snapshot()

        assert 'not started' in str(refused.value)

    def test_an_empty_snapshot_is_a_refusal_and_is_removed(
            self, app, snapshots_dir, monkeypatch):
        empty = snapshots_dir / 'ucm-sqlite-empty.db'
        empty.touch()
        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: empty)

        with app.app_context():
            with pytest.raises(SnapshotError, match='empty'):
                create_source_snapshot()

        assert not empty.exists(), 'a useless artefact must not be kept'

    def test_a_truncated_snapshot_is_a_refusal_and_is_removed(
            self, app, snapshots_dir, monkeypatch):
        """A file that exists is not a snapshot: a copy cut short by a full
        disk looks fine from the outside, which is worse than none at all
        because an operator would trust it."""
        torn = snapshots_dir / 'ucm-sqlite-torn.db'
        torn.write_bytes(b'SQLite format 3\x00' + os.urandom(2048))
        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: torn)

        with app.app_context():
            with pytest.raises(SnapshotError):
                create_source_snapshot()

        assert not torn.exists()

    def test_a_snapshot_missing_a_table_is_a_refusal(
            self, app, snapshots_dir, monkeypatch):
        partial = snapshots_dir / 'ucm-sqlite-partial.db'
        conn = sqlite3.connect(str(partial))
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()
        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: partial)

        with app.app_context():
            with pytest.raises(SnapshotError, match='missing'):
                create_source_snapshot()

    def test_the_refusal_says_why_pg_dump_failed(
            self, app, snapshots_dir, monkeypatch):
        """An operator told only that the snapshot "could not be taken" has
        to go hunting through a log to learn that their pg_dump is older than
        the server it is dumping — a real refusal on a current PostgreSQL."""
        from sqlalchemy.engine import make_url

        monkeypatch.setattr(
            helpers, '_live_database_url',
            lambda: make_url(
                'postgresql://ucm:sup3r-s3cr3t@db.example:5432/ucm'))

        class Failed:
            returncode = 1
            stderr = (b'pg_dump: error: connection to server failed for '
                      b'postgresql://ucm:sup3r-s3cr3t@db.example:5432/ucm\n'
                      b'pg_dump: detail: server version: 18.3; '
                      b'pg_dump version: 17.10')

        monkeypatch.setattr(helpers.subprocess, 'run',
                            lambda *a, **k: Failed())

        with app.app_context():
            with pytest.raises(SnapshotError) as refused:
                create_source_snapshot()

        message = str(refused.value)
        assert 'pg_dump version: 17.10' in message
        # pg_dump quotes the URI it failed on, and this message travels to
        # the caller and into the audit log.
        assert 'sup3r-s3cr3t' not in message
        assert not list(snapshots_dir.iterdir()), 'no half-written dump is kept'

    def test_the_refusal_carries_no_credential(self, app, monkeypatch):
        monkeypatch.setattr(
            snapshot, '_backup_current_db',
            lambda reasons=None, details=None: (_ for _ in ()).throw(
                RuntimeError('pg_dump: postgresql://ucm:s3cr3t@db/ucm failed')))

        with app.app_context():
            with pytest.raises(SnapshotError) as refused:
                create_source_snapshot()

        assert 's3cr3t' not in str(refused.value)


class TestTheMigrationRefusesWithoutOne:
    def test_migrate_stops_before_touching_the_target(
            self, app, tmp_path, monkeypatch):
        from services.database_admin.migration import migrate_data

        monkeypatch.setattr(snapshot, '_backup_current_db',
                            lambda reasons=None, details=None: None)
        target = tmp_path / 'target.db'

        with app.app_context():
            ok, message, stats = migrate_data(f'sqlite:///{target}')

        assert ok is False
        assert stats['refusal'] == 'snapshot'
        assert stats['tables_migrated'] == 0
        assert not target.exists() or target.stat().st_size == 0


class TestTheDumpKeepsTheServiceTransport:
    """pg_dump must reach PostgreSQL the way the service does: the service's
    PGSSLMODE and PGGSSENCMODE survive, and FIPS mode keeps GSSAPI encryption off."""

    @pytest.fixture
    def dump_env(self, app, snapshots_dir, monkeypatch):
        from sqlalchemy.engine import make_url
        for name in ('PGSSLMODE', 'PGGSSENCMODE', 'PGSSLROOTCERT', 'UCM_FIPS'):
            monkeypatch.setenv(name, 'x')
            monkeypatch.delenv(name)
        seen = {}

        class Failed:
            returncode = 1
            stderr = b'pg_dump: error: stopped by the test'

        def run(cmd, env=None, **kwargs):
            seen.update(env)
            return Failed()
        monkeypatch.setattr(helpers.subprocess, 'run', run)

        def dump(url):
            monkeypatch.setattr(helpers, '_live_database_url', lambda: make_url(url))
            seen.clear()
            with app.app_context():
                with pytest.raises(SnapshotError):
                    create_source_snapshot()
            return seen
        return dump

    def test_the_service_sslmode_is_kept(self, dump_env, monkeypatch):
        monkeypatch.setenv('PGSSLMODE', 'require')
        assert dump_env('postgresql://ucm:pw@db.example/ucm')['PGSSLMODE'] == 'require'

    def test_the_url_sslmode_wins(self, dump_env, monkeypatch):
        monkeypatch.setenv('PGSSLMODE', 'require')
        env = dump_env('postgresql://ucm:pw@db.example/ucm?sslmode=verify-full')
        assert env['PGSSLMODE'] == 'verify-full'

    def test_the_service_gssencmode_is_kept(self, dump_env, monkeypatch):
        monkeypatch.setenv('PGGSSENCMODE', 'disable')
        assert dump_env('postgresql://ucm:pw@db.example/ucm')['PGGSSENCMODE'] == 'disable'

    @pytest.mark.parametrize('query', ['', '?gssencmode=prefer'])
    def test_fips_mode_turns_gssapi_encryption_off(self, dump_env, monkeypatch, query):
        monkeypatch.setenv('UCM_FIPS', '1')
        env = dump_env(f'postgresql://ucm:pw@db.example/ucm{query}')
        assert env['PGGSSENCMODE'] == 'disable'

    def test_standard_mode_adds_nothing(self, dump_env):
        env = dump_env('postgresql://ucm:pw@db.example/ucm')
        assert 'PGGSSENCMODE' not in env and 'PGSSLMODE' not in env

    def test_the_service_tls_files_are_kept(self, dump_env, monkeypatch):
        monkeypatch.setenv('PGSSLMODE', 'verify-full')
        monkeypatch.setenv('PGSSLROOTCERT', '/etc/ucm/pg-root.pem')
        env = dump_env('postgresql://ucm:pw@db.example/ucm')
        assert (env['PGSSLMODE'], env['PGSSLROOTCERT']) == ('verify-full', '/etc/ucm/pg-root.pem')

    def test_the_url_tls_files_win(self, dump_env, monkeypatch):
        monkeypatch.setenv('PGSSLROOTCERT', '/etc/ucm/pg-root.pem')
        env = dump_env('postgresql://ucm:pw@db.example/ucm?sslrootcert=/srv/other.pem')
        assert env['PGSSLROOTCERT'] == '/srv/other.pem'
