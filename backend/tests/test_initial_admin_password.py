"""The first administrator's password: provided by the operator, or generated into a file.

Each boot below is a real create_app() in a child process with a data directory
of its own, so its standard output, its log file and its audit rows can be searched
for the password. SQLite always; PostgreSQL too when UCM_TEST_APP_PG_URL is set.
"""
import json
import os
import secrets
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import pg_app_harness

BACKEND = Path(__file__).resolve().parents[1]
PASSWORD_FILE = 'initial-admin-password'

# The child reads neither the host's env file nor its master key, as under conftest
CHILD = textwrap.dedent('''
    import json, os, sys
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    from pathlib import Path
    from security import encryption
    encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
    encryption.key_encryption.reload()
    from config import settings
    from utils.db_url import sqlalchemy_url
    settings.TestingConfig.SQLALCHEMY_DATABASE_URI = sqlalchemy_url(os.environ['CHILD_DB_URI'])
    from app import create_app
    app = create_app('testing')
    print('BOOTED', flush=True)
    from models import db, User, AuditLog
    out = {}
    with app.app_context():
        out['users'] = [[u.username, bool(u.force_password_change)] for u in User.query.all()]
        secret = os.environ.get('CHILD_SECRET')
        if secret:
            out['secret_in_audit'] = any(
                secret in json.dumps([a.details, a.resource_name], default=str)
                for a in AuditLog.query.all())
    login = os.environ.get('CHILD_LOGIN')
    if login:
        client = app.test_client()
        r = client.post('/api/v2/auth/login', json={'username': 'admin', 'password': login})
        out['login'] = r.status_code
        body = r.get_json() or {}
        out['forced'] = bool((body.get('data') or {}).get('force_password_change'))
        new = os.environ.get('CHILD_NEW_PASSWORD')
        if new and r.status_code == 200:
            r = client.post('/api/v2/account/password', json={'new_password': new})
            out['change'] = r.status_code
            out['secret_in_change_reply'] = login in r.get_data(as_text=True)
    print('RESULT ' + json.dumps(out), flush=True)
''')


def _backends():
    yield 'sqlite'
    if pg_app_harness.ENABLED:
        yield 'postgresql'


@pytest.fixture(params=list(_backends()))
def database(request, tmp_path):
    """The URI one installation's boots share: a SQLite file, or a PostgreSQL schema."""
    if request.param == 'sqlite':
        path = tmp_path / 'shared.db'
        return {'CHILD_DB_URI': f'sqlite:///{path}', 'DATABASE_PATH': str(path), 'DATABASE_URL': ''}
    name = f'{pg_app_harness.SCHEMA}_adm{secrets.token_hex(2)}'
    pg_app_harness._new_schema(pg_app_harness._marker[0].cursor(), name)
    url = pg_app_harness.app_url(name)
    return {'CHILD_DB_URI': url, 'DATABASE_URL': url,
            'DATABASE_PATH': str(tmp_path / 'unused.db')}


def _child_env(database, data, extra):
    from cryptography.fernet import Fernet
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('INITIAL_ADMIN_', 'HTTPS_CERT', 'HTTPS_KEY', 'UCM_HA', 'UCM_NODE'))}
    data.mkdir(parents=True, exist_ok=True)
    (data / 'etc').mkdir(exist_ok=True)
    env.update(database, DATA_DIR=str(data), UCM_CONFIG_DIR=str(data / 'etc'),
               SECRET_KEY='initial-admin-test', UCM_SKIP_SECRET_VALIDATION='1',
               KEY_ENCRYPTION_KEY=Fernet.generate_key().decode(), CSRF_DISABLED='true',
               PYTHONDONTWRITEBYTECODE='1')
    env.update(extra or {})
    return env


def _start(database, data, extra=None):
    return subprocess.Popen([sys.executable, '-c', CHILD], cwd=BACKEND,
                            env=_child_env(database, data, extra), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)


def _finish(proc, data, ok=True):
    out = proc.communicate(timeout=240)[0]
    logs = out + ''.join(p.read_text(errors='replace') for p in data.rglob('*.log'))
    if not ok:
        assert proc.returncode != 0, out[-3000:]
        return None, logs
    assert proc.returncode == 0 and 'BOOTED' in out, out[-4000:]
    line = next(l for l in out.splitlines() if l.startswith('RESULT '))
    return json.loads(line[len('RESULT '):]), logs


def _boot(database, data, extra=None, ok=True):
    return _finish(_start(database, data, extra), data, ok)


