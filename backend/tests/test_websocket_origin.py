"""Origins of the Socket.IO channel (#453): the admin base URL counts as soon as it is stored, a
default port is the same origin as none, a refused origin answers 403 before any upgrade (polling
and websocket) with a bounded number of warnings, a request without Origin is unchanged, and no
origin is ever taken from Host, X-Forwarded-Host or the protocol base URL. The API's CORS takes
the same live origins without this host's start names."""
import base64
import logging
import os
import socket
import threading
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from gevent import pywsgi

from models import SystemConfig, db
from websocket import origin_gate

POLL = '/socket.io/?EIO=4&transport=polling'
WS = '/socket.io/?EIO=4&transport=websocket'
PROXY = 'https://proxy.ws-origin.example.test'
OTHER = 'https://other.ws-origin.example.test'
FOREIGN = 'https://evil.ws-origin.example.test'
EXTRA = 'https://extra.ws-origin.example.test'
PROTOCOL = 'http://pki.ws-origin.example.test'


def _read(app, key):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row is not None else None


def _store(app, key, value):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if value is None:
            if row is not None:
                db.session.delete(row)
        elif row is None:
            db.session.add(SystemConfig(key=key, value=value))
        else:
            row.value = value
        db.session.commit()


@pytest.fixture
def setting(app):
    saved = {}

    def put(key, value):
        saved.setdefault(key, _read(app, key))
        _store(app, key, value)
    yield put
    for key, value in saved.items():
        _store(app, key, value)


@pytest.fixture(autouse=True)
def fresh_warnings():
    origin_gate._rejections.clear()
    origin_gate._window.clear()
    yield
    origin_gate._rejections.clear()
    origin_gate._window.clear()


def _poll(client, origin=None, **headers):
    if origin is not None:
        headers['Origin'] = origin
    return client.get(POLL, headers=headers)


def _websocket(client, origin):
    return client.get(WS, headers={
        'Origin': origin, 'Upgrade': 'websocket', 'Connection': 'Upgrade',
        'Sec-WebSocket-Key': base64.b64encode(os.urandom(16)).decode(),
        'Sec-WebSocket-Version': '13'})


def _origins(app):
    with app.test_request_context('/'):
        from utils.public_endpoints import get_cors_origins
        return get_cors_origins()


def _ws_origins(app):
    with app.test_request_context('/'):
        from utils.public_endpoints import get_websocket_origins
        return get_websocket_origins()


def _api_allows(client, origin):
    r = client.options('/api/v2/settings/general', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'PATCH'})
    allowed = r.headers.get('Access-Control-Allow-Origin')
    if allowed is not None:
        assert r.headers.get('Access-Control-Allow-Credentials') == 'true'
    else:
        assert r.headers.get('Access-Control-Allow-Credentials') is None
    return allowed == origin


@pytest.mark.parametrize('raw, expected', [
    ('https://H.Example.test:443', 'https://h.example.test'),
    ('http://h.example.test:80/', 'http://h.example.test'),
    (' HTTPS://h.example.test:8443// ', 'https://h.example.test:8443'),
    ('http://h.example.test:443', 'http://h.example.test:443'),
    ('https://h.example.test:80', 'https://h.example.test:80'),
    ('https://[::1]:443', 'https://[::1]'),
    ('https://[::1]:8443', 'https://[::1]:8443'),
])
def test_an_origin_is_serialized_as_rfc_6454_says(raw, expected):
    from utils.public_endpoints import normalize_origin
    assert normalize_origin(raw) == expected


@pytest.mark.parametrize('raw', [
    None, 42, '', '*', ' * ', 'null', 'https://*.example.test', '.*', 'https://.*\\.example\\.test',
    'ftp://h.example.test', 'https://h.example.test/path', 'https://u:p@h.example.test',
    'https://h.example.test?x=1', 'h.example.test', 'https://', 'https://h.example.test:99999',
])
def test_anything_but_an_explicit_origin_is_none(raw):
    from utils.public_endpoints import normalize_origin
    assert normalize_origin(raw) is None


