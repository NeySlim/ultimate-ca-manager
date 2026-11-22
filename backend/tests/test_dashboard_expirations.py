"""GET /api/v2/dashboard/expirations: certificates expiring per UTC day from today, split manual
and automatic, the signers and active CAs of each day, each day reproduced by the certificate list."""
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, Certificate, SystemConfig, db
from services import dashboard_horizon
from services.dashboard_horizon import AUTOMATIC_SOURCES
from tests.conftest import get_json
from tests.dashboard_pem import self_signed
from tests.dashboard_plans import plan_of
from utils.datetime_utils import utc_now

URL = '/api/v2/dashboard/expirations'
LIST = '/api/v2/certificates'
COUNTS = ('total', 'manual', 'automatic', 'signers', 'cas')


def _midnight(offset=0):
    return datetime.combine(utc_now().date(), datetime.min.time()) + timedelta(days=offset)


def _get(client, days=None):
    r = client.get(URL, query_string={} if days is None else {'days': days})
    assert r.status_code == 200, r.data
    return get_json(r)['data']


def _by_date(data):
    return {p['date']: {k: p[k] for k in COUNTS} for p in data['periods']}


def _delta(before, after):
    out = {}
    for d, counts in after.items():
        diff = {k: counts[k] - before[d][k] for k in COUNTS}
        if any(diff.values()):
            out[d] = diff
    return out


def _config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    previous = None if row is None else row.value
    if row is None:
        row = SystemConfig(key=key)
        db.session.add(row)
    row.value = value
    return key, previous


@pytest.fixture
def seeded(app):
    pem = self_signed(ec.generate_private_key(ec.SECP256R1()))
    at = lambda days, hour=10: _midnight(days) + timedelta(hours=hour)  # noqa: E731
    made, cas, settings = [], [], []
    with app.app_context():
        def cert(valid_to, **kw):
            row = Certificate(refid=str(uuid.uuid4()), descr='expirations-test', crt=pem, valid_to=valid_to, **kw)
            db.session.add(row)
            db.session.flush()
            made.append(row.id)
            return row
        for source in ('acme', 'acme_client', 'scep', 'est', 'wstep', 'letsencrypt'):
            cert(at(2), source=source)
        for source in (None, 'manual', 'import', 'msca'):
            cert(at(2), source=source)
        cert(at(2), source='manual', archived=True)                # archived still expires: counted
        cert(at(2), source='acme', revoked=True)                  # revoked: not counted
        request = Certificate(refid=str(uuid.uuid4()), descr='expirations-csr', csr='-', valid_to=at(2))
        db.session.add(request)                                   # a pending request: not counted
        db.session.flush()
        made.append(request.id)
        tsa = cert(at(5), source='manual')
        responder = cert(at(5), source='manual')
        cert(_midnight(30) - timedelta(microseconds=1), source='est')  # last instant of a 30-day window
        cert(_midnight(30), source='est')                         # first instant after it
        cert(utc_now() - timedelta(minutes=1), source='manual')   # expired today: not counted
        settings.append(_config('tsa_signer_cert_refid', tsa.refid))
        settings.append(_config(f'ocsp_responder_cert_{uuid.uuid4().int % 10**9}', str(responder.id)))
        for descr, valid_to, revoked in (('exp-ca', at(7), False), ('exp-ca-revoked', at(7), True),
                                          ('exp-ca-later', at(400), False)):
            ca = CA(refid=str(uuid.uuid4()), descr=descr, crt='placeholder', valid_to=valid_to, revoked=revoked)
            db.session.add(ca)
            db.session.flush()
            cas.append(ca.id)
        db.session.commit()
    yield at
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_([i for i in made if i])).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(cas)).delete(synchronize_session=False)
        for key, previous in settings:
            row = SystemConfig.query.filter_by(key=key).first()
            if previous is None:
                db.session.delete(row)
            else:
                row.value = previous
        db.session.commit()


@pytest.fixture
def before(auth_client):
    return {days: _by_date(_get(auth_client, days)) for days in (30, 365)}


def test_counts_per_day_are_exact(auth_client, before, seeded):
    after = _get(auth_client, 30)
    day = lambda n: _midnight(n).date().isoformat()  # noqa: E731
    assert _delta(before[30], _by_date(after)) == {
        day(2): {'total': 11, 'manual': 5, 'automatic': 6, 'signers': 0, 'cas': 0},
        day(5): {'total': 2, 'manual': 2, 'automatic': 0, 'signers': 2, 'cas': 0},
        day(7): {'total': 0, 'manual': 0, 'automatic': 0, 'signers': 0, 'cas': 1},
        day(29): {'total': 1, 'manual': 0, 'automatic': 1, 'signers': 0, 'cas': 0},
    }
    flags = {p['date']: p['infrastructure'] for p in after['periods']}
    assert flags[day(5)] and flags[day(7)]
    assert sum(p['total'] for p in after['periods']) == after['total']
    assert after['manual'] + after['automatic'] == after['total']


def test_the_window_is_whole_utc_days_from_today(auth_client, seeded):
    data = _get(auth_client, 30)
    assert (data['days'], data['from'], data['to']) == (30, _midnight().date().isoformat(),
                                                         _midnight(29).date().isoformat())
    assert [p['date'] for p in data['periods']] == [_midnight(i).date().isoformat() for i in range(30)]
    assert data['filter_hint'] == {'status': ['valid', 'expiring'], 'expires_to': _midnight(30).date().isoformat()}
    assert data['automatic_sources'] == list(AUTOMATIC_SOURCES)


def test_a_year_counts_past_thirty_days(auth_client, before, seeded):
    after = _by_date(_get(auth_client, 365))
    assert _delta(before[365], after)[_midnight(30).date().isoformat()]['total'] == 1
    assert len(after) == 365
    # 400 days out is beyond a year
    assert sum(d['cas'] for d in _delta(before[365], after).values()) == 1


def _listed(client, **params):
    r = client.get(LIST, query_string={**params, 'per_page': 1})
    assert r.status_code == 200, r.data
    return get_json(r)['meta']['total']


def test_each_day_and_the_window_open_the_same_rows_in_the_list(auth_client, seeded):
    data = _get(auth_client, 30)
    hint = data['filter_hint']
    for offset in (0, 2, 5, 29):
        period = data['periods'][offset]
        listed = _listed(auth_client, status=hint['status'], expires_from=period['date'],
                         expires_to=_midnight(offset + 1).date().isoformat())
        assert listed == period['total'], period['date']
    assert _listed(auth_client, **hint) == data['total']


def test_ninety_days_by_default(auth_client):
    assert _get(auth_client)['days'] == 90


@pytest.mark.parametrize('days', ['0', '366', 'x', '-1'])
def test_days_out_of_bounds_is_refused(auth_client, days):
    assert auth_client.get(URL, query_string={'days': days}).status_code == 400


def test_requires_auth(client):
    assert client.get(URL).status_code == 401


def test_a_key_without_read_dashboard_is_refused(app, auth_client):
    r = auth_client.post('/api/v2/account/apikeys',
                         json={'name': 'expirations-no-dashboard', 'permissions': ['read:certificates']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    try:
        assert app.test_client().get(URL, headers={'X-API-Key': key['key']}).status_code == 403
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


def test_the_window_reads_the_valid_to_index(app):
    """The per-day statement starts from ix_certificates_valid_to on both backends."""
    plan = plan_of(app, lambda: dashboard_horizon.expirations(db.session, 365), 'GROUP BY date(certificates.valid_to)')
    assert 'ix_certificates_valid_to' in plan, plan
