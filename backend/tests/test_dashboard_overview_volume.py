"""The overview routes run a fixed number of SQL statements whatever the table
sizes: with 5,000 certificates each GET stays within a small statement budget."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import event, insert

from models import Certificate, db
from utils.datetime_utils import utc_now

BUDGET = 12
ROUTES = ('/api/v2/dashboard/queue', '/api/v2/dashboard/health?days=30',
          '/api/v2/dashboard/compliance', '/api/v2/dashboard/issuance?days=90')
MARK = 'dashboard-volume'


def _count(app, call):
    """Statements the engine runs during call()."""
    statements = []
    with app.app_context():
        engine = db.engine
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine, 'before_cursor_execute', listener)
    try:
        result = call()
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
    return statements, result


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.data
    return r


@pytest.fixture(scope='module')
def empty_counts(app, auth_client):
    """Statements per route before the volume is loaded (after a warm-up request)."""
    counts = {}
    for url in ROUTES:
        _get(auth_client, url)
        counts[url] = len(_count(app, lambda u=url: _get(auth_client, u))[0])
    return counts


@pytest.fixture(scope='module')
def many_certificates(app, empty_counts):
    now = utc_now()
    rows = [{
        'refid': str(uuid.uuid4()), 'descr': MARK, 'crt': 'not parsed', 'source': ('manual', 'acme', 'est')[i % 3],
        'key_algo': 'RSA 2048' if i % 2 else 'EC secp256r1', 'key_bits': 2048 if i % 2 else 256,
        'sig_hash': 'sha1' if i % 7 == 0 else 'sha256', 'cert_type': 'server_cert', 'revoked': False,
        'archived': False, 'valid_from': now - timedelta(days=i % 60),
        'valid_to': now + timedelta(days=1 + i % 500), 'created_at': now - timedelta(days=i % 60),
    } for i in range(5000)]
    with app.app_context():
        db.session.execute(insert(Certificate.__table__), rows)
        db.session.commit()
    yield
    with app.app_context():
        Certificate.query.filter_by(descr=MARK).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('name, args', [
    ('work_queue', (100,)), ('protocol_health', (30,)), ('compliance_summary', ()), ('issuance', (90,))])
def test_each_aggregate_stays_within_the_budget(app, many_certificates, name, args):
    from services import dashboard_aggregates
    with app.app_context():
        statements, _ = _count(app, lambda: getattr(dashboard_aggregates, name)(db.session, *args))
        db.session.rollback()
    assert len(statements) <= BUDGET, '\n'.join(statements)


@pytest.mark.parametrize('url', ROUTES)
def test_a_request_runs_as_many_statements_on_5000_rows_as_on_none(app, auth_client, empty_counts,
                                                                   many_certificates, url):
    _get(auth_client, url)
    statements, _ = _count(app, lambda: _get(auth_client, url))
    assert len(statements) == empty_counts[url], '\n'.join(statements)