def test_a_base_url_set_after_the_start_is_accepted_and_one_replaced_is_refused(app, client,
                                                                                setting):
    setting('base_url', PROXY)
    assert _poll(client, PROXY).status_code == 200
    setting('base_url', OTHER)
    assert _poll(client, PROXY).status_code == 403
    assert _poll(client, OTHER).status_code == 200


def test_a_default_port_is_the_same_origin(app, client, setting, monkeypatch):
    setting('base_url', PROXY + ':443')
    monkeypatch.setenv('CORS_EXTRA_ORIGINS', f'{EXTRA}:443/, *, https://.*\\.example\\.test')
    for origin in (PROXY, PROXY + ':443', EXTRA, EXTRA + ':443'):
        assert _poll(client, origin).status_code == 200, origin
    for listed in (_origins(app), _ws_origins(app)):
        assert {PROXY, EXTRA} <= set(listed)
        assert not [o for o in listed if o.endswith((':443', ':80')) or '*' in o], listed


def test_an_ipv6_extra_origin_opens_the_websocket_and_not_the_api(app, client, monkeypatch):
    # Flask-CORS reads brackets as a pattern: only the WebSocket compares an IPv6 origin
    monkeypatch.setenv('CORS_EXTRA_ORIGINS', 'https://[2001:DB8:0::1]:8443')
    v6 = 'https://[2001:db8::1]:8443'
    assert v6 in _ws_origins(app)
    assert _poll(client, v6).status_code == 200
    assert not [o for o in _origins(app) if '[' in o]
    assert not _api_allows(client, v6)


def test_no_http_origin_comes_from_the_settings(app, client, setting, monkeypatch):
    monkeypatch.delenv('CORS_EXTRA_ORIGINS', raising=False)
    setting('protocol_base_url', PROTOCOL)
    assert _poll(client, PROTOCOL).status_code == 403
    assert not _api_allows(client, PROTOCOL)
    # A row written outside the API (restore, import) is not trusted to be HTTPS
    setting('base_url', 'http://proxy.ws-origin.example.test')
    assert _poll(client, 'http://proxy.ws-origin.example.test').status_code == 403
    for listed in (_origins(app), _ws_origins(app)):
        assert not [o for o in listed if o.startswith('http://')], listed


def test_a_start_name_opens_the_websocket_and_not_the_api(app, client, monkeypatch):
    # FQDN, short name and $HOSTNAME (a container id, a pod name) never widen the API's CORS
    start = 'https://ucm-7f9c4.ws-origin.example.test:8443'
    monkeypatch.setitem(app.config, 'CORS_ORIGINS', list(app.config['CORS_ORIGINS']) + [start])
    assert _poll(client, start).status_code == 200
    assert start in _ws_origins(app)
    assert start not in _origins(app)
    assert not _api_allows(client, start)


def test_the_api_cors_allows_the_base_url_and_the_extras(app, client, setting, monkeypatch):
    setting('base_url', PROXY)
    monkeypatch.setenv('CORS_EXTRA_ORIGINS', EXTRA + ':443')
    for origin in (PROXY, EXTRA):
        r = client.get('/api/v2/auth/methods', headers={'Origin': origin})
        assert r.headers.get('Access-Control-Allow-Origin') == origin
    r = client.get('/api/v2/auth/methods', headers={'Origin': FOREIGN})
    assert r.headers.get('Access-Control-Allow-Origin') is None


