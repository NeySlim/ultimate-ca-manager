"""The copy a start takes of a 2.254 SQLite database before migration 300: consistent,
verified before the first step, the condition of the upgrade, single, private, absent on
PostgreSQL, and announced by dry-run and status. The PostgreSQL half needs UCM_TEST_PG_URL."""
import fnmatch
import hashlib
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import pre_upgrade_copy
from tests.test_upgrade_from_2_254 import _untouched, populate
from tests.upgrade_2254_support import make_base, schema_2254

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def base(tmp_path, monkeypatch):
    yield from make_base('sqlite', tmp_path, monkeypatch, 'cp')


def _copy(db):
    return pre_upgrade_copy.copy_path(db.sqlite_path)


def _leftovers(db):
    """Every file next to the database but the database itself."""
    name = Path(db.sqlite_path).name
    return sorted(p.name for p in Path(db.sqlite_path).parent.iterdir() if p.name != name)


def _counts(path):
    conn = sqlite3.connect(path)
    try:
        return pre_upgrade_copy._counts(conn)
    finally:
        conn.close()


def _is_2254(path):
    """Opens, passes the integrity check, and holds a registry the pivot accepts as 2.254."""
    import migration_runner
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        names = pre_upgrade_copy._registry(conn)
        return (pre_upgrade_copy._integrity(conn) == 'ok' and migration_runner.UPGRADE_MIGRATION not in names
                and migration_runner.pivot_refusal('tracked', names) is None)
    finally:
        conn.close()


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _broken_step(monkeypatch, name='143_cluster_commands'):
    import migrations._from_2_254 as package
    real = package.step

    class _Broken:
        @staticmethod
        def upgrade(conn):
            raise RuntimeError('step cut short')
    monkeypatch.setattr(package, 'step', lambda n: _Broken if n == name else real(n))
    return lambda: monkeypatch.setattr(package, 'step', real)


# --- 1. Consistent ----------------------------------------------------------------------------

def test_the_copy_holds_what_the_wal_holds_and_matches_the_source(base):
    """Rows still in the WAL, never checkpointed into the file, are in the copy."""
    populate(base)
    base.engine.dispose()
    writer = sqlite3.connect(base.sqlite_path)
    writer.execute('PRAGMA journal_mode=WAL')
    writer.execute('PRAGMA wal_autocheckpoint=0')
    writer.execute("INSERT INTO system_config (key, value) VALUES ('in_the_wal', 'yes')")
    writer.commit()
    expected = _counts(base.sqlite_path)
    try:
        assert base.upgrade()
    finally:
        writer.close()
    copy = _copy(base)
    assert _is_2254(copy)
    assert _counts(copy) == expected
    conn = sqlite3.connect(copy)
    assert conn.execute("SELECT value FROM system_config WHERE key = 'in_the_wal'").fetchall() == [('yes',)]
    conn.close()


def _diverging_copy(monkeypatch, sql):
    """The partial copy altered between the backup and its verification."""
    real = pre_upgrade_copy._verify

    def verify(path, counts, registry):
        conn = sqlite3.connect(path)
        conn.execute(sql)
        conn.commit()
        conn.close()
        return real(path, counts, registry)
    monkeypatch.setattr(pre_upgrade_copy, '_verify', verify)


@pytest.mark.parametrize('sql, reason', [
    ("INSERT INTO _migrations (name) VALUES ('137_not_from_this_database')",
     'the copy does not hold the 2.254 migration registry'),
    ("DELETE FROM audit_logs", 'the copy does not hold the same rows as the database'),
], ids=['registry', 'rows'])
def test_a_copy_that_differs_from_the_database_stops_the_upgrade(sql, reason, base, monkeypatch, capsys):
    populate(base)
    _diverging_copy(monkeypatch, sql)
    before = _untouched(base)
    assert base.upgrade() is False
    assert _untouched(base) == before
    assert _leftovers(base) == []
    out = capsys.readouterr().out
    assert 'Upgrade not started' in out and reason in out, out


