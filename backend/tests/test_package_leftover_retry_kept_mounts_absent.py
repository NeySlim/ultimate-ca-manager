"""archive-leftovers.sh retried after any fault: each kept directory a mount point, the data
or a mount absent, nothing renamed (see package_leftover_chaos)."""
from tests.package_leftover_chaos import AbsentSuite, NothingRenamesSuite


class TestEachKeptDirectoryAMountPointAbsent(AbsentSuite):
    layout = 'each kept directory a mount point'


class TestEachKeptDirectoryAMountPointNothingRenames(NothingRenamesSuite):
    layout = 'each kept directory a mount point'
