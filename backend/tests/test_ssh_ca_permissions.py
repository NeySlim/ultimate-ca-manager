"""SSH CA routes answer to the ssh_cas scopes, SSH certificate routes to ssh.

`write:ssh` used to create, import, edit and delete SSH CAs as well as sign
certificates, so a key meant to issue certificates could also mint authorities.
"""
import json

import pytest

from auth.permissions import (
    CUSTOM_ROLE_GRANTABLE_PERMISSIONS, GROUP_GRANTABLE_PERMISSIONS, ROLE_PERMISSIONS,
)
from models import User
from tests.test_ssh import _generate_test_ssh_key

ACTIONS = ('read', 'write', 'delete')


def _post(client, url, body, headers=None):
    return client.post(url, data=json.dumps(body), content_type='application/json',
                       headers=headers or {})


def _put(client, url, body, headers=None):
    return client.put(url, data=json.dumps(body), content_type='application/json',
                      headers=headers or {})


def _openssh_private_key():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    key = ed25519.Ed25519PrivateKey.generate()
    return key.private_bytes(Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()).decode()


def _new_ca(auth_client, descr):
    r = _post(auth_client, '/api/v2/ssh/cas', {'descr': descr, 'ca_type': 'user',
                                               'key_type': 'ed25519', 'allow_any_principal': True})
    assert r.status_code == 201, r.data
    return r.get_json()['data']['id']


@pytest.fixture
def api_key(auth_client):
    """Keys owned by the admin, so each holds exactly the scopes it was given."""
    made = []

    def make(permissions):
        r = _post(auth_client, '/api/v2/account/apikeys', {'name': 'ssh-ca-scope', 'permissions': permissions})
        assert r.status_code == 201, r.data
        data = r.get_json()['data']
        made.append(data['id'])
        return {'X-API-Key': data['key']}

    yield make
    for key_id in made:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


def _ca_writes(client, headers, ca_id, spare_id):
    """Status of create, import, update and delete of an SSH CA."""
    return {
        'create': _post(client, '/api/v2/ssh/cas', {'descr': 'Scope probe CA', 'ca_type': 'user',
                                                    'key_type': 'ed25519'}, headers).status_code,
        'import': _post(client, '/api/v2/ssh/cas/import', {'descr': 'Scope import CA', 'ca_type': 'user',
                                                           'private_key': _openssh_private_key()},
                        headers).status_code,
        'update': _put(client, f'/api/v2/ssh/cas/{ca_id}', {'descr': 'Scope renamed CA'}, headers).status_code,
        'delete': client.delete(f'/api/v2/ssh/cas/{spare_id}', headers=headers).status_code,
    }


def _ca_reads(client, headers, ca_id):
    paths = ('/api/v2/ssh/cas', f'/api/v2/ssh/cas/{ca_id}', f'/api/v2/ssh/cas/{ca_id}/public-key',
             f'/api/v2/ssh/cas/{ca_id}/setup-script', f'/api/v2/ssh/cas/{ca_id}/krl')
    return {path: client.get(path, headers=headers).status_code for path in paths}


def _sign(client, headers, ca_id):
    return _post(client, '/api/v2/ssh/certificates', {
        'ca_id': ca_id, 'public_key': _generate_test_ssh_key(), 'cert_type': 'user',
        'principals': ['deploy']}, headers).status_code


class TestApiKeyScopes:
    def test_write_ssh_signs_but_manages_no_ca(self, app, auth_client, api_key):
        ca_id = _new_ca(auth_client, 'Cert scope CA')
        spare = _new_ca(auth_client, 'Cert scope spare CA')
        key = api_key(['read:ssh', 'write:ssh', 'delete:ssh'])
        client = app.test_client()
        assert _sign(client, key, ca_id) == 201
        assert client.get('/api/v2/ssh/certificates', headers=key).status_code == 200
        assert _ca_writes(client, key, ca_id, spare) == {
            'create': 403, 'import': 403, 'update': 403, 'delete': 403}
        assert set(_ca_reads(client, key, ca_id).values()) == {403}

    def test_ssh_cas_manages_cas_but_signs_nothing(self, app, auth_client, api_key):
        ca_id = _new_ca(auth_client, 'CA scope CA')
        spare = _new_ca(auth_client, 'CA scope spare CA')
        key = api_key(['read:ssh_cas', 'write:ssh_cas', 'delete:ssh_cas'])
        client = app.test_client()
        assert _ca_writes(client, key, ca_id, spare) == {
            'create': 201, 'import': 201, 'update': 200, 'delete': 204}
        assert set(_ca_reads(client, key, ca_id).values()) == {200}
        assert _sign(client, key, ca_id) == 403
        assert client.get('/api/v2/ssh/certificates', headers=key).status_code == 403


class TestCustomRole:
    def _login_with_role(self, app, auth_client, create_user, username, permissions):
        r = _post(auth_client, '/api/v2/rbac/roles', {'name': f'{username} role', 'permissions': permissions})
        assert r.status_code == 200, r.data
        role_id = r.get_json()['data']['id']
        create_user(username=username, role='viewer')
        with app.app_context():
            user_id = User.query.filter_by(username=username).first().id
        r = _put(auth_client, f'/api/v2/users/{user_id}', {'custom_role_id': role_id})
        assert r.status_code == 200, r.data
        client = app.test_client()
        r = _post(client, '/api/v2/auth/login', {'username': username, 'password': 'TestPass123!'})
        assert r.status_code == 200, r.data
        return client

    def test_write_ssh_role_signs_but_creates_no_ca(self, app, auth_client, create_user):
        ca_id = _new_ca(auth_client, 'Role cert scope CA')
        spare = _new_ca(auth_client, 'Role cert scope spare CA')
        client = self._login_with_role(app, auth_client, create_user, 'ssh_cert_signer', ['write:ssh'])
        assert _sign(client, None, ca_id) == 201
        assert _ca_writes(client, None, ca_id, spare) == {
            'create': 403, 'import': 403, 'update': 403, 'delete': 403}

    def test_write_ssh_cas_role_creates_but_signs_nothing(self, app, auth_client, create_user):
        ca_id = _new_ca(auth_client, 'Role CA scope CA')
        spare = _new_ca(auth_client, 'Role CA scope spare CA')
        client = self._login_with_role(app, auth_client, create_user, 'ssh_ca_keeper',
                                       ['write:ssh_cas', 'delete:ssh_cas'])
        assert _ca_writes(client, None, ca_id, spare) == {
            'create': 201, 'import': 201, 'update': 200, 'delete': 204}
        assert _sign(client, None, ca_id) == 403


@pytest.mark.parametrize('role', sorted(ROLE_PERMISSIONS))
def test_builtin_roles_keep_every_ssh_right(role):
    perms = ROLE_PERMISSIONS[role]
    for action in ACTIONS:
        if f'{action}:ssh' in perms:
            assert f'{action}:ssh_cas' in perms, (role, action)


def test_custom_roles_and_groups_may_grant_ssh_cas():
    for action in ACTIONS:
        assert f'{action}:ssh_cas' in CUSTOM_ROLE_GRANTABLE_PERMISSIONS
    assert {'read:ssh_cas', 'write:ssh_cas', 'delete:ssh_cas'} <= set(GROUP_GRANTABLE_PERMISSIONS)
