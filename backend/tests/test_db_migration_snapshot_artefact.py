"""The pre-migration snapshot: online SQLite backup, pg_dump environment,
naming, permissions, retention and redaction of what it reports."""
import os
import re
import sqlite3
import stat
import threading
import time

import pytest
from sqlalchemy.engine import make_url

from services.database_admin import helpers


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    directory = tmp_path / 'snapshots'
    monkeypatch.setattr(helpers, 'BACKUP_DIR', directory)
    return directory


def _sqlite_source(path, rows=200):
    conn = sqlite3.connect(str(path))
    conn.execute('CREATE TABLE items (id INTEGER PRIMARY KEY, payload TEXT)')
    conn.executemany('INSERT INTO items (payload) VALUES (?)',
                     [('x' * 2000,) for _ in range(rows)])
    conn.commit()
    conn.close()


@pytest.fixture
def sqlite_live(tmp_path, monkeypatch):
    path = tmp_path / 'live.db'
    _sqlite_source(path)
    monkeypatch.setattr(helpers, '_live_database_url',
                        lambda: make_url(f'sqlite:///{path}'))
    return path


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------

class TestSqliteSnapshot:
    def test_name_permissions_and_method(self, sqlite_live, snap_dir):
        details = {}
        path = helpers._backup_current_db([], details)

        assert re.fullmatch(r'ucm-sqlite-\d{8}_\d{6}-[0-9a-f]{32}\.db', path.name)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(snap_dir.stat().st_mode) == 0o700
        assert details['method'] == 'online backup of the database file'
        copy = sqlite3.connect(str(path))
        assert copy.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 200
        copy.close()

    def test_an_existing_directory_is_tightened_to_0700(self, sqlite_live, snap_dir):
        snap_dir.mkdir(mode=0o755)
        os.chmod(snap_dir, 0o755)
        assert helpers._backup_current_db() is not None
        assert stat.S_IMODE(snap_dir.stat().st_mode) == 0o700

    def test_concurrent_writes_leave_a_valid_database(
            self, sqlite_live, snap_dir, monkeypatch):
        monkeypatch.setattr(helpers, 'DB_MIGRATION_KEEP', 10)
        stop = threading.Event()
        written = []

        def writer():
            conn = sqlite3.connect(str(sqlite_live), timeout=10)
            while not stop.is_set():
                conn.execute('INSERT INTO items (payload) VALUES (?)', ('y' * 500,))
                conn.commit()
                written.append(1)
            conn.close()

        thread = threading.Thread(target=writer)
        thread.start()
        try:
            while not written:
                time.sleep(0.001)
            paths = [helpers._backup_current_db() for _ in range(3)]
        finally:
            stop.set()
            thread.join()

        for path in paths:
            copy = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
            assert copy.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            count = copy.execute('SELECT COUNT(*) FROM items').fetchone()[0]
            copy.close()
            assert 200 <= count <= 200 + len(written)

    def test_a_writer_holding_the_lock_ends_in_a_bounded_failure(
            self, sqlite_live, snap_dir, monkeypatch):
        monkeypatch.setattr(helpers, '_SQLITE_SNAPSHOT_TIMEOUT', 0.5)
        blocker = sqlite3.connect(str(sqlite_live), isolation_level=None)
        blocker.execute('BEGIN EXCLUSIVE')
        reasons, outcome = [], {}

        def run():
            outcome['path'] = helpers._backup_current_db(reasons)

        thread = threading.Thread(target=run, daemon=True)
        started = time.monotonic()
        thread.start()
        thread.join(10)
        finished = not thread.is_alive()
        blocker.execute('ROLLBACK')
        blocker.close()
        thread.join(5)

        assert finished, 'the snapshot waited on the writer without a bound'
        assert time.monotonic() - started < 10
        assert outcome['path'] is None
        assert reasons and 'backup failed' in reasons[-1]
        assert list(snap_dir.iterdir()) == []

    def test_a_failed_online_backup_leaves_nothing_and_never_copies_the_file(
            self, sqlite_live, snap_dir, monkeypatch):
        def half_then_fail(source, target):
            source.backup(target, pages=1, progress=lambda *a: (_ for _ in ()).throw(
                sqlite3.OperationalError('disk I/O error on /var/lib/ucm/live.db')))

        copies = []
        for name in ('copy', 'copy2', 'copyfile'):
            monkeypatch.setattr(helpers.shutil, name,
                                lambda *a, _n=name, **k: copies.append(_n))
        monkeypatch.setattr(helpers, '_sqlite_backup', half_then_fail)

        reasons = []
        assert helpers._backup_current_db(reasons) is None
        assert list(snap_dir.iterdir()) == []
        assert copies == []
        assert 'disk I/O error' in reasons[-1]
        assert '/var/lib/ucm' not in reasons[-1]

    def test_a_database_without_file_is_copied_from_the_live_connection(
            self, snap_dir, monkeypatch):
        memory = sqlite3.connect(':memory:')
        memory.execute('CREATE TABLE only_in_memory (v TEXT)')
        memory.execute("INSERT INTO only_in_memory VALUES ('kept')")
        memory.commit()

        class Raw:
            closed = False

            def close(self):
                self.closed = True

        raw = Raw()
        monkeypatch.setattr(helpers, '_live_database_url', lambda: make_url('sqlite://'))
        monkeypatch.setattr(helpers, '_live_sqlite_connection', lambda: (raw, memory))

        details = {}
        path = helpers._backup_current_db([], details)

        assert details['method'] == 'online backup from the live connection'
        copy = sqlite3.connect(str(path))
        assert copy.execute('SELECT v FROM only_in_memory').fetchall() == [('kept',)]
        copy.close()
        assert raw.closed
        memory.close()

    def test_the_backend_is_the_connected_one_not_the_configured_one(
            self, sqlite_live, snap_dir, monkeypatch):
        from config.settings import Config
        monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI',
                            'postgresql://u:p@elsewhere/db', raising=False)
        monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@elsewhere/db')
        path = helpers._backup_current_db()
        assert path.name.startswith('ucm-sqlite-')


