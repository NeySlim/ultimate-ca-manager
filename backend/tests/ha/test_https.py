"""(h) A certificate applied to HTTPS on node A is the one node B serves after its restart."""
import base64
import ssl

import pytest
from cryptography import x509

from tests.ha.cluster import READY_TIMEOUT, create_ca, issue, wait_until

pytestmark = pytest.mark.ha


def _served(node):
    pem = ssl.get_server_certificate(('127.0.0.1', node.port), timeout=10)
    return x509.load_pem_x509_certificate(pem.encode())


def test_a_certificate_applied_on_a_is_served_by_b(cluster, admin):
    b = cluster[1]
    ca = create_ca(admin, 'HA HTTPS CA')
    cert = issue(admin, ca['id'], 'ucm-ha.test')
    (stored,) = cluster.sql('SELECT crt FROM certificates WHERE id = %s', (cert['id'],))[0]
    applied = x509.load_pem_x509_certificate(base64.b64decode(stored))
    assert _served(b) != applied

    r = admin.post('/api/v2/system/https/apply', {'cert_id': cert['id']})
    assert r.status_code == 200, r.text[:500]
    assert cluster.sql("SELECT count(*) FROM cluster_commands WHERE kind = 'restart'")[0][0] >= 1

    # The rolling restart, as the watchers would run it: node A, then node B, each found
    # with no TLS files at all, which its master writes before opening the socket
    for node in cluster.nodes:
        restart_file = node.data_dir / '.restart_requested'
        wait_until(lambda: restart_file.exists() or not node.alive(), READY_TIMEOUT,
                   f'node {node.name} takes its turn of the rolling restart')
        node.stop()
        restart_file.unlink(missing_ok=True)
        for name in ('https_cert.pem', 'https_key.pem'):
            (node.data_dir / name).unlink()
        node.start()
        wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')
        assert _served(node) == applied

    assert _served(b) == applied
    assert 'written from the database' in b.log_text()
