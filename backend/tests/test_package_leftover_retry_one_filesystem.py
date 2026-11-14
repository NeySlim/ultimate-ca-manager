"""archive-leftovers.sh retried after any fault: one filesystem (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite


class TestOneFilesystem(ChaosSuite):
    layout = 'one filesystem'
