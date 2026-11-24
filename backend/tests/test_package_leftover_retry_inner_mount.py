"""archive-leftovers.sh retried after any fault: a mount point inside the data (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ConvergeSuite


class TestAMountPointInsideTheData(ConvergeSuite):
    layout = 'a mount point inside the data'
