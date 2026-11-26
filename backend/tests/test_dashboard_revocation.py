"""GET /api/v2/dashboard/revocation: the active CAs by what they publish (current, stale or missing
CRL, no distribution point), the same states as the work queue's crl_due and crl_missing."""
import uuid
from datetime import timedelta

import pytest

from models import CA, db
from models.crl import CRLMetadata
from services import dashboard_aggregates as agg
from tests.conftest import get_json
from utils.datetime_utils import utc_now

URL = '/api/v2/dashboard/revocation'
COUNTS = ('total', 'current', 'stale', 'missing', 'no_cdp', 'ocsp_enabled', 'to_publish')


def _crl(ca, next_update, number=1, **kw):
    db.session.add(CRLMetadata(ca_id=ca.id, crl_number=number, this_update=utc_now(), next_update=next_update,
                               crl_pem='-', crl_der=b'-', **kw))


@pytest.fixture
def cas(app):
    now = utc_now()
    made = {}
    with app.app_context():
        def ca(name, **kw):
            kw.setdefault('cdp_enabled', True)
            kw.setdefault('prv', 'k')
            row = CA(refid=str(uuid.uuid4()), descr=f'rev-{name}', crt='placeholder',
                     valid_to=now + timedelta(days=365), **kw)
            db.session.add(row)
            db.session.flush()
            made[name] = row
            return row
        _crl(ca('current', ocsp_enabled=True), now + timedelta(days=3))
        _crl(ca('stale', offline=True), now - timedelta(days=2))
        ca('missing', prv=None)
        ca('no_cdp', cdp_enabled=False)
        ca('no_cdp_null', cdp_enabled=None)
        # the newest full CRL decides, whatever an older one or a delta says
        renewed = ca('renewed')
        _crl(renewed, now - timedelta(days=9), number=1)
        _crl(renewed, now + timedelta(days=1), number=2)
        _crl(renewed, now - timedelta(days=1), number=3, is_delta=True)
        # neither a revoked nor an expired CA is active
        ca('revoked', revoked=True)
        expired = ca('expired')
        expired.valid_to = now - timedelta(days=1)
        db.session.commit()
        ids = {name: row.id for name, row in made.items()}
    yield ids
    with app.app_context():
        CRLMetadata.query.filter(CRLMetadata.ca_id.in_(ids.values())).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(ids.values())).delete(synchronize_session=False)
        db.session.commit()


def _get(client, **params):
    r = client.get(URL, query_string=params)
    assert r.status_code == 200, r.data
    return get_json(r)['data']


@pytest.fixture
def before(auth_client):
    return _get(auth_client, limit=100)


def test_counts_are_exact(auth_client, before, cas):
    after = _get(auth_client, limit=100)
    assert {k: after[k] - before[k] for k in COUNTS} == {
        'total': 6, 'current': 2, 'stale': 1, 'missing': 1, 'no_cdp': 2, 'ocsp_enabled': 1, 'to_publish': 2}
    assert after['current'] + after['stale'] + after['missing'] + after['no_cdp'] == after['total']


def test_items_list_the_holes_first(auth_client, cas):
    items = _get(auth_client, limit=100)['items']
    mine = [i for i in items if i['ca_id'] in cas.values()]
    by_id = {i['ca_id']: i for i in mine}
    assert [i['ca_id'] for i in mine] == [cas['missing'], cas['stale'], cas['renewed'], cas['current']]
    ranks = {'missing': 0, 'stale': 1, 'current': 2}
    assert [ranks[i['state']] for i in items] == sorted(ranks[i['state']] for i in items)
    assert by_id[cas['missing']]['next_update'] is None
    assert (by_id[cas['missing']]['can_publish'], by_id[cas['stale']]['can_publish'],
            by_id[cas['current']]['can_publish']) == (False, False, True)
    assert by_id[cas['stale']]['offline'] is True
    assert by_id[cas['current']]['ocsp_enabled'] is True
    assert by_id[cas['stale']]['href_hint'] == f"/crl-ocsp?ca={cas['stale']}"


def test_the_states_are_the_queue_states(app, auth_client, cas):
    data = _get(auth_client, limit=100)
    with app.app_context():
        queue = agg.work_queue(db.session, 10_000)
    assert queue['counts']['crl_missing'] == data['missing']
    assert sum(1 for i in queue['items'] if i['kind'] == 'crl_due' and i['tier'] == 'critical') == data['stale']


@pytest.mark.parametrize('limit, most', [('1', 1), ('0', 1), ('1000', 100), ('x', 10)])
def test_the_list_is_bounded(auth_client, cas, limit, most):
    assert len(_get(auth_client, limit=limit)['items']) <= most
    assert len(_get(auth_client, limit=limit)['items']) >= 1


def test_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_a_key_without_read_dashboard_is_refused(app, auth_client):
    r = auth_client.post('/api/v2/account/apikeys', json={'password': 'changeme123', 'name': 'revocation-no-dashboard',
                                                          'permissions': ['read:crl']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    try:
        assert app.test_client().get(URL, headers={'X-API-Key': key['key']}).status_code == 403
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")
