"""A node stopped as an orchestrator stops it, twenty times: SIGTERM to the gunicorn master alone
(the container's first process) while a client keeps a connection open, SIGKILL to every process
at the end of the grace. Each time the node's row in cluster_nodes is released before that kill
(docs/HA.md, Upgrading: a node stopped cleanly says so when it exits), and the next start takes it
at once.

An open connection holds the workers' drain for gunicorn's graceful_timeout (30 s), as long as
Kubernetes' default grace: the release must not wait for that drain.
"""
import os
import signal
import time

import pytest

from tests.ha.cluster import READY_TIMEOUT, STOP_TIMEOUT, wait_until

pytestmark = pytest.mark.ha

STOPS = 20
# Kubernetes' default terminationGracePeriodSeconds, the trial's
ORCHESTRATOR_GRACE = 30


def _token(cluster, node):
    rows = cluster.sql('SELECT instance_token, pid FROM cluster_nodes WHERE node_id = %s', (node.name,))
    return rows[0] if rows else None


def test_a_node_stopped_twenty_times_releases_its_row_each_time(cluster):
    node = cluster[1]
    released_after = []
    for stop in range(STOPS):
        if stop:
            node.start()
            wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready after stop {stop}')
        assert _token(cluster, node)[0] is not None
        held = node.session()
        assert held.get(node.url('/health/live'), timeout=10).status_code == 200  # stays open
        os.kill(node.proc.pid, signal.SIGTERM)
        began = time.monotonic()
        try:
            wait_until(lambda: _token(cluster, node) == (None, None), ORCHESTRATOR_GRACE - 1,
                       f'row of {node.name} released and marked stopped (stop {stop + 1})')
        except AssertionError as e:
            row = cluster.sql('SELECT * FROM cluster_nodes WHERE node_id = %s', (node.name,))
            raise AssertionError(f'{e}\nrow: {row}\nconsole:\n{node.console.read_text()[-8000:]}') from None
        released_after.append(time.monotonic() - began)
        node._signal(signal.SIGKILL)
        node.proc.wait(timeout=STOP_TIMEOUT)
        wait_until(lambda: not node.pids(), STOP_TIMEOUT, f'node {node.name} processes gone')
        held.close()
    print(f'{STOPS} stops: row released after {min(released_after):.1f}s to {max(released_after):.1f}s')
    node.start()
    wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready after the last stop')
