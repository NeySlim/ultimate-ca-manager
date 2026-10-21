"""An API key can only mint or regenerate keys within its own scopes.

Granting is bounded by the owner's permissions AND by the credential making the
request: a `read:certificates` key belonging to an admin must not create a `*`
key, nor regenerate one the same admin already holds.
"""
import json

import pytest

from tests.conftest import assert_success


def _create(client, permissions, name='mint-escalation', headers=None):
    return client.post(
        '/api/v2/account/apikeys',
        data=json.dumps({'name': name, 'permissions': permissions}),
        content_type='application/json',
        headers=headers or {},
    )


@pytest.fixture
def keys(auth_client):
    """Create keys through the admin session; revoke them all afterwards (10 per user)."""
    created = []

    def make(permissions, name='mint-escalation'):
        data = assert_success(_create(auth_client, permissions, name), 201)
        created.append(data['id'])
        return data

    yield make, created
    for key_id in created:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


def _as_key(key):
    return {'X-API-Key': key['key']}


def test_narrow_key_cannot_mint_a_wildcard_key(app, keys):
    make, _ = keys
    narrow = make(['read:certificates'])
    r = _create(app.test_client(), ['*'], headers=_as_key(narrow))
    assert r.status_code == 403, r.data


def test_narrow_key_cannot_mint_a_wider_scope(app, keys):
    make, _ = keys
    narrow = make(['read:certificates'])
    for scope in (['write:certificates'], ['read:*'], ['admin:system']):
        r = _create(app.test_client(), scope, headers=_as_key(narrow))
        assert r.status_code == 403, (scope, r.data)


def test_narrow_key_can_mint_within_its_scope(app, keys):
    make, created = keys
    narrow = make(['read:certificates'])
    r = _create(app.test_client(), ['read:certificates'], headers=_as_key(narrow))
    created.append(assert_success(r, 201)['id'])


def test_narrow_key_cannot_regenerate_a_wider_key(app, keys):
    make, created = keys
    wide = make(['*'], name='wide')
    narrow = make(['read:certificates'])
    r = app.test_client().post(f"/api/v2/account/apikeys/{wide['id']}/regenerate",
                               headers=_as_key(narrow))
    assert r.status_code == 403, r.data


def test_key_can_regenerate_itself(app, keys):
    make, created = keys
    narrow = make(['read:certificates'])
    r = app.test_client().post(f"/api/v2/account/apikeys/{narrow['id']}/regenerate",
                               headers=_as_key(narrow))
    created.append(assert_success(r, 201)['id'])


def test_admin_session_still_mints_wildcard_keys(keys):
    make, _ = keys
    assert make(['*'])['permissions'] == ['*']
