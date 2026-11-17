"""The image of a new major stops, untouched, on a database a 2.254 started last until the operator
sets UCM_ACCEPT_MAJOR_UPGRADE=3; a fresh, a 3.x or an older database is decided as before, and a
package install (no UCM_DOCKER) is never asked. SQLite and PostgreSQL (UCM_TEST_PG_URL)."""
import subprocess
import sys

import pytest

from tests.upgrade_2254_support import BACKENDS, make_base, schema_2254, snapshot

MESSAGE_PARTS = ('last started by UCM 2.254', 'Nothing was changed',
                 'UCM_ACCEPT_MAJOR_UPGRADE=3', 'back up', 'UPGRADE.md',
                 "pin the image tag '2'", '2.254.N')


@pytest.fixture(params=BACKENDS)
def dialect(request):
    return request.param


@pytest.fixture
def image(monkeypatch):
    """A start of the Docker image: its Dockerfile sets UCM_DOCKER=1."""
    monkeypatch.setenv('UCM_DOCKER', '1')
    monkeypatch.delenv('UCM_ACCEPT_MAJOR_UPGRADE', raising=False)


def _untouched(db):
    state = (sorted(db.tables()), db.registry(), snapshot(db.engine))
    if db.dialect == 'sqlite':
        state += (open(db.sqlite_path, 'rb').read(),)
    return state


def _data_dir(tmp_path, label):
    """What the runner would write beside a SQLite database: its pre-upgrade copy, a marker."""
    return sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith(label + '.db'))


@pytest.mark.parametrize('value', [None, '', 'true', '2', '4', ' 3', '3.0', 'yes'])
def test_a_2254_database_stops_the_image_untouched(dialect, tmp_path, monkeypatch, capsys, image, value):
    if value is not None:
        monkeypatch.setenv('UCM_ACCEPT_MAJOR_UPGRADE', value)
    for db in make_base(dialect, tmp_path, monkeypatch, 'mu'):
        before, files = _untouched(db), _data_dir(tmp_path, 'mu')
        assert db.upgrade() is False
        assert _untouched(db) == before
        assert _data_dir(tmp_path, 'mu') == files
        assert '300_upgrade_from_2_254' not in db.registry()
    out = capsys.readouterr().out
    for part in MESSAGE_PARTS:
        assert part in out, (part, out)
    assert '—' not in out


def test_the_accepted_major_upgrades_the_2254_database(dialect, tmp_path, monkeypatch, image):
    monkeypatch.setenv('UCM_ACCEPT_MAJOR_UPGRADE', '3')
    for db in make_base(dialect, tmp_path, monkeypatch, 'ok'):
        assert db.upgrade() is True
        assert '300_upgrade_from_2_254' in db.registry()


@pytest.mark.parametrize('docker', [None, '0', 'true'])
def test_a_package_start_upgrades_without_the_variable(dialect, tmp_path, monkeypatch, docker):
    """DEB and RPM: installing the package is the explicit action; the image alone sets UCM_DOCKER=1."""
    monkeypatch.delenv('UCM_ACCEPT_MAJOR_UPGRADE', raising=False)
    if docker is None:
        monkeypatch.delenv('UCM_DOCKER', raising=False)
    else:
        monkeypatch.setenv('UCM_DOCKER', docker)
    for db in make_base(dialect, tmp_path, monkeypatch, 'pkg'):
        assert db.upgrade() is True
        assert '300_upgrade_from_2_254' in db.registry()


@pytest.mark.parametrize('value', [None, '3'])
def test_a_3x_database_starts_the_image_with_or_without_the_variable(dialect, tmp_path, monkeypatch,
                                                                     capsys, image, value):
    from tests.upgrade_2254_support import fresh_metadata
    if value is not None:
        monkeypatch.setenv('UCM_ACCEPT_MAJOR_UPGRADE', value)
    for db in make_base(dialect, tmp_path, monkeypatch, 'v3', sql=''):
        fresh_metadata().create_all(db.engine)
        db.mark_all_applied()
        assert db.upgrade() is True
    assert 'UCM_ACCEPT_MAJOR_UPGRADE' not in capsys.readouterr().out


def test_a_fresh_database_starts_the_image(dialect, tmp_path, monkeypatch, image):
    for db in make_base(dialect, tmp_path, monkeypatch, 'new', sql=''):
        assert db.upgrade() is True
        assert db.tables() == set()


@pytest.mark.parametrize('value', [None, '3'])
def test_an_older_database_keeps_its_own_refusal(dialect, tmp_path, monkeypatch, capsys, image, value):
    if value is not None:
        monkeypatch.setenv('UCM_ACCEPT_MAJOR_UPGRADE', value)
    sql = schema_2254(dialect).replace("INSERT INTO _migrations (name) VALUES ('136_lifted_hold_leftovers');\n", '')
    for db in make_base(dialect, tmp_path, monkeypatch, 'old', sql=sql):
        before = _untouched(db)
        assert db.upgrade() is False
        assert _untouched(db) == before
    out = capsys.readouterr().out
    assert 'last started by a release older than 2.254' in out
    assert 'UCM_ACCEPT_MAJOR_UPGRADE' not in out


