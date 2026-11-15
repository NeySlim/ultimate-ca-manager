"""(a) A session opened on one node is valid on every other one (sessions in the database)."""
import pytest

from tests.ha.cluster import Client, create_ca, node_counts

pytestmark = [pytest.mark.ha, node_counts(2, 3)]


def test_login_on_a_then_authenticated_calls_on_the_others(cluster, admin):
    for node in cluster.nodes[1:]:
        assert Client(node).get('/api/v2/cas').status_code == 401

        on_other = admin.on(node)
        r = on_other.get('/api/v2/auth/verify')
        assert r.status_code == 200 and r.json()['data'].get('authenticated') is not False, r.text[:500]
        assert on_other.get('/api/v2/cas').status_code == 200

        # A write on this node with the CSRF token minted on A, read back through A
        ca = create_ca(on_other, f'HA session CA {node.name}')
        r = admin.get(f"/api/v2/cas/{ca['id']}")
        assert r.status_code == 200 and r.json()['data']['refid'] == ca['refid']
