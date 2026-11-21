"""Integration secrets across nodes: a webhook secret saved through node A signs the delivery node B
sends after a restart (one UCM_DB_ENCRYPTION_KEY for the cluster), and a secret under another key is
named in the log of a node that starts, which still serves.
"""
import hashlib
import hmac
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography.fernet import Fernet

from tests.ha.cluster import READY_TIMEOUT, wait_until

pytestmark = pytest.mark.ha


def _own_address():
    """An address of this host the nodes reach and the SSRF guard allows (loopback it refuses)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(('192.0.2.1', 9))  # no packet is sent: picks the outgoing interface
        return probe.getsockname()[0]


@pytest.fixture
def receiver():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length') or 0))
            received.append((dict(self.headers), body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('0.0.0.0', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://{_own_address()}:{server.server_address[1]}/hook', received
    finally:
        server.shutdown()
        server.server_close()


def _restart(node):
    node.stop()
    node.start()
    wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')


def test_a_secret_saved_on_one_node_signs_what_another_sends_after_a_restart(cluster, admin, receiver):
    url, received = receiver
    secret = secrets.token_urlsafe(32)
    r = admin.post('/api/v2/webhooks', {'name': f'ha-secret-{secrets.token_hex(3)}', 'url': url,
                                        'secret': secret, 'events': ['certificate.issued']})
    assert r.status_code == 201, r.text[:500]
    webhook_id = r.json()['data']['id']
    node_b = cluster[1]
    _restart(node_b)

    r = admin.on(node_b).post(f'/api/v2/webhooks/{webhook_id}/test')
    assert r.status_code == 200, r.text[:500]
    headers, body = received[-1]
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert headers.get('X-UCM-Signature') == f'sha256={signature}'
    assert 'cannot be decrypted' not in node_b.app_log_text()


def test_a_node_names_the_secrets_its_key_does_not_open_and_still_serves(cluster, admin, receiver):
    url, received = receiver
    foreign = Fernet(Fernet.generate_key()).encrypt(b'from-the-former-single-node').decode()
    r = admin.post('/api/v2/webhooks', {'name': f'ha-foreign-{secrets.token_hex(3)}',
                                        'url': url, 'events': ['certificate.issued']})
    assert r.status_code == 201, r.text[:500]
    webhook_id = r.json()['data']['id']
    cluster.sql('UPDATE webhook_endpoints SET secret = %s WHERE id = %s', (foreign, webhook_id))
    node_b = cluster[1]
    _restart(node_b)

    log = node_b.app_log_text()
    assert 'do not decrypt with UCM_DB_ENCRYPTION_KEY' in log
    assert f'webhook_endpoints {webhook_id} secret' in log
    assert 'from-the-former-single-node' not in log and foreign not in log
    r = admin.on(node_b).post(f'/api/v2/webhooks/{webhook_id}/test')
    assert r.status_code == 400 and 'cannot be decrypted' in r.text
    assert received == []  # never sent unsigned
    cluster.sql('DELETE FROM webhook_endpoints WHERE id = %s', (webhook_id,))
