"""The bench's leader reading: a flag that lags the lock reads as "not settled yet" while waiting."""
from types import SimpleNamespace

import pytest

from tests.ha.cluster import single_leader


def _node(name, leader, named):
    report = {'leader': leader, 'cluster': {'leader_node_id': named}}
    return SimpleNamespace(name=name, health=lambda: report)


def test_two_leaders_while_settling_read_as_none():
    # Read one after the other across the instant the flag moves from the old leader
    nodes = [_node('ucm-1', True, 'ucm-1'), _node('ucm-2', True, 'ucm-2'), _node('ucm-3', False, 'ucm-2')]
    assert single_leader(nodes, settling=True) is None
    with pytest.raises(AssertionError, match='more than one leader'):
        single_leader(nodes)


def test_one_leader_named_by_all_is_returned_while_settling():
    nodes = [_node('ucm-1', False, 'ucm-2'), _node('ucm-2', True, 'ucm-2')]
    assert single_leader(nodes, settling=True) is nodes[1]
