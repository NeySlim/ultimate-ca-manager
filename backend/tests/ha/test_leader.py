"""(d) One scheduler leader among two or three nodes; when it dies another node takes over
within the documented delay, and a task runs on the leader only, once per run."""
import time

import pytest

from services.scheduler_leader import STALE_PASSES
from services.scheduler_service import LOCK_RETRY_SECONDS, WAKE_INTERVAL_SECONDS
from tests.ha.cluster import lock_acquisitions, node_counts, single_leader, task_runs, wait_until

pytestmark = [pytest.mark.ha, node_counts(2, 3)]

TASK = 'approval_expiry'
# Documented in docs/ADMIN_GUIDE.md (High availability): a retry period once the lock is free,
# and at worst the heartbeat passes after which a silent leader no longer counts
TAKEOVER_BOUND = LOCK_RETRY_SECONDS + STALE_PASSES * WAKE_INTERVAL_SECONDS
MARGIN = 15


def _run_now(client):
    r = client.post(f'/api/v2/system/scheduler/{TASK}/run')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:500]}'
    status = r.json()['data']
    assert not status.get('queued'), status
    return status


def test_one_leader_then_takeover(cluster, admin):
    leader = wait_until(lambda: single_leader(cluster.nodes), 60, 'one leader')
    followers = [node for node in cluster.nodes if node is not leader]
    # Readiness needs a heartbeat, written after each scheduler process tried the lock once
    assert [lock_acquisitions(n) for n in [leader] + followers] == [1] + [0] * len(followers)

    # Asked on a follower, run by the leader: every run in the logs is one the leader counted
    status = _run_now(admin.on(followers[-1]))
    assert status['run_count'] >= 1
    assert all(task_runs(f.app_log_text(), TASK) == 0 for f in followers)
    assert task_runs(leader.app_log_text(), TASK) == status['run_count']

    leader.kill()
    killed_at = time.monotonic()
    heir = wait_until(lambda: single_leader(followers), TAKEOVER_BOUND + MARGIN, 'a follower takes over')
    assert time.monotonic() - killed_at <= TAKEOVER_BOUND + MARGIN
    # One heir: the lock was taken once, by one survivor
    assert sorted(lock_acquisitions(f) for f in followers) == [0] * (len(followers) - 1) + [1]
    assert lock_acquisitions(heir) == 1

    status = _run_now(admin.on(followers[0]))
    assert status['run_count'] >= 1
    assert task_runs(heir.app_log_text(), TASK) == status['run_count']
    assert all(task_runs(f.app_log_text(), TASK) == 0 for f in followers if f is not heir)
