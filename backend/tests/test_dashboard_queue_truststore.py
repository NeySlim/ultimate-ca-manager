"""The work queue lists trust anchors expiring within 90 days and those already expired
(as the 2.x home page did), for a caller who may read the trust store."""
import hashlib
import uuid
from datetime import timedelta

import pytest

from models import db
from models.truststore import TrustedCertificate
from services import dashboard_aggregates as agg
from tests.conftest import get_json
from utils.datetime_utils import utc_now

KIND = 'truststore_expiring'
URL = '/api/v2/dashboard/queue'


@pytest.fixture
def anchors(app):
    ids = {}
    now = utc_now()
    spec = {'soon': now + timedelta(days=30), 'edge_in': now + timedelta(days=89),
            'edge_out': now + timedelta(days=91), 'far': now + timedelta(days=400),
            'expired': now - timedelta(days=900), 'unknown': None}
    with app.app_context():
        for name, not_after in spec.items():
            row = TrustedCertificate(
                name=f'ts-{name}', certificate_pem='-',
                fingerprint_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(), not_after=not_after)
            db.session.add(row)
            db.session.flush()
            ids[name] = row.id
        db.session.commit()
    yield ids
    with app.app_context():
        TrustedCertificate.query.filter(TrustedCertificate.id.in_(ids.values())).delete(synchronize_session=False)
        db.session.commit()


def _queue(app, permissions=None):
    with app.app_context():
        data = agg.work_queue(db.session, 10_000, permissions=permissions)
    return data, {i['id']: i for i in data['items'] if i['kind'] == KIND}


def test_in_window_out_of_window_expired(app, anchors):
    _, rows = _queue(app)
    assert set(rows) == {anchors['soon'], anchors['edge_in'], anchors['expired']}
    assert rows[anchors['soon']]['tier'] == 'warning'
    assert rows[anchors['expired']]['tier'] == 'critical'
    assert rows[anchors['soon']]['href_hint'] == f"/truststore/{anchors['soon']}"
    assert rows[anchors['soon']]['label'] == 'ts-soon'


def test_counted_in_the_aggregates(app, anchors):
    data, _ = _queue(app)
    assert data['counts'][KIND] >= 3
    assert data['total'] == sum(data['counts'].values())


def test_without_the_permission_nothing_listed_or_counted(app, anchors):
    with_perm, _ = _queue(app, ['read:dashboard', 'read:truststore'])
    without, rows = _queue(app, ['read:dashboard'])
    assert rows == {} and without['counts'][KIND] == 0
    assert with_perm['total'] - without['total'] == with_perm['counts'][KIND] >= 3


def test_route_withholds_from_a_key_without_read_truststore(app, auth_client, anchors):
    mine = [anchors[k] for k in ('soon', 'expired')]
    got = get_json(auth_client.get(URL + f'?kind={KIND}&limit=500'))['data']
    assert set(mine) <= {i['id'] for i in got['items']}
    r = auth_client.post('/api/v2/account/apikeys', json={'name': 'queue-no-truststore', 'permissions': ['read:dashboard']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    try:
        r = app.test_client().get(URL + f'?kind={KIND}', headers={'X-API-Key': key['key']})
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['items'] == [] and data['counts'][KIND] == 0
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")
