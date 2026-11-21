"""Every database session of every node terminated (pg_terminate_backend) with the database closed
to new ones for a while, then opened again: meanwhile /health/ready answers 503 with the database
check failed; afterwards every node serves again without a restart, under one leader, issues and
revokes, and no advisory lock, lease or maintenance is left behind.

The cut is deterministic: the database refuses new connections (ALLOW_CONNECTIONS false) before
the sessions are terminated, until the test opens it again.
"""
import time

import pytest

from services.notification.scheduler import EXPIRY_LEASE_KEY
from services.scheduler_leader import LEADER_LOCK_KEY
from services.scheduler_service import LOCK_RETRY_SECONDS, WAKE_INTERVAL_SECONDS
from tests.ha.cluster import create_ca, issue, node_counts, single_leader, wait_until

pytestmark = [pytest.mark.ha, node_counts(3)]

# The cut lasts two lock retry periods: every scheduler process meets it at least once
CUT_SECONDS = 2 * LOCK_RETRY_SECONDS
MARGIN = 15


def _advisory_locks(cluster):
    """(key, granted, node) of every advisory lock a node's session holds or waits for."""
    rows = cluster.sql(
        "SELECT l.pid, l.classid, l.objid, l.granted FROM pg_locks l JOIN pg_stat_activity a "
        "ON a.pid = l.pid WHERE l.locktype = 'advisory' AND a.application_name = ANY(%s)",
        (cluster.app_names(),))
    owners = {b['pid']: b['node'] for b in cluster.backends()}
    return [((int(c) << 32) | int(o), granted, owners.get(pid)) for pid, c, o, granted in rows]


def test_every_session_cut_then_the_database_back(cluster, admin):
    wait_until(lambda: single_leader(cluster.nodes), 60, 'one leader')
    ca = create_ca(admin, 'HA database cut CA')
    started = {n.name: n.health().get('started_at') for n in cluster.nodes}
    pids = {n.name: n.pids() for n in cluster.nodes}
    clients = {node.name: admin.on(node) for node in cluster.nodes}

    probes = []
    with cluster.database_closed():
        cut = cluster.sql('SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                          'WHERE application_name = ANY(%s)', (cluster.app_names(),))
        assert cut and all(done for (done,) in cut), cut
        until = time.monotonic() + CUT_SECONDS
        while time.monotonic() < until:
            for node in cluster.nodes:
                r = node.http.get(node.url('/health/ready'), timeout=30)
                probes.append((node.name, r.status_code, r.text[:300]))
            time.sleep(0.5)
        live = [node.http.get(node.url('/health/live'), timeout=10).status_code for node in cluster.nodes]
    opened_at = time.monotonic()

    # docs: /health/ready answers 503 when a check fails, here the database; /health/live 200
    assert probes and all(code == 503 for _, code, _ in probes), probes
    assert all('"database"' in text and 'Database connection failed' in text for _, _, text in probes), probes
    assert live == [200] * len(cluster.nodes)

    for node in cluster.nodes:
        wait_until(node.ready, 2 * WAKE_INTERVAL_SECONDS, f'node {node.name} ready again')
    # The lock freed with its session: a node takes it at its next retry once the database is
    # back (docs/ADMIN_GUIDE.md, Leader), and /health names that node
    def led():
        holders = _advisory_locks(cluster)
        leader = single_leader(cluster.nodes, settling=True)
        return leader if leader and holders == [(LEADER_LOCK_KEY, True, leader.name)] else None
    leader = wait_until(led, LOCK_RETRY_SECONDS + MARGIN - (time.monotonic() - opened_at),
                        'one lock holder, named leader by every node')
    # Nobody restarted
    assert {n.name: n.health().get('started_at') for n in cluster.nodes} == started
    assert {n.name: n.pids() for n in cluster.nodes} == pids

    # Every node issues and revokes at its first try
    for node in cluster.nodes:
        cert = issue(clients[node.name], ca['id'], f'after-cut-{node.name}.ucm-ha.test')
        r = clients[node.name].post(f"/api/v2/certificates/{cert['id']}/revoke", {'reason': 'superseded'})
        assert r.status_code == 200, f'revoke on {node.name}: {r.status_code} {r.text[:500]}'

    # Still one advisory lock: the leader's, held by a session of the leader
    assert _advisory_locks(cluster) == [(LEADER_LOCK_KEY, True, leader.name)]
    # No lease still held, no maintenance, every node registered under its own live token
    leases = cluster.sql("SELECT key, value FROM system_config WHERE (key LIKE 'crl_schedule_lease_%%' "
                         "OR key = %s) AND value <> ''", (EXPIRY_LEASE_KEY,))
    assert leases == [], leases
    slots = dict(cluster.sql("SELECT key, value FROM system_config "
                             "WHERE key IN ('backup.last_run', 'backup.concluded_run')"))
    assert slots.get('backup.last_run') == slots.get('backup.concluded_run'), slots
    assert cluster.sql('SELECT count(*) FROM cluster_maintenance') == [(0,)]
    rows = cluster.sql('SELECT node_id, instance_token FROM cluster_nodes ORDER BY node_id')
    assert [n for n, token in rows if token] == [n.name for n in cluster.nodes], rows
