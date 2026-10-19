"""The SCEP challenge validity range the API reports is the one it enforces."""


def test_reported_range_is_enforced(auth_client):
    cfg = auth_client.get('/api/v2/scep/config').get_json()['data']
    low, high = cfg['challenge_validity_range']
    assert (low, high) == (1, 720)
    try:
        for value, status in ((low, 200), (high, 200), (low - 1, 400), (high + 1, 400)):
            r = auth_client.patch('/api/v2/scep/config', json={'challenge_validity': value})
            assert r.status_code == status, (value, r.data)
    finally:
        auth_client.patch('/api/v2/scep/config', json={'challenge_validity': cfg['challenge_validity']})