# --- 2. Before any write of the upgrade, after the pivot guard ---------------------------------

def test_the_copy_is_verified_before_the_first_step_runs(base, monkeypatch):
    import migrations._from_2_254 as package
    from migrations._from_2_254 import STEPS
    populate(base)
    expected = _counts(base.sqlite_path)
    real, seen = package.step, []

    def step(name):
        if name == STEPS[0] and not seen:
            seen.append((_copy(base).exists() and _is_2254(_copy(base)), _counts(_copy(base))))
        return real(name)
    monkeypatch.setattr(package, 'step', step)
    assert base.upgrade()
    assert seen == [(True, expected)]


REFUSED = {
    '2.253': lambda sql: sql.replace("INSERT INTO _migrations (name) VALUES ('136_lifted_hold_leftovers');\n", ''),
    'unknown': lambda sql: sql + "INSERT INTO _migrations (name) VALUES ('301_from_a_later_release');\n",
    'legacy': lambda sql: '\n'.join(line for line in sql.splitlines() if '_migrations' not in line),
}


@pytest.mark.parametrize('kind', sorted(REFUSED))
def test_a_refused_database_is_not_copied(kind, tmp_path, monkeypatch):
    """Not even attempted: the guard answers first."""
    calls = []
    monkeypatch.setattr(pre_upgrade_copy, 'take', lambda path: calls.append(path))
    for db in make_base('sqlite', tmp_path, monkeypatch, 'rf', sql=REFUSED[kind](schema_2254('sqlite'))):
        assert db.upgrade() is False
        assert _leftovers(db) == [] and calls == []


# --- 3. No upgrade without a copy -------------------------------------------------------------

def _no_space(monkeypatch, db):
    import shutil
    monkeypatch.setattr(pre_upgrade_copy.shutil, 'disk_usage',
                        lambda p: shutil._ntuple_diskusage(10 ** 9, 10 ** 9 - 1000, 1000))
    return '0.0 MB available'


def _occupied(monkeypatch, db):
    partial = Path(str(_copy(db)) + pre_upgrade_copy.PARTIAL_SUFFIX)
    partial.mkdir()
    (partial / 'in-the-way').write_text('x')
    return 'Is a directory'


def _corrupt(monkeypatch, db):
    monkeypatch.setattr(pre_upgrade_copy, '_integrity', lambda conn: 'page 3: btree corrupted')
    return 'integrity check of the copy: page 3: btree corrupted'


@pytest.mark.parametrize('failure', [_no_space, _occupied, _corrupt], ids=['no-space', 'denied', 'corrupt'])
def test_no_copy_means_no_upgrade_and_a_database_left_as_it_was(failure, base, monkeypatch, capsys):
    populate(base)
    reason = failure(monkeypatch, base)
    before = _untouched(base)
    assert base.upgrade() is False
    assert _untouched(base) == before
    assert not _copy(base).exists()
    out = capsys.readouterr().out
    assert 'Upgrade not started: the copy of the 2.254 database could not be taken' in out, out
    assert reason in out
    assert f'MB free in {Path(base.sqlite_path).resolve().parent}' in out
    assert 'Nothing was changed' in out


# --- 4. Never truncated, never multiplied -----------------------------------------------------

def _schema(path):
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        return pre_upgrade_copy._schema(conn)
    finally:
        conn.close()


def _roll_back(db):
    """The documented rollback: the copy put back in place of the database."""
    db.engine.dispose()
    for leftover in (f'{db.sqlite_path}-wal', f'{db.sqlite_path}-shm'):
        Path(leftover).unlink(missing_ok=True)
    Path(db.sqlite_path).write_bytes(_copy(db).read_bytes())


