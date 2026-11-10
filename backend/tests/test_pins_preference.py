"""The shell pins: at most three module ids per user, stored with the preferences."""
import pytest


def _put(client, pins):
    return client.put('/api/v2/account/preferences', json={'pins': pins})


def test_pins_are_stored_and_read_back_in_order(auth_client):
    r = _put(auth_client, ['audit', 'keyRecovery', 'ssh-cas'])
    assert r.status_code == 200
    assert r.get_json()['data']['pins'] == ['audit', 'keyRecovery', 'ssh-cas']
    r = auth_client.get('/api/v2/account/preferences')
    assert r.get_json()['data']['pins'] == ['audit', 'keyRecovery', 'ssh-cas']


def test_empty_pins_are_accepted(auth_client):
    r = _put(auth_client, [])
    assert r.status_code == 200
    assert r.get_json()['data']['pins'] == []


@pytest.mark.parametrize('bad', [
    ['a', 'b', 'c', 'd'],          # fourth pin
    ['audit', 'audit'],            # duplicate
    'audit',                       # not a list
    [1],                           # not a string
    [[1]],                         # unhashable element
    ['audit\n'],                   # trailing newline
    [{}],
    [''],                          # empty id
    ['Has Space'],                 # format
    ['../etc'],
    ['x' * 41],
    None,
    {'0': 'audit'},
])
def test_invalid_pins_are_refused_with_400(auth_client, bad):
    assert _put(auth_client, ['cas']).status_code == 200
    r = _put(auth_client, bad)
    assert r.status_code == 400
    # the stored value is untouched by the refused request
    r = auth_client.get('/api/v2/account/preferences')
    assert r.get_json()['data']['pins'] == ['cas']


def test_refused_pins_do_not_discard_other_keys(auth_client):
    assert auth_client.put('/api/v2/account/preferences',
                           json={'language': 'fr', 'pins': ['cas']}).status_code == 200
    assert _put(auth_client, ['a'] * 4).status_code == 400
    data = auth_client.get('/api/v2/account/preferences').get_json()['data']
    assert data == {'language': 'fr', 'pins': ['cas']}
