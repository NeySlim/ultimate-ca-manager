"""The HA bench guard stops a node process that touches an installation path, before the access."""
import subprocess
import sys

import pytest

from tests.ha.cluster import Node


# Read-only accesses to paths that do not exist: harmless even if the guard ever let them through
@pytest.mark.parametrize('statement', [
    "open('/etc/ucm/ha-bench-probe.absent')",
    "import os; os.listdir('/opt/ucm/ha-bench-probe.absent')",
    "open('/var/log/ucm/ha-bench-probe.absent')",
    "open('/var/lib/softhsm/ha-bench-probe.absent')",
])
def test_guard_kills_the_node_on_an_installation_path(tmp_path, statement):
    node = Node('guarded', tmp_path, {})
    result = subprocess.run([sys.executable, '-c', statement + "; print('reached')"], env=node.env,
                            cwd=tmp_path, capture_output=True, text=True, timeout=60,
                            start_new_session=True)
    assert result.returncode == -9 and 'reached' not in result.stdout, result
    assert node.guard_hits().count('\n') == 1, node.guard_hits()


def test_guard_lets_the_bench_paths_through(tmp_path):
    node = Node('guarded', tmp_path, {})
    script = f"open({str(tmp_path / 'data' / 'probe')!r}, 'w').write('x'); print('reached')"
    result = subprocess.run([sys.executable, '-c', script], env=node.env, cwd=tmp_path,
                            capture_output=True, text=True, timeout=60, start_new_session=True)
    assert result.returncode == 0 and 'reached' in result.stdout, result
    assert not node.guard_hits()