def test_nothing_provided_generates_a_file_that_opens_a_forced_account(database, tmp_path):
    data = tmp_path / 'node'
    result, logs = _boot(database, data)
    path = data / PASSWORD_FILE
    assert result['users'] == [['admin', True]]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    value = path.read_text().rstrip('\n')
    assert len(value) >= 20 and value != 'changeme123'
    assert value not in logs
    assert str(path) in logs  # the log names where to read it

    # A second start keeps the same file; the password opens the account, which must change it
    result, logs = _boot(database, data, {'CHILD_LOGIN': value, 'CHILD_SECRET': value,
                                          'CHILD_NEW_PASSWORD': 'An0ther-Strong-Pass!'})
    assert result['login'] == 200 and result['forced'] is True
    assert result['change'] == 200 and result['secret_in_change_reply'] is False
    assert result['secret_in_audit'] is False
    assert value not in logs
    assert not path.exists()
    assert result['users'] == [['admin', True]]  # read before the change, in the same child

    result, _ = _boot(database, data)
    assert result['users'] == [['admin', False]] and not path.exists()


def test_changeme123_opens_nothing_unless_provided(database, tmp_path):
    result, _ = _boot(database, tmp_path / 'node', {'CHILD_LOGIN': 'changeme123'})
    assert result['login'] == 401


def test_a_provided_variable_is_used_without_file_or_forced_change(database, tmp_path):
    data = tmp_path / 'node'
    result, logs = _boot(database, data, {'INITIAL_ADMIN_PASSWORD': 'Operator-Chosen-1!',
                                          'CHILD_LOGIN': 'Operator-Chosen-1!'})
    assert result['login'] == 200 and result['forced'] is False
    assert result['users'] == [['admin', False]]
    assert not (data / PASSWORD_FILE).exists()
    assert 'Operator-Chosen-1!' not in logs


def test_a_password_a_deployment_tool_generated_is_forced_without_a_file(database, tmp_path):
    """The Helm chart's own random value: the operator never chose it."""
    data = tmp_path / 'node'
    result, logs = _boot(database, data, {'INITIAL_ADMIN_PASSWORD': 'Chart-Generated-Value-1',
                                          'INITIAL_ADMIN_PASSWORD_FORCE_CHANGE': '1',
                                          'CHILD_LOGIN': 'Chart-Generated-Value-1'})
    assert result['login'] == 200 and result['forced'] is True
    assert result['users'] == [['admin', True]]
    assert not (data / PASSWORD_FILE).exists()
    assert 'Chart-Generated-Value-1' not in logs


def test_a_provided_file_is_used_without_generation_or_forced_change(database, tmp_path):
    data = tmp_path / 'node'
    secret = tmp_path / 'secret'
    secret.write_text('From-A-Docker-Secret-9\n')
    result, logs = _boot(database, data, {'INITIAL_ADMIN_PASSWORD_FILE': str(secret),
                                          'CHILD_LOGIN': 'From-A-Docker-Secret-9'})
    assert result['login'] == 200 and result['forced'] is False
    assert not (data / PASSWORD_FILE).exists()
    assert 'From-A-Docker-Secret-9' not in logs


@pytest.mark.parametrize('content', [None, '', '\n'], ids=['missing', 'empty', 'newline'])
def test_an_unusable_password_file_refuses_to_start(database, tmp_path, content):
    data = tmp_path / 'node'
    secret = tmp_path / 'secret'
    if content is not None:
        secret.write_text(content)
    _, logs = _boot(database, data, {'INITIAL_ADMIN_PASSWORD_FILE': str(secret)}, ok=False)
    assert 'INITIAL_ADMIN_PASSWORD_FILE' in logs
    assert not (data / PASSWORD_FILE).exists()


def test_both_sources_refuse_to_start(database, tmp_path):
    data = tmp_path / 'node'
    secret = tmp_path / 'secret'
    secret.write_text('From-File-1!\n')
    _, logs = _boot(database, data, {'INITIAL_ADMIN_PASSWORD_FILE': str(secret),
                                     'INITIAL_ADMIN_PASSWORD': 'From-Var-1!'}, ok=False)
    assert 'INITIAL_ADMIN_PASSWORD_FILE' in logs and 'From-Var-1!' not in logs
    assert not (data / PASSWORD_FILE).exists()


def test_an_unwritable_data_directory_creates_no_administrator(database, tmp_path):
    data = tmp_path / 'node'
    data.mkdir()
    blocker = data / PASSWORD_FILE
    blocker.mkdir()  # os.replace cannot put a file over a directory, whoever runs this
    _, logs = _boot(database, data, ok=False)
    assert PASSWORD_FILE in logs


