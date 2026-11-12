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
