"""The bench itself: a closed cluster leaves no process, no schema and no database session."""
import pytest

from tests.ha.cluster import Cluster, group_pids

pytestmark = pytest.mark.ha


def test_close_leaves_nothing_behind(tmp_path):
    bench = Cluster(tmp_path)
    bench.create_schema()
    try:
        bench.start()
        groups = [node.proc.pid for node in bench.nodes]
        assert all(group_pids(pgid) for pgid in groups)
        assert bench.sessions_left() > 0
    finally:
        bench.close()

    assert not any(group_pids(pgid) for pgid in groups)
    assert not bench.schema_exists()
    assert bench.sessions_left() == 0
    assert not bench.guard_hits()
