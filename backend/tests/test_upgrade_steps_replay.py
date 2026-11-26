"""A 3.0 database (300 recorded) runs at its next start the steps added to migration 300 since it
was upgraded or built, each recorded once done, on SQLite and PostgreSQL; a registry without
step rows (3.0-rc1 to rc6) ran the steps of rc1 and runs the later ones."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

from tests.upgrade_2254_support import BACKENDS, fresh_metadata, make_base

STEP_ROW = '300_upgrade_from_2_254/%'


@pytest.fixture(params=BACKENDS)
def dialect(request):
    return request.param


def _as_rc6(db):
    """A 2.254 database upgraded, then put in the state 3.0-rc6 left: 300 recorded, no step
    row, no certificates.comment, revoked_serials.published, ssh_krls nor ssh_hosts (steps 175,
    176, 179 and 180 came after it)."""
    assert db.upgrade()
    db.run("ALTER TABLE certificates DROP COLUMN comment")
    db.run("ALTER TABLE revoked_serials DROP COLUMN published")
    db.run("DROP TABLE ssh_krls")
    db.run("DROP TABLE ssh_hosts")
    db.run("DROP TABLE ssh_host_enrollment_tokens")
    db.run("DELETE FROM _migrations WHERE name LIKE :p", {'p': STEP_ROW})
    assert '300_upgrade_from_2_254' in db.registry()
    assert not [n for n in db.registry() if n.startswith('300_upgrade_from_2_254/')]


@pytest.fixture
def rc6(dialect, tmp_path, monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'rc6'):
        _as_rc6(db)
        yield db


def _columns(db, table):
    return {c['name'] for c in inspect(db.engine).get_columns(table)}


def _spy_steps(monkeypatch):
    """The names of the steps whose upgrade() runs from now on, in order."""
    import types
    import migrations._from_2_254 as package
    real, ran = package.step, []

    def step(name):
        module = real(name)

        def upgrade(conn):
            ran.append(name)
            return module.upgrade(conn)
        return types.SimpleNamespace(upgrade=upgrade, refusal=getattr(module, 'refusal', None))
    monkeypatch.setattr(package, 'step', step)
    return ran


def _holds_every_step(db):
    import migration_runner
    return set(migration_runner.fresh_registry_names()) <= set(db.registry())


# The child reads neither the host's env file nor its master key, as under conftest; it starts
# the application on DATABASE_URL and lists the certificates as an administrator
_START_AND_LIST = '''
import json, os
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from pathlib import Path
from security import encryption
encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
encryption.key_encryption.reload()
from config import settings
from utils.db_url import sqlalchemy_url
settings.TestingConfig.SQLALCHEMY_DATABASE_URI = sqlalchemy_url(os.environ['DATABASE_URL'])
from app import create_app
app = create_app('testing')
app.config['WTF_CSRF_ENABLED'] = False
from models import db, User
with app.app_context():
    User.query.filter_by(username='admin').update({'force_password_change': False})
    db.session.commit()
client = app.test_client()
r = client.post('/api/v2/auth/login', data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
                content_type='application/json')
print('LOGIN', r.status_code)
for query in ('', '?search=note', '?sort_by=comment'):
    r = client.get('/api/v2/certificates' + query)
    print('LIST', r.status_code, r.get_data(as_text=True)[:300])
'''


def _child_url(db):
    if db.dialect == 'sqlite':
        return db.url
    from urllib.parse import quote
    return f"{db.url}{'&' if '?' in db.url else '?'}options={quote(db.options)}"


def _start_and_list(db, tmp_path):
    data = tmp_path / 'node'
    data.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(DATA_DIR=str(data), DATABASE_PATH=str(data / 'ucm.db'), DATABASE_URL=_child_url(db),
               UCM_SKIP_SECRET_VALIDATION='1', UCM_HA='0', INITIAL_ADMIN_PASSWORD='changeme123')
    backend = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, '-c', _START_AND_LIST], cwd=backend, env=env,
                         capture_output=True, text=True, timeout=300)
    return run.returncode, run.stdout, run.stderr


def test_a_rc6_database_gets_the_comment_column_and_lists_its_certificates(rc6, tmp_path):
    code, out, err = _start_and_list(rc6, tmp_path)
    assert code == 0, out[-3000:] + err[-3000:]
    assert 'LOGIN 200' in out, out[-3000:] + err[-3000:]
    assert out.count('LIST 200') == 3, out[-3000:] + err[-3000:]
    assert 'comment' in _columns(rc6, 'certificates')
    assert 'published' in _columns(rc6, 'revoked_serials')
    assert {'ssh_krls', 'ssh_hosts', 'ssh_host_enrollment_tokens'} <= set(inspect(rc6.engine).get_table_names())


def test_a_rc6_database_runs_the_steps_after_rc1_and_records_every_step(rc6, monkeypatch):
    from migrations._from_2_254 import STEPS, UNRECORDED
    ran = _spy_steps(monkeypatch)
    assert rc6.upgrade()
    assert ran == [s for s in STEPS if s not in UNRECORDED]
    assert '175_certificate_comment' in ran and '176_revoked_serial_publication' in ran
    assert '179_ssh_krls' in ran and '180_ssh_hosts' in ran
    assert '165_sso_ldap_group_base_dn' in ran  # changed after rc1: runs again
    assert 'comment' in _columns(rc6, 'certificates')
    assert _holds_every_step(rc6)


def test_a_second_start_runs_no_step(rc6, monkeypatch, capsys):
    assert rc6.upgrade()
    registry = rc6.registry()
    capsys.readouterr()
    ran = _spy_steps(monkeypatch)
    assert rc6.upgrade()
    assert ran == []
    assert rc6.registry() == registry
    assert 'up to date' in capsys.readouterr().out


def test_a_failed_step_is_not_recorded_and_runs_at_the_next_start(rc6, monkeypatch, capsys):
    import migrations._from_2_254 as package
    real = package.step

    class _Broken:
        @staticmethod
        def upgrade(conn):
            raise RuntimeError('disk full')
    monkeypatch.setattr(package, 'step', lambda name: _Broken if name == '175_certificate_comment'
                        else real(name))
    assert rc6.upgrade() is False
    assert 'disk full' in capsys.readouterr().out
    assert '300_upgrade_from_2_254/175_certificate_comment' not in rc6.registry()
    # The steps before it are recorded: the next start runs 175 and the steps after it
    assert '300_upgrade_from_2_254/174_windows_profile_renewal_cas' in rc6.registry()
    monkeypatch.setattr(package, 'step', real)
    ran = _spy_steps(monkeypatch)
    assert rc6.upgrade()
    from migrations._from_2_254 import STEPS
    assert ran == list(STEPS[STEPS.index('175_certificate_comment'):])
    assert 'comment' in _columns(rc6, 'certificates')


def test_a_step_refusal_stops_the_start_before_any_write(rc6, monkeypatch, capsys):
    import migrations._from_2_254 as package
    real = package.step

    class _Refusing:
        @staticmethod
        def refusal(conn):
            return 'Upgrade refused: two rows'

        @staticmethod
        def upgrade(conn):
            raise AssertionError('a refused step never runs')
    monkeypatch.setattr(package, 'step', lambda name: _Refusing if name == '175_certificate_comment'
                        else real(name))
    registry = rc6.registry()
    assert rc6.upgrade() is False
    assert 'Upgrade refused: two rows' in capsys.readouterr().out
    assert rc6.registry() == registry
    assert 'comment' not in _columns(rc6, 'certificates')


def test_dry_run_status_and_pending_name_the_step_without_running_it(rc6, capsys):
    runner = rc6._route()
    registry = rc6.registry()
    assert runner.run_all_migrations(dry_run=True) is True
    runner.show_status()
    out = capsys.readouterr().out
    assert 'up to date' not in out
    assert 'step 175_certificate_comment: (dry run)' in out
    assert '○ 300_upgrade_from_2_254/175_certificate_comment' in out
    assert '300_upgrade_from_2_254/175_certificate_comment' in runner.pending_migrations(rc6.engine)
    assert rc6.registry() == registry
    assert 'comment' not in _columns(rc6, 'certificates')


def test_the_upgrade_from_2254_records_its_steps_and_the_next_start_runs_none(dialect, tmp_path,
                                                                              monkeypatch):
    for db in make_base(dialect, tmp_path, monkeypatch, 'up'):
        assert db.upgrade()
        assert _holds_every_step(db)
        ran = _spy_steps(monkeypatch)
        assert db.upgrade()
        assert ran == []


def test_a_fresh_install_records_every_step(dialect, tmp_path, monkeypatch):
    import migration_runner
    for db in make_base(dialect, tmp_path, monkeypatch, 'fi', sql=''):
        db._route()
        migration_runner.build_fresh_schema(lambda: fresh_metadata().create_all(db.engine))
        assert db.registry() == migration_runner.fresh_registry_names()
        assert migration_runner.pending_migrations(db.engine) == []
        ran = _spy_steps(monkeypatch)
        assert db.upgrade()
        assert ran == []


def test_the_check_of_the_package_scripts_starts_a_database_with_step_rows(dialect, tmp_path, monkeypatch):
    """A step row is no unknown migration: the pivot accepts the database."""
    import migration_runner
    for db in make_base(dialect, tmp_path, monkeypatch, 'ck'):
        assert db.upgrade()
        state, applied = migration_runner._get_state(db.engine)
        assert migration_runner.unknown_migrations(applied) == []
        assert migration_runner.pivot_refusal(state, applied) is None


def test_the_rc1_steps_are_a_prefix_of_the_steps():
    from migrations._from_2_254 import STEPS, UNRECORDED
    assert set(UNRECORDED) <= set(STEPS[:STEPS.index('170_sso_sign_in_tests') + 1])
    assert '165_sso_ldap_group_base_dn' not in UNRECORDED
    assert UNRECORDED[-1] == '170_sso_sign_in_tests' and '175_certificate_comment' not in UNRECORDED
