"""Sessions on a real Redis server, shared by two applications.

With REDIS_URL set the sessions live in Redis (not in files, not in the SQL table):
a session opened on one node serves the other, ends on both at logout, expires,
and closes with a credential change while the current one survives under a new
identifier. Redis down: requests carrying a session fail (500), nothing falls back
to another store; Redis back: the nodes serve again without a restart.
"""
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pyotp
import pytest

from models import SystemConfig, User, db
from tests.redis_support import RedisServer, guard_hits, needs_redis, sandbox_env

pytestmark = needs_redis

BACKEND = Path(__file__).resolve().parent.parent
PREFIX = 'ucm:session:'
PASSWORD = 'Redis-Sess10ns-42!'
NEW_PASSWORD = 'Redis-Changed-77!'
PG_URL = os.getenv('UCM_TEST_APP_PG_URL') or os.getenv('UCM_TEST_PG_URL')


def _post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type='application/json')


def _sid(c):
    cookie = c.get_cookie('session')
    return cookie.value if cookie else None


def _status(c):
    return c.get('/api/v2/account/profile').status_code


def redis_apps(monkeypatch, tmp_path, url, count=2):
    """``count`` applications on one SQLite file, with the Redis session store at ``url``,
    configured as config.settings does when REDIS_URL is set at startup."""
    from config.settings import TestingConfig
    from tests import pg_app_harness
    from websocket import events
    if pg_app_harness.ENABLED:
        pytest.skip('file-database nodes, not meaningful in PostgreSQL mode')
    monkeypatch.setenv('REDIS_URL', url)
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "redis-nodes.db"}')
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'redis')
    monkeypatch.setattr(TestingConfig, 'SESSION_REDIS', url, raising=False)
    monkeypatch.setattr(TestingConfig, 'SESSION_KEY_PREFIX', PREFIX, raising=False)
    # Socket.IO is one per process: the event path is proven in test_redis_events.py
    monkeypatch.setattr(events, '_message_queue', lambda _app: None)
    from app import create_app
    from tests.conftest import clear_admin_password_flag
    nodes = [create_app('testing') for _ in range(count)]
    for node in nodes:
        node.config['PROPAGATE_EXCEPTIONS'] = False
    clear_admin_password_flag(nodes[0])
    return nodes


def dispose(*nodes):
    for node in nodes:
        with node.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture
def store(redis_server):
    client = redis_server.client()
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def nodes(store, redis_server, monkeypatch, tmp_path):
    created = redis_apps(monkeypatch, tmp_path, redis_server.url())
    yield created
    dispose(*created)


def _make_user(node, totp=False):
    with node.app_context():
        user = User(username=f'redis-{uuid.uuid4().hex[:8]}', role='operator',
                    email=f'{uuid.uuid4().hex[:8]}@example.test')
        user.set_password(PASSWORD)
        if totp:
            user.totp_secret = pyotp.random_base32()
            user.totp_confirmed = True
        db.session.add(user)
        db.session.commit()
        info = {'id': user.id, 'username': user.username, 'secret': user.totp_secret}
        db.session.remove()
        return info


def _login(node, user, password=PASSWORD):
    c = node.test_client()
    r = _post(c, '/api/v2/auth/login/password', {'username': user['username'], 'password': password})
    assert r.status_code == 200, r.data
    if user.get('secret'):
        with node.app_context():
            db.session.execute(db.update(User).where(User.id == user['id']).values(totp_last_step=None))
            db.session.commit()
            db.session.remove()
        r = _post(c, '/api/v2/auth/login/2fa', {'code': pyotp.TOTP(user['secret']).now()})
        assert r.status_code == 200, r.data
    assert _status(c) == 200
    return c


def _on(node, c):
    """A client of ``node`` holding the cookie of ``c``."""
    other = node.test_client()
    other.set_cookie('session', _sid(c))
    return other


def _session_files():
    from config.settings import TestingConfig
    directory = Path(TestingConfig.DATA_DIR) / 'sessions'
    return set(directory.iterdir()) if directory.is_dir() else set()


# ---------------------------------------------------------------- 1. the store


def test_with_redis_the_session_lives_in_redis_only(nodes, store):
    from sqlalchemy import inspect
    node_a, _node_b = nodes
    assert node_a.config['SESSION_TYPE'] == 'redis'
    files = _session_files()
    c = _login(node_a, {'username': 'admin'}, 'changeme123')
    assert store.exists(PREFIX + _sid(c))
    assert 86000 < store.ttl(PREFIX + _sid(c)) <= 86400  # PERMANENT_SESSION_LIFETIME
    assert _session_files() == files
    with node_a.app_context():
        assert 'flask_sessions' not in inspect(db.engine).get_table_names()


