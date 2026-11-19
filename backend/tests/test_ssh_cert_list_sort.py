"""The SSH certificate list honours sort_by and sort_order, as the other lists do."""
import pytest

from tests.test_ssh import _generate_test_ssh_key, post_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

KEY_IDS = ['sortlist-b', 'sortlist-c', 'sortlist-a']


@pytest.fixture(scope='module')
def ca_id(auth_client):
    r = post_json(auth_client, '/api/v2/ssh/cas', {
        'descr': 'Sort CA', 'ca_type': 'user', 'key_type': 'ed25519',
        'allow_any_principal': True, 'allow_custom_key_id': True})
    assert r.status_code == 201, r.data
    ca = r.get_json()['data']['id']
    for key_id, seconds in zip(KEY_IDS, (7200, 3600, 10800)):
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca, 'public_key': _generate_test_ssh_key(), 'cert_type': 'user',
            'principals': ['alice'], 'key_id': key_id, 'validity_seconds': seconds})
        assert r.status_code == 201, r.data
    return ca


def _list(auth_client, ca_id, **params):
    r = auth_client.get('/api/v2/ssh/certificates', query_string={'ca_id': ca_id, **params})
    assert r.status_code == 200, r.data
    return r.get_json()['data']


def _key_ids(rows):
    return [row['key_id'] for row in rows]


def test_key_id_ascending_and_descending(auth_client, ca_id):
    assert _key_ids(_list(auth_client, ca_id, sort_by='key_id', sort_order='asc')) == sorted(KEY_IDS)
    assert _key_ids(_list(auth_client, ca_id, sort_by='key_id', sort_order='desc')) == sorted(KEY_IDS, reverse=True)


def test_expiry_orders_by_the_validity_given(auth_client, ca_id):
    asc = _key_ids(_list(auth_client, ca_id, sort_by='valid_to', sort_order='asc'))
    assert asc == ['sortlist-c', 'sortlist-b', 'sortlist-a']


def test_the_default_is_newest_first(auth_client, ca_id):
    assert _key_ids(_list(auth_client, ca_id)) == list(reversed(KEY_IDS))


@pytest.mark.parametrize('params', [{'sort_by': 'nonsense'}, {'sort_by': 'key_id; DROP TABLE x'},
                                    {'sort_order': 'sideways'}])
def test_an_unknown_value_falls_back_to_the_default(auth_client, ca_id, params):
    assert _key_ids(_list(auth_client, ca_id, **params)) == list(reversed(KEY_IDS))
