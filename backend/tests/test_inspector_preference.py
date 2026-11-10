"""The inspector's position and size are a per-user preference, validated server-side."""
import pytest

GOOD = {'position': 'right', 'height': 420, 'width': 560}


def test_inspector_preference_is_stored_and_read_back(auth_client):
    r = auth_client.put('/api/v2/account/preferences', json={'inspector': GOOD})
    assert r.status_code == 200
    assert r.get_json()['data'] == {'inspector': GOOD}
    r = auth_client.get('/api/v2/account/preferences')
    assert r.get_json()['data']['inspector'] == GOOD


@pytest.mark.parametrize('bad', [
    'right', None, [], {'position': 'left'}, {'position': 'bottom', 'height': 'tall'},
    {'position': 'bottom', 'height': 10}, {'position': 'bottom', 'width': 99999},
    {'position': 'bottom', 'height': True}, {'position': 'bottom', 'extra': 1},
])
def test_invalid_inspector_preference_is_refused(auth_client, bad):
    auth_client.put('/api/v2/account/preferences', json={'inspector': GOOD})
    r = auth_client.put('/api/v2/account/preferences', json={'inspector': bad})
    assert r.status_code == 400
    # The refused write leaves the stored value untouched
    r = auth_client.get('/api/v2/account/preferences')
    assert r.get_json()['data']['inspector'] == GOOD


def test_partial_inspector_preference_is_accepted(auth_client):
    r = auth_client.put('/api/v2/account/preferences', json={'inspector': {'position': 'bottom'}})
    assert r.status_code == 200