def _store_in_fresh_process(root, redis_url, database_url=''):
    """The store an application started with this environment uses, and what a login
    leaves in the SQL table (None: no table). Runs in the sandbox of redis_support."""
    code = '''
import json
from config.settings import Config, TestingConfig
if Config.DATABASE_TYPE == 'postgresql':
    TestingConfig.SQLALCHEMY_DATABASE_URI = Config.SQLALCHEMY_DATABASE_URI
    TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = dict(Config.SQLALCHEMY_ENGINE_OPTIONS)
from app import create_app
from models import db, User
app = create_app('testing')
with app.app_context():
    User.query.filter_by(username='admin').update({'force_password_change': False})
    db.session.commit()
c = app.test_client()
r = c.post('/api/v2/auth/login/password', json={'username': 'admin', 'password': 'changeme123'})
rows = None
with app.app_context():
    from sqlalchemy import inspect, text
    if 'flask_sessions' in inspect(db.engine).get_table_names():
        rows = db.session.execute(text('SELECT COUNT(*) FROM flask_sessions')).scalar()
cookie = c.get_cookie('session')
files = sorted(p.name for p in (Config.DATA_DIR / 'sessions').glob('*'))
print(json.dumps([app.config['SESSION_TYPE'], r.status_code, cookie.value if cookie else None, rows, files]))
'''
    env = sandbox_env(root, REDIS_URL=redis_url, DATABASE_URL=database_url)
    proc = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=env, start_new_session=True,
                          capture_output=True, text=True, timeout=300)
    assert not guard_hits(root), guard_hits(root)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_a_process_started_with_redis_url_keeps_its_sessions_in_redis(store, redis_server, tmp_path):
    """No configuration patched: settings and app read REDIS_URL as a real start does."""
    from tests import pg_app_harness
    if pg_app_harness.ENABLED:
        pytest.skip('file-database process, not meaningful in PostgreSQL mode')
    store_type, status, sid, rows, files = _store_in_fresh_process(tmp_path, redis_server.url())
    assert (store_type, status) == ('redis', 200)
    assert sid and store.exists(PREFIX + sid)
    assert rows is None, 'no session table without the SQL store'
    assert files == [], 'no session file'


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the Redis-over-SQL priority test')
def test_on_postgresql_redis_wins_over_the_session_table(store, redis_server, tmp_path):
    """docs/HA.md: sessions in PostgreSQL, in Redis when REDIS_URL is set."""
    import psycopg
    schema = f'ucm_redis_{uuid.uuid4().hex[:8]}'
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        sep = '&' if '?' in PG_URL else '?'
        store_type, status, sid, rows, files = _store_in_fresh_process(
            tmp_path, redis_server.url(), f'{PG_URL}{sep}options=-csearch_path%3D{schema}')
        assert (store_type, status) == ('redis', 200)
        assert sid and store.exists(PREFIX + sid)
        assert not rows and files == [], 'neither the session table nor a file holds a session'
    finally:
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()


# ---------------------------------------------------------------- 2. one session, two nodes


def test_a_session_of_a_serves_b_and_a_logout_on_b_ends_it_on_a(nodes, store):
    node_a, node_b = nodes
    user = _make_user(node_a)
    on_a = _login(node_a, user)
    on_b = _on(node_b, on_a)
    assert _status(on_b) == 200
    assert _post(on_b, '/api/v2/auth/logout').status_code == 200
    assert not store.exists(PREFIX + _sid(on_a))
    assert _status(on_a) == 401
    assert _status(on_b) == 401


def test_the_redis_entry_expires_with_the_session_lifetime(nodes, store):
    node_a, node_b = nodes
    for node in nodes:
        node.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=1)
    user = _make_user(node_a)
    on_a = _login(node_a, user)
    assert 0 < store.ttl(PREFIX + _sid(on_a)) <= 1
    time.sleep(1.5)
    assert not store.exists(PREFIX + _sid(on_a))
    assert _status(_on(node_b, on_a)) == 401


def test_a_session_past_the_inactivity_timeout_is_refused_and_dropped(nodes, store):
    node_a, node_b = nodes
    user = _make_user(node_a)
    on_a = _login(node_a, user)
    with node_a.app_context():
        db.session.add(SystemConfig(key='session_timeout', value='1'))
        db.session.commit()
    try:
        time.sleep(1.5)
        on_b = _on(node_b, on_a)
        assert _status(on_b) == 401
        assert not store.exists(PREFIX + _sid(on_a))
    finally:
        with node_a.app_context():
            SystemConfig.query.filter_by(key='session_timeout').delete()
            db.session.commit()


