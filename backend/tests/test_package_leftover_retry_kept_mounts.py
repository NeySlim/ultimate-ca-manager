"""archive-leftovers.sh retried after any fault: each kept directory a mount point (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite, NothingRenamesSuite


class TestEachKeptDirectoryAMountPoint(ChaosSuite):
    layout = 'each kept directory a mount point'


class TestEachKeptDirectoryAMountPointNothingRenames(NothingRenamesSuite):
    layout = 'each kept directory a mount point'
