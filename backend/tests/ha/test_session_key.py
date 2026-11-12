"""The session key rotated on A: B loads it without a restart, the tokens of both keys pass."""
import pytest

from tests.ha.cluster import Client, create_ca, wait_until

pytestmark = pytest.mark.ha


def test_rotation_on_a_keeps_old_tokens_and_b_accepts_new_ones(cluster, admin):
    a, b = cluster.nodes
    started = {n.name: n.health().get('started_at') for n in cluster.nodes}
    old = admin.on(b)  # the CSRF token of the login, signed with the environment's key

    r = admin.post('/api/v2/system/security/rotate-secrets')
    assert r.status_code == 200, r.text[:500]
    body = r.json()['data']
    assert body['mode'] == 'database' and body['previous_accepted_until']

    # A token minted by A after the rotation, accepted by B once it applied the command
    r = admin.get('/api/v2/auth/verify')
    fresh = Client(b, cookies=admin.http.cookies.get_dict(), csrf=r.json()['data']['csrf_token'])
    assert fresh.csrf != old.csrf

    def b_accepts_the_new_key():
        r = fresh.post('/api/v2/cas', {'type': 'root'})
        return r.status_code != 403 or 'CSRF' not in r.text
    wait_until(b_accepts_the_new_key, 30, 'node B accepts a token of the new key')
    create_ca(fresh, 'HA session key new')
    # The token signed before the rotation stays valid on both nodes during the grace
    create_ca(old, 'HA session key old on B')
    create_ca(admin, 'HA session key old on A')
    # Nobody restarted
    assert {n.name: n.health().get('started_at') for n in cluster.nodes} == started
