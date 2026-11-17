"""On a database of its own, outside the isolation fixture: "Optimize database" on a small
installation, then growth. The queue and the renewal lists keep their indexes whatever the
statistics say."""
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

