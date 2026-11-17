"""An administrator lists and revokes another user's API keys.

The secret is never returned, a revoked key stops authenticating at once, a
second call deletes it, and the audit log names who acted on whose key.
"""
import json
import uuid

import pytest

from models import User, db
from models.api_key import APIKey
from models.audit_log import AuditLog
from tests.conftest import get_json


def _login(app, username, password):
    c = app.test_client()
    r = c.post('/api/v2/auth/login', data=json.dumps({'username': username, 'password': password}),
               content_type='application/json')
    assert r.status_code == 200, r.data
    return c


@pytest.fixture
def owner(app, create_user, request):
    """An operator holding one API key; its rows are removed afterwards."""
    username = getattr(request, 'param', 'apikey-owner-{}').format(uuid.uuid4().hex[:8])
    user = create_user(username=username, role='operator')
    with app.app_context():
        row = db.session.get(User, user['id'])
        row.force_password_change = False
        db.session.commit()
    c = _login(app, username, 'TestPass123!')
    r = c.post('/api/v2/account/apikeys', json={'name': 'ci-runner', 'permissions': ['read:certificates']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    yield {'id': user['id'], 'username': username, 'key_id': key['id'], 'secret': key['key']}
    with app.app_context():
        APIKey.query.filter_by(user_id=user['id']).delete()
        db.session.commit()


def _url(owner, key_id=None):
    base = f"/api/v2/users/{owner['id']}/apikeys"
    return base if key_id is None else f'{base}/{key_id}'


def _key_works(app, secret):
    return app.test_client().get('/api/v2/certificates', headers={'X-API-Key': secret}).status_code == 200


def _last_audit(app, action):
    with app.app_context():
        return AuditLog.query.filter_by(action=action).order_by(AuditLog.id.desc()).first()


def test_admin_lists_the_keys_without_their_secret(auth_client, owner):
    listed = get_json(auth_client.get(_url(owner)))['data']
    assert [k['id'] for k in listed] == [owner['key_id']]
    assert listed[0]['name'] == 'ci-runner' and listed[0]['is_active'] is True
    assert not {'key', 'key_hash'} & set(listed[0])


@pytest.mark.parametrize('owner', ['apikey-owner-{}', 'brace{{{}}}', 'open{{{}'], indirect=True)
def test_admin_revokes_then_deletes(app, auth_client, owner):
    assert _key_works(app, owner['secret'])

    r = auth_client.delete(_url(owner, owner['key_id']))
    assert r.status_code == 200 and get_json(r)['message'] == 'API key revoked'
    assert not _key_works(app, owner['secret'])
    entry = _last_audit(app, 'apikey_admin_revoke')
    assert entry.username == 'admin' and entry.resource_id == str(owner['key_id'])
    assert owner['username'] in entry.details and 'by admin' in entry.details

    r = auth_client.delete(_url(owner, owner['key_id']))
    assert r.status_code == 200 and get_json(r)['message'] == 'API key deleted'
    with app.app_context():
        assert db.session.get(APIKey, owner['key_id']) is None
    assert _last_audit(app, 'apikey_admin_delete').resource_id == str(owner['key_id'])


def test_a_key_of_another_user_is_not_found(app, auth_client, owner):
    with app.app_context():
        admin_id = User.query.filter_by(username='admin').first().id
    assert auth_client.delete(f"/api/v2/users/{admin_id}/apikeys/{owner['key_id']}").status_code == 404
    assert auth_client.get('/api/v2/users/999999/apikeys').status_code == 404
    assert _key_works(app, owner['secret'])


def test_without_write_users_both_routes_are_refused(app, viewer_client, owner):
    assert viewer_client.get(_url(owner)).status_code == 403
    assert viewer_client.delete(_url(owner, owner['key_id'])).status_code == 403
    assert _key_works(app, owner['secret'])


def test_an_api_key_cannot_revoke_through_its_own_account(app, auth_client):
    r = auth_client.post('/api/v2/account/apikeys', json={'name': 'own-account', 'permissions': ['*']})
    key = get_json(r)['data']
    with app.app_context():
        admin_id = User.query.filter_by(username='admin').first().id
    r = app.test_client().delete(f"/api/v2/users/{admin_id}/apikeys/{key['id']}",
                                 headers={'X-API-Key': key['key']})
    assert r.status_code == 403
    assert _key_works(app, key['key'])


def test_the_owner_route_still_revokes_then_deletes(app, owner):
    c = _login(app, owner['username'], 'TestPass123!')
    url = f"/api/v2/account/apikeys/{owner['key_id']}"
    assert get_json(c.delete(url))['message'] == 'API key revoked'
    assert _last_audit(app, 'apikey_revoke').resource_id == str(owner['key_id'])
    assert get_json(c.delete(url))['message'] == 'API key deleted'
    assert _last_audit(app, 'apikey_delete').details == 'Deleted API key: ci-runner'
