"""An API key outlives a password change: a session creating or regenerating one
proves the account holder again (OWASP ASVS 4.0.3 V3.7.1). A key calling with its
own credential is no session, and its child is bounded by it (scopes, expiry)."""
import json

import pytest

from models import db
from models.api_key import APIKey

pytestmark = pytest.mark.usefixtures('drop_new_users')

PASSWORD = 'TestPass123!'
BODY = {'name': 'proof-probe', 'permissions': ['read:certificates']}


def _post(client, url, body, **kw):
    return client.post(url, data=json.dumps(body), content_type='application/json', **kw)


def _signed_in(app, create_user, username, role='operator'):
    create_user(username=username, role=role)
    client = app.test_client()
    r = _post(client, '/api/v2/auth/login', {'username': username, 'password': PASSWORD})
    assert r.status_code == 200, r.data
    return client


def _reauth(r):
    return ((r.get_json() or {}).get('details') or {}).get('reauth')


def _own_keys(app, client):
    with app.app_context():
        db.session.expire_all()
        uid = client.get('/api/v2/account/profile').get_json()['data']['id']
        return APIKey.query.filter_by(user_id=uid).count()


@pytest.mark.parametrize('body, message', [
    (BODY, None), (dict(BODY, password='not-the-password'), 'Invalid password')])
def test_a_session_creates_no_key_without_the_password(app, create_user, body, message):
    c = _signed_in(app, create_user, f'apikey_proof_{bool(message)}')
    r = _post(c, '/api/v2/account/apikeys', body)
    assert r.status_code == 403, r.data
    assert _reauth(r) == 'password'
    if message:
        assert r.get_json()['message'] == message
    assert _own_keys(app, c) == 0


def test_a_session_creates_and_regenerates_with_the_password(app, create_user):
    c = _signed_in(app, create_user, 'apikey_proof_ok')
    r = _post(c, '/api/v2/account/apikeys', dict(BODY, password=PASSWORD))
    assert r.status_code == 201, r.data
    key_id = r.get_json()['data']['id']

    r = _post(c, f'/api/v2/account/apikeys/{key_id}/regenerate', {})
    assert r.status_code == 403, r.data
    assert _reauth(r) == 'password'
    with app.app_context():
        assert db.session.get(APIKey, key_id).is_active

    r = _post(c, f'/api/v2/account/apikeys/{key_id}/regenerate', {'password': PASSWORD})
    assert r.status_code == 201, r.data


def test_a_key_creates_a_key_with_its_own_credential(app, create_user):
    c = _signed_in(app, create_user, 'apikey_proof_by_key')
    parent = _post(c, '/api/v2/account/apikeys',
                   {'name': 'parent', 'permissions': ['read:certificates'], 'password': PASSWORD})
    assert parent.status_code == 201, parent.data
    r = _post(app.test_client(), '/api/v2/account/apikeys', BODY,
              headers={'X-API-Key': parent.get_json()['data']['key']})
    assert r.status_code == 201, r.data
