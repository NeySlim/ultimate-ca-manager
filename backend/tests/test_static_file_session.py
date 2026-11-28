"""A static file answers without the session (invariant I12), on each session store.

A file the build ships (hashed asset, favicon, font) is cacheable by anyone: its
answer never reads or writes the session store, never carries Set-Cookie nor Vary: Cookie,
and leaves the signed-in account's session as it was. index.html, the guide and the API keep
theirs, refreshed on each request; the security headers and the admin allowlist still apply.
"""
import contextlib
import json
from pathlib import Path

import pytest

from tests.app_disposal import dispose_app
from tests.header_guard import guarded
from tests.redis_support import needs_redis

ASSET = '/assets/vendor-AbC123.js'
FILES = (ASSET, '/favicon.ico', '/manifest.webmanifest', '/fonts/inter-latin-400.woff2')
INDEX = '<!doctype html>\n<html lang="en"><body><div id="root"></div></body></html>\n'
PREFIX = 'ucm:session:'
STORE_CALLS = ('_retrieve_session_data', '_upsert_session', '_delete_session', '_record_exists',
               '_remove_if_present', '_purge_expired', '_delete_expired_sessions')
# The security headers an asset carried before the change, as the app sets them
SECURITY_HEADERS = {
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy': (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self' wss: ws:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"),
    'Strict-Transport-Security': 'max-age=31536000',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
}


@pytest.fixture
def frontend(tmp_path, monkeypatch):
    """A build: index.html, the files the browser fetches, and HTML pages served by rule."""
    import api.ui_routes as ui
    root = tmp_path / 'dist'
    for sub in ('assets', 'fonts', 'guide-prerender/en', 'guide'):
        (root / sub).mkdir(parents=True)
    (root / 'index.html').write_text(INDEX)
    (root / 'assets' / 'vendor-AbC123.js').write_text('export default 1;')
    (root / 'favicon.ico').write_bytes(b'\x00\x00\x01\x00')
    (root / 'manifest.webmanifest').write_text('{"name": "UCM"}')
    (root / 'fonts' / 'inter-latin-400.woff2').write_bytes(b'wOF2')
    # Present on disk, yet answered by the guide's rule (index.html), never as files
    (root / 'guide-prerender' / 'en' / 'cas.html').write_text(INDEX)
    (root / 'guide' / 'cas.html').write_text(INDEX)
    monkeypatch.setattr(ui, 'FRONTEND_DIR', root)
    return root


@contextlib.contextmanager
def _store_app(kind, monkeypatch, tmp_path, request):
    from config.settings import TestingConfig
    from tests import pg_app_harness
    from tests.conftest import clear_admin_password_flag
    from tests.fresh_app import fresh_app
    if kind == 'filesystem':
        with fresh_app() as application:
            yield application
        return
    if pg_app_harness.ENABLED:
        pytest.skip('file-database application, not meaningful in PostgreSQL mode')
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "store.db"}')
    if kind == 'sqlalchemy':
        monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
        monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
        # Registers the expired-session purge hook, which the spy makes run on every request
        monkeypatch.setattr(TestingConfig, 'SESSION_CLEANUP_N_REQUESTS', 1, raising=False)
    else:
        from websocket import events
        server = request.getfixturevalue('redis_server')
        server.client().flushdb()
        monkeypatch.setenv('REDIS_URL', server.url())
        monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'redis')
        monkeypatch.setattr(TestingConfig, 'SESSION_REDIS', server.url(), raising=False)
        monkeypatch.setattr(TestingConfig, 'SESSION_KEY_PREFIX', PREFIX, raising=False)
        monkeypatch.setattr(events, '_message_queue', lambda _app: None)
    from app import create_app
    application = guarded(create_app('testing'))
    application.config['PROPAGATE_EXCEPTIONS'] = False
    clear_admin_password_flag(application)
    try:
        yield application
    finally:
        dispose_app(application)
        from models import db
        table = db.metadata.tables.get('flask_sessions')
        if table is not None:
            db.metadata.remove(table)


@pytest.fixture(params=['filesystem', 'sqlalchemy', pytest.param('redis', marks=needs_redis)])
def store_app(request, monkeypatch, tmp_path, frontend):
    monkeypatch.setenv('UCM_HSTS_ENABLED', '1')
    monkeypatch.setenv('UCM_HSTS_MAX_AGE', '31536000')
    monkeypatch.setenv('UCM_HSTS_INCLUDE_SUBDOMAINS', '0')
    with _store_app(request.param, monkeypatch, tmp_path, request) as application:
        yield application


@pytest.fixture
def spy(store_app, monkeypatch):
    """Every call into the store, and the sessions it opened (whether a hook read them)."""
    import utils.session_store as store
    iface = store_app.session_interface
    calls, opened = [], []
    for name in STORE_CALLS:
        original = getattr(iface, name, None)
        if original is None:
            continue

        def counted(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)
        monkeypatch.setattr(iface, name, counted)
    real_open = iface.open_session

    def open_session(app, request):
        session = real_open(app, request)
        opened.append(session)
        return session
    monkeypatch.setattr(iface, 'open_session', open_session)
    # The SQL store's purge would ride every request
    if getattr(iface, 'cleanup_n_requests', None):
        monkeypatch.setattr(store.random, 'randint', lambda a, b: 0)
    return _Spy(calls, opened)