def _half_upgraded(tmp_path, monkeypatch, label):
    """A SQLite 2.254 database an accepted upgrade began (marker committed, 300 not recorded).
    PostgreSQL runs 300 in one transaction: a stop leaves no such state there."""
    import pre_upgrade_copy
    for db in make_base('sqlite', tmp_path, monkeypatch, label):
        pre_upgrade_copy.mark_started(db.sqlite_path)
        assert pre_upgrade_copy.MARKER_TABLE in db.tables()
        yield db


def test_an_upgrade_stopped_partway_resumes_without_the_variable(tmp_path, monkeypatch, capsys, image):
    for db in _half_upgraded(tmp_path, monkeypatch, 'half'):
        assert db.upgrade() is True
        assert '300_upgrade_from_2_254' in db.registry()
        assert '_upgrade_from_2_254_started' not in db.tables()
    out = capsys.readouterr().out
    assert 'UCM_ACCEPT_MAJOR_UPGRADE' not in out
    assert "pin the image tag '2'" not in out


def test_the_checks_let_an_upgrade_stopped_partway_resume(tmp_path, monkeypatch, capsys, image):
    from services.database_admin import migration as switch
    for db in _half_upgraded(tmp_path, monkeypatch, 'halfchk'):
        before = _untouched(db)
        assert _check(db, monkeypatch, True) == 0
        assert switch._start_refusal(db.engine, True) is None
        assert switch.start_refusal(db.url) is None
        assert _untouched(db) == before
    assert 'UCM_ACCEPT_MAJOR_UPGRADE' not in capsys.readouterr().out


# ---- the read-only check the image's entrypoint runs before any write ---------------------------

def _check(db, monkeypatch, *flags):
    """check_database as the CLI runs it, on *db*, read-only."""
    runner = db._route()
    if db.dialect == 'sqlite':
        monkeypatch.setenv('DATABASE_URL', db.url)
    return runner.check_database(*flags)


@pytest.mark.parametrize('value, expected', [(None, 7), ('true', 7), ('3', 0)])
def test_the_entrypoint_check_names_the_major_upgrade(dialect, tmp_path, monkeypatch, capsys, image,
                                                      value, expected):
    if value is not None:
        monkeypatch.setenv('UCM_ACCEPT_MAJOR_UPGRADE', value)
    for db in make_base(dialect, tmp_path, monkeypatch, 'chk'):
        before = _untouched(db)
        assert _check(db, monkeypatch, True) == expected
        assert _untouched(db) == before
    out = capsys.readouterr().out
    assert ('UCM_ACCEPT_MAJOR_UPGRADE=3' in out) is (expected == 7)


def test_the_package_check_is_unchanged_for_a_2254_database(dialect, tmp_path, monkeypatch, capsys, image):
    """The package scripts call `check` without the flag: a 2.254 database stays startable (0)."""
    for db in make_base(dialect, tmp_path, monkeypatch, 'pchk'):
        assert _check(db, monkeypatch) == 0
    assert 'UCM_ACCEPT_MAJOR_UPGRADE' not in capsys.readouterr().out


def test_the_cli_takes_the_flag(tmp_path):
    """`check --major-upgrade` on a missing SQLite file: fresh (3), the flag parsed."""
    from pathlib import Path
    backend = Path(__file__).resolve().parents[1]
    env = {'PATH': '/usr/bin:/bin', 'DATABASE_URL': f'sqlite:///{tmp_path}/none.db', 'UCM_DOCKER': '1',
           'PYTHONDONTWRITEBYTECODE': '1'}
    r = subprocess.run([sys.executable, 'migration_runner.py', 'check', '--major-upgrade'], cwd=backend,
                       env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 3, (r.stdout, r.stderr)


# ---- a backend switch predicts the start it asks for --------------------------------------------

@pytest.mark.parametrize('docker, value, refused', [('1', None, True), ('1', '3', False), (None, None, False)])
def test_a_switch_to_a_2254_database_says_the_image_would_stop(dialect, tmp_path, monkeypatch, docker, value,
                                                              refused):
    from services.database_admin import migration as switch
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.delenv('UCM_ACCEPT_MAJOR_UPGRADE', raising=False)
    if docker:
        monkeypatch.setenv('UCM_DOCKER', docker)
    if value:
        monkeypatch.setenv('UCM_ACCEPT_MAJOR_UPGRADE', value)
    for db in make_base(dialect, tmp_path, monkeypatch, 'sw'):
        before = _untouched(db)
        refusal = switch._start_refusal(db.engine, True)
        assert (refusal is not None and 'UCM_ACCEPT_MAJOR_UPGRADE=3' in refusal) is refused, refusal
        if dialect == 'sqlite':
            refusal = switch.start_refusal(db.url)
            assert (refusal is not None and 'UCM_ACCEPT_MAJOR_UPGRADE=3' in refusal) is refused, refusal
        assert _untouched(db) == before