# ---------------------------------------------------------------------------
# PostgreSQL: pg_dump's command line and environment
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_dump_capture(snap_dir, monkeypatch):
    for name in ('PGHOST', 'PGPORT', 'PGUSER', 'PGDATABASE', 'PGPASSWORD',
                 'PGSSLMODE', 'PGSERVICE', 'PGGSSENCMODE', 'UCM_FIPS'):
        monkeypatch.delenv(name, raising=False)
    seen = {}

    class Done:
        returncode = 0
        stderr = b''

    def run(cmd, env=None, **kwargs):
        seen['cmd'], seen['env'] = list(cmd), dict(env)
        target = next(a.split('=', 1)[1] for a in cmd if a.startswith('--file='))
        with open(target, 'wb') as handle:
            handle.write(b'PGDMP')
        return Done()

    monkeypatch.setattr(helpers.subprocess, 'run', run)

    def dump(url):
        monkeypatch.setattr(helpers, '_live_database_url', lambda: make_url(url))
        seen.clear()
        details = {}
        seen['path'] = helpers._backup_current_db([], details)
        seen['details'] = details
        return seen
    return dump


class TestPgDump:
    def test_credentials_travel_by_environment_only(self, pg_dump_capture):
        out = pg_dump_capture('postgresql://ucm:p%40ss@db.example:5433/ucmdb')

        env, cmd = out['env'], out['cmd']
        assert (env['PGHOST'], env['PGPORT'], env['PGUSER'], env['PGDATABASE'],
                env['PGPASSWORD']) == ('db.example', '5433', 'ucm', 'ucmdb', 'p@ss')
        joined = ' '.join(cmd)
        for value in ('p@ss', 'p%40ss', 'db.example', 'ucmdb'):
            assert value not in joined
        assert '--no-password' in cmd and cmd[cmd.index('-F') + 1] == 'c'
        assert out['details']['method'] == 'pg_dump, custom format'
        assert re.fullmatch(r'ucm-pg-\d{8}_\d{6}-[0-9a-f]{32}\.dump', out['path'].name)
        assert stat.S_IMODE(out['path'].stat().st_mode) == 0o600

    def test_settings_absent_from_the_url_are_not_inherited(
            self, pg_dump_capture, monkeypatch):
        for name, value in (('PGHOST', 'inherited'), ('PGPORT', '6543'),
                            ('PGUSER', 'root'), ('PGDATABASE', 'other'),
                            ('PGPASSWORD', 'inherited-secret')):
            monkeypatch.setenv(name, value)
        env = pg_dump_capture('postgresql:///ucm')['env']
        assert env['PGDATABASE'] == 'ucm'
        for name in ('PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD'):
            assert name not in env

    def test_service_transport_kept_unless_the_url_says_otherwise(
            self, pg_dump_capture, monkeypatch):
        monkeypatch.setenv('PGSSLMODE', 'verify-full')
        monkeypatch.setenv('PGSERVICE', 'elsewhere')
        env = pg_dump_capture('postgresql://u:p@h/db')['env']
        assert env['PGSSLMODE'] == 'verify-full'
        assert 'PGSERVICE' not in env
        env = pg_dump_capture('postgresql://u:p@h/db?sslmode=require')['env']
        assert env['PGSSLMODE'] == 'require'

    def test_fips_forces_gssapi_encryption_off(self, pg_dump_capture, monkeypatch):
        monkeypatch.setenv('UCM_FIPS', '1')
        env = pg_dump_capture('postgresql://u:p@h/db?gssencmode=prefer')['env']
        assert env['PGGSSENCMODE'] == 'disable'

    def test_url_libpq_options_reach_their_variables(self, pg_dump_capture):
        env = pg_dump_capture(
            'postgresql://u:p@h/db?sslrootcert=/r.pem&connect_timeout=7'
            '&application_name=ucm-dump&target_session_attrs=read-write')['env']
        assert (env['PGSSLROOTCERT'], env['PGCONNECT_TIMEOUT'], env['PGAPPNAME'],
                env['PGTARGETSESSIONATTRS']) == ('/r.pem', '7', 'ucm-dump', 'read-write')

    def test_a_failed_dump_leaves_no_partial_artefact(self, snap_dir, monkeypatch):
        class Failed:
            returncode = 1
            stderr = b'pg_dump: error: password authentication failed for postgresql://u:hunter2@h/db'

        def run(cmd, env=None, **kwargs):
            target = next(a.split('=', 1)[1] for a in cmd if a.startswith('--file='))
            with open(target, 'wb') as handle:
                handle.write(b'PGDMP partial')
            return Failed()

        monkeypatch.setattr(helpers.subprocess, 'run', run)
        monkeypatch.setattr(helpers, '_live_database_url',
                            lambda: make_url('postgresql://u:hunter2@h/db'))
        reasons = []
        assert helpers._backup_current_db(reasons) is None
        assert list(snap_dir.iterdir()) == []
        assert 'authentication failed' in reasons[-1]
        assert 'hunter2' not in reasons[-1]


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def _make_snapshots(directory, count):
    directory.mkdir(exist_ok=True)
    now = time.time()
    made = []
    for i in range(count):
        suffix = 'db' if i % 2 else 'dump'
        path = directory / f'ucm-{"sqlite" if i % 2 else "pg"}-2026010{i}_000000-{i:032x}.{suffix}'
        path.write_bytes(b'x')
        os.utime(path, (now - (count - i) * 60, now - (count - i) * 60))
        made.append(path)
    return made


