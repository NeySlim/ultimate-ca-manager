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
