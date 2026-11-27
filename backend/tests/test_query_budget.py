"""SQL statements per authenticated GET, frozen per engine in query_budget.json.

A change that lowers a route's cost lowers its budget in the same commit.
"""
import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, insert

from config.settings import SESSION_TABLE
from models import CA, Certificate, db
from utils.datetime_utils import utc_now

from tests import pg_app_harness
UCM_PG = pg_app_harness.ENABLED
BUDGET_FILE = Path(__file__).with_name('query_budget.json')
MARK = 'query-budget'
ASSET = '/assets/vendor-AbC123.js'
ROUTES = (
    '/api/v2/health', '/api/v2/auth/verify', '/api/v2/webhooks', '/api/v2/dashboard/stats',
    '/api/v2/dashboard/queue?limit=100', '/api/v2/cas', '/api/v2/certificates/stats',
    '/api/v2/settings/general', '/api/v2/reports/schedule', ASSET,
)


def _budget():
    return json.loads(BUDGET_FILE.read_text())


def _seed(app):
    """Three CAs and forty certificates, the same on every run and every engine."""
    now = utc_now()
    with app.app_context():
        for i in range(3):
            db.session.add(CA(refid=uuid.uuid4().hex, descr=f'{MARK} ca {i}', crt=''))
        db.session.flush()
        db.session.execute(insert(Certificate.__table__), [{
            'refid': str(uuid.uuid4()), 'descr': MARK, 'crt': 'not parsed',
            'source': ('manual', 'acme', 'est')[i % 3], 'key_algo': 'RSA 2048', 'key_bits': 2048,
            'sig_hash': 'sha256', 'cert_type': 'server_cert', 'revoked': i % 10 == 0, 'archived': False,
            'valid_from': now - timedelta(days=i), 'valid_to': now + timedelta(days=10 + i * 9),
            'created_at': now - timedelta(days=i),
        } for i in range(40)])
        db.session.commit()


@pytest.fixture(scope='module')
def fixed_data(app):
    _seed(app)
    yield
    with app.app_context():
        Certificate.query.filter_by(descr=MARK).delete(synchronize_session=False)
        CA.query.filter(CA.descr.like(f'{MARK} ca %')).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture(scope='module')
def asset_dir(tmp_path_factory):
    import api.ui_routes as ui
    folder = tmp_path_factory.mktemp('frontend')
    (folder / 'assets').mkdir()
    (folder / 'assets' / 'vendor-AbC123.js').write_text('export default 1;')
    saved = ui.FRONTEND_DIR
    ui.FRONTEND_DIR = folder
    yield folder
    ui.FRONTEND_DIR = saved


@pytest.fixture(scope='module')
def lecteur(app, viewer_client):
    return viewer_client


def _measure(app, client, url):
    """(session statements, other statements) one GET runs, after a warm-up request."""
    from utils import admin_allowlist
    admin_allowlist.invalidate_cache()
    # The expired-session purge rides a random one request in N: not part of a route's cost
    app.session_interface.cleanup_n_requests = 0
    client.get(url)
    with app.app_context():
        engines = {db.engine}
        if hasattr(app.session_interface, 'dispose'):  # the SQL store has a pool of its own
            engines.add(app.session_interface._engine())
    session, other = [], []

    def listener(conn, cursor, statement, parameters, context, executemany):
        (session if SESSION_TABLE in statement else other).append(statement)

    for engine in engines:
        event.listen(engine, 'before_cursor_execute', listener)
    try:
        response = client.get(url)
    finally:
        for engine in engines:
            event.remove(engine, 'before_cursor_execute', listener)
    # A viewer is refused on some routes (403): the refusal has its own cost, frozen the same way
    assert response.status_code in (200, 403), (url, response.status_code, response.data[:200])
    return len(session), len(other)


def _engine(app):
    with app.app_context():
        return db.engine.dialect.name


@pytest.mark.parametrize('who', ['admin', 'viewer'])
def test_query_budget(app, auth_client, lecteur, fixed_data, asset_dir, who):
    _check(app, auth_client if who == 'admin' else lecteur, _engine(app), who)


def _check(app, client, engine, who):
    budget = _budget()[engine][who]
    measured = {url: _measure(app, client, url) for url in ROUTES}
    if budget is None:  # first measurement, to freeze
        pytest.fail('MEASURED ' + engine + ' ' + who + ' ' + json.dumps({u: list(m) for u, m in measured.items()}))
    over = [f'{url}: measured {m[0]} session + {m[1]} other, budget {budget[url][0]} + {budget[url][1]}'
            for url, m in measured.items() if m[0] > budget[url][0] or m[1] > budget[url][1]]
    assert not over, 'over budget (a lot that lowers a cost lowers the budget):\n' + '\n'.join(over)


def test_query_budget_is_stable(app, auth_client, fixed_data, asset_dir):
    first = {url: _measure(app, auth_client, url) for url in ROUTES}
    second = {url: _measure(app, auth_client, url) for url in ROUTES}
    assert first == second


def test_query_budget_sql_sessions(monkeypatch, asset_dir):
    """PostgreSQL with the session store in the database: its reads and writes are counted apart."""
    from config.settings import TestingConfig
    from tests.conftest import admin_client
    from tests.fresh_app import fresh_app

    if not UCM_PG:
        pytest.skip('needs the PostgreSQL mode of the application suite')
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', SESSION_TABLE, raising=False)
    monkeypatch.setattr(TestingConfig, 'SESSION_CLEANUP_N_REQUESTS', 1, raising=False)
    with fresh_app() as application:
        _seed(application)
        assert application.config['SESSION_TYPE'] == 'sqlalchemy'
        _check(application, admin_client(application), 'postgresql+sql-sessions', 'admin')
