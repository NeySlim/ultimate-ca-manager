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
           'PATH': f'{pathlib.Path(sys.executable).parent}:/usr/bin:/bin'}
    script = (f'. {HELPER}; cp() {{ echo "cp $*"; }}; find() {{ :; }}; '
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
           'PATH': f'{pathlib.Path(sys.executable).parent}:/usr/bin:/bin'}
    script = (f'. {HELPER}; ucm_refuse_unstartable_database || exit $?; '
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
