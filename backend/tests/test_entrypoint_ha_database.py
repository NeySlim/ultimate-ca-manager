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
    env = {'UCM_DATABASE_PATH': str(db), 'UCM_BACKUP_ENABLED': 'true', 'UCM_BACKUP_RETENTION_DAYS': '30'}
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
    env = {'UCM_DATABASE_PATH': str(tmp_path / 'absent.db'), 'UCM_INITIAL_ADMIN_USERNAME': 'admin', **provided}
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


def _df(avail_kb):
    """df -Pk stubbed: one data line whose fourth column is the space available."""
    return f'df() {{ echo "Filesystem 1024-blocks Used Available Capacity Mounted"; echo "/dev/x 100 0 {avail_kb} 0% /"; }}; '


@pytest.mark.parametrize('backup,needed_kb', [('true', 2 * 3000), ('false', 3000)])
def test_the_start_is_refused_before_the_copy_when_the_disk_is_short(tmp_path, backup, needed_kb):
    env = _sqlite_env(tmp_path, None)
    env['UCM_BACKUP_ENABLED'] = backup
    (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    r = _run(_df(needed_kb - 1) + 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    out = r.stdout + r.stderr
    assert f'needs {needed_kb // 1024} MB free' in out and f'{(needed_kb - 1) // 1024} MB available' in out, out


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
    assert 'needs 2 MB free' in r.stdout, r.stdout


def test_a_restored_database_claims_the_upgrade_room(tmp_path):
    # a 2.254 copy put back after a 3.0 start: its registry decides, not what started last
    env = _env(tmp_path, 'true')
    _database(tmp_path, NAMES)
    (tmp_path / '.ucm-started-version').write_text('3.0\n')
    _database(tmp_path, [n for n in NAMES if n != '300_upgrade_from_2_254'])
    r = _run(_df(2 * 3000 - 1) + _START, env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'needs 5 MB free' in r.stdout, r.stdout


def test_a_pending_serial_replay_claims_the_upgrade_room(tmp_path):
    env = _env(tmp_path, 'false')
    _database(tmp_path, NAMES, pending_serial=True)
    r = _run(_df(2999) + _START, env, tmp_path)
    assert r.returncode != 0 and 'needs 2 MB free' in r.stdout, r.stdout


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
    assert r.returncode != 0 and 'needs 2 MB free' in r.stdout, r.stdout


def test_the_check_leaves_the_database_unchanged(tmp_path):
    env = _env(tmp_path, 'false')
    _database(tmp_path, NAMES)
    before = (tmp_path / 'ucm.db').read_bytes()
    entries = sorted(p.name for p in tmp_path.iterdir())
    r = _run(_df(0) + _START, env, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / 'ucm.db').read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == entries
