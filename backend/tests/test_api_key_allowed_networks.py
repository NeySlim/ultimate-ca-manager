"""An API key limited to source networks (#403): refused (403) from any other address, before
its use is recorded; a key it creates stays inside them; the list survives a regeneration."""
import json

import pytest

from models import db
from models.api_key import APIKey
from tests.conftest import assert_success

CONSOLE = '192.0.2.10'
ELSEWHERE = '198.51.100.7'


def _create(client, body, headers=None, environ=None):
    if not headers:  # a session proves the holder; a key calling with its own credential is exempt
        body = {**body, 'password': 'changeme123'}
    return client.post('/api/v2/account/apikeys', data=json.dumps(body), content_type='application/json',
                       headers=headers or {}, environ_base=environ or {})


def _get(app, key, addr, path='/api/v2/certificates'):
    return app.test_client().get(path, headers={'X-API-Key': key}, environ_base={'REMOTE_ADDR': addr})


@pytest.fixture(scope='module')
def limited(auth_client):
    data = assert_success(_create(auth_client, {
        'name': 'console-limited', 'permissions': ['read:certificates', 'write:certificates'],
        'allowed_networks': ['192.0.2.0/24', '2001:db8::1']}), 201)
    return data


def test_the_list_is_stored_canonical_and_returned(limited):
    assert limited['allowed_networks'] == ['192.0.2.0/24', '2001:db8::1']


def test_a_listed_address_is_served(app, limited):
    assert _get(app, limited['key'], CONSOLE).status_code == 200
    assert _get(app, limited['key'], '2001:db8::1').status_code == 200


def test_another_address_is_refused_with_403_and_no_use_recorded(app, limited):
    with app.app_context():
        before = db.session.get(APIKey, limited['id']).last_used_at
    r = _get(app, limited['key'], ELSEWHERE)
    assert r.status_code == 403
    assert b'not allowed from this address' in r.data
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(APIKey, limited['id']).last_used_at == before


def test_an_ipv4_mapped_peer_is_matched_as_ipv4(app, limited):
    assert _get(app, limited['key'], '::ffff:192.0.2.10').status_code == 200


def test_a_key_without_a_list_is_served_from_anywhere(app, auth_client):
    key = assert_success(_create(auth_client, {'name': 'open', 'permissions': ['read:certificates']}), 201)
    assert key['allowed_networks'] == []
    assert _get(app, key['key'], ELSEWHERE).status_code == 200


@pytest.mark.parametrize('bad', [['not-an-ip'], ['10.0.0.0/33'], 'fe80::1%eth0', 5])
def test_an_invalid_list_is_refused(auth_client, bad):
    r = _create(auth_client, {'name': 'bad', 'permissions': ['read:certificates'], 'allowed_networks': bad})
    assert r.status_code == 400


def test_the_list_is_also_read_from_a_comma_separated_string(auth_client):
    data = assert_success(_create(auth_client, {'name': 'csv', 'permissions': ['read:certificates'],
                                                'allowed_networks': '10.1.0.0/16, 10.2.0.1'}), 201)
    assert data['allowed_networks'] == ['10.1.0.0/16', '10.2.0.1']


def test_a_key_created_by_a_limited_key_inherits_its_list(app, limited):
    client = app.test_client()
    r = _create(client, {'name': 'child', 'permissions': ['read:certificates']},
                headers={'X-API-Key': limited['key']}, environ={'REMOTE_ADDR': CONSOLE})
    child = assert_success(r, 201)
    assert child['allowed_networks'] == limited['allowed_networks']
    assert _get(app, child['key'], ELSEWHERE).status_code == 403


def test_a_limited_key_cannot_create_a_wider_one(app, limited):
    client = app.test_client()
    for wider in (['0.0.0.0/0'], ['192.0.0.0/16'], ['198.51.100.7']):
        r = _create(client, {'name': 'wider', 'permissions': ['read:certificates'], 'allowed_networks': wider},
                    headers={'X-API-Key': limited['key']}, environ={'REMOTE_ADDR': CONSOLE})
        assert r.status_code == 403, wider
    narrower = _create(client, {'name': 'narrower', 'permissions': ['read:certificates'],
                                'allowed_networks': ['192.0.2.128/25']},
                       headers={'X-API-Key': limited['key']}, environ={'REMOTE_ADDR': CONSOLE})
    assert assert_success(narrower, 201)['allowed_networks'] == ['192.0.2.128/25']


def test_regeneration_keeps_the_list(app, auth_client):
    old = assert_success(_create(auth_client, {'name': 'regen', 'permissions': ['read:certificates'],
                                               'allowed_networks': ['192.0.2.0/24']}), 201)
    new = assert_success(auth_client.post(f"/api/v2/account/apikeys/{old['id']}/regenerate",
                                               json={'password': 'changeme123'}), 201)
    assert new['allowed_networks'] == ['192.0.2.0/24']
    assert _get(app, new['key'], ELSEWHERE).status_code == 403


def test_the_listing_shows_the_list(auth_client, limited):
    listed = assert_success(auth_client.get('/api/v2/account/apikeys'))
    row = next(k for k in listed if k['id'] == limited['id'])
    assert row['allowed_networks'] == ['192.0.2.0/24', '2001:db8::1']


def test_the_archive_carries_the_list_and_a_restore_writes_it_back(app, limited):
    from services.backup.export_generic import IdentityIndex, export_section
    from services.backup.backup_service import BackupService
    with app.app_context():
        key_hash = db.session.get(APIKey, limited['id']).key_hash
        rows = [r for r in export_section('api_keys', IdentityIndex()) if r.get('key_hash') == key_hash]
        assert json.loads(rows[0]['allowed_networks']) == ['192.0.2.0/24', '2001:db8::1']
        key = db.session.get(APIKey, limited['id'])
        key.allowed_networks = None
        db.session.commit()
        results = {'api_keys': 0}
        BackupService()._restore_api_keys({'api_keys': rows}, results)
        db.session.commit()
        db.session.expire_all()
        assert json.loads(db.session.get(APIKey, limited['id']).allowed_networks) == [
            '192.0.2.0/24', '2001:db8::1']


def _regenerate(app, key_id, caller):
    return app.test_client().post(f'/api/v2/account/apikeys/{key_id}/regenerate',
                                  headers={'X-API-Key': caller}, environ_base={'REMOTE_ADDR': CONSOLE})


def test_a_limited_key_regenerating_an_open_key_gives_it_its_own_list(app, auth_client, limited):
    sibling = assert_success(_create(auth_client, {'name': 'open-sibling', 'permissions': ['read:certificates']}), 201)
    new = assert_success(_regenerate(app, sibling['id'], limited['key']), 201)
    assert new['allowed_networks'] == limited['allowed_networks']
    assert _get(app, new['key'], ELSEWHERE).status_code == 403


def test_a_limited_key_cannot_regenerate_a_key_wider_than_itself(app, auth_client, limited):
    wider = assert_success(_create(auth_client, {'name': 'wider-sibling', 'permissions': ['read:certificates'],
                                                 'allowed_networks': ['198.51.100.0/24']}), 201)
    r = _regenerate(app, wider['id'], limited['key'])
    assert r.status_code == 403
    assert b'limited to its own networks' in r.data
    with app.app_context():
        assert db.session.get(APIKey, wider['id']).is_active
