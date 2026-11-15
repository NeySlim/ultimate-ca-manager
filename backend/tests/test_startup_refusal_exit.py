"""A database this release refuses stops the service with exit 78, which the one systemd
unit both packages install does not restart; any other failure keeps restarting it.
The PostgreSQL case needs UCM_TEST_PG_URL."""
import configparser
import os
import shutil
import subprocess
import sys
import textwrap
from contextlib import nullcontext
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


def test_a_database_out_of_reach_is_not_a_refusal(monkeypatch):
    """Unreachable now, perhaps reachable at the next start: an ordinary failure."""
    monkeypatch.setattr(migration_runner, '_get_db_url', lambda: 'postgresql://ucm:x@127.0.0.1:1/ucm')
    with pytest.raises(Exception) as caught:
        startup_refusal.migrate_or_refuse(_no_lock)
    assert not isinstance(caught.value, startup_refusal.DatabaseRefused)


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
