"""Every node replaced by a node of another identifier, as a Kubernetes rolling restart does
(the pod name changes): /health counts the live nodes only, none stale. A row silent for
GONE_PASSES is counted nowhere and the leader deletes it; a node back under that identifier
writes a new one (docs/HA.md, Checking the cluster)."""
import pytest

from services.scheduler_leader import GONE_PASSES, STALE_PASSES
from services.scheduler_service import WAKE_INTERVAL_SECONDS
from tests.ha.cluster import READY_TIMEOUT, single_leader, wait_until

pytestmark = pytest.mark.ha

LOST = 'node-lost'


def _counts(node):
    cluster = node.health()['cluster']
    return cluster['nodes'], cluster['stale']


def _all_count(nodes):
    return all(_counts(n) == (len(nodes), 0) for n in nodes)


def test_replaced_nodes_leave_the_count_and_a_gone_row_leaves_the_registry(cluster):
    old = list(cluster.nodes)
    wait_until(lambda: single_leader(old), 60, 'one leader')
    live = list(old)
    for node in old:
        successor = cluster.add_node(f'{node.name}-next')
        successor.start()
        wait_until(successor.ready, READY_TIMEOUT, f'node {successor.name} ready')
        node.stop()
        live = [n for n in live if n is not node] + [successor]
        # The replaced node released its row as it stopped: counted at once in neither number
        wait_until(lambda: _all_count(live), WAKE_INTERVAL_SECONDS, f'{len(live)} nodes, none stale')
    tokens = dict(cluster.sql('SELECT node_id, instance_token FROM cluster_nodes'))
    assert all(node.name in tokens and tokens[node.name] is None for node in old), tokens
    leader = wait_until(lambda: single_leader(live, settling=True), 2 * WAKE_INTERVAL_SECONDS, 'one leader')

    # A node killed longer ago than GONE_PASSES: counted nowhere at once, deleted by the leader
    # once it has led a stale window
    cluster.sql("INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, pid, instance_token) "
                "VALUES (%s, clock_timestamp() AT TIME ZONE 'UTC' - make_interval(secs => %s), "
                "clock_timestamp() AT TIME ZONE 'UTC' - make_interval(secs => %s), false, 1, 'lost-token')",
                (LOST, GONE_PASSES * WAKE_INTERVAL_SECONDS + 120, GONE_PASSES * WAKE_INTERVAL_SECONDS + 60))
    assert _all_count(live)
    wait_until(lambda: not cluster.sql('SELECT 1 FROM cluster_nodes WHERE node_id = %s', (LOST,)),
               (STALE_PASSES + 2) * WAKE_INTERVAL_SECONDS, f'row of {LOST} deleted by {leader.name}')
    assert set(tokens) - {LOST} <= {r[0] for r in cluster.sql('SELECT node_id FROM cluster_nodes')}

    back = cluster.add_node(LOST)
    back.start()
    wait_until(back.ready, READY_TIMEOUT, f'node {LOST} ready')
    live.append(back)
    wait_until(lambda: _all_count(live), WAKE_INTERVAL_SECONDS, f'{len(live)} nodes, none stale')
