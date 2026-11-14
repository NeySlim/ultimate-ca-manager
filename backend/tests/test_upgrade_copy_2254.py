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


# --- 4. Never truncated, never multiplied: the decision table -------------------------------
# No marker: the database is 2.254, a fresh copy replaces any other. A marker: the upgrade
# started, a valid copy is kept, and a missing or invalid one is never made from the database.

def _marked(path):
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        return pre_upgrade_copy._started(conn)
    finally:
        conn.close()


def _roll_back(db):
    """The documented rollback: the copy put back in place of the database."""
    db.engine.dispose()
    for leftover in (f'{db.sqlite_path}-wal', f'{db.sqlite_path}-shm'):
        Path(leftover).unlink(missing_ok=True)
    Path(db.sqlite_path).write_bytes(_copy(db).read_bytes())


def _holds(path, key):
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        return conn.execute("SELECT 1 FROM system_config WHERE key = ?", (key,)).fetchall() == [(1,)]
    finally:
        conn.close()


def _written_by_2254(db, key):
    """2.254 started on this database: a setting written, then the ANALYZE that adds sqlite_stat1."""
    db.run(f"INSERT INTO system_config (key, value) VALUES ('{key}', '1')")
    db.run("ANALYZE")


def _break_index(path):
    """A copy that opens and keeps its 2.254 registry but fails the integrity check."""
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE t(a, b); CREATE INDEX t_a ON t(a); INSERT INTO t VALUES (1, 2), (3, 4);")
    conn.execute("PRAGMA writable_schema=ON")
    conn.execute("UPDATE sqlite_master SET sql = 'CREATE INDEX t_a ON t(b)' WHERE name = 't_a'")
    conn.commit()
    conn.close()


def _add_300(path):
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO _migrations (name) VALUES ('300_upgrade_from_2_254')")
    conn.commit()
    conn.close()


def test_the_marker_is_set_after_the_copy_and_before_the_first_step(base, monkeypatch):
    import migrations._from_2_254 as package
    from migrations._from_2_254 import STEPS
    real, seen = package.step, []

    def step(name):
        if name == STEPS[0] and not seen:
            seen.append((_marked(base.sqlite_path), _marked(_copy(base))))
        return real(name)
    monkeypatch.setattr(package, 'step', step)
    assert base.upgrade()
    assert seen == [(True, False)]


def test_a_successful_upgrade_removes_the_marker(base):
    assert base.upgrade()
    assert not _marked(base.sqlite_path)
    assert pre_upgrade_copy.MARKER_TABLE not in base.tables()


def test_the_marker_goes_with_the_registry_row_of_300(base, capsys):
    """Removed in the transaction that records 300: a start cut short there keeps it."""
    base.run("CREATE TRIGGER cut BEFORE INSERT ON _migrations WHEN NEW.name = '300_upgrade_from_2_254' "
             "BEGIN SELECT RAISE(ABORT, 'cut before the registry row'); END")
    assert base.upgrade() is False
    assert 'cut before the registry row' in capsys.readouterr().out
    assert _marked(base.sqlite_path)


# No marker, a copy already there -------------------------------------------------------------

def test_after_a_rollback_and_2254_running_again_the_copy_is_replaced(base, monkeypatch):
    """Failed at step 143, the copy put back, 2.254 wrote a row then ran ANALYZE: a new copy holds the row."""
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    first = _sha(_copy(base))
    _roll_back(base)
    assert not _marked(base.sqlite_path)
    _written_by_2254(base, 'written_by_2254_meanwhile')
    restore()
    assert base.upgrade()
    assert _sha(_copy(base)) != first
    assert _holds(_copy(base), 'written_by_2254_meanwhile')
    assert _leftovers(base) == [_copy(base).name]


@pytest.mark.parametrize('spoil', [_break_index, _add_300], ids=['integrity', 'registry'])
def test_without_a_marker_an_invalid_copy_is_replaced(spoil, base):
    _copy(base).write_bytes(Path(base.sqlite_path).read_bytes())
    spoil(_copy(base))
    assert base.upgrade()
    assert _is_2254(_copy(base))
    assert _leftovers(base) == [_copy(base).name]


def test_a_start_cut_between_the_copy_and_the_marker_copies_again(base, monkeypatch):
    """The database is still 2.254 then: the next start replaces the copy with an equal one."""
    populate(base)
    real = pre_upgrade_copy.mark_started
    monkeypatch.setattr(pre_upgrade_copy, 'mark_started', lambda path: (_ for _ in ()).throw(OSError('cut')))
    before = _untouched(base)
    assert base.upgrade() is False
    assert _untouched(base) == before
    monkeypatch.setattr(pre_upgrade_copy, 'mark_started', real)
    expected = _counts(base.sqlite_path)
    assert base.upgrade()
    assert _counts(_copy(base)) == expected


