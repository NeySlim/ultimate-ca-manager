"""archive-leftovers.sh retried after any fault: the database outside the data, absent or
unmounted (see package_leftover_chaos)."""
from tests.package_leftover_chaos import AbsentSuite


class TestDatabaseOutsideAbsent(AbsentSuite):
    layout = 'a database outside the data'
