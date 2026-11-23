"""Origins of the Socket.IO channel (#453): the admin base URL and the protocol base URL count as
soon as they are stored, a default port is the same origin as none, a refused origin answers 403
before any upgrade (polling and websocket) with one warning per origin, a request without Origin
is unchanged, and no origin is ever taken from Host or X-Forwarded-Host."""
import base64
import logging
import os
import socket
import threading
import time

import pytest
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
    yield
    origin_gate._rejections.clear()


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
    setting('protocol_base_url', PROTOCOL + ':80')
    for origin in (PROXY, PROXY + ':443', EXTRA, EXTRA + ':443', PROTOCOL, PROTOCOL + ':80'):
        assert _poll(client, origin).status_code == 200, origin
    listed = _origins(app)
    assert {PROXY, EXTRA, PROTOCOL} <= set(listed)
    assert not [o for o in listed if o.endswith((':443', ':80')) or '*' in o], listed


def test_an_ipv6_origin_stays_out_of_both_lists(app, client, monkeypatch):
    # UPGRADE.md: an IPv6 origin in brackets is ignored, by the API CORS and the WebSocket alike
    monkeypatch.setenv('CORS_EXTRA_ORIGINS', 'https://[2001:db8::1]:8443')
    assert not [o for o in _origins(app) if '[' in o]
    assert _poll(client, 'https://[2001:db8::1]:8443').status_code == 403


def test_the_protocol_base_url_counts_only_while_it_is_set(app, client, setting):
    setting('protocol_base_url', PROTOCOL)
    assert _poll(client, PROTOCOL).status_code == 200
    setting('protocol_base_url', '')
    assert _poll(client, PROTOCOL).status_code == 403


def test_the_api_cors_allows_the_same_origins(app, client, setting, monkeypatch):
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


def test_a_request_without_origin_is_unchanged_and_reads_no_list(app, client, monkeypatch):
    import utils.public_endpoints as public_endpoints

    def refused():
        raise AssertionError('the origin list was read for a request without Origin')
    monkeypatch.setattr(public_endpoints, 'get_cors_origins', refused)
    r = _poll(client)
    assert r.status_code == 200
    assert r.get_data(as_text=True).startswith('0{')


def test_no_origin_is_taken_from_host_or_forwarded_host(app, client, setting):
    setting('base_url', PROXY)
    host = 'evil.ws-origin.example.test'
    r = _poll(client, FOREIGN, Host=host, **{'X-Forwarded-Host': host, 'X-Forwarded-Proto': 'https'})
    assert r.status_code == 403
    with app.test_request_context('/', headers={'Host': host, 'X-Forwarded-Host': host}):
        from utils.public_endpoints import get_cors_origins
        assert not [o for o in get_cors_origins() if host in o]


# ------------------------------------------------ the gunicorn worker's handler

def _gated_server(app, seen):
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


def test_the_worker_refuses_before_switching_protocols(app, monkeypatch):
    monkeypatch.setattr(origin_gate, 'origin_accepted', lambda origin: origin == PROXY)
    seen = []
    address = _gated_server(app, seen)
    assert _handshake(address, FOREIGN).startswith(b'HTTP/1.1 403')
    assert seen == []
    assert _handshake(address, PROXY).startswith(b'HTTP/1.1 101')
    assert _handshake(address, None).startswith(b'HTTP/1.1 101')
    # The application runs after the 101 has gone out: wait for it
    deadline = time.monotonic() + 5
    while len(seen) < 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert sorted(seen, key=str) == sorted([PROXY, None], key=str)
