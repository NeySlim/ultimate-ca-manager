"""(d) One scheduler leader; when it dies the other node takes over within the documented delay,
and a task runs on the leader only, once per run."""
import time

import pytest

from services.scheduler_leader import STALE_PASSES
from services.scheduler_service import LOCK_RETRY_SECONDS, WAKE_INTERVAL_SECONDS
from tests.ha.cluster import task_runs, wait_until

pytestmark = pytest.mark.ha

TASK = 'approval_expiry'
# Documented in docs/ADMIN_GUIDE.md (High availability): a retry period once the lock is free,
# and at worst the heartbeat passes after which a silent leader no longer counts
TAKEOVER_BOUND = LOCK_RETRY_SECONDS + STALE_PASSES * WAKE_INTERVAL_SECONDS
MARGIN = 15


def _single_leader(nodes):
    reports = {node.name: node.health() for node in nodes}
    leaders = [name for name, r in reports.items() if r['leader'] is True]
    named = {r['cluster']['leader_node_id'] for r in reports.values()}
    if len(leaders) > 1:
        raise AssertionError(f'more than one leader: {reports}')
    if len(leaders) == 1 and named == set(leaders) \
            and all(r['leader'] is False for name, r in reports.items() if name != leaders[0]):
        return next(node for node in nodes if node.name == leaders[0])
    return None


def _acquisitions(node):
    return node.app_log_text().count('Scheduler lock acquired:')


def _run_now(client):
    r = client.post(f'/api/v2/system/scheduler/{TASK}/run')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:500]}'
    status = r.json()['data']
    assert not status.get('queued'), status
    return status


def test_one_leader_then_takeover(cluster, admin):
    leader = wait_until(lambda: _single_leader(cluster.nodes), 60, 'one leader')
    follower = next(node for node in cluster.nodes if node is not leader)
    # Readiness needs a heartbeat, written after each scheduler process tried the lock once
    assert (_acquisitions(leader), _acquisitions(follower)) == (1, 0)

    # Asked on the follower, run by the leader: every run in the logs is one the leader counted
    status = _run_now(admin.on(follower))
    assert status['run_count'] >= 1
    assert task_runs(follower.app_log_text(), TASK) == 0
    assert task_runs(leader.app_log_text(), TASK) == status['run_count']

    leader.kill()
    killed_at = time.monotonic()
    wait_until(lambda: _single_leader([follower]) is follower and
               follower.health()['cluster']['leader_node_id'] == follower.name,
               TAKEOVER_BOUND + MARGIN, f'{follower.name} takes over')
    assert time.monotonic() - killed_at <= TAKEOVER_BOUND + MARGIN
    assert _acquisitions(follower) == 1

    status = _run_now(admin.on(follower))
    assert status['run_count'] >= 1
    assert task_runs(follower.app_log_text(), TASK) == status['run_count']
