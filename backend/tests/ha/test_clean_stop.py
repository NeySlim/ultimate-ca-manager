"""A node stopped as an orchestrator stops it, twenty times: SIGTERM to the gunicorn master alone
(the container's first process) while a client keeps a connection open, SIGKILL to every process
at the end of the grace. Each time the node's token in cluster_nodes is released before the
workers' drain ends, its row is marked stopped when it exits (docs/HA.md, Upgrading), both before
that kill, and the next start takes the row at once.

An open connection holds the workers' drain for gunicorn's graceful_timeout (30 s): the token
release must not wait for it; the row keeps its pid as long as that connection holds the drain,
and is marked stopped (on_exit) only once it is closed, within the chart's grace.
"""
import os
import signal
import time

import pytest

from tests.ha.cluster import READY_TIMEOUT, STOP_TIMEOUT, wait_until

pytestmark = pytest.mark.ha

STOPS = 20
# gunicorn's default graceful_timeout, which an open connection holds to the end
DRAIN = 30
# The chart's terminationGracePeriodSeconds (60) less its preStop sleep (10): the time UCM gets
ORCHESTRATOR_GRACE = 50
# Seconds after the token release that the row is seen keeping its pid while the connection is held
HOLD_CHECKS = 3


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
            wait_until(lambda: _token(cluster, node)[0] is None, DRAIN - 1,
                       f'token of {node.name} released before the drain ends (stop {stop + 1})')
            released_after.append(time.monotonic() - began)
            # The held connection keeps the workers draining: the row keeps its pid meanwhile
            for _ in range(HOLD_CHECKS):
                assert node.alive(), f'{node.name} exited while a connection was held (stop {stop + 1})'
                assert _token(cluster, node)[1] is not None, \
                    f'{node.name} marked stopped while its workers drain (stop {stop + 1})'
                time.sleep(1)
            held.close()
            wait_until(lambda: _token(cluster, node) == (None, None), ORCHESTRATOR_GRACE - 1 - (time.monotonic() - began),
                       f'row of {node.name} marked stopped before the kill (stop {stop + 1})')
        except AssertionError as e:
            row = cluster.sql('SELECT * FROM cluster_nodes WHERE node_id = %s', (node.name,))
            raise AssertionError(f'{e}\nrow: {row}\nconsole:\n{node.console.read_text()[-8000:]}') from None
        node._signal(signal.SIGKILL)
        node.proc.wait(timeout=STOP_TIMEOUT)
        wait_until(lambda: not node.pids(), STOP_TIMEOUT, f'node {node.name} processes gone')
    print(f'{STOPS} stops: token released after {min(released_after):.1f}s to {max(released_after):.1f}s')
    node.start()
    wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready after the last stop')