# A marker and a valid copy: kept -------------------------------------------------------------

def test_a_restart_loop_after_a_partial_upgrade_keeps_the_copy_and_says_so(base, monkeypatch, capsys):
    """Steps commit one by one: the next start finds a half-upgraded database, its copy stays."""
    populate(base)
    _broken_step(monkeypatch, '150_users_id_never_reused')
    assert base.upgrade() is False
    kept = _sha(_copy(base))
    capsys.readouterr()
    assert base.upgrade() is False
    out = capsys.readouterr().out
    assert f'kept the copy taken by an earlier start: {_copy(base).resolve()}' in out, out
    assert '✓ ' + str(_copy(base).resolve()) not in out
    assert _sha(_copy(base)) == kept
    assert _is_2254(_copy(base))
    assert _leftovers(base) == [_copy(base).name]


def test_2254_restarted_on_a_half_upgraded_database_keeps_the_original_copy(base, monkeypatch):
    """No rollback: the marker is still there, so the copy is kept, without what 2.254 wrote since."""
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    kept = _sha(_copy(base))
    _written_by_2254(base, 'written_on_a_half_upgraded_database')
    restore()
    assert base.upgrade()
    assert _sha(_copy(base)) == kept
    assert not _holds(_copy(base), 'written_on_a_half_upgraded_database')


def test_a_start_cut_between_the_marker_and_the_first_step_keeps_the_copy(base, monkeypatch):
    import migrations._from_2_254 as package
    from migrations._from_2_254 import STEPS
    populate(base)
    real = package.step

    def step(name):
        if name == STEPS[0]:
            raise RuntimeError('cut before the first statement')
        return real(name)
    monkeypatch.setattr(package, 'step', step)
    assert base.upgrade() is False
    kept = _sha(_copy(base))
    monkeypatch.setattr(package, 'step', real)
    assert base.upgrade()
    assert _sha(_copy(base)) == kept


# A marker and no valid copy: none is made from the database ----------------------------------

def _started_without_a_copy(base, monkeypatch, spoil):
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    restore()
    if spoil is None:
        _copy(base).unlink()
        return None
    spoil(_copy(base))
    return _sha(_copy(base))


@pytest.mark.parametrize('spoil', [None, _break_index, _add_300], ids=['missing', 'integrity', 'registry'])
def test_a_started_upgrade_without_a_valid_copy_resumes_without_copying(spoil, base, monkeypatch, capsys):
    left = _started_without_a_copy(base, monkeypatch, spoil)
    capsys.readouterr()
    assert base.upgrade()
    out = capsys.readouterr().out
    assert 'no copy of the 2.254 database exists' in out, out
    assert 'kept the copy' not in out
    if left is None:
        assert not _copy(base).exists()
        assert _leftovers(base) == []
    else:
        assert _sha(_copy(base)) == left
    assert _upgraded(base)


def _upgraded(db):
    import migration_runner
    return migration_runner.UPGRADE_MIGRATION in db.registry()


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


def _rolled_back(base, monkeypatch):
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    restore()
    _roll_back(base)


def _half_upgraded(base, monkeypatch):
    populate(base)
    restore = _broken_step(monkeypatch)
    assert base.upgrade() is False
    restore()


def _half_upgraded_without_copy(base, monkeypatch):
    _half_upgraded(base, monkeypatch)
    _copy(base).unlink()


@pytest.mark.parametrize('state, says', [
    (_rolled_back, 'a copy of the 2.254 database is taken first, replacing the one there: {copy}'),
    (_half_upgraded, 'the upgrade resumes with the copy taken by an earlier start: {copy}'),
    (_half_upgraded_without_copy, 'no copy of the 2.254 database exists'),
], ids=['replaced', 'kept', 'none'])
def test_dry_run_and_status_tell_which_case_applies_without_writing(state, says, base, monkeypatch, capsys):
    state(base, monkeypatch)
    base.engine.dispose()
    runner = base._route()
    copy = _copy(base)
    files = {p.name: _sha(p) for p in Path(base.sqlite_path).parent.iterdir() if p.is_file()}
    capsys.readouterr()
    assert runner.run_all_migrations(dry_run=True) is True
    runner.show_status()
    out = capsys.readouterr().out
    assert out.count(says.format(copy=copy.resolve())) == 2, out
    assert {p.name: _sha(p) for p in Path(base.sqlite_path).parent.iterdir() if p.is_file()} == files


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
