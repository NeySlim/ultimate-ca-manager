"""The four certificate queue kinds: the queue total equals the list its filter opens."""
import pytest

from models import db
from tests.conftest import get_json
from tests.test_dashboard_queue import URL
from tests.test_dashboard_queue_rules import CERT_KINDS, rules, _queue  # noqa: F401


def _list(client, kind):
    ids, page = [], 1
    while True:
        r = client.get('/api/v2/certificates', query_string={'renewal': kind, 'per_page': 100, 'page': page})
        assert r.status_code == 200, r.data
        body = get_json(r)
        ids += [c['id'] for c in body['data']]
        if len(ids) >= body['meta']['total']:
            return sorted(ids), body['meta']['total']
        page += 1


@pytest.fixture
def seeded(app, rules):  # noqa: F811
    with app.app_context():
        offline = rules.ca('filters-offline', offline=True, prv='k')
        mine = {
            'manual_renewal_due': rules.cert('filters-manual', 10, prv=None).id,
            'client_renewal_overdue': rules.cert('filters-client', 5, prv=None, source='acme').id,
            'auto_renewal_blocked': rules.cert('filters-blocked', 10, prv='k', caref=offline.refid).id,
        }
        declined = rules.cert('filters-declined', 10, prv='k')
        rules.reject(declined, trigger='manual')
        mine['renewal_declined'] = declined.id
        rules.cert('filters-fine', 200, prv='k')
        db.session.commit()
        return mine


@pytest.mark.parametrize('kind', CERT_KINDS)
def test_queue_total_equals_the_filtered_list(app, auth_client, seeded, kind):
    data = _queue(auth_client)
    ids, total = _list(auth_client, kind)
    assert total == data['counts'][kind] == len(ids)
    assert seeded[kind] in ids
    assert data['filter_hints'][kind] == {'renewal': kind}
    queued = {i['id'] for i in data['items'] if i['kind'] == kind}
    assert queued <= set(ids)


def test_a_certificate_is_listed_under_its_own_kind_only(app, auth_client, seeded):
    for kind, cid in seeded.items():
        for other in CERT_KINDS:
            assert (cid in _list(auth_client, other)[0]) is (other == kind), (kind, other)


@pytest.mark.parametrize('param', ['foo', '_'])
def test_an_unknown_parameter_is_ignored(auth_client, param):
    assert auth_client.get('/api/v2/certificates', query_string={param: '1'}).status_code == 200


def test_an_invalid_value_of_a_known_filter_is_refused(auth_client):
    assert auth_client.get('/api/v2/certificates', query_string={'renewal': 'nope'}).status_code == 400


@pytest.mark.parametrize('param', ['key_bits_below', 'lifetime_over_days'])
@pytest.mark.parametrize('value', ['1000001', str(10 ** 30)])
def test_a_number_above_its_bound_is_refused(auth_client, param, value):
    r = auth_client.get('/api/v2/certificates', query_string={'live': 'true', param: value})
    assert r.status_code == 400, r.data


@pytest.mark.parametrize('param,value', [('key_bits_below', '1000000'), ('lifetime_over_days', '100000')])
def test_a_number_at_its_bound_is_accepted(auth_client, param, value):
    assert auth_client.get('/api/v2/certificates', query_string={param: value}).status_code == 200
