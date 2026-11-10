"""Which server-side session store is used, and that the SQL store is shared.

Redis wins, then the shared database on PostgreSQL, else files; the test
configuration keeps files unless a test forces the SQL store.
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from config.settings import session_store

BACKEND = Path(__file__).resolve().parent.parent
PG_URL = os.getenv('UCM_TEST_APP_PG_URL') or os.getenv('UCM_TEST_PG_URL')


@pytest.mark.parametrize('redis, database, expected', [
    (None, 'sqlite', 'filesystem'),
    (None, 'postgresql', 'sqlalchemy'),
    ('redis://cache:6379/0', 'sqlite', 'redis'),
    ('redis://cache:6379/0', 'postgresql', 'redis'),
    (None, 'external', 'filesystem'),
])
def test_store_follows_redis_then_database(redis, database, expected):
    assert session_store(redis, database) == expected


def _settings_in_fresh_process(**env):
    """Config and TestingConfig as a process started with this environment sees them."""
    clean = {k: v for k, v in os.environ.items() if k not in ('REDIS_URL', 'DATABASE_URL')}
    clean.update(env, SECRET_KEY='x', UCM_ENV='test')
    code = ("import json; from config.settings import Config, TestingConfig; "
            "print(json.dumps([Config.SESSION_TYPE, TestingConfig.SESSION_TYPE, "
            "str(getattr(Config, 'SESSION_FILE_DIR', None))]))")
    out = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=clean,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


@pytest.mark.parametrize('env, production, testing', [
    ({}, 'filesystem', 'filesystem'),
    ({'DATABASE_URL': 'postgresql://u:p@db.invalid/ucm'}, 'sqlalchemy', 'filesystem'),
    ({'REDIS_URL': 'redis://cache.invalid:6379/0'}, 'redis', 'redis'),
    ({'REDIS_URL': 'redis://cache.invalid:6379/0',
      'DATABASE_URL': 'postgresql://u:p@db.invalid/ucm'}, 'redis', 'redis'),
])
def test_configuration_picks_the_store(env, production, testing):
    got_production, got_testing, directory = _settings_in_fresh_process(**env)
    assert (got_production, got_testing) == (production, testing)
    if production == 'sqlalchemy':
        assert directory == 'None', 'the SQL store has no session directory'


@pytest.fixture
def two_nodes(monkeypatch):
    """Two applications on one PostgreSQL schema, both with the SQL session store."""
    import psycopg

    from config.settings import TestingConfig
    from tests import pg_app_harness
    from utils.db_url import sqlalchemy_url

    schema = f'ucm_sess_{uuid.uuid4().hex[:8]}'
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    sep = '&' if '?' in PG_URL else '?'
    url = f'{PG_URL}{sep}options=-csearch_path%3D{schema}'
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', sqlalchemy_url(url))
    monkeypatch.setattr(TestingConfig, 'DATABASE_TYPE', 'postgresql')
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
    # The shared-suite wrapper would give each application its own schema
    pg_app_harness._creating_session_app.append(True)
    node_a = None
    try:
        from app import create_app
        node_a = create_app('testing')
        node_b = create_app('testing')
        yield node_a, node_b
    finally:
        pg_app_harness._creating_session_app.pop()
        from models import db
        with node_a.app_context():
            db.session.remove()
            db.engine.dispose()
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the two-node session test')
def test_a_session_opened_on_one_node_is_valid_on_the_other(two_nodes):
    from sqlalchemy import text

    from models import db
    from tests.conftest import clear_admin_password_flag

    node_a, node_b = two_nodes
    assert node_a.config['SESSION_TYPE'] == 'sqlalchemy'
    clear_admin_password_flag(node_a)
    client_a, client_b = node_a.test_client(), node_b.test_client()

    login = client_a.post('/api/v2/auth/login/password', content_type='application/json',
                          data=json.dumps({'username': 'admin', 'password': 'changeme123'}))
    assert login.status_code == 200, login.data
    cookie = client_a.get_cookie('session')
    client_b.set_cookie('session', cookie.value)
    assert client_b.get('/api/v2/account/profile').status_code == 200

    with node_b.app_context():
        assert db.session.execute(text('SELECT COUNT(*) FROM flask_sessions')).scalar() >= 1
        db.session.execute(text("UPDATE flask_sessions SET expiry = '2000-01-01'"))
        db.session.commit()
        from services.session_cleanup_task import SessionCleanupTask
        SessionCleanupTask.execute()
        assert db.session.execute(text('SELECT COUNT(*) FROM flask_sessions')).scalar() == 0
    assert client_b.get('/api/v2/account/profile').status_code == 401
    assert client_a.get('/api/v2/account/profile').status_code == 401


@pytest.fixture
def sql_store_app(monkeypatch, tmp_path):
    """One application with the SQL session store on a file database."""
    from config.settings import TestingConfig
    from tests import pg_app_harness

    if pg_app_harness.ENABLED:
        pytest.skip('file-database fixture, not meaningful in PostgreSQL mode')
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "s.db"}')
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
    from app import create_app
    application = create_app('testing')
    application.config['PROPAGATE_EXCEPTIONS'] = False
    yield application
    from models import db
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


def test_a_failing_request_does_not_commit_its_pending_work_through_the_store(sql_store_app):
    from models import db
    from models.system_config import SystemConfig
    from tests.conftest import clear_admin_password_flag

    app = sql_store_app
    assert app.config['SESSION_TYPE'] == 'sqlalchemy'

    @app.route('/zz-boom', methods=['POST'])
    def zz_boom():
        db.session.add(SystemConfig(key='zz_probe', value='x'))
        db.session.flush()
        raise RuntimeError('boom')

    clear_admin_password_flag(app)
    client = app.test_client()
    login = client.post('/api/v2/auth/login/password', content_type='application/json',
                        data=json.dumps({'username': 'admin', 'password': 'changeme123'}))
    assert login.status_code == 200, login.data
    assert client.post('/zz-boom').status_code == 500

    with app.app_context():
        assert SystemConfig.query.filter_by(key='zz_probe').count() == 0


def test_the_store_never_waits_on_the_request_pool(monkeypatch, tmp_path):
    """A request holding its one pool connection can still save its session."""
    from config.settings import TestingConfig
    from tests import pg_app_harness
    from tests.conftest import clear_admin_password_flag

    if pg_app_harness.ENABLED:
        pytest.skip('file-database fixture, not meaningful in PostgreSQL mode')
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "p.db"}')
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_ENGINE_OPTIONS',
                        {'pool_size': 1, 'max_overflow': 0, 'pool_timeout': 2})
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
    from app import create_app
    from models import db
    app = create_app('testing')
    app.config['PROPAGATE_EXCEPTIONS'] = False
    try:
        clear_admin_password_flag(app)
        client = app.test_client()
        login = client.post('/api/v2/auth/login/password', content_type='application/json',
                            data=json.dumps({'username': 'admin', 'password': 'changeme123'}))
        assert login.status_code == 200, login.data
        assert client.get('/api/v2/account/profile').status_code == 200
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def _expiry_indexed(app):
    from sqlalchemy import inspect

    from models import db
    with app.app_context():
        return 'ix_flask_sessions_expiry' in {
            ix['name'] for ix in inspect(db.engine).get_indexes('flask_sessions')}


def test_a_fresh_sqlite_store_has_the_expiry_index(sql_store_app):
    assert _expiry_indexed(sql_store_app)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the fresh-schema index test')
def test_a_fresh_postgresql_store_has_the_expiry_index(two_nodes):
    assert _expiry_indexed(two_nodes[0])


@pytest.mark.parametrize('method, args', [
    ('_delete_expired_sessions', ()),
    ('_retrieve_session_data', ('sid',)),
    ('_delete_session', ('sid',)),
    ('_upsert_session', (__import__('datetime').timedelta(hours=1), {'a': 1}, 'sid')),
])
def test_store_methods_retry_a_transient_database_error(sql_store_app, monkeypatch, method, args):
    from sqlalchemy.exc import OperationalError

    app = sql_store_app
    interface = app.session_interface
    real, calls = interface._store, []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError('SELECT 1', {}, Exception('connection lost'))
        return real()

    monkeypatch.setattr(interface, '_store', flaky)
    monkeypatch.setattr('time.sleep', lambda *_: None)
    with app.app_context():
        getattr(interface, method)(*args)
    assert len(calls) == 2
