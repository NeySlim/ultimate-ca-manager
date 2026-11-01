"""A request with "Connection: upgrade" but no WebSocket handshake reads its body
normally (issue #427); a real handshake still upgrades."""
import base64
import json
import os
import socket
import threading

import pytest
from flask import Flask, request
from gevent import pywsgi

from workers import MTLSWebSocketHandler


def _app():
    app = Flask(__name__)

    @app.route('/echo', methods=['POST'])
    def echo():
        return {'got': request.get_json(silent=True)}

    @app.route('/ws')
    def ws():
        sock = request.environ.get('wsgi.websocket')
        if sock is not None:
            sock.close()
        return ''

    return app


@pytest.fixture(scope='module')
def server():
    # gevent keeps one hub per thread: the server is built and run in its own, unpatched
    ready, holder = threading.Event(), {}

    def run():
        srv = pywsgi.WSGIServer(('127.0.0.1', 0), _app(), handler_class=MTLSWebSocketHandler,
                                log=None, error_log=None)
        srv.init_socket()
        holder['address'] = srv.address
        ready.set()
        srv.serve_forever()

    threading.Thread(target=run, daemon=True).start()
    assert ready.wait(5)
    yield holder['address']


def _send(address, raw):
    with socket.create_connection(address, timeout=5) as sock:
        sock.sendall(raw)
        data = b''
        try:
            while b'\r\n\r\n' not in data or not _complete(data):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pytest.fail(f'no complete response within 5 s, got {data!r}')
    return data


def _complete(data):
    head, _, body = data.partition(b'\r\n\r\n')
    if head.startswith(b'HTTP/1.1 101'):
        return True
    for line in head.split(b'\r\n'):
        if line.lower().startswith(b'content-length:'):
            return len(body) >= int(line.split(b':')[1])
    return False


def _post(connection, body, chunked=False):
    headers = [b'POST /echo HTTP/1.1', b'Host: localhost', b'Content-Type: application/json',
               b'Connection: ' + connection]
    if chunked:
        headers.append(b'Transfer-Encoding: chunked')
        body = b'%x\r\n%s\r\n0\r\n\r\n' % (len(body), body)
    else:
        headers.append(b'Content-Length: %d' % len(body))
    return b'\r\n'.join(headers) + b'\r\n\r\n' + body


@pytest.mark.parametrize('connection', [b'upgrade', b'Upgrade', b'keep-alive'])
@pytest.mark.parametrize('chunked', [False, True])
def test_a_post_reads_its_body_whatever_the_connection_header(server, connection, chunked):
    response = _send(server, _post(connection, b'{"username": "admin"}', chunked))
    head, _, body = response.partition(b'\r\n\r\n')
    assert head.startswith(b'HTTP/1.1 200')
    assert json.loads(body) == {'got': {'username': 'admin'}}


def test_a_websocket_handshake_still_upgrades(server):
    key = base64.b64encode(os.urandom(16))
    raw = (b'GET /ws HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
           b'Connection: Upgrade\r\nSec-WebSocket-Key: ' + key +
           b'\r\nSec-WebSocket-Version: 13\r\n\r\n')
    assert _send(server, raw).startswith(b'HTTP/1.1 101')
