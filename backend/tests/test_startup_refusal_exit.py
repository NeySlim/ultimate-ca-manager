"""A database this release refuses, or an upgrade that fails, stops the service with exit 78,
which the one systemd unit both packages install does not restart; a failure once running does.
The PostgreSQL case needs UCM_TEST_PG_URL."""
import configparser
import os
import shutil
import subprocess
import sys
import textwrap
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

import migration_runner
import startup_refusal
from tests.test_upgrade_copy_2254 import REFUSED, _occupied
from tests.upgrade_2254_support import make_base, schema_2254

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
UNIT = ROOT / 'packaging' / 'systemd' / 'ucm.service'


def _no_lock(_url):
    return nullcontext()


@pytest.mark.parametrize('dialect, case', [
    ('sqlite', 'older than 2.254'), ('sqlite', 'no copy'),
    pytest.param('postgresql', 'older than 2.254', marks=pytest.mark.postgres)])
def test_each_refusal_of_the_runner_is_the_refusal_that_exits_78(dialect, case, tmp_path, monkeypatch):
    sql = schema_2254(dialect)
    if case == 'older than 2.254':
        sql = REFUSED['2.253'](sql)
        assert sql != schema_2254(dialect)
    for db in make_base(dialect, tmp_path, monkeypatch, 'refusal', sql=sql):
        db._route()
        if case == 'no copy':
            _occupied(monkeypatch, db)
        with pytest.raises(startup_refusal.DatabaseRefused):
            startup_refusal.migrate_or_refuse(_no_lock)


def test_a_migration_step_that_raises_stops_the_service_with_78_too(tmp_path, monkeypatch, capsys):
    """Deterministic, and half applied: a restart would only replay it, so the unit leaves it failed."""
    import types

    def broken(path):
        module = types.ModuleType(path.stem)

        def upgrade(conn):
            raise RuntimeError('step failed here')
        module.upgrade = upgrade
        return module

    for db in make_base('sqlite', tmp_path, monkeypatch, 'step'):
        db._route()
        monkeypatch.setattr(migration_runner, '_load_module', broken)
        with pytest.raises(startup_refusal.DatabaseRefused):
            startup_refusal.migrate_or_refuse(_no_lock)
    assert 'step failed here' in capsys.readouterr().out


def test_a_database_out_of_reach_is_not_a_refusal(monkeypatch):
    """Unreachable now, perhaps reachable at the next start: an ordinary failure."""
    monkeypatch.setattr(migration_runner, '_get_db_url', lambda: 'postgresql://ucm:x@127.0.0.1:1/ucm')
    with pytest.raises(Exception) as caught:
        startup_refusal.migrate_or_refuse(_no_lock)
    assert not isinstance(caught.value, startup_refusal.DatabaseRefused)


UNREACHABLE = 'postgresql://ucm:x@127.0.0.1:1/ucm'
SQLALCHEMY_ON_SQL_ASCII = 'cannot use a string pattern on a bytes-like object'


def _ha(monkeypatch, on, encoding):
    """Simulated: the server answers *encoding*; each step that opens a SQLAlchemy connection
    (the restore wait, the HA startup lock) records itself, and fails as it does on SQL_ASCII."""
    import utils.ha
    from services import cluster_maintenance
    monkeypatch.setenv('DATABASE_URL', UNREACHABLE)
    monkeypatch.setattr(migration_runner, '_server_encoding', lambda engine: encoding)
    monkeypatch.setattr(utils.ha, 'ha_enabled', lambda: on)
    reached = []

    def restore_wait(url, poll=None):
        reached.append('restore wait')
        raise TypeError(SQLALCHEMY_ON_SQL_ASCII)

    @contextmanager
    def lock(url):
        reached.append('startup lock')
        if on:
            raise TypeError(SQLALCHEMY_ON_SQL_ASCII)
        yield

    monkeypatch.setattr(cluster_maintenance, 'wait_while_restoring', restore_wait)
    return reached, lock


