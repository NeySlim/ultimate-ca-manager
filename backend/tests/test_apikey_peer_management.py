"""An API key manages a sibling key of its owner (rename, revoke, delete) only when it holds every
scope of that key, the rule regenerate applies: a narrow key that leaks cannot take down or erase
the owner's wider keys. A key always manages itself, and a session every key of its account."""
import json

import pytest

from models import db
from models.api_key import APIKey

pytestmark = pytest.mark.usefixtures('drop_new_users')

PASSWORD = 'TestPass123!'


def _send(client, method, url, body=None, **kw):
    return client.open(url, method=method, data=json.dumps(body or {}), content_type='application/json', **kw)


@pytest.fixture
def keys(app, create_user):
    create_user(username='apikey_peer_owner', role='admin')
    session = app.test_client()
    assert _send(session, 'POST', '/api/v2/auth/login',
                 {'username': 'apikey_peer_owner', 'password': PASSWORD}).status_code == 200
    made = {}
    for name, perms in (('wide', ['*']), ('narrow', ['read:certificates'])):
        r = _send(session, 'POST', '/api/v2/account/apikeys',
                  {'name': name, 'permissions': perms, 'password': PASSWORD})
        assert r.status_code == 201, r.data
        data = r.get_json()['data']
        made[name] = (data['id'], {'X-API-Key': data['key']})
    made['session'] = session
    return made


def _state(app, key_id):
    with app.app_context():
        db.session.expire_all()
        key = db.session.get(APIKey, key_id)
        return None if key is None else (key.name, bool(key.is_active))


def test_a_narrow_key_cannot_revoke_delete_or_rename_a_wider_one(app, keys):
    wide_id, _ = keys['wide']
    _, narrow = keys['narrow']
    client = app.test_client()
    for _ in range(2):  # a second DELETE would erase the revoked row
        assert _send(client, 'DELETE', f'/api/v2/account/apikeys/{wide_id}', headers=narrow).status_code == 403
    assert _send(client, 'PATCH', f'/api/v2/account/apikeys/{wide_id}', {'name': 'taken'},
                 headers=narrow).status_code == 403
    assert _state(app, wide_id) == ('wide', True)


def test_a_key_manages_itself_and_the_keys_it_covers(app, keys):
    wide_id, wide = keys['wide']
    narrow_id, narrow = keys['narrow']
    client = app.test_client()
    assert _send(client, 'PATCH', f'/api/v2/account/apikeys/{narrow_id}', {'name': 'mine'},
                 headers=narrow).status_code == 200
    assert _send(client, 'PATCH', f'/api/v2/account/apikeys/{narrow_id}', {'name': 'renamed by wide'},
                 headers=wide).status_code == 200
    assert _state(app, narrow_id) == ('renamed by wide', True)
    assert _send(client, 'DELETE', f'/api/v2/account/apikeys/{narrow_id}', headers=wide).status_code == 200
    assert _state(app, narrow_id) == ('renamed by wide', False)
    assert _send(client, 'DELETE', f'/api/v2/account/apikeys/{wide_id}', headers=wide).status_code == 200
    assert _state(app, wide_id) == ('wide', False)


def test_a_key_revokes_itself_even_when_narrow(app, keys):
    narrow_id, narrow = keys['narrow']
    assert _send(app.test_client(), 'DELETE', f'/api/v2/account/apikeys/{narrow_id}',
                 headers=narrow).status_code == 200
    assert _state(app, narrow_id) == ('narrow', False)


def test_a_session_still_manages_every_key(app, keys):
    wide_id, _ = keys['wide']
    session = keys['session']
    assert _send(session, 'PATCH', f'/api/v2/account/apikeys/{wide_id}', {'name': 'w2'}).status_code == 200
    assert _send(session, 'DELETE', f'/api/v2/account/apikeys/{wide_id}').status_code == 200
    assert _send(session, 'DELETE', f'/api/v2/account/apikeys/{wide_id}').status_code == 200
    assert _state(app, wide_id) is None


def test_a_scope_the_owner_lost_leaves_the_key_to_a_session(app, keys):
    """Even a `*` key cannot manage a sibling holding a scope its owner no longer has."""
    from models import User
    session = keys['session']
    r = _send(session, 'POST', '/api/v2/account/apikeys',
              {'name': 'writer', 'permissions': ['write:certificates'], 'password': PASSWORD})
    assert r.status_code == 201, r.data
    writer_id = r.get_json()['data']['id']
    with app.app_context():
        User.query.filter_by(username='apikey_peer_owner').one().role = 'viewer'
        db.session.commit()
    wide_id, wide = keys['wide']
    r = _send(app.test_client(), 'DELETE', f'/api/v2/account/apikeys/{writer_id}', headers=wide)
    assert r.status_code == 403
    message = r.get_json()['message']
    assert 'owner' in message and 'session' in message, message
    assert _state(app, writer_id) == ('writer', True)
    assert _send(session, 'DELETE', f'/api/v2/account/apikeys/{writer_id}').status_code == 200
