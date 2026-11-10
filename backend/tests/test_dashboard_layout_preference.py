"""The overview layout is a per-user preference under the `dashboard` key."""
import pytest

GOOD = {'order': ['queue', 'health'], 'hidden': ['issuance'], 'queueShowAll': True}


def _put(client, value):
    r = client.put('/api/v2/account/preferences', json={'dashboard': value})
    assert r.status_code == 200
    return r.get_json()['data']


def test_the_layout_is_stored_and_read_back(auth_client):
    assert _put(auth_client, GOOD) == {'dashboard': GOOD}
    assert auth_client.get('/api/v2/account/preferences').get_json()['data']['dashboard'] == GOOD
    _put(auth_client, {})


@pytest.mark.parametrize('bad', ['x', ['queue'], {'order': 'queue'}, {'order': [1]}, {'other': 1},
                                 {'queueShowAll': 'yes'}, {'hidden': ['x' * 31]}, {'order': ['a'] * 21}])
def test_an_invalid_layout_is_dropped(auth_client, bad):
    assert 'dashboard' not in _put(auth_client, bad)
