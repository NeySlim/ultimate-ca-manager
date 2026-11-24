"""archive-leftovers.sh retried after any fault: a mount point inside the data, the data or a
mount absent, nothing renamed (see package_leftover_chaos)."""
from tests.package_leftover_chaos import AbsentSuite, NothingRenamesSuite


class TestAMountPointInsideTheDataAbsent(AbsentSuite):
    layout = 'a mount point inside the data'


class TestAMountPointInsideTheDataNothingRenames(NothingRenamesSuite):
    layout = 'a mount point inside the data'
