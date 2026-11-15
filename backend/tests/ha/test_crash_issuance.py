"""Twenty issuances in parallel over three nodes, one follower killed (SIGKILL) while its
requests are inside their transaction: what a client was told issued is issued, readable from
another node, under a unique serial; what was cut left nothing; the CA's count matches.

The instant is made deterministic by a row lock: the test holds the CA's row, which the
issuance's serial count updates (utils/ca_serial_counter.py), and kills the node once every node
has a request waiting on it in pg_stat_activity.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from tests.ha.cluster import create_ca, node_counts, single_leader, wait_until

pytestmark = [pytest.mark.ha, node_counts(3)]

COUNT = 20


def _attempt(client, ca_id, cn):
    """(status, body) of one issuance, (None, error) when the connection broke."""
    try:
        r = client.post('/api/v2/certificates', {'cn': cn, 'ca_id': ca_id, 'validity_days': 30})
    except requests.RequestException as e:
        return None, repr(e)
    try:
        body = r.json()
    except ValueError:
        body = r.text[:300]
    return r.status_code, body


def test_a_follower_killed_during_parallel_issuance(cluster, admin):
    leader = wait_until(lambda: single_leader(cluster.nodes), 60, 'one leader')
    victim = next(node for node in cluster.nodes if node is not leader)
    survivors = [node for node in cluster.nodes if node is not victim]
    clients = {node.name: admin.on(node) for node in cluster.nodes}
    ca = create_ca(admin, 'HA crash issuance CA')
    targets = [cluster.nodes[i % len(cluster.nodes)] for i in range(COUNT)]

    with ThreadPoolExecutor(max_workers=COUNT) as pool:
        with cluster.holding('SELECT id FROM certificate_authorities WHERE id = %s FOR UPDATE',
                             (ca['id'],)) as hold:
            futures = [pool.submit(_attempt, clients[node.name], ca['id'], f'crash-{i}.ucm-ha.test')
                       for i, node in enumerate(targets)]
            wait_until(lambda: all(cluster.waiting_on_lock(node) for node in cluster.nodes), 60,
                       'a request of every node waits on the CA row')
            victim.kill()
            hold.rollback()
        outcomes = [future.result() for future in futures]

    by_node = {}
    for node, outcome in zip(targets, outcomes):
        by_node.setdefault(node.name, []).append(outcome)
    issued = [body['data'] for status, body in outcomes if status in (200, 201)]
    # The survivors served every request sent to them
    for node in survivors:
        assert all(status in (200, 201) for status, _ in by_node[node.name]), by_node[node.name]
    # The killed node's requests failed as a client sees a crash: a broken connection or a 5xx
    cut = by_node[victim.name]
    assert all(status is None or status >= 500 for status, _ in cut), cut

    rows = cluster.sql('SELECT id, serial_number, crt FROM certificates WHERE caref = %s', (ca['refid'],))
    # Nothing half written: every row has its serial and its certificate, under a unique serial
    assert all(serial and crt for _, serial, crt in rows), rows
    assert len({serial for _, serial, _ in rows}) == len(rows)
    # Exactly the certificates a client was told about, no row of a cut request
    assert sorted(cert_id for cert_id, _, _ in rows) == sorted(c['id'] for c in issued)
    # The count is bumped in the issuing transaction (no gap): it equals the certificates kept
    (count,), = cluster.sql('SELECT serial FROM certificate_authorities WHERE id = %s', (ca['id'],))
    assert count == len(rows), (count, len(rows))

    # Each one is served by another node than the one that issued it
    for node, (status, body) in zip(targets, outcomes):
        if status not in (200, 201):
            continue
        reader = next(n for n in survivors if n is not node)
        r = clients[reader.name].get(f"/api/v2/certificates/{body['data']['id']}")
        assert r.status_code == 200, (reader.name, r.status_code, r.text[:300])
        assert r.json()['data']['serial_number'] == body['data']['serial_number']
