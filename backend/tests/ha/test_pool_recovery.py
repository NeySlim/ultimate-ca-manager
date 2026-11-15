"""Every application connection killed by PostgreSQL (a restart, a failover): the next
requests on each node succeed, and the pools replace their dead connections unseen.

The dedicated connections (leader lock, command applier, relay LISTEN) are not pooled:
they log their loss once and reconnect on their next tick, which this file leaves alone.
"""
import pytest

pytestmark = pytest.mark.ha

_KILL = ("SELECT count(pg_terminate_backend(pid, 10000)) FROM pg_stat_activity "
         "WHERE application_name = %s AND pid <> pg_backend_pid()")
# Flask-Session's retry of a session read that met a dead pooled connection
_SESSION_RETRY = 'Exception when querying database'


def _size(node):
    return node.app_log.stat().st_size if node.app_log.exists() else 0


def _since(node, size):
    with open(node.app_log, 'rb') as handle:
        handle.seek(size)
        return handle.read().decode(errors='replace')


def test_requests_after_every_session_was_terminated_succeed(cluster, admin):
    clients = [admin.on(node) for node in cluster.nodes]
    for client in clients:  # each node's pools hold connections opened before the cut
        for _ in range(3):
            assert client.get('/api/v2/cas').status_code == 200
            assert client.node.http.get(client.node.url('/health/ready'), timeout=30).status_code == 200
    before = {node.name: _size(node) for node in cluster.nodes}

    killed = cluster.sql(_KILL, (cluster.schema,))[0][0]
    assert killed >= len(cluster.nodes)

    # The readiness probe first: the application pool, no session read to retry it
    ready = [(node.name, node.http.get(node.url('/health/ready'), timeout=30).status_code)
             for node in cluster.nodes]
    assert all(code == 200 for _, code in ready), ready
    answers = [(client.node.name, client.get('/api/v2/cas').status_code)
               for _ in range(5) for client in clients]
    assert all(code == 200 for _, code in answers), answers
    retried = {node.name: _since(node, before[node.name]).count(_SESSION_RETRY) for node in cluster.nodes}
    assert not any(retried.values()), retried