def test_a_retry_after_a_rollback_replaces_the_previous_copy(base, monkeypatch):
    """A start that failed after its copy, the copy put back, 2.254 ran again: the next start copies anew."""
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    first = _sha(_copy(base))
    _roll_back(base)
    base.run("INSERT INTO system_config (key, value) VALUES ('written_by_2254_meanwhile', '1')")
    restore()
    assert base.upgrade()
    assert _sha(_copy(base)) != first
    conn = sqlite3.connect(_copy(base))
    assert conn.execute("SELECT 1 FROM system_config WHERE key = 'written_by_2254_meanwhile'").fetchall() == [(1,)]
    conn.close()
    assert _leftovers(base) == [_copy(base).name]


def test_a_restart_loop_after_a_partial_upgrade_keeps_the_pristine_copy(base, monkeypatch):
    """Steps commit one by one: the next start finds a half-upgraded database, its copy stays 2.254."""
    populate(base)
    pristine = _schema(base.sqlite_path)
    _broken_step(monkeypatch, '150_users_id_never_reused')
    assert base.upgrade() is False
    assert _schema(base.sqlite_path) != pristine
    kept = _sha(_copy(base))
    assert base.upgrade() is False
    assert _schema(_copy(base)) == pristine
    assert _sha(_copy(base)) == kept
    assert _leftovers(base) == [_copy(base).name]


def test_a_partial_copy_left_by_a_killed_start_is_replaced(base):
    partial = Path(str(_copy(base)) + pre_upgrade_copy.PARTIAL_SUFFIX)
    partial.write_bytes(b'cut short')
    assert base.upgrade()
    assert _leftovers(base) == [_copy(base).name]
    assert _is_2254(_copy(base))


def test_a_valid_copy_is_never_replaced_by_one_that_fails_verification(base, monkeypatch):
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    restore()
    _roll_back(base)
    kept = _sha(_copy(base))
    _corrupt(monkeypatch, base)
    assert base.upgrade() is False
    assert _sha(_copy(base)) == kept
    assert _leftovers(base) == [_copy(base).name]


# --- 5. Once ----------------------------------------------------------------------------------

def test_a_fresh_install_is_not_copied(tmp_path, monkeypatch):
    for db in make_base('sqlite', tmp_path, monkeypatch, 'fi', sql=''):
        assert db.upgrade()
        assert _leftovers(db) == []


def test_a_3_0_database_is_not_copied(base):
    assert base.upgrade()
    _copy(base).unlink()
    assert base.upgrade()
    assert _leftovers(base) == []


def test_the_step_144_replay_is_not_copied(base):
    populate(base)
    assert base.upgrade()
    assert base.run("SELECT key FROM system_config WHERE key = 'serial_unique_index_pending'") != []
    _copy(base).unlink()
    base.run("DELETE FROM certificates WHERE id = 3")
    assert base.upgrade()
    assert base.run("SELECT key FROM system_config WHERE key = 'serial_unique_index_pending'") == []
    assert _leftovers(base) == []


# --- 6. Private and out of reach --------------------------------------------------------------

def test_the_copy_is_private_whatever_the_umask(base):
    old = os.umask(0)
    try:
        assert base.upgrade()
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(_copy(base)).st_mode) == 0o600


@pytest.mark.skipif(not hasattr(os, 'geteuid') or os.geteuid() != 0, reason='chown needs root')
def test_the_copy_belongs_to_the_owner_of_the_database(base):
    os.chown(base.sqlite_path, 4242, 4243)
    assert base.upgrade()
    st = os.stat(_copy(base))
    assert (st.st_uid, st.st_gid) == (4242, 4243)


def test_the_copy_is_no_archive_and_no_retention_matches_it(base):
    from services.backup.schedule import _BACKUP_GLOB
    from services.backup.storage import is_archive_name
    assert base.upgrade()
    name = _copy(base).name
    assert name == 'cp.db.2.254-before-3.0'
    assert _copy(base).parent == Path(base.sqlite_path).resolve().parent
    assert not is_archive_name(name)
    # The application's archive retention, and the Docker entrypoint's sweep of its own copies
    assert not fnmatch.fnmatch(name, _BACKUP_GLOB)
    assert not fnmatch.fnmatch(name, 'ucm-backup-*.db')


