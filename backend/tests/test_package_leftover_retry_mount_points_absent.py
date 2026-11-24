"""archive-leftovers.sh retried after any fault: data and config are mount points, the data
or a mount absent, nothing renamed (see package_leftover_chaos)."""
from tests.package_leftover_chaos import AbsentSuite, NothingRenamesSuite


class TestDataAndConfigAreMountPointsAbsent(AbsentSuite):
    layout = 'data and config are mount points'


class TestDataAndConfigAreMountPointsNothingRenames(NothingRenamesSuite):
    layout = 'data and config are mount points'
