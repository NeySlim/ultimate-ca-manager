"""Every application connection killed by PostgreSQL (a restart, a failover): the next
requests on each node succeed, the pool replaces its dead connections unseen."""
import pytest

pytestmark = pytest.mark.ha

_KILL = ("SELECT count(pg_terminate_backend(pid, 10000)) FROM pg_stat_activity "
         "WHERE application_name = %s AND pid <> pg_backend_pid()")


def test_requests_after_every_session_was_terminated_succeed(cluster, admin):
    clients = [admin.on(node) for node in cluster.nodes]
    for client in clients:  # each node's pool holds connections opened before the cut
        for _ in range(3):
            assert client.get('/api/v2/cas').status_code == 200

    killed = cluster.sql(_KILL, (cluster.schema,))[0][0]
    assert killed >= len(cluster.nodes)

    answers = [(client.node.name, client.get('/api/v2/cas').status_code)
               for _ in range(5) for client in clients]
    assert all(code == 200 for _, code in answers), answers
