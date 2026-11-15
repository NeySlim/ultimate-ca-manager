"""archive-leftovers.sh retried after any fault: one filesystem (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite, NothingRenamesSuite


class TestOneFilesystem(ChaosSuite):
    layout = 'one filesystem'


class TestOneFilesystemNothingRenames(NothingRenamesSuite):
    layout = 'one filesystem'
