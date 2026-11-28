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
from models.ca_cross_certificate import CACrossCertificate
from utils.datetime_utils import utc_now

from tests import pg_app_harness
from tests.fresh_app import fresh_app_fixtures
UCM_PG = pg_app_harness.ENABLED
BUDGET_FILE = Path(__file__).with_name('query_budget.json')
MARK = 'query-budget'
ASSET = '/assets/vendor-AbC123.js'
ROUTES = (
    '/api/v2/health', '/api/v2/auth/verify', '/api/v2/webhooks', '/api/v2/dashboard/stats',
    '/api/v2/dashboard/queue?limit=100', '/api/v2/cas', '/api/v2/certificates/stats',
    '/api/v2/settings/general', '/api/v2/reports/schedule', ASSET,
)

# A database of its own: rows other files leave behind change which conditional queries a listing runs.
app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


def _budget():
    return json.loads(BUDGET_FILE.read_text())


def _seed(app):
    """A root and an intermediate with a CN, a bare third CA, a cross-certificate and forty certificates."""
    now = utc_now()
    with app.app_context():
        root = CA(refid=uuid.uuid4().hex, descr=f'{MARK} ca 0', crt='', subject='CN=Budget Root')
        db.session.add(root)
        db.session.flush()
        inter = CA(refid=uuid.uuid4().hex, descr=f'{MARK} ca 1', crt='', subject='CN=Budget Issuing',
                   caref=root.refid)
        db.session.add_all([inter, CA(refid=uuid.uuid4().hex, descr=f'{MARK} ca 2', crt='')])
        db.session.flush()
        db.session.add(CACrossCertificate(
            ca_id=inter.id, crt='', fingerprint_sha256='b' * 64, subject='CN=Budget Issuing',
            issuer='CN=Budget Root', issuer_caref=root.refid, served=True,
            valid_from=now - timedelta(days=1), valid_to=now + timedelta(days=300)))
        db.session.execute(insert(Certificate.__table__), [{
            'refid': str(uuid.uuid4()), 'descr': MARK, 'crt': 'not parsed',
            'source': ('manual', 'acme', 'est')[i % 3], 'key_algo': 'RSA 2048', 'key_bits': 2048,
            'sig_hash': 'sha256', 'cert_type': 'server_cert', 'revoked': i % 10 == 0, 'archived': False,
            'valid_from': now - timedelta(days=i), 'valid_to': now + timedelta(days=10 + i * 9),
            'created_at': now - timedelta(days=i),
            'caref': inter.refid if i % 2 else None,
        } for i in range(40)])
        db.session.commit()


@pytest.fixture(scope='module')
def fixed_data(app):
    _seed(app)


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


# A viewer is refused (403) on these: the refusal has its own cost, frozen the same way
VIEWER_REFUSED = {'/api/v2/webhooks', '/api/v2/settings/general', '/api/v2/reports/schedule'}


@pytest.fixture(scope='module', autouse=True)
def warm_allowlist():
    """The admin allowlist is cached 5 s per process: a slow runner must not count its reload."""
    from utils import admin_allowlist
    saved = admin_allowlist._CACHE_TTL_SECONDS
    admin_allowlist._CACHE_TTL_SECONDS = 3600.0
    yield
    admin_allowlist._CACHE_TTL_SECONDS = saved


@pytest.fixture(scope='module')
def lecteur(viewer_client):
    # viewer_client falls back to the admin client if the viewer cannot be created
    assert viewer_client.get('/api/v2/auth/verify').get_json()['data']['user']['role'] == 'viewer'
    return viewer_client


def _measure(app, client, url, expected=200):
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
    assert response.status_code == expected, (url, response.status_code, response.data[:200])
    return len(session), len(other)


def _engine(app):
    with app.app_context():
        return db.engine.dialect.name


@pytest.mark.parametrize('who', ['admin', 'viewer'])
def test_query_budget(app, auth_client, lecteur, fixed_data, asset_dir, who):
    _check(app, auth_client if who == 'admin' else lecteur, _engine(app), who)


def _check(app, client, engine, who):
    budget = _budget()[engine][who]
    measured = {url: _measure(app, client, url, 403 if who == 'viewer' and url in VIEWER_REFUSED else 200)
                for url in ROUTES}
    if budget is None:  # first measurement, to freeze
        pytest.fail('MEASURED ' + engine + ' ' + who + ' ' + json.dumps({u: list(m) for u, m in measured.items()}))
    # Equality: a cost lowered without its budget would let a regression back to it pass unseen
    off = [f'{url}: measured {m[0]} session + {m[1]} other, budget {budget.get(url)}'
           for url, m in measured.items() if list(m) != budget.get(url)]
    assert not off, 'off budget (raise it only for a reason, lower it with the cost):\n' + '\n'.join(off)


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
        try:
            _check(application, admin_client(application), 'postgresql+sql-sessions', 'admin')
        finally:
            application.session_interface.dispose()
