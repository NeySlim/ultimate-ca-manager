"""An API key cannot outlive the key that created it, and a dead key is not regenerated."""
import json
from datetime import datetime, timedelta

import pytest

from models import db
from models.api_key import APIKey
from tests.conftest import assert_success
from utils.datetime_utils import utc_now


def _create(client, body, headers=None):
    return client.post('/api/v2/account/apikeys', data=json.dumps(body),
                       content_type='application/json', headers=headers or {})


def _expiry(data):
    value = data['expires_at']
    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None) if value else None


@pytest.fixture
def keys(auth_client):
    created = []

    def make(expires_days=1, permissions=('read:certificates',)):
        data = assert_success(_create(auth_client, {'name': 'lifetime', 'permissions': list(permissions),
                                                    'expires_days': expires_days}), 201)
        created.append(data['id'])
        return data

    yield make, created
    for key_id in created:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


@pytest.mark.parametrize('body', [{'expires_days': None}, {'expires_days': 365}, {}])
def test_a_key_made_by_a_key_expires_with_it(app, keys, body):
    make, created = keys
    parent = make(expires_days=1)
    r = _create(app.test_client(), {'name': 'child', 'permissions': ['read:certificates'], **body},
                headers={'X-API-Key': parent['key']})
    child = assert_success(r, 201)
    created.append(child['id'])
    assert _expiry(child) is not None
    assert _expiry(child) <= _expiry(parent)


def test_a_session_still_creates_a_key_without_expiry(keys):
    make, _ = keys
    assert make(expires_days=None)['expires_at'] is None


def test_a_revoked_key_is_not_regenerated(app, auth_client, keys):
    make, _ = keys
    key = make()
    with app.app_context():
        db.session.get(APIKey, key['id']).is_active = False
        db.session.commit()
    r = auth_client.post(f"/api/v2/account/apikeys/{key['id']}/regenerate")
    assert r.status_code == 409, r.data


def test_an_expired_key_is_not_regenerated(app, auth_client, keys):
    make, _ = keys
    key = make()
    with app.app_context():
        db.session.get(APIKey, key['id']).expires_at = utc_now() - timedelta(minutes=1)
        db.session.commit()
    r = auth_client.post(f"/api/v2/account/apikeys/{key['id']}/regenerate")
    assert r.status_code == 409, r.data


def test_regenerate_keeps_the_original_lifetime(auth_client, keys):
    make, created = keys
    key = make(expires_days=7)
    data = assert_success(auth_client.post(f"/api/v2/account/apikeys/{key['id']}/regenerate"), 201)
    created.append(data['id'])
    lifetime = _expiry(data) - utc_now().replace(tzinfo=None)
    assert timedelta(days=6) < lifetime <= timedelta(days=7)


def test_regenerate_through_a_key_is_capped_by_it(app, auth_client, keys):
    make, created = keys
    forever = make(expires_days=None)
    parent = make(expires_days=1)
    r = app.test_client().post(f"/api/v2/account/apikeys/{forever['id']}/regenerate",
                               headers={'X-API-Key': parent['key']})
    data = assert_success(r, 201)
    created.append(data['id'])
    assert _expiry(data) is not None
    assert _expiry(data) <= _expiry(parent)
