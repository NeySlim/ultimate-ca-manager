"""The bench addresses each node alone: distinct ports within a cluster, and a report
answered by another node's process fails as such instead of counting as the node's own.
No node is started here: these run in the ordinary suite."""
import pytest

from tests.ha import cluster as bench


class _Kernel:
    """bind(0) hands out the lowest free port, as a kernel may: a port released is free again."""

    def __init__(self):
        self.bound = set()
        kernel = self

        class Sock:
            def __init__(self, *_):
                self.port = None

            def bind(self, address):
                port = address[1] or min(set(range(40000, 40100)) - kernel.bound)
                kernel.bound.add(port)
                self.port = port

            def getsockname(self):
                return ('127.0.0.1', self.port)

            def close(self):
                kernel.bound.discard(self.port)

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        self.socket = Sock


def test_the_nodes_of_a_cluster_never_share_a_port(tmp_path, monkeypatch):
    monkeypatch.setattr(bench.socket, 'socket', _Kernel().socket)
    nodes = bench.Cluster(tmp_path, names=bench.NODE_NAMES).nodes
    assert len({node.port for node in nodes}) == len(nodes), [node.port for node in nodes]


class _Answer:
    def __init__(self, report):
        self.report = report

    def raise_for_status(self):
        pass

    def json(self):
        return self.report


def _report(node_id, leader):
    return {'node_id': node_id, 'leader': leader, 'cluster': {'leader_node_id': 'node-c'}}


def test_a_report_from_another_node_is_not_taken_for_the_node_asked(tmp_path, monkeypatch):
    nodes = bench.Cluster(tmp_path, names=bench.NODE_NAMES).nodes
    # node-a's address answered by node-c's process, as when both were given one port
    answers = {'node-a': _report('node-c', True), 'node-b': _report('node-b', False),
               'node-c': _report('node-c', True)}
    for node in nodes:
        monkeypatch.setattr(node.http, 'get', lambda url, timeout, n=node.name: _Answer(answers[n]))
    with pytest.raises(AssertionError, match='node-a.*answered by node-c'):
        bench.single_leader(nodes)


class _Running:
    returncode = None

    def poll(self):
        return None


def test_readiness_answered_by_another_node_fails_as_such(tmp_path, monkeypatch):
    node = bench.Cluster(tmp_path, names=bench.NODE_NAMES[:1]).nodes[0]
    node.proc = _Running()
    answer = _Answer({'status': 'ready', 'node_id': 'node-c'})
    answer.status_code = 200
    monkeypatch.setattr(node.http, 'get', lambda url, timeout: answer)
    with pytest.raises(AssertionError, match='node-a.*answered by node-c'):
        node.ready()