def test_a_foreign_origin_gets_403_before_any_upgrade_and_one_warning(app, client, setting,
                                                                       caplog):
    setting('base_url', PROXY)
    with caplog.at_level(logging.WARNING, logger='websocket.origin_gate'):
        for _ in range(3):
            assert _poll(client, FOREIGN).status_code == 403
            r = _websocket(client, FOREIGN)
            assert r.status_code == 403
            assert 'Sec-WebSocket-Accept' not in r.headers
        assert _poll(client, OTHER).status_code == 403
    warned = [r.getMessage() for r in caplog.records if r.name == 'websocket.origin_gate']
    assert len(warned) == 2, warned
    assert 'Rejected WebSocket origin' in warned[0] and FOREIGN in warned[0]
    assert OTHER in warned[1]


def test_the_warnings_have_one_ceiling_for_every_origin(app, client, setting, monkeypatch,
                                                         caplog):
    clock = [1000.0]
    monkeypatch.setattr(origin_gate, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    setting('base_url', PROXY)
    with caplog.at_level(logging.WARNING, logger='websocket.origin_gate'):
        for i in range(60):
            assert _poll(client, f'https://flood{i}.ws-origin.example.test').status_code == 403
        warned = [r.getMessage() for r in caplog.records if r.name == 'websocket.origin_gate']
        assert len(warned) == origin_gate._MAX_WARNINGS_PER_WINDOW == 10, len(warned)
        clock[0] += origin_gate._REJECTION_LOG_INTERVAL + 1
        assert _poll(client, FOREIGN).status_code == 403
    warned = [r.getMessage() for r in caplog.records if r.name == 'websocket.origin_gate']
    assert len(warned) == 12, warned[10:]
    assert '50 more' in warned[10] and 'earlier 300 s window' in warned[10], warned[10]
    assert FOREIGN in warned[11]


def _base_url_reads(app):
    """Counts the SELECTs of the base_url row while the block runs."""
    table = SystemConfig.__tablename__
    reads = []

    def seen(conn, cursor, statement, parameters, context, executemany):
        values = parameters.values() if isinstance(parameters, dict) else parameters or ()
        if table in statement and 'base_url' in values:
            reads.append(statement)
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', seen)
    return reads, lambda: event.remove(engine, 'before_cursor_execute', seen)


def test_each_list_reads_the_base_url_once(app, setting):
    setting('base_url', PROXY)
    reads, stop = _base_url_reads(app)
    try:
        assert PROXY in _origins(app)
        api_reads = len(reads)
        reads.clear()
        assert PROXY in _ws_origins(app)
        ws_reads = len(reads)
    finally:
        stop()
    assert (api_reads, ws_reads) == (1, 1)


def test_a_request_without_origin_is_unchanged_and_reads_no_list(app, client, monkeypatch):
    import utils.public_endpoints as public_endpoints

    def refused():
        raise AssertionError('the origin list was read for a request without Origin')
    monkeypatch.setattr(public_endpoints, 'get_cors_origins', refused)
    monkeypatch.setattr(public_endpoints, 'get_websocket_origins', refused)
    r = _poll(client)
    assert r.status_code == 200
    assert r.get_data(as_text=True).startswith('0{')


def test_no_origin_is_taken_from_host_or_forwarded_host(app, client, setting):
    setting('base_url', PROXY)
    host = 'evil.ws-origin.example.test'
    r = _poll(client, FOREIGN, Host=host, **{'X-Forwarded-Host': host, 'X-Forwarded-Proto': 'https'})
    assert r.status_code == 403
    with app.test_request_context('/', headers={'Host': host, 'X-Forwarded-Host': host}):
        from utils.public_endpoints import get_cors_origins, get_websocket_origins
        assert not [o for o in get_cors_origins() + get_websocket_origins() if host in o]


# ------------------------------------------------ the gunicorn worker's handler

def _gated_server(app, seen, allowlist=False):
    from workers import MTLSWebSocketHandler

    def inner(environ, start_response):
        seen.append(environ.get('HTTP_ORIGIN'))
        ws = environ.get('wsgi.websocket')
        if ws is not None:
            ws.close()
            return []
        start_response('200 OK', [('Content-Length', '0')])
        return []

    gate = origin_gate.SocketIOOriginGate(inner, app)
    if allowlist:
        from utils.admin_allowlist import SocketIOAllowlistGate
        gate = SocketIOAllowlistGate(gate, app)
    ready, holder = threading.Event(), {}

    def run():
        # gevent keeps one hub per thread: the server is built and run in its own
        srv = pywsgi.WSGIServer(('127.0.0.1', 0), gate, handler_class=MTLSWebSocketHandler,
                                log=None, error_log=None)
        srv.init_socket()
        holder['address'] = srv.address
        ready.set()
        srv.serve_forever()

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(5)
    return holder['address']


def _handshake(address, origin):
    lines = [b'GET ' + WS.encode() + b' HTTP/1.1', b'Host: localhost', b'Upgrade: websocket',
             b'Connection: Upgrade', b'Sec-WebSocket-Key: ' + base64.b64encode(os.urandom(16)),
             b'Sec-WebSocket-Version: 13']
    if origin is not None:
        lines.append(b'Origin: ' + origin.encode())
    with socket.create_connection(address, timeout=5) as sock:
        sock.sendall(b'\r\n'.join(lines) + b'\r\n\r\n')
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
    return data.split(b'\r\n', 1)[0]


def _wait_for(seen, count):
    # The application runs after the 101 has gone out
    deadline = time.monotonic() + 5
    while len(seen) < count and time.monotonic() < deadline:
        time.sleep(0.02)


@pytest.fixture
def gate_registry(monkeypatch):
    """The gates register themselves for the worker: the test's ones are dropped afterwards."""
    from utils import admin_allowlist
    monkeypatch.setattr(origin_gate, '_flask_app', origin_gate._flask_app)
    monkeypatch.setattr(admin_allowlist, '_socketio_gate', admin_allowlist._socketio_gate)
    return admin_allowlist


def test_the_worker_reads_the_origin_list_once_per_upgrade(app, monkeypatch, gate_registry):
    import utils.public_endpoints as public_endpoints
    reads = []

    def listed():
        reads.append(1)
        return [PROXY]
    monkeypatch.setattr(public_endpoints, 'get_websocket_origins', listed)
    seen = []
    address = _gated_server(app, seen)
    assert _handshake(address, PROXY).startswith(b'HTTP/1.1 101')
    _wait_for(seen, 1)
    assert seen == [PROXY]
    assert len(reads) == 1


def test_the_worker_refuses_an_address_off_the_allowlist_before_switching_protocols(
        app, monkeypatch, gate_registry):
    allowed = [False]
    monkeypatch.setattr(gate_registry, 'disabled_by_env', lambda: False)
    monkeypatch.setattr(gate_registry, 'is_allowed', lambda addr: allowed[0])
    monkeypatch.setattr(origin_gate, 'origin_accepted', lambda origin: origin == PROXY)
    seen = []
    address = _gated_server(app, seen, allowlist=True)
    assert _handshake(address, PROXY).startswith(b'HTTP/1.1 403')
    assert _handshake(address, None).startswith(b'HTTP/1.1 403')
    assert seen == []
    allowed[0] = True
    assert _handshake(address, FOREIGN).startswith(b'HTTP/1.1 403')
    assert _handshake(address, PROXY).startswith(b'HTTP/1.1 101')
    _wait_for(seen, 1)
    assert seen == [PROXY]


def test_the_worker_refuses_before_switching_protocols(app, monkeypatch, gate_registry):
    monkeypatch.setattr(origin_gate, 'origin_accepted', lambda origin: origin == PROXY)
    seen = []
    address = _gated_server(app, seen)
    assert _handshake(address, FOREIGN).startswith(b'HTTP/1.1 403')
    assert seen == []
    assert _handshake(address, PROXY).startswith(b'HTTP/1.1 101')
    assert _handshake(address, None).startswith(b'HTTP/1.1 101')
    _wait_for(seen, 2)
    assert sorted(seen, key=str) == sorted([PROXY, None], key=str)
