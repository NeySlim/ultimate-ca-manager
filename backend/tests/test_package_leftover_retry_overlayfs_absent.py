"""archive-leftovers.sh retried after any fault: overlayfs, the data or a mount absent,
nothing renamed (see package_leftover_chaos)."""
from tests.package_leftover_chaos import AbsentSuite, NothingRenamesSuite


class TestOverlayfsAbsent(AbsentSuite):
    layout = 'overlayfs'


class TestOverlayfsNothingRenames(NothingRenamesSuite):
    layout = 'overlayfs'
