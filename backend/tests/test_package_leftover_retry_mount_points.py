"""archive-leftovers.sh retried after any fault: data and config are mount points (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite, NothingRenamesSuite


class TestDataAndConfigAreMountPoints(ChaosSuite):
    layout = 'data and config are mount points'


class TestDataAndConfigAreMountPointsNothingRenames(NothingRenamesSuite):
    layout = 'data and config are mount points'
