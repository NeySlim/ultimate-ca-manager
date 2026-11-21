"""PostgreSQL: the restore transaction plans each statement for its own rows.

The tables a restore fills start empty, so a plan cached early (psycopg prepares a statement
from its sixth run) scanned the table it was filling: one lookup per certificate became
linear, the restore quadratic. Gated on UCM_TEST_APP_PG_URL (the application on PostgreSQL).
"""
import os

import pytest
from sqlalchemy import text

from models import db
from services.backup.restore import single_transaction

pytestmark = pytest.mark.skipif(not os.getenv('UCM_TEST_APP_PG_URL'),
                                reason='UCM_TEST_APP_PG_URL not set')

ROWS = 3000


def _plan_after_runs(session):
    """The plan of a lookup prepared and run on a table analyzed empty, once the table is filled
    (as a restore runs its first lookups on an empty table, then thousands more)."""
    session.execute(text("CREATE TEMP TABLE plan_probe (id serial PRIMARY KEY, "
                         "refid varchar(64) NOT NULL, pad text) ON COMMIT DROP"))
    session.execute(text("CREATE UNIQUE INDEX ON plan_probe (refid)"))
    session.execute(text("ANALYZE plan_probe"))
    session.execute(text("PREPARE plan_probe_lookup(varchar) AS "
                         "SELECT * FROM plan_probe WHERE refid = $1 LIMIT 1"))
    try:
        for i in range(10):
            session.execute(text(f"EXECUTE plan_probe_lookup('absent-{i}')"))
        session.execute(text("INSERT INTO plan_probe (refid, pad) "
                             "SELECT md5(i::text), repeat('x', 2000) FROM generate_series(1, :n) i"),
                        {'n': ROWS})
        return '\n'.join(r[0] for r in session.execute(
            text("EXPLAIN EXECUTE plan_probe_lookup('absent')")))
    finally:
        session.execute(text("DEALLOCATE plan_probe_lookup"))


def test_a_lookup_in_the_restore_transaction_keeps_its_index(app):
    with app.app_context():
        assert db.engine.dialect.name == 'postgresql'
        db.session.rollback()
        with single_transaction() as session:
            plan = _plan_after_runs(session)
        assert 'Index Scan' in plan, plan
        assert db.session.execute(text('SHOW plan_cache_mode')).scalar() == 'auto'
        db.session.rollback()
