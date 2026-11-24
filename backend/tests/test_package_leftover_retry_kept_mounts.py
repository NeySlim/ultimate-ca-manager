"""archive-leftovers.sh retried after any fault: each kept directory a mount point (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ConvergeSuite


class TestEachKeptDirectoryAMountPoint(ConvergeSuite):
    layout = 'each kept directory a mount point'