class TestRetention:
    def test_eight_snapshots_cap_five(self, snap_dir):
        made = _make_snapshots(snap_dir, 8)
        (snap_dir / 'notes.txt').write_bytes(b'x')
        (snap_dir / 'other-1.db').write_bytes(b'x')

        assert helpers._prune_db_migration_snapshots(keep=5) == 3
        assert sorted(p.name for p in snap_dir.glob('ucm-*')) == sorted(p.name for p in made[3:])
        assert (snap_dir / 'notes.txt').exists() and (snap_dir / 'other-1.db').exists()

    def test_keep_zero_still_keeps_one(self, snap_dir):
        made = _make_snapshots(snap_dir, 4)
        assert helpers._prune_db_migration_snapshots(keep=0) == 3
        assert [p for p in made if p.exists()] == [made[-1]]

    def test_a_snapshot_prunes_beyond_the_cap(self, sqlite_live, snap_dir, monkeypatch):
        monkeypatch.setattr(helpers, 'DB_MIGRATION_KEEP', 2)
        old = _make_snapshots(snap_dir, 3)
        newest = helpers._backup_current_db()
        survivors = set(snap_dir.iterdir())
        assert survivors == {old[-1], newest}


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_short_err_hides_every_password_and_the_layout():
    msg = ('could not connect to postgresql://ucm:auth@pass@db:5432/ucm'
           '?sslpassword=keysecret&PassWord=other&sslmode=require: '
           'see /opt/ucm/data/backups/db_migration/ucm-pg-x.dump')
    out = helpers._short_err(msg)
    for secret in ('auth@pass', 'pass@db', 'keysecret', 'other', '/opt/ucm'):
        assert secret not in out
    assert 'ucm-pg-x.dump' in out and 'sslmode=require' in out


def test_short_err_redacts_before_truncating():
    msg = 'x' * 180 + ' postgresql://u:supersecretpassword@host/db'
    out = helpers._short_err(msg)
    assert 'supe' not in out
    assert out.endswith('...') and len(out) == 203
