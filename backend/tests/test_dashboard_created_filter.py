"""The certificate list's creation interval, ``created_from`` (inclusive) to ``created_to`` (exclusive):
the list behind one day of the overview's issuance flow."""
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from werkzeug.datastructures import MultiDict

from models import Certificate, db
from services.dashboard_aggregates import certificate_list_conditions
from tests.conftest import get_json
from tests.dashboard_pem import self_signed
from tests.dashboard_plans import plan_of
from utils.datetime_utils import utc_now

LIST = '/api/v2/certificates'
MARK = f'created-filter-{uuid.uuid4().hex[:8]}'
# A UTC day of the flow's 30-day window that no other fixture of this module writes to
DAY = (utc_now() - timedelta(days=17)).replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture(scope='module')
def dated(app):
    pem = self_signed(ec.generate_private_key(ec.SECP256R1()))
    spec = {'before': datetime(2031, 3, 13, 23, 59, 59), 'midnight': datetime(2031, 3, 14),
            'evening': datetime(2031, 3, 14, 23, 59, 59, 999000), 'next': datetime(2031, 3, 15),
            'flow_acme': DAY + timedelta(hours=3), 'flow_manual': DAY + timedelta(hours=22),
            'flow_after': DAY + timedelta(days=1)}
    sources = {'flow_acme': 'acme', 'flow_manual': None}
    ids = {}
    with app.app_context():
        for name, created in spec.items():
            row = Certificate(refid=str(uuid.uuid4()), descr=f'{MARK}-{name}', crt=pem, created_at=created,
                              valid_to=datetime(2040, 1, 1), source=sources.get(name, 'manual'))
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
    assert _ids(auth_client, created_from='2031-03-14', created_to='2031-03-15') == _names(
        dated, 'midnight', 'evening')


def test_each_bound_alone(auth_client, dated):
    assert _ids(auth_client, created_from='2031-03-15') == _names(dated, 'next')
    assert _ids(auth_client, created_from='2031-01-01', created_to='2031-03-14') == _names(dated, 'before')


def test_an_offset_is_read_as_utc(auth_client, dated):
    # 01:00 at +02:00 is 23:00 UTC the day before
    assert _ids(auth_client, created_from='2031-03-14T01:00:00+02:00',
                created_to='2031-03-14T00:00:00.000001Z') == _names(dated, 'before', 'midnight')


def test_the_list_of_a_flow_day_counts_what_the_flow_counts(auth_client, dated):
    """Clicking a column of the issuance flow opens the list of that UTC day: same rows, same count."""
    day = DAY.date().isoformat()
    after = (DAY + timedelta(days=1)).date().isoformat()
    assert _ids(auth_client, created_from=day, created_to=after) == _names(dated, 'flow_acme', 'flow_manual')
    flow = get_json(auth_client.get('/api/v2/dashboard/issuance', query_string={'days': 30}))['data']['flow']
    period = next(p for p in flow['periods'] if p['date'] == day)
    r = auth_client.get(LIST, query_string={'created_from': day, 'created_to': after, 'per_page': 1})
    assert get_json(r)['meta']['total'] == period['total']


@pytest.mark.parametrize('value', ['x', '2031-13-01', '', '14/03/2031'])
@pytest.mark.parametrize('name', ['created_from', 'created_to'])
def test_an_invalid_bound_is_refused(auth_client, name, value):
    r = auth_client.get(LIST, query_string={name: value})
    assert r.status_code == 400
    assert name in get_json(r)['message']


def test_the_interval_reads_the_created_at_index(app):
    """The creation interval starts from ix_certificates_created_at on both backends."""
    def run():
        args = MultiDict({'created_from': '2031-03-14', 'created_to': '2031-03-15'})
        conditions = certificate_list_conditions(args, db.engine.dialect.name)
        db.session.execute(select(Certificate.id).where(*conditions)).all()
    plan = plan_of(app, run, 'certificates.created_at >=')
    assert 'ix_certificates_created_at' in plan, plan
