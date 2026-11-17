"""PostgreSQL that falls silent (no answer, no refusal) under three nodes, for 60 seconds: every
node answers /health/live within a second each second, /health/ready answers 503 within
READY_DATABASE_TIMEOUT_SECONDS; once the database answers again every node is ready, without a
restart (docs/HA.md, When PostgreSQL is unavailable).

The nodes reach PostgreSQL through a relay of the bench that stops forwarding and leaves new
connections unanswered, as a frozen server or an address that no longer routes does.
"""
import threading
import time

import pytest
import requests

from api.health_routes import READY_DATABASE_TIMEOUT_SECONDS
from services.scheduler_service import WAKE_INTERVAL_SECONDS
from tests.ha.cluster import NODE_NAMES, Cluster, single_leader, wait_until

pytestmark = pytest.mark.ha

SILENT_SECONDS = 60
LIVE_LIMIT = 1.0
READY_MARGIN = 2.0


@pytest.fixture(scope='module')
def cluster(tmp_path_factory):
    bench = Cluster(tmp_path_factory.mktemp('ha'), names=NODE_NAMES[:3], silent_proxy=True)
    bench.create_schema()
    try:
        bench.start()
        yield bench
        assert not bench.guard_hits(), bench.guard_hits()
    finally:
        bench.close()


def _probe(node, path, timeout):
    """(status or the exception's name, seconds), on a new connection as a kubelet probe makes."""
    http = requests.Session()
    http.verify = False  # the node's self-signed certificate
    began = time.monotonic()
    try:
        code = http.get(node.url(path), timeout=timeout).status_code
    except requests.RequestException as e:
        code = type(e).__name__
    finally:
        http.close()
    return code, time.monotonic() - began


def _every(period, until, node, path, timeout, into):
    while time.monotonic() < until:
        began = time.monotonic()
        into.append((node.name, *_probe(node, path, timeout)))
        time.sleep(max(0.0, period - (time.monotonic() - began)))


def test_live_answers_and_ready_says_503_while_the_database_is_silent(cluster):
    wait_until(lambda: single_leader(cluster.nodes), 60, 'one leader')
    started = {n.name: n.health().get('started_at') for n in cluster.nodes}
    pids = {n.name: n.pids() for n in cluster.nodes}

    live, ready = [], []
    with cluster.proxy.silent():
        until = time.monotonic() + SILENT_SECONDS
        threads = [threading.Thread(target=_every, args=(1.0, until, node, '/health/live', 5, live))
                   for node in cluster.nodes]
        threads += [threading.Thread(target=_every, args=(2.0, until, node, '/health/ready', 30, ready))
                    for node in cluster.nodes]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    worst = {n.name: max(s for name, _, s in live if name == n.name) for n in cluster.nodes}
    print(f'silent database {SILENT_SECONDS}s: /health/live {len(live)} probes, slowest per node '
          + ', '.join(f'{k} {v:.3f}s' for k, v in worst.items())
          + f'; /health/ready {len(ready)} probes, slowest {max(s for *_, s in ready):.3f}s')
    assert all(code == 200 for _, code, _ in live), [p for p in live if p[1] != 200]
    assert max(worst.values()) < LIVE_LIMIT, worst
    assert len(live) >= len(cluster.nodes) * (SILENT_SECONDS - 5), len(live)
    assert ready and all(code == 503 for _, code, _ in ready), [p for p in ready if p[1] != 503]
    assert max(s for *_, s in ready) < READY_DATABASE_TIMEOUT_SECONDS + READY_MARGIN, ready

    for node in cluster.nodes:
        wait_until(node.ready, 2 * WAKE_INTERVAL_SECONDS, f'node {node.name} ready again')
    assert {n.name: n.health().get('started_at') for n in cluster.nodes} == started
    assert {n.name: n.pids() for n in cluster.nodes} == pids
