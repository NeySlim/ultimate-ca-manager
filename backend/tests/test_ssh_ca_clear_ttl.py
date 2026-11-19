"""The default and maximum validity of an SSH CA can be emptied again."""
import pytest

from tests.test_ssh import _generate_test_ssh_key, post_json, put_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401


def _ca(auth_client, **extra):
    r = post_json(auth_client, '/api/v2/ssh/cas', {
        'descr': 'TTL CA', 'ca_type': 'user', 'key_type': 'ed25519',
        'allow_any_principal': True, 'default_ttl': '8h', 'max_ttl': '24h', **extra})
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _read(auth_client, ca_id):
    return auth_client.get(f'/api/v2/ssh/cas/{ca_id}').get_json()['data']


@pytest.mark.parametrize('field', ['default_ttl', 'max_ttl'])
def test_null_empties_the_field(auth_client, field):
    ca = _ca(auth_client)
    before = _read(auth_client, ca['id'])
    assert before[field]
    r = put_json(auth_client, f'/api/v2/ssh/cas/{ca["id"]}', {field: None})
    assert r.status_code == 200, r.data
    after = _read(auth_client, ca['id'])
    assert after[field] in (None, 0)
    other = 'max_ttl' if field == 'default_ttl' else 'default_ttl'
    assert after[other] == before[other]


def test_an_absent_key_leaves_both_alone(auth_client):
    ca = _ca(auth_client)
    before = _read(auth_client, ca['id'])
    assert put_json(auth_client, f'/api/v2/ssh/cas/{ca["id"]}', {'comment': 'x'}).status_code == 200
    after = _read(auth_client, ca['id'])
    assert (after['default_ttl'], after['max_ttl']) == (before['default_ttl'], before['max_ttl'])


def test_an_emptied_maximum_stops_capping(auth_client):
    ca = _ca(auth_client, max_ttl='1h')
    put_json(auth_client, f'/api/v2/ssh/cas/{ca["id"]}', {'max_ttl': None})
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(), 'cert_type': 'user',
        'principals': ['alice'], 'validity_seconds': 7200})
    assert r.status_code == 201, r.data
    from datetime import datetime
    d = r.get_json()['data']
    span = (datetime.fromisoformat(d['valid_to'].replace('Z', '+00:00'))
            - datetime.fromisoformat(d['valid_from'].replace('Z', '+00:00'))).total_seconds()
    assert span > 7200
