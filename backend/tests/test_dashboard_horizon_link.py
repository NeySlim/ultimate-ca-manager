"""Horizon card: the expiring and expired counters equal the list their link opens."""
import uuid
from datetime import timedelta

import pytest

from models import Certificate, db
from tests.conftest import get_json
from utils.datetime_utils import utc_now


def _list(client, status):
    ids, page = [], 1
    while True:
        r = client.get('/api/v2/certificates', query_string={'status': status, 'per_page': 100, 'page': page})
        assert r.status_code == 200, r.data
        body = get_json(r)
        ids += [c['id'] for c in body['data']]
        if not body['data'] or len(ids) >= body['meta']['total']:
            return set(ids), body['meta']['total']
        page += 1


@pytest.fixture
def seeded(app):
    now = utc_now()
    created = {}

    def add(name, days, **kw):
        kw.setdefault('crt', 'PEM')
        row = Certificate(refid=str(uuid.uuid4()), descr=f'horizon-{name}', valid_from=now - timedelta(days=400),
                          valid_to=now + timedelta(days=days), **kw)
        db.session.add(row)
        db.session.flush()
        created[name] = row.id

    with app.app_context():
        add('expiring', 10)
        add('expiring_archived', 10, archived=True)
        add('edge', 30.5)  # just past the window: counted by neither
        add('expired', -3)
        add('revoked', 10, revoked=True)
        add('request_only', 10, crt=None)
        db.session.commit()
    yield created
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(created.values())).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('status,mine', [('expiring', {'expiring', 'expiring_archived'}), ('expired', {'expired'})])
def test_counter_equals_the_list_its_link_opens(auth_client, seeded, status, mine):
    r = auth_client.get('/api/v2/certificates/stats')
    assert r.status_code == 200, r.data
    count = get_json(r)['data'][status]
    ids, total = _list(auth_client, status)
    assert count == total == len(ids)
    assert {name for name, cid in seeded.items() if cid in ids} == mine
