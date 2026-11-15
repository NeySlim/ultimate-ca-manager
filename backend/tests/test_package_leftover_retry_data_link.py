"""archive-leftovers.sh retried after any fault: the data a symbolic link (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ChaosSuite, NothingRenamesSuite


class TestTheDataASymbolicLink(ChaosSuite):
    layout = 'the data a symbolic link'


class TestTheDataASymbolicLinkNothingRenames(NothingRenamesSuite):
    layout = 'the data a symbolic link'
