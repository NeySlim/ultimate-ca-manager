"""GET /api/v2/dashboard/issuance: certificates issued per CA and per UTC day,
zeros on the quiet days, and the total per source over the period."""
import uuid
from datetime import datetime, time, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, Certificate, db
from tests.conftest import get_json
from tests.dashboard_pem import self_signed
from utils.datetime_utils import utc_now

URL = '/api/v2/dashboard/issuance'


@pytest.mark.parametrize('days', ['0', '91', 'x'])
def test_days_out_of_bounds_is_refused(auth_client, days):
    assert auth_client.get(f'{URL}?days={days}').status_code == 400


def _issuance(client, days=7):
    r = client.get(f'{URL}?days={days}')
    assert r.status_code == 200, r.data
    return get_json(r)['data']


@pytest.fixture
def two_cas(app):
    pem = self_signed(ec.generate_private_key(ec.SECP256R1()))
    today = utc_now().date()
    noon = lambda d: datetime.combine(today - timedelta(days=d), time(12))  # noqa: E731
    with app.app_context():
        cas = [CA(refid=str(uuid.uuid4()), descr=f'issuance-ca-{i}', crt='placeholder') for i in range(2)]
        db.session.add_all(cas)
        db.session.flush()
        plan = [(cas[0], 0, 'acme'), (cas[0], 0, 'acme'), (cas[0], 2, 'manual'), (cas[0], 4, None),
                (cas[1], 2, 'scep'), (cas[1], 10, 'scep')]
        certs = [Certificate(refid=str(uuid.uuid4()), descr='issuance', caref=ca.refid, crt=pem,
                             source=source, created_at=noon(d)) for ca, d, source in plan]
        # a pending request is not an issuance
        certs.append(Certificate(refid=str(uuid.uuid4()), descr='issuance-csr', caref=cas[0].refid,
                                 csr='-', created_at=noon(0)))
        db.session.add_all(certs)
        db.session.commit()
        ids = {'cas': [c.id for c in cas], 'refids': [c.refid for c in cas], 'certs': [c.id for c in certs]}
    yield ids, noon
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids['certs'])).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(ids['cas'])).delete(synchronize_session=False)
        db.session.commit()


def test_per_ca_per_day_with_zeros_and_per_source(auth_client, two_cas):
    ids, noon = two_cas
    data = _issuance(auth_client)
    dates = [(utc_now().date() - timedelta(days=6 - i)).isoformat() for i in range(7)]
    by_ca = {e['caref']: e for e in data['by_ca']}
    first, second = by_ca[ids['refids'][0]], by_ca[ids['refids'][1]]
    assert (first['ca_id'], first['ca_name']) == (ids['cas'][0], 'issuance-ca-0')
    expected_first = {noon(0).date().isoformat(): 2, noon(2).date().isoformat(): 1,
                      noon(4).date().isoformat(): 1}
    assert first['periods'] == [{'date': d, 'count': expected_first.get(d, 0)} for d in dates]
    assert first['total'] == 4
    assert second['total'] == 1  # the one ten days back is outside the window
    assert [p['date'] for p in second['periods']] == dates
    assert data['total'] >= first['total'] + second['total'] == 5


def test_sources_are_totalled_and_null_reads_as_manual(app, auth_client):
    before = _issuance(auth_client)['by_source']
    pem = self_signed(ec.generate_private_key(ec.SECP256R1()))
    with app.app_context():
        rows = [Certificate(refid=str(uuid.uuid4()), descr='issuance-src', crt=pem, source=s)
                for s in ('est', 'est', None, 'manual')]
        db.session.add_all(rows)
        db.session.commit()
        created = [r.id for r in rows]
    try:
        after = _issuance(auth_client)['by_source']
        delta = {k: after.get(k, 0) - before.get(k, 0) for k in after if after.get(k, 0) != before.get(k, 0)}
        assert delta == {'est': 2, 'manual': 2}
    finally:
        with app.app_context():
            Certificate.query.filter(Certificate.id.in_(created)).delete(synchronize_session=False)
            db.session.commit()


def test_ninety_days_is_accepted(auth_client):
    data = _issuance(auth_client, 90)
    assert data['from'] == (utc_now().date() - timedelta(days=89)).isoformat()
    assert all(len(e['periods']) == 90 for e in data['by_ca'])


def test_requires_auth(client):
    assert client.get(URL).status_code == 401
