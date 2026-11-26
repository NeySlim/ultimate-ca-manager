"""A request signed by an API key holds no session: issuing it a CSRF token opens none (#457).

Each such call would otherwise create a server-side session record and a cookie, and on the
file store crowd out the records of signed-in users.
"""
import json


def _api_key(auth_client):
    r = auth_client.post('/api/v2/account/apikeys', data=json.dumps({
        'name': 'csrf-no-session', 'permissions': ['read:certificates'],
    }), content_type='application/json')
    assert r.status_code == 201, r.data
    return r.get_json()['data']['key']


def test_an_api_key_verify_sets_no_session_cookie(app, auth_client):
    key = _api_key(auth_client)
    for _ in range(2):
        c = app.test_client()
        r = c.get('/api/v2/auth/verify', headers={'X-API-Key': key})
        assert r.status_code == 200, r.data
        data = r.get_json()['data']
        assert data['authenticated'] is True
        assert data['auth_method'] == 'api_key'
        cookies = r.headers.getlist('Set-Cookie')
        assert not [h for h in cookies if h.startswith(app.config.get('SESSION_COOKIE_NAME', 'session') + '=')], cookies
        assert c.get_cookie(app.config.get('SESSION_COOKIE_NAME', 'session')) is None
