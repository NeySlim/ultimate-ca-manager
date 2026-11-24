"""archive-leftovers.sh retried after any fault, the left ucm.env being the line the new one
is (UCM_FIPS_BUILD=1), the data or a mount absent (see package_leftover_chaos)."""
from tests.package_leftover_chaos import AbsentSuite


class TestTheLeftConfigurationIsTheFipsLineAbsent(AbsentSuite):
    layout = 'data and config are mount points'
    env = 'fips only'