@pytest.mark.parametrize('ha', [True, False], ids=['HA', 'single node'])
def test_an_encoding_refusal_exits_78_before_any_sqlalchemy_connection(monkeypatch, ha):
    reached, lock = _ha(monkeypatch, ha, 'SQL_ASCII')
    with pytest.raises(startup_refusal.DatabaseRefused, match='uses the encoding SQL_ASCII; UCM needs UTF8'):
        startup_refusal.migrate_or_refuse(lock)
    assert reached == []


def test_in_ha_a_utf8_database_waits_for_a_restore_then_takes_the_startup_lock(monkeypatch):
    reached, lock = _ha(monkeypatch, True, 'UTF8')
    with pytest.raises(TypeError):
        startup_refusal.migrate_or_refuse(lock)
    assert reached == ['restore wait']
    reached.clear()
    from services import cluster_maintenance
    monkeypatch.setattr(cluster_maintenance, 'wait_while_restoring', lambda url, poll=None: reached.append('restore wait'))
    with pytest.raises(TypeError):
        startup_refusal.migrate_or_refuse(lock)
    assert reached == ['restore wait', 'startup lock']


def test_the_status_command_names_the_encoding_of_a_refused_database(monkeypatch, capsys):
    """Simulated, as above: the diagnostic reads no registry after it."""
    monkeypatch.setenv('DATABASE_URL', UNREACHABLE)
    monkeypatch.setattr(migration_runner, '_server_encoding', lambda engine: 'SQL_ASCII')
    monkeypatch.setattr(migration_runner, '_get_state', lambda engine: pytest.fail('registry read'))
    migration_runner.show_status()
    assert 'Refused: This PostgreSQL database uses the encoding SQL_ASCII' in capsys.readouterr().out


STUB_APP = textwrap.dedent('''
    import sys, types
    sys.path.insert(0, '.')
    import startup_refusal
    app = types.ModuleType('app')
    def create_app():
        raise {error}('refused here')
    app.create_app = create_app
    sys.modules['app'] = app
    import wsgi
''')


@pytest.mark.parametrize('error, code', [('startup_refusal.DatabaseRefused', 78), ('ValueError', 1)])
def test_the_wsgi_module_exits_78_on_a_refusal_alone(error, code):
    out = subprocess.run([sys.executable, '-c', STUB_APP.format(error=error)], cwd=BACKEND,
                         capture_output=True, text=True, timeout=60, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    assert out.returncode == code, out.stderr
    if code == 78:
        assert 'refused here' in out.stderr


def test_gunicorn_passes_on_the_exit_code_of_a_preloaded_application(tmp_path):
    """preload_app loads the application in the master, which exits with its code."""
    gunicorn = Path(sys.executable).with_name('gunicorn')
    if not gunicorn.exists():
        pytest.skip('gunicorn is not installed beside this interpreter')
    (tmp_path / 'refusing.py').write_text('import sys\nsys.exit(78)\n')
    out = subprocess.run([str(gunicorn), '--preload', '-b', '127.0.0.1:0', 'refusing:app'],
                         cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert out.returncode == 78, out.stderr


def _unit():
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(UNIT.read_text())
    return parser


def test_the_unit_does_not_restart_a_refusal_and_restarts_any_other_failure():
    unit = _unit()
    service = unit['Service']
    assert service['Restart'] == 'on-failure'
    assert str(startup_refusal.EXIT_CODE) in service['RestartPreventExitStatus'].split()
    assert int(unit['Unit']['StartLimitBurst']) > 1 and int(unit['Unit']['StartLimitIntervalSec']) > 0


def test_both_packages_install_the_one_unit():
    assert not (ROOT / 'packaging' / 'debian' / 'ucm.service').exists()
    assert not (ROOT / 'packaging' / 'rpm' / 'ucm.service').exists()
    if shutil.which('make'):
        rules = subprocess.run(['make', '-n', '-f', 'packaging/debian/rules', 'override_dh_auto_install'],
                               cwd=ROOT, capture_output=True, text=True, timeout=10)
        assert rules.returncode == 0, rules.stderr
        assert 'install -m 644 packaging/systemd/ucm.service debian/ucm/lib/systemd/system/' in rules.stdout
    spec = (ROOT / 'packaging' / 'rpm' / 'ucm.spec').read_text()
    assert 'install -m 644 packaging/systemd/ucm.service %{buildroot}%{_unitdir}/%{name}.service' in spec
