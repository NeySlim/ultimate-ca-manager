"""archive-leftovers.sh retried after any fault: a mount point inside the data (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite


class TestAMountPointInsideTheData(ChaosSuite):
    layout = 'a mount point inside the data'
