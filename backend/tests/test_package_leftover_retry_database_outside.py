"""archive-leftovers.sh retried after any fault: the database DATABASE_PATH placed outside
the data, on a filesystem of its own (see package_leftover_chaos)."""
from tests.package_leftover_chaos import ConvergeSuite


class TestDatabaseOutside(ConvergeSuite):
    layout = 'a database outside the data'