# --- 7. PostgreSQL ----------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgresql_takes_no_copy_and_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'never.db'))
    for db in make_base('postgresql', tmp_path, monkeypatch, 'pgc'):
        before = sorted(p.name for p in tmp_path.iterdir())
        assert db.upgrade()
        out = capsys.readouterr().out
        assert pre_upgrade_copy.PG_NOTE in out
        assert sorted(p.name for p in tmp_path.iterdir()) == before
        # The second node of a cluster finds 300 applied: no note, nothing to copy
        assert db.upgrade()
        assert pre_upgrade_copy.PG_NOTE not in capsys.readouterr().out


@pytest.mark.postgres
def test_postgresql_dry_run_and_status_say_no_copy_is_taken(tmp_path, monkeypatch, capsys):
    for db in make_base('postgresql', tmp_path, monkeypatch, 'pgs'):
        runner = db._route()
        assert runner.run_all_migrations(dry_run=True)
        runner.show_status()
        assert capsys.readouterr().out.count('no automatic copy is taken') == 2
        assert '300_upgrade_from_2_254' not in db.registry()


# --- 8. Faithful simulation -------------------------------------------------------------------

def test_dry_run_and_status_tell_where_the_copy_goes_without_taking_it(base, capsys):
    populate(base)
    runner = base._route()
    before = _untouched(base)
    assert runner.run_all_migrations(dry_run=True) is True
    runner.show_status()
    out = capsys.readouterr().out
    assert _untouched(base) == before
    assert _leftovers(base) == []
    assert out.count(f'a copy of the 2.254 database is taken first: {_copy(base).resolve()}') == 2, out


def test_status_of_a_3_0_database_announces_no_copy(base, capsys):
    assert base.upgrade()
    capsys.readouterr()
    base._route().show_status()
    assert 'copy' not in capsys.readouterr().out.lower()


# --- End to end -------------------------------------------------------------------------------

CHILD = textwrap.dedent('''
    import os
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    from pathlib import Path
    from security import encryption
    encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
    encryption.key_encryption.reload()
    from config import settings
    settings.TestingConfig.SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.environ['DATABASE_PATH']
    from app import create_app
    create_app('testing')
    print('BOOTED', flush=True)
''')


def test_a_real_start_copies_upgrades_and_the_copy_puts_2254_back(tmp_path):
    from cryptography.fernet import Fernet
    import migration_runner
    data = tmp_path / 'data'
    (data / 'etc').mkdir(parents=True)
    db_path = data / 'ucm.db'
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_2254('sqlite'))
    conn.close()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('UCM_HA', 'UCM_NODE', 'HTTPS_'))}
    env.update(DATA_DIR=str(data), UCM_CONFIG_DIR=str(data / 'etc'), DATABASE_PATH=str(db_path),
               DATABASE_URL='', SECRET_KEY='upgrade-copy-test', UCM_SKIP_SECRET_VALIDATION='1',
               KEY_ENCRYPTION_KEY=Fernet.generate_key().decode(), CSRF_DISABLED='true',
               PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, '-c', CHILD], cwd=BACKEND, env=env, capture_output=True,
                          text=True, timeout=240)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0 and 'BOOTED' in out, out[-4000:]
    copy = pre_upgrade_copy.copy_path(db_path)
    assert _is_2254(copy)
    conn = sqlite3.connect(db_path)
    assert migration_runner.UPGRADE_MIGRATION in pre_upgrade_copy._registry(conn)
    conn.close()
    # The documented rollback: the service stopped, the copy put back in place of the database
    for leftover in (db_path, Path(f'{db_path}-wal'), Path(f'{db_path}-shm')):
        leftover.unlink(missing_ok=True)
    os.replace(copy, db_path)
    conn = sqlite3.connect(db_path)
    names = pre_upgrade_copy._registry(conn)
    conn.close()
    assert migration_runner.UPGRADE_MIGRATION not in names
    assert migration_runner.pivot_refusal('tracked', names) is None
    assert names
