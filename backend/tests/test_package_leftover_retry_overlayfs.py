"""archive-leftovers.sh retried after any fault: overlayfs (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite, NothingRenamesSuite


class TestOverlayfs(ChaosSuite):
    layout = 'overlayfs'


class TestOverlayfsNothingRenames(NothingRenamesSuite):
    layout = 'overlayfs'
