"""The Ko-fi support card remembers, per user, the version it was dismissed for."""


def test_kofi_seen_version_is_stored_and_read_back(auth_client):
    r = auth_client.put('/api/v2/account/preferences',
                        json={'language': 'fr', 'kofi_seen_version': '2.242'})
    assert r.status_code == 200
    assert r.get_json()['data'] == {'language': 'fr', 'kofi_seen_version': '2.242'}

    r = auth_client.get('/api/v2/account/preferences')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data.get('kofi_seen_version') == '2.242'
    assert data.get('language') == 'fr'


def test_kofi_seen_version_rejects_invalid_values(auth_client):
    for bad in ('x' * 33, '', 2242, None, ['2.242']):
        r = auth_client.put('/api/v2/account/preferences',
                            json={'kofi_seen_version': bad})
        assert r.status_code == 200
        assert 'kofi_seen_version' not in r.get_json()['data'], bad
