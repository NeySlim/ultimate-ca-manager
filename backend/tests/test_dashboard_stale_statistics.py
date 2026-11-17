"""On a database of its own, outside the isolation fixture: "Optimize database" on a small
installation, then growth. The queue and the renewal lists keep their indexes whatever the
statistics say, and the periodic task brings the statistics back to the grown tables."""
import json
import time
import uuid

import pytest
from sqlalchemy import insert, text

from models import db
from models.policy import ApprovalRequest
from services import dashboard_aggregates as da
from tests.fresh_app import fresh_app
from tests.test_dashboard_queue_scale import _ca, _grow, _Rows, _sqlite_violations, _statements

KINDS = da.RENEWAL_KINDS
GROWTH = 2000


def _calls(client):
    return {
        'queue': lambda: client.get('/api/v2/dashboard/queue'),
        **{f'list:{k}': (lambda k=k: client.get('/api/v2/certificates', query_string={'renewal': k}))
           for k in KINDS},
    }


def _violations(app, client):
    found = {}
    with app.app_context():
        for name, call in _calls(client).items():
            for statement, parameters in _statements(app, call):
                if 'certificates' not in statement:
                    continue
                bad = _sqlite_violations(statement, parameters)
                db.session.rollback()
                if bad:
                    found.setdefault(name, set()).update(bad)
    return found


def _rows_of(app, table):
    with app.app_context():
        stats = db.session.execute(text('SELECT stat FROM sqlite_stat1 WHERE tbl = :t'), {'t': table}).scalars().all()
    return {int(s.split()[0]) for s in stats}


def _small_then_grown(app, state):
    """A small installation (optimized in `stale` and `fresh`), then GROWTH more rows in every
    table the kinds look into; `fresh` analyzes again after the growth."""
    from tests.conftest import admin_client
    client = admin_client(app)
    rows = _Rows()
    with app.app_context():
        db.session.add(ApprovalRequest(request_type='renewal', status='pending',
                                       request_data=json.dumps({'certificate_id': 1})))
        _grow(rows, _ca(rows, 'stale-ca'), 'small', 0, 1)
    if state != 'never':
        assert client.post('/api/v2/system/database/optimize').status_code == 200
    with app.app_context():
        _grow(rows, db.session.merge(_ca(rows, 'grown-ca')), uuid.uuid4().hex[:6], 0, GROWTH // 2)
        db.session.execute(insert(ApprovalRequest), [
            dict(request_type='renewal', status='rejected',
                 request_data=json.dumps({'certificate_id': 10 ** 7 + i, 'trigger': 'auto'}))
            for i in range(GROWTH)])
        db.session.commit()
    if state == 'fresh':
        assert client.post('/api/v2/system/database/optimize').status_code == 200
    return client


@pytest.fixture
def own_app():
    with fresh_app() as application:
        with application.app_context():
            if db.engine.dialect.name != 'sqlite':
                pytest.skip("sqlite_stat1 is SQLite's; PostgreSQL analyzes on its own")
        yield application


@pytest.mark.parametrize('state', ['never', 'stale', 'fresh'])
def test_the_lists_keep_their_indexes_whatever_the_statistics(own_app, state):
    client = _small_then_grown(own_app, state)
    if state == 'stale':
        assert max(_rows_of(own_app, 'approval_requests')) < 10  # the case: stats of the small table
    started = time.perf_counter()
    for call in _calls(client).values():
        assert call().status_code == 200
    print(f'{state}: queue and four lists in {time.perf_counter() - started:.3f}s')
    assert not _violations(own_app, client)


def test_the_periodic_task_analyzes_the_grown_tables(own_app):
    from services.sqlite_statistics import scheduled_refresh
    _small_then_grown(own_app, 'stale')
    assert max(_rows_of(own_app, 'approval_requests')) < 10
    with own_app.app_context():
        scheduled_refresh()
    assert min(_rows_of(own_app, 'approval_requests')) > GROWTH
    # a partial index counts only its own rows
    assert max(_rows_of(own_app, 'certificates')) > GROWTH


def test_optimize_analyzes_under_the_analysis_limit_and_puts_it_back(own_app):
    from services.sqlite_statistics import ANALYSIS_LIMIT
    from tests.conftest import admin_client
    client = admin_client(own_app)
    with own_app.app_context():
        raw = db.session.connection().connection.driver_connection
        raw.execute('PRAGMA analysis_limit = 7')
        traced = []
        raw.set_trace_callback(traced.append)
        try:
            assert client.post('/api/v2/system/database/optimize').status_code == 200
        finally:
            raw.set_trace_callback(None)
        analyze = [i for i, s in enumerate(traced) if s.strip().upper() == 'ANALYZE']
        limits = [(i, s) for i, s in enumerate(traced) if 'analysis_limit =' in s]
        assert analyze, traced
        # the last limit set before ANALYZE is the bound, the previous one is restored after it
        assert [s for i, s in limits if i < analyze[0]][-1].endswith(f'= {ANALYSIS_LIMIT}'), limits
        assert raw.execute('PRAGMA analysis_limit').fetchone()[0] == 7


def test_the_task_runs_on_sqlite_only(app, auth_client):
    from services.sqlite_statistics import refresh_statistics
    tasks = {t['name'] for t in auth_client.get('/api/v2/system/scheduler').get_json()['data']['tasks']}
    with app.app_context():
        sqlite = db.engine.dialect.name == 'sqlite'
        assert ('sqlite_statistics' in tasks) is sqlite, sorted(tasks)
        assert refresh_statistics() is sqlite
        db.session.rollback()


def test_a_sqlite_connection_is_reopened_to_load_fresh_statistics(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = {k: v for k, v in os.environ.items() if k != 'DATABASE_URL'}
    env['DATABASE_PATH'] = str(tmp_path / 'ucm.db')
    out = subprocess.run(
        [sys.executable, '-c', 'from config.settings import Config; '
         'print(Config.SQLALCHEMY_ENGINE_OPTIONS.get("pool_recycle"))'],
        cwd=Path(__file__).resolve().parent.parent, env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == '3600'