class _Spy:
    def __init__(self, calls, opened):
        self.calls, self.opened = calls, opened

    def reset(self):
        self.calls.clear()
        self.opened.clear()


def _login(application):
    client = application.test_client()
    r = client.post('/api/v2/auth/login/password', content_type='application/json',
                    data=json.dumps({'username': 'admin', 'password': 'changeme123'}))
    assert r.status_code == 200, r.data
    return client


def _vary(response):
    return {v.strip().lower() for v in response.headers.get('Vary', '').split(',') if v.strip()}


def _records(application):
    """The session records the store holds."""
    kind = application.config['SESSION_TYPE']
    iface = application.session_interface
    if kind == 'filesystem':
        return sorted(p.name for p in Path(iface.cache._path).iterdir())
    if kind == 'redis':
        return sorted(k.decode() for k in iface.client.keys('*'))
    from sqlalchemy import text
    from models import db
    with application.app_context():
        return sorted(r[0] for r in db.session.execute(text('SELECT session_id FROM flask_sessions')))


@pytest.mark.parametrize('path', FILES)
def test_a_signed_in_file_request_leaves_the_session_alone(store_app, spy, path):
    client = _login(store_app)
    before = client.get_cookie('session').value
    stored = _records(store_app)
    spy.reset()
    r = client.get(path)
    assert r.status_code == 200, r.data[:200]
    assert 'Set-Cookie' not in r.headers
    assert 'cookie' not in _vary(r)
    if path == ASSET:
        assert r.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert spy.calls == []
    assert spy.opened and not any(s.accessed for s in spy.opened), 'a hook read the session'
    assert _records(store_app) == stored
    # The account's session is untouched: the API still serves it, under the same cookie
    assert client.get_cookie('session').value == before
    assert client.get('/api/v2/account/profile').status_code == 200


def test_a_file_request_without_a_session_creates_none(store_app, spy):
    client = store_app.test_client()
    stored = _records(store_app)
    spy.reset()
    r = client.get(ASSET)
    assert r.status_code == 200
    assert 'Set-Cookie' not in r.headers
    assert 'cookie' not in _vary(r)
    assert client.get_cookie('session') is None
    assert spy.calls == []
    assert _records(store_app) == stored


def test_a_hook_writing_to_a_file_request_session_stores_nothing(store_app, spy):
    """Even written to by a hook, a file's session is neither stored nor sent."""
    from flask import request, session

    @store_app.before_request
    def write_on_files():
        if request.path == ASSET:
            session['seen'] = 1
    anonymous = store_app.test_client()
    client = _login(store_app)
    before = client.get_cookie('session').value
    stored = _records(store_app)
    spy.reset()
    for c in (anonymous, client):
        r = c.get(ASSET)
        assert r.status_code == 200
        assert 'Set-Cookie' not in r.headers
        assert 'cookie' not in _vary(r)
    assert anonymous.get_cookie('session') is None
    assert client.get_cookie('session').value == before
    assert spy.calls == []
    assert _records(store_app) == stored


# index.html, a missing asset (index.html in its place), the guide's pages and the API
SESSION_PATHS = ('/', '/index.html', '/certificates', '/assets/gone-XyZ987.js', '/guide-prerender/en/cas.html',
                 '/guide/cas.html', '/api/v2/account/profile')


@pytest.mark.parametrize('path', SESSION_PATHS)
def test_index_guide_and_api_keep_their_session(store_app, spy, path):
    client = _login(store_app)
    spy.reset()
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code)
    # Refreshed on each request (SESSION_REFRESH_EACH_REQUEST): written and sent again
    assert 'session=' in r.headers.get('Set-Cookie', ''), path
    assert 'Expires=' in r.headers['Set-Cookie']
    assert 'cookie' in _vary(r)
    assert '_upsert_session' in spy.calls
    if store_app.config['SESSION_TYPE'] == 'sqlalchemy':
        assert '_purge_expired' in spy.calls, 'the purge hook is not armed'


def test_security_headers_still_apply_to_a_file(store_app):
    r = store_app.test_client().get(ASSET)
    assert r.status_code == 200
    assert {name: r.headers.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS


def test_the_admin_allowlist_still_refuses_a_file(store_app):
    from models import SystemConfig, db
    from utils import admin_allowlist
    with store_app.app_context():
        db.session.add(SystemConfig(key=admin_allowlist.CONFIG_KEY, value='10.0.0.0/8'))
        db.session.commit()
    admin_allowlist.invalidate_cache()
    try:
        client = store_app.test_client()
        page = client.get('/', environ_base={'REMOTE_ADDR': '203.0.113.9'})
        refused = client.get(ASSET, environ_base={'REMOTE_ADDR': '203.0.113.9'})
        assert refused.status_code == page.status_code == 403
        assert refused.data == page.data
        assert admin_allowlist.REFUSAL_MESSAGE.encode() in refused.data
        assert refused.headers['Content-Type'] == 'text/plain; charset=utf-8'
        assert 'Set-Cookie' not in refused.headers
        admitted = client.get(ASSET, environ_base={'REMOTE_ADDR': '10.1.2.3'})
        assert admitted.status_code == 200 and 'Set-Cookie' not in admitted.headers
    finally:
        with store_app.app_context():
            SystemConfig.query.filter_by(key=admin_allowlist.CONFIG_KEY).delete()
            db.session.commit()
        admin_allowlist.invalidate_cache()
