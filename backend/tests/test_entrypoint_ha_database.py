"""With UCM_HA the image entrypoint leaves SQLite alone: no DATABASE_PATH, no file copy."""
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'docker' / 'ha-database.sh'


def _run(body, env, cwd):
    script = f'. {HELPER}; {body}'
    return subprocess.run(['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
                          capture_output=True, text=True, cwd=cwd)


def _sqlite_env(tmp_path, ha):
    db = tmp_path / 'ucm.db'
    db.write_text('x')
    # never the image's default migrations directory, which on a host is an installation's
    env = {'UCM_DATABASE_PATH': str(db), 'UCM_BACKUP_ENABLED': 'true', 'UCM_BACKUP_RETENTION_DAYS': '30',
           'UCM_MIGRATIONS_DIR': str(tmp_path / 'no-migrations')}
    if ha is not None:
        env['UCM_HA'] = ha
    return env


@pytest.mark.parametrize('ha', ['1', 'true', ' YES '])
def test_ha_writes_no_database_path_neg(tmp_path, ha):
    r = _run('ucm_env_database_line; ucm_export_database_path; echo "[${DATABASE_PATH:-unset}]"',
             _sqlite_env(tmp_path, ha), tmp_path)
    assert 'DATABASE_PATH=' not in r.stdout and '[unset]' in r.stdout


@pytest.mark.parametrize('ha', [None, '0', 'false', ''])
def test_without_ha_the_sqlite_path_is_written_pos(tmp_path, ha):
    env = _sqlite_env(tmp_path, ha)
    r = _run('ucm_env_database_line; ucm_export_database_path; echo "[${DATABASE_PATH}]"', env, tmp_path)
    assert f"DATABASE_PATH={env['UCM_DATABASE_PATH']}" in r.stdout
    assert f"[{env['UCM_DATABASE_PATH']}]" in r.stdout


def test_ha_does_not_copy_the_sqlite_file_neg(tmp_path):
    # cp and find are stubbed: a regression must never touch a real backup directory
    r = _run('cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup',
             _sqlite_env(tmp_path, '1'), tmp_path)
    assert r.returncode == 0 and 'cp ' not in r.stdout


def test_without_ha_the_sqlite_file_is_still_copied_pos(tmp_path):
    # BACKUP_DIR is fixed in the function: stub cp and find to see the call
    env = _sqlite_env(tmp_path, None)
    r = _run('cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert 'cp ' + env['UCM_DATABASE_PATH'] in r.stdout


def test_ha_summary_names_postgresql_pos(tmp_path):
    r = _run('ucm_database_label', _sqlite_env(tmp_path, '1'), tmp_path)
    assert 'PostgreSQL' in r.stdout


def test_dockerfile_ships_the_helper_pos():
    assert 'docker/ha-database.sh /ha-database.sh' in (ROOT / 'Dockerfile').read_text()


@pytest.mark.parametrize('provided,expect', [
    ({}, 'docker exec <container> cat /opt/ucm/data/initial-admin-password'),
    ({'UCM_INITIAL_ADMIN_PASSWORD': 'Op-Chosen-1!'}, 'the one you provided (INITIAL_ADMIN_PASSWORD)'),
    ({'UCM_INITIAL_ADMIN_PASSWORD_FILE': '/run/secrets/a'}, 'the one you provided (INITIAL_ADMIN_PASSWORD_FILE)'),
])
def test_the_first_run_notice_never_shows_a_password(tmp_path, provided, expect):
    env = {'UCM_DATABASE_PATH': str(tmp_path / 'absent.db'), 'UCM_INITIAL_ADMIN_USERNAME': 'admin',
           'UCM_MIGRATIONS_DIR': str(tmp_path / 'no-migrations'), **provided}
    r = _run('ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode == 0 and expect in r.stdout, r.stdout
    assert 'changeme123' not in r.stdout and 'Op-Chosen-1!' not in r.stdout


def test_the_first_run_notice_says_both_sources_refuse_the_start(tmp_path):
    env = {'UCM_DATABASE_PATH': str(tmp_path / 'absent.db'), 'UCM_INITIAL_ADMIN_USERNAME': 'operator',
           'UCM_INITIAL_ADMIN_PASSWORD': 'Op-Chosen-1!', 'UCM_INITIAL_ADMIN_PASSWORD_FILE': '/run/secrets/a'}
    r = _run('ucm_initial_admin_notice', env, tmp_path)
    assert r.returncode == 0, r.stderr
    assert 'Username: operator' in r.stdout
    assert 'both set' in r.stdout and 'refused' in r.stdout
    assert 'the one you provided' not in r.stdout and 'Op-Chosen-1!' not in r.stdout


# -- a database the runner refuses stops the start before anything is written ---------

import sqlite3  # noqa: E402
import sys  # noqa: E402


def _registry(path, complete):
    sys.path.insert(0, str(ROOT / 'backend'))
    from migrations._from_2_254 import PIVOT_NAMES
    names = sorted(PIVOT_NAMES)
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    conn.executemany('INSERT INTO _migrations (name) VALUES (?)',
                     [(n,) for n in (names if complete else names[:-1])])
    conn.commit()
    conn.close()


def _start(tmp_path, db_state):
    """The entrypoint's database steps, in its order, with cp recording its calls."""
    db = tmp_path / 'ucm.db'
    if db_state != 'absent':
        _registry(db, db_state == '2.254')
    env = {'UCM_DATABASE_PATH': str(db), 'UCM_BACKUP_ENABLED': 'true', 'UCM_BACKUP_RETENTION_DAYS': '30',
           'UCM_BASE_PATH': str(ROOT), 'UCM_INITIAL_ADMIN_USERNAME': 'admin',
           'UCM_MIGRATIONS_DIR': str(ROOT / 'backend' / 'migrations'),
           'PATH': f'{pathlib.Path(sys.executable).parent}:/usr/bin:/bin'}
    script = (f'. {HELPER}; UCM_SQLITE_BACKUP_DIR={tmp_path}/backups; '
              'cp() { echo "cp $*"; }; find() { :; }; '
              'ucm_refuse_unstartable_database || exit $?; ucm_sqlite_check_and_backup')
    return subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True,
                          cwd=tmp_path, timeout=60)


def test_a_database_older_than_2_254_stops_the_start_before_its_copy(tmp_path):
    r = _start(tmp_path, '2.253')
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert 'cp ' not in r.stdout
    assert 'older than 2.254' in r.stdout and 'Nothing was written to the volume' in r.stdout


@pytest.mark.parametrize('db_state, copied', [('2.254', True), ('absent', False)])
def test_a_database_the_runner_starts_on_goes_on_as_before(tmp_path, db_state, copied):
    r = _start(tmp_path, db_state)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert ('cp ' in r.stdout) is copied


def _fingerprint(top):
    import hashlib
    return {str(p.relative_to(top)): (p.is_dir(), p.stat().st_mode, None if p.is_dir() else
                                       hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(top.rglob('*'))}


def _volume_start(tmp_path, where, db_state, database_path=None):
    """The entrypoint's steps from its refusal to the copy of the database, on a temporary
    volume: the data at its path, and a path from before 2.70 that still holds files;
    database_path: UCM_DATABASE_PATH, relative to the volume (default: in the data)."""
    volume = tmp_path / 'volume'
    data, old = volume / 'opt/ucm/data', volume / 'opt/ucm/backend/data'
    data.mkdir(parents=True)
    (old / 'ca').mkdir(parents=True)
    (old / 'ca' / 'root.pem').write_text('ca')
    _registry((data if where == 'current' else old) / 'ucm.db', db_state == '2.254')
    # Joined as text: pathlib would remove the ./ and // a spelling test needs
    db = f'{volume}/{database_path}' if database_path else data / 'ucm.db'
    env = {'UCM_DATABASE_PATH': str(db), 'UCM_BACKUP_ENABLED': 'true',
           'UCM_BACKUP_RETENTION_DAYS': '30', 'UCM_BASE_PATH': str(ROOT), 'DATA_PATH': str(data),
           'UCM_OLD_DATA_PATHS': f'{old} {volume}/app/backend/data', 'UCM_INITIAL_ADMIN_USERNAME': 'admin',
           'UCM_MIGRATIONS_DIR': str(ROOT / 'backend' / 'migrations'),
           'PATH': f'{pathlib.Path(sys.executable).parent}:/usr/bin:/bin'}
    # the image's backups directory is the data's; here it is the temporary volume's
    script = (f'. {HELPER}; UCM_SQLITE_BACKUP_DIR="$DATA_PATH/backups"; ucm_refuse_unstartable_database || exit $?; '
              'ucm_carry_old_data_paths; mkdir -p "$DATA_PATH/backups"; ucm_sqlite_check_and_backup')
    before = _fingerprint(volume)
    r = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True,
                       cwd=tmp_path, timeout=60)
    return r, before, _fingerprint(volume), data


@pytest.mark.parametrize('where', ['current', 'from before 2.70'])
def test_a_refused_database_at_either_path_leaves_the_whole_volume_unchanged(tmp_path, where):
    r, before, after, _data = _volume_start(tmp_path, where, '2.253')
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert 'older than 2.254' in r.stdout and 'Nothing was written to the volume' in r.stdout
    assert after == before


@pytest.mark.parametrize('where', ['current', 'from before 2.70'])
def test_a_2_254_database_at_either_path_is_carried_over_and_copied(tmp_path, where):
    r, _before, _after, data = _volume_start(tmp_path, where, '2.254')
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (data / 'ucm.db').is_file() and (data / 'ca' / 'root.pem').read_text() == 'ca'
    assert len(list((data / 'backups').glob('ucm-backup-*.db'))) == 1


@pytest.mark.parametrize('database_path, refused', [
    ('srv/pki.db', False), ('opt/ucm/data/./ucm.db', True), ('opt/ucm/data//ucm.db', True)])
def test_a_refused_database_at_the_old_path_counts_only_where_the_application_opens_it(
        tmp_path, database_path, refused):
    """UCM_DATABASE_PATH elsewhere: the old ucm.db is never opened, so never refused for;
    the same data path spelled otherwise still is."""
    r, before, after, _data = _volume_start(tmp_path, 'from before 2.70', '2.253', database_path)
    assert (r.returncode == 78) is refused, (r.stdout, r.stderr)
    assert ('older than 2.254' in r.stdout) is refused, r.stdout
    if refused:
        assert after == before


_STAT_ONE_DEVICE = 'stat() { if [ "$2" = %d ]; then echo 7; else command stat "$@"; fi; }; '


def _df(avail_kb):
    """df -Pk stubbed: one data line whose fourth column is the space available; one device."""
    return _STAT_ONE_DEVICE + f'df() {{ echo "Filesystem 1024-blocks Used Available Capacity Mounted"; echo "/dev/x 100 0 {avail_kb} 0% /"; }}; '


@pytest.mark.parametrize('backup,needed_kb', [('true', 2 * 3000), ('false', 3000)])
def test_the_start_is_refused_before_the_copy_when_the_disk_is_short(tmp_path, backup, needed_kb):
    env = _sqlite_env(tmp_path, None)
    env['UCM_BACKUP_ENABLED'] = backup
    (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    r = _run(_df(needed_kb - 1) + 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    out = r.stdout + r.stderr
    # needed rounded up, available down: never "needs 2 MB, 2 MB available"
    assert f'needs {-(-needed_kb // 1024)} MB free' in out and f'{(needed_kb - 1) // 1024} MB available' in out, out


@pytest.mark.parametrize('backup', ['true', 'false'])
def test_the_start_goes_on_when_the_disk_has_room(tmp_path, backup):
    env = _sqlite_env(tmp_path, None)
    env['UCM_BACKUP_ENABLED'] = backup
    (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    need = 6000 if backup == 'true' else 3000
    r = _run(_df(need) + 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ('cp ' in r.stdout) is (backup == 'true')


def test_a_df_that_cannot_answer_never_blocks_the_start(tmp_path):
    env = _sqlite_env(tmp_path, None)
    r = _run('df() { return 1; }; cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode == 0 and 'cp ' in r.stdout


MIGRATIONS = ROOT / 'backend' / 'migrations'
NAMES = sorted(f.stem for f in MIGRATIONS.glob('*.py') if not f.name.startswith('_'))


def _database(tmp_path, applied, pending_serial=False, kb=3000):
    """Real SQLite file of `kb` KB (zero padding past its pages) recording `applied`."""
    import sqlite3
    db = tmp_path / 'ucm.db'
    db.unlink(missing_ok=True)
    with sqlite3.connect(db) as c:
        c.execute('PRAGMA page_size = 1024')
        c.execute('CREATE TABLE _migrations (name TEXT PRIMARY KEY)')
        c.executemany('INSERT INTO _migrations VALUES (?)', [(n,) for n in applied])
        c.execute('CREATE TABLE system_config (key TEXT, value TEXT)')
        if pending_serial:
            c.execute("INSERT INTO system_config VALUES ('serial_unique_index_pending', '1')")
    c.close()
    import os
    os.truncate(db, kb * 1024)


def _env(tmp_path, backup):
    env = _sqlite_env(tmp_path, None)
    env.update(UCM_BACKUP_ENABLED=backup, UCM_MIGRATIONS_DIR=str(MIGRATIONS), UCM_VERSION='3.0')
    return env


_START = 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup'


@pytest.mark.parametrize('backup,avail_kb', [('false', 2900), ('false', 0), ('true', 3000)])
def test_an_ordinary_start_claims_only_the_copy(tmp_path, backup, avail_kb):
    env = _env(tmp_path, backup)
    _database(tmp_path, NAMES)
    r = _run(_df(avail_kb) + _START, env, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ('cp ' in r.stdout) is (backup == 'true')


def test_an_ordinary_start_still_needs_room_for_the_copy(tmp_path):
    env = _env(tmp_path, 'true')
    _database(tmp_path, NAMES)
    r = _run(_df(2999) + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'needs 3 MB free, 2 MB available' in r.stdout, r.stdout


def test_a_restored_database_claims_the_upgrade_room(tmp_path):
    # a 2.254 copy put back after a 3.0 start: its registry decides, not what started last
    env = _env(tmp_path, 'true')
    _database(tmp_path, NAMES)
    (tmp_path / '.ucm-started-version').write_text('3.0\n')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df(2 * 3000 - 1) + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'needs 6 MB free, 5 MB available' in r.stdout, r.stdout


def test_a_pending_serial_replay_claims_the_upgrade_room(tmp_path):
    env = _env(tmp_path, 'false')
    _database(tmp_path, NAMES, pending_serial=True)
    r = _run(_df(2999) + _START, env, tmp_path)
    assert r.returncode != 0 and 'needs 3 MB free' in r.stdout, r.stdout


@pytest.mark.parametrize('case', ['not a database', 'no registry', 'no migrations dir'])
def test_a_database_that_cannot_be_read_claims_the_upgrade_room(tmp_path, case):
    env = _env(tmp_path, 'false')
    _database(tmp_path, NAMES)
    if case == 'not a database':
        (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    elif case == 'no registry':
        import sqlite3
        with sqlite3.connect(tmp_path / 'ucm.db') as c:
            c.execute('DROP TABLE _migrations')
        c.close()
    else:
        env['UCM_MIGRATIONS_DIR'] = str(tmp_path / 'absent')
    r = _run(_df(2999) + _START, env, tmp_path)
    assert r.returncode != 0 and 'needs 3 MB free' in r.stdout, r.stdout


def test_the_check_leaves_the_database_unchanged(tmp_path):
    env = _env(tmp_path, 'false')
    _database(tmp_path, NAMES)
    before = (tmp_path / 'ucm.db').read_bytes()
    entries = sorted(p.name for p in tmp_path.iterdir())
    r = _run(_df(0) + _START, env, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / 'ucm.db').read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == entries


def _files(directory):
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in directory.iterdir()}


_HOT_JOURNAL = r'''
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1], isolation_level=None)
c.execute('PRAGMA cache_size = 1')
c.execute('BEGIN')
c.execute("UPDATE _migrations SET name = name || '-'")
c.execute("INSERT INTO system_config SELECT hex(randomblob(400)), '' FROM _migrations, _migrations AS b LIMIT 5000")
os._exit(0)  # killed mid-transaction: the journal stays hot
'''


@pytest.mark.parametrize('case', ['wal', 'wal after a crash', 'hot journal'])
def test_the_check_creates_and_changes_nothing(tmp_path, case):
    import sqlite3
    import sys
    env = _env(tmp_path, 'false')
    _database(tmp_path, NAMES)
    db = tmp_path / 'ucm.db'
    if case.startswith('wal'):
        c = sqlite3.connect(db)
        c.execute('PRAGMA journal_mode = WAL')
        if case == 'wal after a crash':
            subprocess.run([sys.executable, '-I', '-c', 'import os, sqlite3, sys\n'
                            'c = sqlite3.connect(sys.argv[1]); c.execute("PRAGMA wal_autocheckpoint = 0")\n'
                            'c.execute("INSERT INTO _migrations VALUES (\'x\')"); c.commit(); os._exit(0)', str(db)],
                           check=True)
        c.close()
        if case == 'wal after a crash':
            # the closing connection checkpointed: write again from a process that dies holding the log
            subprocess.run([sys.executable, '-I', '-c', 'import os, sqlite3, sys\n'
                            'c = sqlite3.connect(sys.argv[1]); c.execute("PRAGMA wal_autocheckpoint = 0")\n'
                            'c.execute("INSERT INTO _migrations VALUES (\'y\')"); c.commit(); os._exit(0)', str(db)],
                           check=True)
            assert (tmp_path / 'ucm.db-wal').exists()
    else:
        subprocess.run([sys.executable, '-I', '-c', _HOT_JOURNAL, str(db)], check=True)
        assert (tmp_path / 'ucm.db-journal').stat().st_size > 0
    before = _files(tmp_path)
    r = _run(_df(0) + _START, env, tmp_path)
    assert _files(tmp_path) == before
    # neither case can be read without writing: both count as an upgrade
    assert r.returncode != 0 and 'upgrading it needs' in r.stdout, r.stdout


@pytest.mark.parametrize('python3', [
    'hash -p /nonexistent/python3 python3',
    'python3() { echo "Traceback: boom" >&2; return 1; }',
])
def test_a_missing_or_failing_python_counts_as_an_upgrade_and_never_stops_the_start(tmp_path, python3):
    # as the entrypoint runs it: set -e and its ERR trap
    env = _env(tmp_path, 'true')
    _database(tmp_path, NAMES)
    head = f"set -e; trap 'echo TRAPPED; exit 1' ERR; . {HELPER}; {python3}; "
    for avail_kb, starts in ((2 * 3000, True), (3000, False)):
        r = subprocess.run(['bash', '-c', head + _df(avail_kb) + _START + '; echo REACHED'],
                           env={'PATH': '/usr/bin:/bin', **env}, capture_output=True, text=True, cwd=tmp_path)
        # the refusal itself stops the entrypoint through its trap, as intended
        assert ('TRAPPED' in r.stdout) is not starts, r.stdout
        assert ('REACHED' in r.stdout) is starts and ('cp ' in r.stdout) is starts, r.stdout
        assert starts or 'upgrading it needs' in r.stdout, r.stdout


def test_a_2_254_database_and_an_older_2x_database_count_as_an_upgrade(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / 'backend'))
    from migrations._from_2_254 import PIVOT_NAMES
    env = _env(tmp_path, 'false')
    for applied in (sorted(PIVOT_NAMES), sorted(n for n in PIVOT_NAMES if n < '120')):
        _database(tmp_path, applied)
        r = _run(_df(2999) + _START, env, tmp_path)
        assert r.returncode != 0 and 'upgrading it needs' in r.stdout, r.stdout


def test_a_database_lacking_one_migration_of_several_counts_as_an_upgrade(tmp_path):
    # a later release ships 300 and 301: a database that recorded only 300 still upgrades
    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    for name in ('300_upgrade_from_2_254', '301_later', '_helper'):
        (migrations / f'{name}.py').write_text('')
    env = _env(tmp_path, 'false')
    env['UCM_MIGRATIONS_DIR'] = str(migrations)
    _database(tmp_path, ['300_upgrade_from_2_254', '_helper'])
    assert 'upgrading it needs' in _run(_df(2999) + _START, env, tmp_path).stdout
    _database(tmp_path, ['300_upgrade_from_2_254', '301_later'])
    assert _run(_df(2999) + _START, env, tmp_path).returncode == 0


def _df_two(tmp_path, db_kb, copy_kb):
    """Two filesystems: the backups directory on its own, the database's directory on another."""
    backups = tmp_path / 'backups'
    return (f'UCM_SQLITE_BACKUP_DIR={backups}; '
            f'stat() {{ if [ "$2" = %d ]; then if [ "$3" = "{backups}" ]; then echo 2; else echo 1; fi; '
            f'else command stat "$@"; fi; }}; df() {{ echo "Filesystem 1024-blocks Used Available Capacity Mounted"; '
            f'if [ "$2" = "{backups}" ]; then echo "/dev/b 100 0 {copy_kb} 0% /b"; '
            f'else echo "/dev/a 100 0 {db_kb} 0% /a"; fi; }}; ')


@pytest.mark.parametrize('db_kb,copy_kb,refused_in', [
    (3000, 3000, None),           # each filesystem holds its part: no sum
    (2999, 9000, 'db'),           # the upgrade's room beside the database
    (9000, 2999, 'backups'),      # the copy's room in the backups directory
])
def test_the_copy_and_the_upgrade_are_measured_on_their_own_filesystems(tmp_path, db_kb, copy_kb, refused_in):
    env = _env(tmp_path, 'true')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df_two(tmp_path, db_kb, copy_kb) + _START, env, tmp_path)
    if refused_in is None:
        assert r.returncode == 0 and 'cp ' in r.stdout, r.stdout
        return
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    where = tmp_path / 'backups' if refused_in == 'backups' else tmp_path
    assert f'Not enough disk space in {where}: the start needs 3 MB free, 2 MB available' in r.stdout, r.stdout
    assert ('upgrading it needs' in r.stdout) is (refused_in == 'db'), r.stdout


def test_the_copy_lands_in_the_measured_backups_directory(tmp_path):
    env = _env(tmp_path, 'true')
    _database(tmp_path, NAMES)
    r = _run(_df_two(tmp_path, 0, 3000) + _START, env, tmp_path)
    assert r.returncode == 0 and f"cp {env['UCM_DATABASE_PATH']} {tmp_path / 'backups'}/ucm-backup-" in r.stdout, r.stdout


@pytest.mark.parametrize('url', ['postgresql://ucm@db/ucm', 'postgres://ucm@db/ucm', 'postgresql+psycopg2://ucm@db/ucm',
                                 'postgresql+psycopg://ucm@db/ucm'])
def test_a_database_url_leaves_the_sqlite_file_unchecked_and_uncopied(tmp_path, url):
    # the application opens DATABASE_URL whenever it is set, never DATABASE_PATH
    env = _env(tmp_path, 'true')
    env['DATABASE_URL'] = url
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df(0) + _START, env, tmp_path)
    assert r.returncode == 0 and 'cp ' not in r.stdout and 'Not enough' not in r.stdout, r.stdout
    assert 'DATABASE_URL' in r.stdout, r.stdout


@pytest.mark.parametrize('form', ['sqlite:///{p}', 'sqlite:////{p}', 'sqlite+pysqlite:///{p}',
                                  'sqlite:///file:{p}?uri=true', 'sqlite:////elsewhere/other.db',
                                  'sqlite:///relative/ucm.db', 'mysql://u@h/d'])
def test_any_other_database_url_still_checks_and_copies_the_sqlite_file(tmp_path, form):
    # only a PostgreSQL URL is certain to leave the file alone; no other URL is parsed
    env = _env(tmp_path, 'true')
    env['DATABASE_URL'] = form.format(p=env['UCM_DATABASE_PATH'])
    _database(tmp_path, NAMES)
    r = _run(_df(2999) + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout and 'Not enough' in r.stdout, r.stdout
    r = _run(_df(3000) + _START, env, tmp_path)
    assert r.returncode == 0 and 'cp ' in r.stdout and 'not used' not in r.stdout, r.stdout


def test_an_empty_database_url_still_checks_and_copies_the_sqlite_file(tmp_path):
    env = _env(tmp_path, 'true')
    env['DATABASE_URL'] = ''
    _database(tmp_path, NAMES)
    r = _run(_df(3000) + _START, env, tmp_path)
    assert r.returncode == 0 and 'cp ' in r.stdout, r.stdout


def _df_names(db_kb, copy_kb, db_dev, copy_dev, name_db='tmpfs', name_copy='tmpfs'):
    """Both directories named alike by df, whatever their device ids say."""
    backups = '/ucm-test-backups'
    return (f'UCM_SQLITE_BACKUP_DIR={backups}; '
            f'stat() {{ if [ "$2" = %d ]; then case "$3" in {backups}|/) echo {copy_dev};; *) echo {db_dev};; esac; '
            f'else command stat "$@"; fi; }}; df() {{ echo "Filesystem 1024-blocks Used Available Capacity Mounted"; '
            f'if [ "$2" = "{backups}" ]; then echo "{name_copy} 100 0 {copy_kb} 0% /b"; '
            f'else echo "{name_db} 100 0 {db_kb} 0% /a"; fi; }}; ')


def test_two_mounts_with_one_df_name_are_measured_apart(tmp_path):
    # two tmpfs both print "tmpfs": the backups' room must still be measured on its own
    env = _env(tmp_path, 'true')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df_names(90000, 100, 1, 2) + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'Not enough disk space in /ucm-test-backups' in r.stdout, r.stdout


def test_one_filesystem_under_two_df_names_is_measured_on_the_total(tmp_path):
    # the same export mounted twice: one device, so the upgrade and the copy add up
    env = _env(tmp_path, 'true')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df_names(5999, 5999, 4, 4, 'nfs:/a', 'nfs:/b') + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'needs 6 MB free' in r.stdout, r.stdout


def test_two_subvolumes_of_one_block_device_are_measured_on_the_total(tmp_path):
    # btrfs subvolumes: distinct device ids, one /dev source and one pool of free space
    env = _env(tmp_path, 'true')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df_names(5999, 5999, 4, 5, '/dev/sda2', '/dev/sda2') + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'needs 6 MB free' in r.stdout, r.stdout


def test_a_device_that_cannot_be_read_is_measured_on_the_total(tmp_path):
    # stat failing: the cautious reading is one filesystem, the smaller room against the sum
    env = _env(tmp_path, 'true')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df_names(9000, 5999, 1, '', 'a', 'b') + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    # the 5 MB are the backups directory's room: that directory is the one named
    assert 'Not enough disk space in /ucm-test-backups: the start needs 6 MB free, 5 MB available' in r.stdout, r.stdout


@pytest.mark.parametrize('suffix', ['', '?timeout=30'])
def test_a_sqlite_url_on_the_same_file_still_checks_and_copies_it(tmp_path, suffix):
    # the application opens that very file: the room check and the pre-start copy apply
    env = _env(tmp_path, 'true')
    env['DATABASE_URL'] = f"sqlite:///{env['UCM_DATABASE_PATH']}{suffix}"
    _database(tmp_path, NAMES)
    r = _run(_df(2999) + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout and 'Not enough' in r.stdout, r.stdout
    r = _run(_df(3000) + _START, env, tmp_path)
    assert r.returncode == 0 and 'cp ' in r.stdout and 'not used' not in r.stdout, r.stdout


def test_two_tmpfs_each_holding_its_part_are_not_summed(tmp_path):
    # same df name, distinct devices, no /dev source: two filesystems
    env = _env(tmp_path, 'true')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df_names(3000, 3000, 1, 2) + _START, env, tmp_path)
    assert r.returncode == 0 and 'cp ' in r.stdout, r.stdout


@pytest.mark.parametrize('ha', [None, '1'])
@pytest.mark.parametrize('url,label', [
    ('postgresql://ucm:s3cret@db.example:5432/ucmprod?sslmode=require', 'PostgreSQL, database ucmprod'),
    ('postgres://ucm:s3cret@db/ucm', 'PostgreSQL, database ucm'),
    ('postgresql+psycopg://ucm@db:5432/pki', 'PostgreSQL, database pki'),
])
def test_the_summary_names_the_database_in_use_not_the_sqlite_path(tmp_path, ha, url, label):
    """A single instance on PostgreSQL showed the unused SQLite path; never the address or password."""
    env = {**_sqlite_env(tmp_path, ha), 'DATABASE_URL': url}
    r = _run('ucm_database_label', env, tmp_path)
    assert r.stdout.strip() == label
    assert 's3cret' not in r.stdout and 'db.example' not in r.stdout


def test_without_database_url_the_summary_names_the_sqlite_file(tmp_path):
    env = _sqlite_env(tmp_path, None)
    assert _run('ucm_database_label', env, tmp_path).stdout.strip() == f"SQLite, {env['UCM_DATABASE_PATH']}"
