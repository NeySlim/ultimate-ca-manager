"""The image's entrypoint stops on a database 2.254 started last, before anything is written to the
volume, until UCM_ACCEPT_MAJOR_UPGRADE=3; it sources docker/ha-database.sh as these tests do.
SQLite at either data path, a DATABASE_URL, HA, and PostgreSQL when UCM_TEST_PG_URL is set."""
import hashlib
import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

from tests.upgrade_2254_support import make_base, snapshot

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'docker' / 'ha-database.sh'
ENTRYPOINT = ROOT / 'docker' / 'entrypoint.sh'
GATES = 'ucm_refuse_unstartable_database || exit $?; ucm_refuse_unaccepted_major_upgrade || exit $?; '

sys.path.insert(0, str(ROOT / 'backend'))


def _registry(path, state):
    from migrations._from_2_254 import PIVOT_NAMES
    names = sorted(PIVOT_NAMES)
    if state == '2.253':
        names = names[:-1]
    elif state == '3.x':
        names = names + ['300_upgrade_from_2_254']
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    conn.executemany('INSERT INTO _migrations (name) VALUES (?)', [(n,) for n in names])
    conn.commit()
    conn.close()


def _fingerprint(top):
    return {str(p.relative_to(top)): (p.is_dir(), p.stat().st_mode, None if p.is_dir() else
                                       hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(top.rglob('*'))}


def _env(volume, data, old, extra):
    env = {'UCM_BACKUP_ENABLED': 'true', 'UCM_BACKUP_RETENTION_DAYS': '30', 'UCM_BASE_PATH': str(ROOT),
           'DATA_PATH': str(data), 'UCM_OLD_DATA_PATHS': f'{old} {volume}/app/backend/data',
           'UCM_DATABASE_PATH': str(data / 'ucm.db'), 'UCM_INITIAL_ADMIN_USERNAME': 'admin',
           'UCM_MIGRATIONS_DIR': str(ROOT / 'backend' / 'migrations'),
           'PATH': f'{pathlib.Path(sys.executable).parent}:/usr/bin:/bin'}
    return {**env, **{k: v for k, v in extra.items() if v is not None}}


def _volume_start(tmp_path, where, db_state, **extra):
    """The entrypoint's steps from its gates to the copy of the database, on a temporary volume:
    the old-path carry-over, the data directories, a key written there, the pre-start copy."""
    volume = tmp_path / 'volume'
    data, old = volume / 'opt/ucm/data', volume / 'opt/ucm/backend/data'
    data.mkdir(parents=True)
    (old / 'ca').mkdir(parents=True)
    (old / 'ca' / 'root.pem').write_text('ca')
    if db_state != 'absent':
        _registry((data if where == 'current' else old) / 'ucm.db', db_state)
    script = (f'. {HELPER}; UCM_SQLITE_BACKUP_DIR="$DATA_PATH/backups"; {GATES}'
              'ucm_carry_old_data_paths; mkdir -p "$DATA_PATH/backups"; echo key > "$DATA_PATH/https_key.pem"; '
              'ucm_sqlite_check_and_backup')
    before = _fingerprint(volume)
    r = subprocess.run(['bash', '-c', script], env=_env(volume, data, old, extra), capture_output=True,
                       text=True, cwd=tmp_path, timeout=120)
    return r, before, _fingerprint(volume), data


def _says_major(out):
    return 'UCM_ACCEPT_MAJOR_UPGRADE=3' in out and 'Nothing was changed' in out


@pytest.mark.parametrize('where', ['current', 'from before 2.70'])
@pytest.mark.parametrize('value', [None, '', 'true', '2', '4', '3 '])
def test_a_2254_volume_stops_the_image_unchanged(tmp_path, where, value):
    r, before, after, _data = _volume_start(tmp_path, where, '2.254', UCM_ACCEPT_MAJOR_UPGRADE=value)
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert after == before
    assert _says_major(r.stdout), r.stdout
    assert "pin the image tag '2'" in r.stdout and 'UPGRADE.md' in r.stdout
    assert '—' not in r.stdout


@pytest.mark.parametrize('where', ['current', 'from before 2.70'])
def test_the_accepted_major_goes_on_as_before(tmp_path, where):
    r, _before, _after, data = _volume_start(tmp_path, where, '2.254', UCM_ACCEPT_MAJOR_UPGRADE='3')
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (data / 'ucm.db').is_file() and (data / 'ca' / 'root.pem').read_text() == 'ca'
    assert len(list((data / 'backups').glob('ucm-backup-*.db'))) == 1


@pytest.mark.parametrize('db_state', ['3.x', 'absent'])
def test_a_3x_or_new_volume_starts_without_the_variable(tmp_path, db_state):
    r, _before, _after, _data = _volume_start(tmp_path, 'current', db_state)
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert 'UCM_ACCEPT_MAJOR_UPGRADE' not in r.stdout


@pytest.mark.parametrize('value', [None, '3'])
def test_an_older_volume_keeps_its_own_refusal(tmp_path, value):
    r, before, after, _data = _volume_start(tmp_path, 'current', '2.253', UCM_ACCEPT_MAJOR_UPGRADE=value)
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert after == before
    assert 'older than 2.254' in r.stdout and 'UCM_ACCEPT_MAJOR_UPGRADE' not in r.stdout


@pytest.mark.parametrize('ha', [None, '1'])
def test_a_database_url_is_asked_too(tmp_path, ha):
    """PostgreSQL and HA skip the SQLite gate: the database the URL names is asked all the same."""
    db = tmp_path / 'elsewhere.db'
    _registry(db, '2.254')
    r, before, after, _data = _volume_start(tmp_path, 'current', 'absent', DATABASE_URL=f'sqlite:///{db}',
                                            UCM_HA=ha)
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert after == before
    assert _says_major(r.stdout), r.stdout


def test_an_unreadable_database_url_is_left_to_the_application(tmp_path):
    r, *_ = _volume_start(tmp_path, 'current', 'absent', DATABASE_URL='postgresql://u@127.0.0.1:9/none')
    assert r.returncode == 0, (r.stdout, r.stderr)


def _pg_untouched(db):
    return sorted(db.tables()), db.registry(), snapshot(db.engine)


@pytest.mark.postgres
@pytest.mark.parametrize('value, refused', [(None, True), ('true', True), ('3', False)])
def test_a_2254_postgresql_database_is_asked_before_any_write(tmp_path, monkeypatch, value, refused):
    for db in make_base('postgresql', tmp_path, monkeypatch, 'ep'):
        url = db.url + ('&' if '?' in db.url else '?') + 'options=' + db.options.replace('=', '%3D')
        before = _pg_untouched(db)
        r, vol_before, vol_after, _data = _volume_start(tmp_path, 'current', 'absent', DATABASE_URL=url,
                                                        UCM_HA='1', UCM_ACCEPT_MAJOR_UPGRADE=value)
        assert (r.returncode == 78) is refused, (r.stdout, r.stderr)
        assert _says_major(r.stdout) is refused, r.stdout
        assert _pg_untouched(db) == before
        if refused:
            assert vol_after == vol_before


def test_the_entrypoint_asks_before_its_first_write():
    # textual order: the behaviour is the tests above; the gate follows the older-release one
    # and precedes the first write to the volume (the old-path carry-over)
    text = ENTRYPOINT.read_text()
    gate = text.index('ucm_refuse_unaccepted_major_upgrade || exit $?')
    assert text.index('ucm_refuse_unstartable_database || exit $?') < gate
    assert gate < text.index('\nucm_carry_old_data_paths') < text.index('mkdir -p "$DATA_PATH"')


def test_the_package_scripts_never_ask():
    """DEB and RPM: no package script runs the image's check."""
    for top in ('debian', 'packaging'):
        for path in (ROOT / top).rglob('*'):
            if path.is_file() and path.suffix not in ('.png', '.ico'):
                text = path.read_text(errors='replace')
                assert '--major-upgrade' not in text and 'UCM_ACCEPT_MAJOR_UPGRADE' not in text, path
                assert 'UCM_DOCKER' not in text, path


def test_the_refusal_never_echoes_the_database_url(tmp_path):
    db = tmp_path / 'secret-name.db'
    _registry(db, '2.254')
    r, *_ = _volume_start(tmp_path, 'current', 'absent', DATABASE_URL=f'sqlite:///{db}')
    assert r.returncode == 78, (r.stdout, r.stderr)
    assert os.path.basename(str(db)) not in r.stdout
