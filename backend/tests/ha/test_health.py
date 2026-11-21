"""(f) Each node's /health reports its own node_id and the same cluster state."""
import pytest

from tests.ha.cluster import wait_until

pytestmark = pytest.mark.ha


def test_each_node_reports_itself_and_the_same_cluster(cluster):
    def converged():
        reports = [node.health() for node in cluster.nodes]
        clusters = [r.get('cluster') for r in reports]
        if all(c and c['nodes'] == len(cluster.nodes) and c['stale'] == 0 and c['leader_node_id']
               for c in clusters) and all(c == clusters[0] for c in clusters):
            return reports
        return None

    reports = wait_until(converged, 30, 'every node reports one cluster')

    assert [r['node_id'] for r in reports] == [n.name for n in cluster.nodes]
    assert all(r['ha'] is True and r['status'] == 'ok' for r in reports)
    leader = reports[0]['cluster']['leader_node_id']
    assert leader in {n.name for n in cluster.nodes}
    assert [r['leader'] for r in reports] == [n.name == leader for n in cluster.nodes]
    for node in cluster.nodes:
        ready = node.ready()
        assert ready['node_id'] == node.name and ready['checks']['cluster']['status'] == 'ok'
