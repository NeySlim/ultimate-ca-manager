"""archive-leftovers.sh retried after any fault: overlayfs (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ConvergeSuite


class TestOverlayfs(ConvergeSuite):
    layout = 'overlayfs'