# ---------------------------------------------------------------- 3. closing the other sessions


def _change_password(c):
    return _post(c, '/api/v2/account/password',
                 {'current_password': PASSWORD, 'new_password': NEW_PASSWORD})


def _revoke_all(c):
    return _post(c, '/api/v2/account/sessions/revoke-all')


@pytest.mark.parametrize('change', [_change_password, _revoke_all], ids=['password', 'revoke-all'])
def test_a_credential_change_on_a_closes_the_sessions_on_b(nodes, store, change):
    """The other sessions are refused on every node and their entries go at their next
    request; the current one survives under a new identifier, the old entry deleted."""
    node_a, node_b = nodes
    user = _make_user(node_a)
    others = [_login(node_b, user), _login(node_b, user)]
    this = _login(node_a, user)
    before = _sid(this)
    assert change(this).status_code == 200
    after = _sid(this)
    assert after != before
    assert not store.exists(PREFIX + before) and store.exists(PREFIX + after)
    assert _status(_on(node_b, this)) == 200
    for other in others:
        sid = _sid(other)
        assert store.exists(PREFIX + sid)  # closed by version, not deleted yet
        assert _status(other) == 401
        assert not store.exists(PREFIX + sid)


def test_the_census_counts_the_sessions_in_redis(nodes, store):
    from utils.session_census import count_sessions
    node_a, node_b = nodes
    user = _make_user(node_a)
    other_user = _make_user(node_a)
    _login(node_b, user)
    _login(node_a, user)
    _login(node_b, other_user)
    with node_a.test_request_context():
        account = db.session.get(User, user['id'])
        assert count_sessions(account, 0) == 2
        assert count_sessions(account, 1) == 0
        assert count_sessions(db.session.get(User, other_user['id']), 0) == 1
        db.session.remove()


def test_a_totp_change_on_a_counts_and_closes_the_redis_sessions_of_b(nodes, store):
    node_a, node_b = nodes
    user = _make_user(node_a, totp=True)
    others = [_login(node_b, user), _login(node_b, user)]
    this = _login(node_a, user)
    before = _sid(this)
    with node_a.app_context():
        db.session.execute(db.update(User).where(User.id == user['id']).values(totp_last_step=None))
        db.session.commit()
        db.session.remove()
    r = _post(this, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(user['secret']).now()})
    assert r.status_code == 200, r.data
    assert r.get_json()['meta']['other_sessions_closed'] == 2
    assert not store.exists(PREFIX + before) and store.exists(PREFIX + _sid(this))
    sids = [_sid(other) for other in others]
    assert [_status(other) for other in others] == [401, 401]
    assert not any(store.exists(PREFIX + sid) for sid in sids)
    assert _status(this) == 200


# ---------------------------------------------------------------- 5. Redis down, then back


@pytest.fixture
def private_redis(tmp_path):
    server = RedisServer(tmp_path / 'r').start()
    yield server
    server.close()


def test_redis_down_refuses_every_session_request_and_falls_back_nowhere(private_redis, monkeypatch,
                                                                          tmp_path):
    node_a, node_b = redis_apps(monkeypatch, tmp_path, private_redis.url())
    try:
        user = _make_user(node_a)
        on_a = _login(node_a, user)
        files = _session_files()
        private_redis.stop()
        assert _status(_on(node_b, on_a)) == 500
        assert _status(on_a) == 500
        fresh = node_a.test_client()
        r = _post(fresh, '/api/v2/auth/login/password', {'username': user['username'], 'password': PASSWORD})
        assert r.status_code == 500
        assert _status(fresh) != 200
        assert _session_files() == files
        assert node_a.test_client().get('/api/v2/health').status_code != 500  # no cookie: no store read
        private_redis.start()
        # No persistence: the session is gone, refused cleanly; a new one works on both nodes
        assert _status(on_a) == 401
        again = _login(node_a, user)
        assert _status(_on(node_b, again)) == 200
    finally:
        dispose(node_a, node_b)


def test_a_node_started_while_redis_is_down_keeps_redis(private_redis, monkeypatch, tmp_path):
    private_redis.stop()
    node_a, node_b = redis_apps(monkeypatch, tmp_path, private_redis.url())
    try:
        assert node_a.config['SESSION_TYPE'] == 'redis'
        user = _make_user(node_a)
        c = node_a.test_client()
        r = _post(c, '/api/v2/auth/login/password', {'username': user['username'], 'password': PASSWORD})
        assert r.status_code == 500
        private_redis.start()
        on_a = _login(node_a, user)
        assert private_redis.client().exists(PREFIX + _sid(on_a))
        assert _status(_on(node_b, on_a)) == 200
    finally:
        dispose(node_a, node_b)
