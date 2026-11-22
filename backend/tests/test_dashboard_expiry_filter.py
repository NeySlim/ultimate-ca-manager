"""The certificate list's expiry interval, ``expires_from`` (inclusive) to ``expires_to`` (exclusive):
the list behind one day or one week of the overview's expiry calendar."""
import uuid
from datetime import datetime

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import Certificate, db
from tests.conftest import get_json
from tests.dashboard_pem import self_signed

LIST = '/api/v2/certificates'
MARK = f'expiry-filter-{uuid.uuid4().hex[:8]}'


@pytest.fixture(scope='module')
def dated(app):
    pem = self_signed(ec.generate_private_key(ec.SECP256R1()))
    spec = {'before': datetime(2031, 3, 13, 23, 59, 59), 'midnight': datetime(2031, 3, 14),
            'evening': datetime(2031, 3, 14, 23, 59, 59, 999000), 'next': datetime(2031, 3, 15),
            'none': None}
    ids = {}
    with app.app_context():
        for name, valid_to in spec.items():
            row = Certificate(refid=str(uuid.uuid4()), descr=f'{MARK}-{name}', crt=pem, valid_to=valid_to)
            db.session.add(row)
            db.session.flush()
            ids[name] = row.id
        db.session.commit()
    yield ids
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids.values())).delete(synchronize_session=False)
        db.session.commit()


def _ids(client, **params):
    r = client.get(LIST, query_string={'search': MARK, 'per_page': 100, **params})
    assert r.status_code == 200, r.data
    return {c['id'] for c in get_json(r)['data']}


def _names(dated, *names):
    return {dated[n] for n in names}


def test_one_utc_day_is_half_open(auth_client, dated):
    assert _ids(auth_client, expires_from='2031-03-14', expires_to='2031-03-15') == _names(
        dated, 'midnight', 'evening')


def test_each_bound_alone(auth_client, dated):
    assert _ids(auth_client, expires_from='2031-03-15') == _names(dated, 'next')
    assert _ids(auth_client, expires_to='2031-03-14') == _names(dated, 'before')


def test_an_offset_is_read_as_utc(auth_client, dated):
    # 01:00 at +02:00 is 23:00 UTC the day before
    assert _ids(auth_client, expires_from='2031-03-14T01:00:00+02:00',
                expires_to='2031-03-14T00:00:00.000001Z') == _names(dated, 'before', 'midnight')


@pytest.mark.parametrize('value', ['x', '2031-13-01', '', '14/03/2031'])
@pytest.mark.parametrize('name', ['expires_from', 'expires_to'])
def test_an_invalid_bound_is_refused(auth_client, name, value):
    r = auth_client.get(LIST, query_string={name: value})
    assert r.status_code == 400
    assert name in get_json(r)['message']
