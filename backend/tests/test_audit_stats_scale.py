"""GET /api/v2/audit/stats on a large journal: every statement reads the period
through the timestamp index, so entries older than the period cost nothing."""
import json
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import event, insert

from models import AuditLog, db
from services.audit import AuditService
from tests.planner_stats import STATES, planner_statistics
from utils.datetime_utils import utc_now

MARK = 'stats-scale'


@pytest.fixture
def frozen(monkeypatch):
    now = utc_now()
    monkeypatch.setattr('services.audit.query.utc_now', lambda: now)
    return now


@pytest.fixture(params=STATES)
def planner_stats(request, app):
    if request.param != 'no_stats':
        with app.app_context():
            if db.engine.dialect.name != 'sqlite':
                pytest.skip("sqlite_stat1 is SQLite's; PostgreSQL analyzes on its own")
    with planner_statistics(app, request.param, ('audit_logs',)):
        yield request.param


@pytest.fixture
def journal(app):
    """Rows added by the test (bulk, unsealed: the chain is not under test), removed afterwards."""
    with app.app_context():
        yield
        db.session.rollback()
        AuditLog.query.filter(AuditLog.resource_type == MARK).delete(synchronize_session=False)
        db.session.commit()


def _add(now, count, days_ago, users=7):
    rows = [dict(timestamp=now - timedelta(days=days_ago, seconds=i), username=f'{MARK}-u{i % users}',
                 action=f'{MARK}-a{i % 3}', resource_type=MARK, success=i % 5 != 0) for i in range(count)]
    db.session.execute(insert(AuditLog.__table__), rows)
    db.session.commit()


def _statements(call):
    seen = []
    listener = lambda conn, cur, statement, params, ctx, many: seen.append((statement, params))  # noqa: E731
    event.listen(db.engine, 'before_cursor_execute', listener)
    try:
        call()
    finally:
        event.remove(db.engine, 'before_cursor_execute', listener)
    return [(s, p) for s, p in seen if 'audit_logs' in s]


def _full_scans(statement, parameters):
    raw = db.session.connection().connection.driver_connection
    if db.engine.dialect.name == 'sqlite':
        plan = raw.execute('EXPLAIN QUERY PLAN ' + statement, parameters or ()).fetchall()
        return [row[3] for row in plan if row[3].startswith('SCAN audit_logs')]
    with raw.cursor() as cur:
        cur.execute('SET LOCAL enable_seqscan = off')
        cur.execute('EXPLAIN (FORMAT JSON) ' + statement, parameters)
        plan = cur.fetchone()[0]
        plan = json.loads(plan) if isinstance(plan, str) else plan
    bad = []

    def walk(node):
        if node.get('Relation Name') == 'audit_logs' and 'timestamp' not in str(node.get('Index Cond', '')) + str(
                node.get('Recheck Cond', '')):
            bad.append(f"{node['Node Type']} on audit_logs")
        for child in node.get('Plans', []):
            walk(child)

    walk(plan[0]['Plan'])
    return bad


def test_every_statement_reads_the_period_by_its_timestamp(app, journal, frozen, planner_stats):
    with app.app_context():
        _add(frozen, 50, 2)
        found = {}
        for statement, parameters in _statements(lambda: AuditService.get_stats(30)):
            bad = _full_scans(statement, parameters)
            db.session.rollback()
            if bad:
                found[statement.split('FROM')[0][:80]] = bad
    assert not found, found


def test_the_figures_are_those_of_the_period(app, journal, frozen):
    with app.app_context():
        _add(frozen, 120, 3, users=7)
        _add(frozen, 40, 45, users=3)   # outside the period
        stats = AuditService.get_stats(30)
        since = frozen - timedelta(days=30)
        rows = db.session.query(AuditLog.username, AuditLog.success).filter(AuditLog.timestamp >= since).all()
        # Ties by name as the database collates it (PostgreSQL's locale is not byte order), NULL included
        by_name = [u for (u,) in db.session.query(AuditLog.username).filter(AuditLog.timestamp >= since)
                   .distinct().order_by(AuditLog.username)]
    users = Counter(u for u, _ in rows)
    rank = {u: i for i, u in enumerate(by_name)}
    expected = sorted(users.items(), key=lambda item: (-item[1], rank[item[0]]))[:10]
    assert [(u['username'], u['count']) for u in stats['top_users']] == expected
    assert stats['unique_users'] == len({u for u, _ in rows if u is not None})
    assert stats['total_logs'] == len(rows)
    assert stats['success_count'] == sum(1 for _, s in rows if s is True)


def _steps(app):
    counter = [0]
    with app.app_context():
        raw = db.session.connection().connection.driver_connection
        raw.set_progress_handler(lambda: counter.__setitem__(0, counter[0] + 1) or 0, 1000)
        try:
            AuditService.get_stats(30)
        finally:
            raw.set_progress_handler(None, 1000)
            db.session.rollback()
    return counter[0]


def test_entries_older_than_the_period_cost_nothing(app, journal, frozen, planner_stats):
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('instruction counts are a SQLite measure; the plan test covers PostgreSQL')
    k = 4000
    base = _steps(app)
    with app.app_context():
        _add(frozen, k, 2)
    recent = _steps(app) - base
    with app.app_context():
        _add(frozen, k, 200)
    old = _steps(app) - base - recent
    # As many rows outside the period as inside it: an index range never visits them
    assert old < 0.1 * recent, (base, recent, old)
