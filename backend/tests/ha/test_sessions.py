"""(a) A session opened on one node is valid on the other (sessions in the database)."""
import pytest

from tests.ha.cluster import Client, create_ca

pytestmark = pytest.mark.ha


def test_login_on_a_then_authenticated_calls_on_b(cluster, admin):
    a, b = cluster.nodes
    assert Client(b).get('/api/v2/cas').status_code == 401

    on_b = admin.on(b)
    r = on_b.get('/api/v2/auth/verify')
    assert r.status_code == 200 and r.json()['data'].get('authenticated') is not False, r.text[:500]
    assert on_b.get('/api/v2/cas').status_code == 200

    # A write on B with the CSRF token minted on A, read back through A
    ca = create_ca(on_b, 'HA session CA')
    r = admin.get(f"/api/v2/cas/{ca['id']}")
    assert r.status_code == 200 and r.json()['data']['refid'] == ca['refid']
