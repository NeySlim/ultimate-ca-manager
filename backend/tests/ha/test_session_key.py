"""The session key rotated on A: every other node loads it without a restart, the tokens of both
keys pass."""
import pytest

from tests.ha.cluster import Client, create_ca, node_counts, wait_until

pytestmark = [pytest.mark.ha, node_counts(2, 3)]


def test_rotation_on_a_keeps_old_tokens_and_the_others_accept_new_ones(cluster, admin):
    others = cluster.nodes[1:]
    started = {n.name: n.health().get('started_at') for n in cluster.nodes}
    # CSRF tokens of the login, signed with the environment's key
    old = {node.name: admin.on(node) for node in others}

    r = admin.post('/api/v2/system/security/rotate-secrets')
    assert r.status_code == 200, r.text[:500]
    body = r.json()['data']
    assert body['mode'] == 'database' and body['previous_accepted_until']

    # A token minted by A after the rotation, accepted by each node once it applied the command
    r = admin.get('/api/v2/auth/verify')
    csrf = r.json()['data']['csrf_token']
    for node in others:
        fresh = Client(node, cookies=admin.http.cookies.get_dict(), csrf=csrf)
        assert fresh.csrf != old[node.name].csrf

        def accepts_the_new_key(fresh=fresh):
            r = fresh.post('/api/v2/cas', {'type': 'root'})
            return r.status_code != 403 or 'CSRF' not in r.text
        wait_until(accepts_the_new_key, 30, f'node {node.name} accepts a token of the new key')
        create_ca(fresh, f'HA session key new on {node.name}')
    # The token signed before the rotation stays valid on every node during the grace
    for node in others:
        create_ca(old[node.name], f'HA session key old on {node.name}')
    create_ca(admin, 'HA session key old on A')
    # Nobody restarted
    assert {n.name: n.health().get('started_at') for n in cluster.nodes} == started
