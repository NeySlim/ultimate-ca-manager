"""The bench names a node's database sessions by application_name, whatever address PostgreSQL
sees: behind a published port (docker-proxy) every client port is the proxy's. No database here."""
from urllib.parse import parse_qs, urlsplit

from tests.ha.cluster import NODE_NAMES, Cluster


def _app_name(node):
    return parse_qs(urlsplit(node.env['DATABASE_URL']).query)['application_name'][0]


def test_each_node_connects_under_its_own_application_name(tmp_path):
    bench = Cluster(tmp_path, names=NODE_NAMES)
    names = [_app_name(node) for node in bench.nodes]
    assert len(set(names)) == len(names)
    # The abandoned-schema sweep keeps a schema alive while a session's name starts with it
    assert all(name.startswith(bench.schema) for name in names)


def test_backends_owner_comes_from_application_name(tmp_path, monkeypatch):
    bench = Cluster(tmp_path, names=NODE_NAMES)
    apps = {node.name: _app_name(node) for node in bench.nodes}
    activity = [(101, apps['node-a'], 'Lock', 'UPDATE certificate_authorities'),
                (102, apps['node-c'], None, 'SELECT 1'),
                (103, f'{bench.schema}_admin', None, 'SELECT 2')]

    def sql(statement, params=None):
        wanted = set(params[0])
        return [row for row in activity if row[1] in wanted]
    monkeypatch.setattr(bench, 'sql', sql)

    # No node process runs: the owner cannot come from the sockets they hold
    assert [(b['pid'], b['node']) for b in bench.backends()] == [(101, 'node-a'), (102, 'node-c')]
    assert bench.waiting_on_lock(bench[0], 'certificate_authorities') == 1
    assert bench.waiting_on_lock(bench[2]) == 0