def test_an_existing_installation_reads_no_password_source_again(database, tmp_path):
    """2.x upgrade: the account exists, a leftover changeme123 and a broken _FILE change nothing."""
    data = tmp_path / 'node'
    _boot(database, data, {'INITIAL_ADMIN_PASSWORD': 'Chosen-At-Install-1!'})
    result, _ = _boot(database, data, {'INITIAL_ADMIN_PASSWORD': 'changeme123',
                                       'INITIAL_ADMIN_PASSWORD_FILE': str(tmp_path / 'gone'),
                                       'CHILD_LOGIN': 'changeme123'})
    assert result['login'] == 401 and result['users'] == [['admin', False]]
    assert not (data / PASSWORD_FILE).exists()


def test_a_start_drops_a_file_that_opens_no_account(database, tmp_path):
    """Left by a reset that failed half-way, or a password changed on another node."""
    data = tmp_path / 'node'
    _boot(database, data, {'INITIAL_ADMIN_PASSWORD': 'Chosen-At-Install-1!'})
    (data / PASSWORD_FILE).write_text('Stale-Value-Opens-Nothing\n')
    _boot(database, data)
    assert not (data / PASSWORD_FILE).exists()


@pytest.mark.skipif(not pg_app_harness.ENABLED, reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')
def test_two_ha_nodes_starting_together_make_one_administrator_and_one_file(tmp_path):
    name = f'{pg_app_harness.SCHEMA}_adm{secrets.token_hex(2)}'
    pg_app_harness._new_schema(pg_app_harness._marker[0].cursor(), name)
    url = pg_app_harness.app_url(name)
    database = {'CHILD_DB_URI': url, 'DATABASE_URL': url, 'DATABASE_PATH': str(tmp_path / 'u.db')}
    nodes = [tmp_path / f'node{n}' for n in (0, 1)]
    procs = [_start(database, d, {'UCM_HA': '1', 'UCM_NODE_ID': f'adm-{n}'})
             for n, d in enumerate(nodes)]
    results = [_finish(p, d) for p, d in zip(procs, nodes)]
    files = [d / PASSWORD_FILE for d in nodes if (d / PASSWORD_FILE).exists()]
    assert len(files) == 1
    for result, _ in results:
        assert result['users'] == [['admin', True]]
    holder = 'adm-0' if files[0].parent == nodes[0] else 'adm-1'
    other_logs = results[1 if holder == 'adm-0' else 0][1]
    assert f'on node {holder}' in other_logs
    value = files[0].read_text().rstrip('\n')
    assert all(value not in logs for _, logs in results)

    # Changed through the other node: the holder drops its file at its next start
    other = nodes[1] if holder == 'adm-0' else nodes[0]
    result, _ = _boot(database, other, {'UCM_HA': '1', 'UCM_NODE_ID': 'adm-x',
                                        'CHILD_LOGIN': value, 'CHILD_NEW_PASSWORD': 'Chang3d-Elsewhere!'})
    assert result['change'] == 200 and files[0].exists()
    _boot(database, files[0].parent, {'UCM_HA': '1', 'UCM_NODE_ID': holder})
    assert not files[0].exists()


# ------------------------------------------------------------ in process

def test_the_generated_password_has_no_character_to_misread():
    from auth import initial_admin
    values = {initial_admin.resolve({}).value for _ in range(50)}
    assert len(values) == 50
    for value in values:
        assert len(value) == initial_admin.LENGTH
        assert not set(value) - set(initial_admin.ALPHABET)
        assert not set(value) & set('0Oo1lI')


def test_a_password_file_loses_its_line_ending_only(tmp_path):
    from auth import initial_admin
    secret = tmp_path / 'secret'
    secret.write_text(' spaced value \r\n')
    got = initial_admin.resolve({'INITIAL_ADMIN_PASSWORD_FILE': str(secret)})
    assert got.value == ' spaced value ' and not got.generated
    assert 'spaced' not in repr(got)


@pytest.fixture
def marked_user(app, tmp_path):
    """An account named by the marker, its password in tmp_path's file."""
    from auth import initial_admin
    from models import ClusterCommand, SystemConfig, User, db
    config = {'DATA_DIR': str(tmp_path)}
    with app.app_context():
        user = User(username=f'initial-{secrets.token_hex(3)}', email='i@example.test',
                    role='admin', active=True, force_password_change=True)
        user.set_password('Generated-Value-7')
        db.session.add(user)
        db.session.flush()
        SystemConfig.query.filter_by(key=initial_admin.MARKER_KEY).delete()
        db.session.add(SystemConfig(key=initial_admin.MARKER_KEY,
                                    value=json.dumps({'user_id': user.id, 'node': 'n1'})))
        db.session.commit()
        user_id = user.id
    path = tmp_path / PASSWORD_FILE
    path.write_text('Generated-Value-7\n')
    yield user_id, path, config
    with app.app_context():
        SystemConfig.query.filter_by(key=initial_admin.MARKER_KEY).delete()
        ClusterCommand.query.filter_by(kind='drop_initial_password').delete()
        User.query.filter_by(id=user_id).delete()
        db.session.commit()


def test_the_sweep_keeps_a_file_that_still_opens_the_account(app, marked_user):
    from auth import initial_admin
    _, path, config = marked_user
    with app.app_context():
        initial_admin.sweep(config)
    assert path.exists()


def test_the_sweep_drops_a_file_whose_password_was_changed_elsewhere(app, marked_user):
    from auth import initial_admin
    from models import User, db
    user_id, path, config = marked_user
    with app.app_context():
        # As another node does: the hash moves, this node's file stays behind
        from utils.password_hash import hash_password
        User.query.filter_by(id=user_id).update({'password_hash': hash_password('Changed-On-Node-2!')})
        db.session.commit()
        initial_admin.sweep(config)
    assert not path.exists()


def test_the_sweep_drops_a_file_no_marker_names(app, marked_user):
    from auth import initial_admin
    from models import SystemConfig, db
    _, path, config = marked_user
    with app.app_context():
        SystemConfig.query.filter_by(key=initial_admin.MARKER_KEY).delete()
        db.session.commit()
        initial_admin.sweep(config)
    assert not path.exists()


def test_a_change_queues_the_cluster_command_and_drops_the_file_on_commit(app, marked_user, monkeypatch):
    from auth import initial_admin
    from config.settings import Config
    from models import ClusterCommand, SystemConfig, User, db
    user_id, path, config = marked_user
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(initial_admin, 'password_file', lambda _config: path)
    with app.app_context():
        db.session.get(User, user_id).set_password('Chosen-After-Login-1!')
        assert path.exists()  # not before the commit
        db.session.commit()
        assert not path.exists()
        assert SystemConfig.query.filter_by(key=initial_admin.MARKER_KEY).first() is None
        assert ClusterCommand.query.filter_by(kind='drop_initial_password').count() == 1


def test_a_change_rolled_back_keeps_the_file_and_the_marker(app, marked_user, monkeypatch):
    from auth import initial_admin
    from models import SystemConfig, User, db
    user_id, path, config = marked_user
    monkeypatch.setattr(initial_admin, 'password_file', lambda _config: path)
    with app.app_context():
        db.session.get(User, user_id).set_password('Chosen-After-Login-1!')
        db.session.rollback()
        db.session.commit()  # a later commit of anything else
        assert path.exists()
        assert SystemConfig.query.filter_by(key=initial_admin.MARKER_KEY).first() is not None


def test_the_cluster_command_runs_the_sweep(app, monkeypatch):
    from auth import initial_admin
    from services import cluster_commands
    seen = []
    monkeypatch.setattr(initial_admin, 'sweep', lambda config: seen.append(config))
    with app.app_context():
        cluster_commands.HANDLERS[cluster_commands.DROP_INITIAL_PASSWORD](None)
    assert seen and cluster_commands.DROP_INITIAL_PASSWORD in cluster_commands.KINDS


def test_a_weak_provided_password_is_kept_and_said_without_its_value(app, caplog):
    from auth import initial_admin
    with app.app_context(), caplog.at_level('WARNING', logger='auth.initial_admin'):
        got = initial_admin.prepare({'INITIAL_ADMIN_PASSWORD': 'changeme123'})
    assert got.value == 'changeme123' and not got.generated
    assert 'does not meet the password policy' in caplog.text
    assert 'changeme123' not in caplog.text


@pytest.mark.parametrize('flag, forced', [('1', True), ('true', True), ('', False), ('0', False)])
def test_the_force_change_flag_marks_a_provided_password(flag, forced):
    from auth import initial_admin
    got = initial_admin.resolve({'INITIAL_ADMIN_PASSWORD': 'Some-Value-1!',
                                 'INITIAL_ADMIN_PASSWORD_FORCE_CHANGE': flag})
    assert got.force_change is forced and not got.generated
