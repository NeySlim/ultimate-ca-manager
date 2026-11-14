"""archive-leftovers.sh retried after any fault: data and config are mount points (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite


class TestDataAndConfigAreMountPoints(ChaosSuite):
    layout = 'data and config are mount points'
