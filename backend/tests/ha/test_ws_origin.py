"""(#453) A base URL stored through node A is a WebSocket origin on node B at once, without a
restart; a foreign origin gets 403 from gunicorn's worker before any 101, with a warning."""
import base64
import os
import socket
import ssl

import pytest

from tests.ha.cluster import wait_until

pytestmark = pytest.mark.ha

PROXY = 'https://proxy.ucm-ha.test'
OTHER = 'https://other.ucm-ha.test'
FOREIGN = 'https://evil.ucm-ha.test'


def _status(node, origin, transport='websocket'):
    lines = [f'GET /socket.io/?EIO=4&transport={transport} HTTP/1.1', f'Host: 127.0.0.1:{node.port}',
             f'Origin: {origin}', 'Connection: close']
    if transport == 'websocket':
        lines[-1] = 'Connection: Upgrade'
        lines += ['Upgrade: websocket', 'Sec-WebSocket-Version: 13',
                  'Sec-WebSocket-Key: ' + base64.b64encode(os.urandom(16)).decode()]
    context = ssl.create_default_context()
    context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection(('127.0.0.1', node.port), timeout=15) as raw:
        with context.wrap_socket(raw) as sock:
            sock.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode())
            data = b''
            while b'\r\n' not in data:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
    return int(data.split(b' ', 2)[1])


def _base_url(admin, value):
    r = admin.patch('/api/v2/settings/general', {'base_url': value, 'force': True})
    assert r.status_code == 200, r.text[:500]


def test_a_base_url_stored_on_a_is_an_origin_on_b_without_restart(cluster, admin):
    a, b = cluster.nodes
    try:
        _base_url(admin, PROXY)
        for node in (a, b):
            assert _status(node, PROXY) == 101
            assert _status(node, PROXY + ':443') == 101
            assert _status(node, PROXY, 'polling') == 200
            assert _status(node, FOREIGN) == 403
            assert _status(node, FOREIGN, 'polling') == 403
        _base_url(admin, OTHER)
        assert _status(b, PROXY) == 403
        assert _status(b, OTHER) == 101
        wait_until(lambda: f"Rejected WebSocket origin '{FOREIGN}'" in b.log_text(), 30,
                   'the refusal is logged on node B')
    finally:
        _base_url(admin, '')
