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


def _started(tmp_path, version):
    """Marker the application leaves next to the database after a start that migrated."""
    (tmp_path / '.ucm-started-version').write_text(version + '\n')


@pytest.mark.parametrize('backup,avail_kb', [('false', 2900), ('false', 0), ('true', 3000)])
def test_an_ordinary_start_claims_only_the_copy(tmp_path, backup, avail_kb):
    env = _sqlite_env(tmp_path, None)
    env.update(UCM_BACKUP_ENABLED=backup, UCM_VERSION='3.0')
    (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    _started(tmp_path, '3.0')
    r = _run(_df(avail_kb) + 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ('cp ' in r.stdout) is (backup == 'true')


def test_an_ordinary_start_still_needs_room_for_the_copy(tmp_path):
    env = _sqlite_env(tmp_path, None)
    env['UCM_VERSION'] = '3.0'
    (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    _started(tmp_path, '3.0')
    r = _run(_df(2999) + 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode != 0 and 'cp ' not in r.stdout, r.stdout
    assert 'needs 2 MB free' in r.stdout, r.stdout


@pytest.mark.parametrize('last,current', [('2.254.1', '3.0'), ('3.0', ''), ('3.0', 'unknown')])
def test_a_new_or_unknown_version_claims_the_upgrade_room(tmp_path, last, current):
    env = _sqlite_env(tmp_path, None)
    env.update(UCM_BACKUP_ENABLED='false', UCM_VERSION=current)
    (tmp_path / 'ucm.db').write_bytes(b'\0' * 3000 * 1024)
    _started(tmp_path, last)
    r = _run(_df(2999) + 'cp() { echo "cp $*"; }; find() { :; }; ucm_sqlite_check_and_backup', env, tmp_path)
    assert r.returncode != 0 and 'needs 2 MB free' in r.stdout, r.stdout
