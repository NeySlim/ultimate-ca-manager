"""
SSH Certificate Authority & Certificate API Tests — /api/v2/ssh/*

Comprehensive tests for SSH CA and certificate management:
- List SSH CAs (GET)
- Create SSH CA — user & host types (POST)
- Get SSH CA details (GET)
- Update SSH CA (PUT)
- Delete SSH CA (DELETE)
- Get CA public key (GET)
- List SSH Certificates (GET)
- Sign / issue SSH certificate (POST)
- Generate key + certificate (POST)
- Get SSH certificate (GET)
- Delete SSH certificate (DELETE)
- Revoke SSH certificate (POST)
- Export SSH certificate (GET)
- SSH Stats (GET)
- Auth required checks
- RBAC viewer permission checks

Uses shared conftest fixtures: app, client, auth_client, viewer_client.
"""
import pytest
import json
import os
import sys
from tests.conftest import get_json, assert_success, assert_error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'

VALID_USER_CA = {
    'descr': 'Test User CA',
    'ca_type': 'user',
    'key_type': 'ed25519',
}

VALID_HOST_CA = {
    'descr': 'Test Host CA',
    'ca_type': 'host',
    'key_type': 'ed25519',
}

def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _create_ssh_ca(auth_client, ca_type='user', descr=None, key_type='ed25519'):
    """Helper to create an SSH CA and return the response data."""
    payload = {
        'descr': descr or f'Test {ca_type.capitalize()} CA',
        'ca_type': ca_type,
        'key_type': key_type,
    }
    r = post_json(auth_client, '/api/v2/ssh/cas', payload)
    assert r.status_code == 201, f'Create SSH CA failed ({r.status_code}): {r.data}'
    return json.loads(r.data).get('data', json.loads(r.data))


def _generate_test_ssh_key():
    """Generate a test Ed25519 SSH public key using the cryptography library."""
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives.serialization import ssh as ssh_ser
    private_key = ed25519.Ed25519PrivateKey.generate()
    pub_bytes = ssh_ser.serialize_ssh_public_key(private_key.public_key())
    return pub_bytes.decode('utf-8')


# ============================================================
# Auth Required — all SSH endpoints must reject unauthenticated
# ============================================================

class TestSSHAuthRequired:
    """All SSH endpoints must return 401 without authentication."""

    def test_list_ssh_cas_requires_auth(self, client):
        assert client.get('/api/v2/ssh/cas').status_code == 401

    def test_create_ssh_ca_requires_auth(self, client):
        r = post_json(client, '/api/v2/ssh/cas', VALID_USER_CA)
        assert r.status_code == 401

    def test_get_ssh_ca_requires_auth(self, client):
        assert client.get('/api/v2/ssh/cas/1').status_code == 401

    def test_update_ssh_ca_requires_auth(self, client):
        r = put_json(client, '/api/v2/ssh/cas/1', {'descr': 'x'})
        assert r.status_code == 401

    def test_delete_ssh_ca_requires_auth(self, client):
        assert client.delete('/api/v2/ssh/cas/1').status_code == 401

    def test_get_ssh_ca_public_key_requires_auth(self, client):
        assert client.get('/api/v2/ssh/cas/1/public-key').status_code == 401

    def test_list_ssh_certificates_requires_auth(self, client):
        assert client.get('/api/v2/ssh/certificates').status_code == 401

    def test_sign_ssh_certificate_requires_auth(self, client):
        r = post_json(client, '/api/v2/ssh/certificates', {})
        assert r.status_code == 401

    def test_get_ssh_certificate_requires_auth(self, client):
        assert client.get('/api/v2/ssh/certificates/1').status_code == 401

    def test_delete_ssh_certificate_requires_auth(self, client):
        assert client.delete('/api/v2/ssh/certificates/1').status_code == 401

    def test_revoke_ssh_certificate_requires_auth(self, client):
        r = post_json(client, '/api/v2/ssh/certificates/1/revoke', {})
        assert r.status_code == 401

    def test_generate_ssh_certificate_requires_auth(self, client):
        r = post_json(client, '/api/v2/ssh/certificates/generate', {})
        assert r.status_code == 401

    def test_ssh_stats_requires_auth(self, client):
        assert client.get('/api/v2/ssh/stats').status_code == 401


# ============================================================
# Create SSH CA
# ============================================================

class TestCreateSSHCA:
    """POST /api/v2/ssh/cas"""

    def test_create_user_ca(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/cas', VALID_USER_CA)
        data = assert_success(r, status=201)
        assert data['id'] is not None
        assert data['ca_type'] == 'user'
        assert data['key_type'] == 'ed25519'
        assert data['descr'] == 'Test User CA'
        assert data['public_key'].startswith('ssh-ed25519')
        assert data['fingerprint'].startswith('SHA256:')

    def test_create_host_ca(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/cas', VALID_HOST_CA)
        data = assert_success(r, status=201)
        assert data['id'] is not None
        assert data['ca_type'] == 'host'
        assert data['key_type'] == 'ed25519'

    def test_create_ca_rsa_key(self, auth_client):
        payload = {**VALID_USER_CA, 'descr': 'RSA User CA', 'key_type': 'rsa'}
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        data = assert_success(r, status=201)
        assert data['key_type'] == 'rsa'
        assert data['public_key'].startswith('ssh-rsa')

    def test_create_ca_ecdsa_key(self, auth_client):
        payload = {**VALID_USER_CA, 'descr': 'ECDSA User CA', 'key_type': 'ecdsa-p256'}
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        data = assert_success(r, status=201)
        assert data['key_type'] == 'ecdsa-p256'

    def test_create_ca_missing_descr(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/cas', {'ca_type': 'user'})
        assert_error(r, 400)

    def test_create_ca_empty_descr(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/cas', {'descr': '', 'ca_type': 'user'})
        assert_error(r, 400)

    def test_create_ca_invalid_type(self, auth_client):
        payload = {**VALID_USER_CA, 'ca_type': 'invalid'}
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        assert_error(r, 400)

    def test_create_ca_invalid_key_type(self, auth_client):
        payload = {**VALID_USER_CA, 'key_type': 'dsa'}
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        assert_error(r, 400)

    def test_create_ca_with_custom_ttl(self, auth_client):
        payload = {**VALID_USER_CA, 'descr': 'Custom TTL CA', 'default_ttl': 3600}
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        data = assert_success(r, status=201)
        assert data['default_ttl'] == 3600

    def test_create_ca_with_allowed_principals(self, auth_client):
        payload = {
            **VALID_USER_CA,
            'descr': 'Restricted CA',
            'allowed_principals': ['admin', 'deploy'],
        }
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        data = assert_success(r, status=201)
        assert 'admin' in data['allowed_principals']
        assert 'deploy' in data['allowed_principals']

    def test_create_ca_user_default_extensions(self, auth_client):
        """User CAs should get default OpenSSH extensions."""
        payload = {**VALID_USER_CA, 'descr': 'Default Ext CA'}
        r = post_json(auth_client, '/api/v2/ssh/cas', payload)
        data = assert_success(r, status=201)
        assert 'permit-pty' in data['default_extensions']

    def test_create_ca_empty_body(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/cas', {})
        assert_error(r, 400)


# ============================================================
# List SSH CAs
# ============================================================

class TestListSSHCAs:
    """GET /api/v2/ssh/cas"""

    def test_list_ssh_cas_returns_array(self, auth_client):
        _create_ssh_ca(auth_client, descr='Listed SSH CA')
        r = auth_client.get('/api/v2/ssh/cas')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_ssh_cas_pagination_meta(self, auth_client):
        r = auth_client.get('/api/v2/ssh/cas?page=1&per_page=5')
        body = get_json(r)
        assert r.status_code == 200
        assert 'meta' in body
        assert body['meta']['page'] == 1
        assert body['meta']['per_page'] == 5

    def test_list_ssh_cas_filter_by_type(self, auth_client):
        _create_ssh_ca(auth_client, ca_type='host', descr='Host Filter CA')
        r = auth_client.get('/api/v2/ssh/cas?type=host')
        data = assert_success(r)
        for ca in data:
            assert ca['ca_type'] == 'host'

    def test_list_ssh_cas_search(self, auth_client):
        _create_ssh_ca(auth_client, descr='UniqueSearchSSHCA')
        r = auth_client.get('/api/v2/ssh/cas?search=UniqueSearchSSHCA')
        data = assert_success(r)
        assert any('UniqueSearchSSHCA' in ca['descr'] for ca in data)

    def test_list_ssh_cas_contains_expected_fields(self, auth_client):
        _create_ssh_ca(auth_client, descr='Fields Check CA')
        r = auth_client.get('/api/v2/ssh/cas')
        data = assert_success(r)
        ca = data[0]
        for field in ['id', 'descr', 'ca_type', 'key_type', 'fingerprint',
                       'public_key', 'default_ttl', 'cert_count']:
            assert field in ca, f'Missing field: {field}'


# ============================================================
# Get SSH CA
# ============================================================

class TestGetSSHCA:
    """GET /api/v2/ssh/cas/<id>"""

    def test_get_ssh_ca(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Get Me CA')
        r = auth_client.get(f'/api/v2/ssh/cas/{ca["id"]}')
        data = assert_success(r)
        assert data['id'] == ca['id']
        assert data['descr'] == 'Get Me CA'

    def test_get_ssh_ca_not_found(self, auth_client):
        r = auth_client.get('/api/v2/ssh/cas/999999')
        assert_error(r, 404)


# ============================================================
# Update SSH CA
# ============================================================

class TestUpdateSSHCA:
    """PUT /api/v2/ssh/cas/<id>"""

    def test_update_ssh_ca_descr(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Before Update')
        r = put_json(auth_client, f'/api/v2/ssh/cas/{ca["id"]}', {'descr': 'After Update'})
        data = assert_success(r)
        assert data['descr'] == 'After Update'

    def test_update_ssh_ca_default_ttl(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='TTL Update CA')
        r = put_json(auth_client, f'/api/v2/ssh/cas/{ca["id"]}', {'default_ttl': 7200})
        data = assert_success(r)
        assert data['default_ttl'] == 7200

    def test_update_ssh_ca_not_found(self, auth_client):
        r = put_json(auth_client, '/api/v2/ssh/cas/999999', {'descr': 'x'})
        assert_error(r, 400)


# ============================================================
# Delete SSH CA
# ============================================================

class TestDeleteSSHCA:
    """DELETE /api/v2/ssh/cas/<id>"""

    def test_delete_ssh_ca(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='To Be Deleted CA')
        r = auth_client.delete(f'/api/v2/ssh/cas/{ca["id"]}')
        assert r.status_code == 204

        # Verify gone
        r = auth_client.get(f'/api/v2/ssh/cas/{ca["id"]}')
        assert_error(r, 404)

    def test_delete_ssh_ca_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/ssh/cas/999999')
        assert_error(r, 404)

    def test_delete_ssh_ca_with_certificates(self, auth_client):
        """Deleting a CA that has issued certs should be blocked (409)."""
        ca = _create_ssh_ca(auth_client, descr='CA With Certs')
        pub_key = _generate_test_ssh_key()
        post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': ['testuser'],
        })
        r = auth_client.delete(f'/api/v2/ssh/cas/{ca["id"]}')
        assert_error(r, 409)


# ============================================================
# Get SSH CA Public Key
# ============================================================

class TestGetSSHCAPublicKey:
    """GET /api/v2/ssh/cas/<id>/public-key"""

    def test_get_public_key(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='PubKey CA')
        r = auth_client.get(f'/api/v2/ssh/cas/{ca["id"]}/public-key')
        assert r.status_code == 200
        assert r.content_type == 'text/plain; charset=utf-8'
        assert r.data.decode('utf-8').startswith('ssh-ed25519')

    def test_get_public_key_not_found(self, auth_client):
        r = auth_client.get('/api/v2/ssh/cas/999999/public-key')
        assert_error(r, 404)


# ============================================================
# Sign / Issue SSH Certificate (POST /api/v2/ssh/certificates)
# ============================================================

class TestSignSSHCertificate:
    """POST /api/v2/ssh/certificates"""

    def test_sign_user_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, ca_type='user', descr='Sign User CA')
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': ['testuser'],
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        data = assert_success(r, status=201)
        assert data['cert_type'] == 'user'
        assert data['ssh_ca_id'] == ca['id']
        assert 'testuser' in data['principals']
        assert data['serial'] >= 1
        assert data['fingerprint'].startswith('SHA256:')
        assert data['certificate'] is not None
        assert data['status'] == 'valid'
        assert data['revoked'] is False

    def test_sign_host_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, ca_type='host', descr='Sign Host CA')
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'host',
            'principals': ['server1.example.com'],
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        data = assert_success(r, status=201)
        assert data['cert_type'] == 'host'
        assert 'server1.example.com' in data['principals']

    def test_sign_certificate_multiple_principals(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Multi Principal CA')
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': ['alice', 'bob', 'deploy'],
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        data = assert_success(r, status=201)
        assert set(['alice', 'bob', 'deploy']).issubset(set(data['principals']))

    def test_sign_certificate_custom_validity(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Validity CA')
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': ['testuser'],
            'validity_seconds': 3600,
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        data = assert_success(r, status=201)
        assert data['valid_from'] is not None
        assert data['valid_to'] is not None

    def test_sign_certificate_custom_key_id(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='KeyID CA')
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': ['testuser'],
            'key_id': 'custom-key-identifier',
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        data = assert_success(r, status=201)
        assert data['key_id'] == 'custom-key-identifier'

    def test_sign_certificate_missing_ca_id(self, auth_client):
        pub_key = _generate_test_ssh_key()
        payload = {'public_key': pub_key, 'cert_type': 'user', 'principals': ['u']}
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        assert_error(r, 400)

    def test_sign_certificate_missing_public_key(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='No PubKey CA')
        payload = {'ca_id': ca['id'], 'cert_type': 'user', 'principals': ['u']}
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        assert_error(r, 400)

    def test_sign_certificate_missing_principals(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='No Principals CA')
        pub_key = _generate_test_ssh_key()
        payload = {'ca_id': ca['id'], 'public_key': pub_key, 'cert_type': 'user'}
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        assert_error(r, 400)

    def test_sign_certificate_empty_principals(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Empty Principals CA')
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': ca['id'],
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': [],
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        assert_error(r, 400)

    def test_sign_certificate_nonexistent_ca(self, auth_client):
        pub_key = _generate_test_ssh_key()
        payload = {
            'ca_id': 999999,
            'public_key': pub_key,
            'cert_type': 'user',
            'principals': ['testuser'],
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        assert r.status_code in (400, 404, 500)

    def test_sign_certificate_invalid_public_key(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Bad Key CA')
        payload = {
            'ca_id': ca['id'],
            'public_key': 'not-a-valid-ssh-key',
            'cert_type': 'user',
            'principals': ['testuser'],
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
        assert r.status_code in (400, 500)

    def test_sign_increments_serial(self, auth_client):
        """Each certificate from the same CA should have an incrementing serial."""
        ca = _create_ssh_ca(auth_client, descr='Serial CA')
        serials = []
        for i in range(3):
            pub_key = _generate_test_ssh_key()
            payload = {
                'ca_id': ca['id'],
                'public_key': pub_key,
                'cert_type': 'user',
                'principals': [f'user{i}'],
            }
            r = post_json(auth_client, '/api/v2/ssh/certificates', payload)
            data = assert_success(r, status=201)
            serials.append(data['serial'])
        assert serials == sorted(serials)
        assert len(set(serials)) == 3


# ============================================================
# Generate SSH Certificate (POST /api/v2/ssh/certificates/generate)
# ============================================================

class TestGenerateSSHCertificate:
    """POST /api/v2/ssh/certificates/generate"""

    def test_generate_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Generate CA')
        payload = {
            'ca_id': ca['id'],
            'cert_type': 'user',
            'principals': ['genuser'],
            'key_type': 'ed25519',
        }
        r = post_json(auth_client, '/api/v2/ssh/certificates/generate', payload)
        data = assert_success(r, status=201)
        assert data['cert_type'] == 'user'
        assert 'genuser' in data['principals']
        assert 'private_key' in data
        assert 'BEGIN OPENSSH PRIVATE KEY' in data['private_key']
        assert data['certificate'] is not None

    def test_generate_missing_ca_id(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/certificates/generate', {
            'cert_type': 'user', 'principals': ['u'],
        })
        assert_error(r, 400)

    def test_generate_missing_principals(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Gen NoPrin CA')
        r = post_json(auth_client, '/api/v2/ssh/certificates/generate', {
            'ca_id': ca['id'], 'cert_type': 'user',
        })
        assert_error(r, 400)


# ============================================================
# List SSH Certificates
# ============================================================

class TestListSSHCertificates:
    """GET /api/v2/ssh/certificates"""

    def test_list_certificates_returns_array(self, auth_client):
        r = auth_client.get('/api/v2/ssh/certificates')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_certificates_pagination_meta(self, auth_client):
        r = auth_client.get('/api/v2/ssh/certificates?page=1&per_page=5')
        body = get_json(r)
        assert r.status_code == 200
        assert 'meta' in body
        assert body['meta']['page'] == 1

    def test_list_certificates_filter_by_ca(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Filter By CA')
        pub_key = _generate_test_ssh_key()
        post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['filteruser'],
        })
        r = auth_client.get(f'/api/v2/ssh/certificates?ca_id={ca["id"]}')
        data = assert_success(r)
        assert len(data) >= 1
        for cert in data:
            assert cert['ssh_ca_id'] == ca['id']

    def test_list_certificates_filter_by_type(self, auth_client):
        r = auth_client.get('/api/v2/ssh/certificates?type=user')
        data = assert_success(r)
        for cert in data:
            assert cert['cert_type'] == 'user'

    def test_list_certificates_search(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Search Cert CA')
        pub_key = _generate_test_ssh_key()
        post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['searchableprincipal'],
            'key_id': 'unique-search-key-id',
        })
        r = auth_client.get('/api/v2/ssh/certificates?search=unique-search-key-id')
        data = assert_success(r)
        assert any('unique-search-key-id' in c['key_id'] for c in data)


# ============================================================
# Get SSH Certificate
# ============================================================

class TestGetSSHCertificate:
    """GET /api/v2/ssh/certificates/<id>"""

    def test_get_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Get Cert CA')
        pub_key = _generate_test_ssh_key()
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['getuser'],
        })
        cert = assert_success(r, status=201)

        r = auth_client.get(f'/api/v2/ssh/certificates/{cert["id"]}')
        data = assert_success(r)
        assert data['id'] == cert['id']
        assert data['cert_type'] == 'user'
        assert 'getuser' in data['principals']
        for field in ['id', 'refid', 'key_id', 'certificate', 'public_key',
                       'serial', 'valid_from', 'valid_to', 'fingerprint',
                       'status', 'extensions', 'ssh_ca_id']:
            assert field in data, f'Missing field: {field}'

    def test_get_certificate_not_found(self, auth_client):
        r = auth_client.get('/api/v2/ssh/certificates/999999')
        assert_error(r, 404)


# ============================================================
# Delete SSH Certificate
# ============================================================

class TestDeleteSSHCertificate:
    """DELETE /api/v2/ssh/certificates/<id>"""

    def test_delete_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Delete Cert CA')
        pub_key = _generate_test_ssh_key()
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['deluser'],
        })
        cert = assert_success(r, status=201)

        r = auth_client.delete(f'/api/v2/ssh/certificates/{cert["id"]}')
        assert r.status_code == 204

        # Verify gone
        r = auth_client.get(f'/api/v2/ssh/certificates/{cert["id"]}')
        assert_error(r, 404)

    def test_delete_certificate_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/ssh/certificates/999999')
        assert_error(r, 404)


# ============================================================
# Revoke SSH Certificate
# ============================================================

class TestRevokeSSHCertificate:
    """POST /api/v2/ssh/certificates/<id>/revoke"""

    def test_revoke_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Revoke Cert CA')
        pub_key = _generate_test_ssh_key()
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['revokeuser'],
        })
        cert = assert_success(r, status=201)

        r = post_json(auth_client, f'/api/v2/ssh/certificates/{cert["id"]}/revoke', {
            'reason': 'compromised',
        })
        data = assert_success(r)
        assert data['revoked'] is True
        assert data['revoke_reason'] == 'compromised'
        assert data['revoked_at'] is not None
        assert data['status'] == 'revoked'

    def test_revoke_already_revoked(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Double Revoke CA')
        pub_key = _generate_test_ssh_key()
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['revoketwice'],
        })
        cert = assert_success(r, status=201)

        post_json(auth_client, f'/api/v2/ssh/certificates/{cert["id"]}/revoke', {})
        r = post_json(auth_client, f'/api/v2/ssh/certificates/{cert["id"]}/revoke', {})
        assert_error(r, 400)

    def test_revoke_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/certificates/999999/revoke', {})
        assert r.status_code in (400, 404)


# ============================================================
# Export SSH Certificate
# ============================================================

class TestExportSSHCertificate:
    """GET /api/v2/ssh/certificates/<id>/export"""

    def test_export_certificate(self, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Export Cert CA')
        pub_key = _generate_test_ssh_key()
        r = post_json(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'public_key': pub_key,
            'cert_type': 'user', 'principals': ['exportuser'],
        })
        cert = assert_success(r, status=201)

        r = auth_client.get(f'/api/v2/ssh/certificates/{cert["id"]}/export')
        data = assert_success(r)
        assert 'certificate' in data
        assert 'public_key' in data
        assert 'ca_public_key' in data

    def test_export_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/ssh/certificates/999999/export')
        assert_error(r, 404)


# ============================================================
# SSH Stats
# ============================================================

class TestSSHStats:
    """GET /api/v2/ssh/stats"""

    def test_stats_returns_structure(self, auth_client):
        r = auth_client.get('/api/v2/ssh/stats')
        data = assert_success(r)
        assert 'cas' in data
        assert 'certificates' in data
        assert 'total' in data['cas']
        assert 'user' in data['cas']
        assert 'host' in data['cas']
        assert 'total' in data['certificates']
        assert 'valid' in data['certificates']
        assert 'revoked' in data['certificates']
        assert 'expired' in data['certificates']

    def test_stats_counts_match(self, auth_client):
        """Stats should reflect CAs and certs we've created."""
        r = auth_client.get('/api/v2/ssh/stats')
        data = assert_success(r)
        # Counts should be non-negative integers
        assert data['cas']['total'] >= 0
        assert data['certificates']['total'] >= 0
        assert data['cas']['total'] == data['cas']['user'] + data['cas']['host']


# ============================================================
# Viewer Permissions (RBAC)
# ============================================================

class TestSSHViewerPermissions:
    """Viewer role can read SSH but not write/delete."""

    def test_viewer_can_list_ssh_cas(self, viewer_client):
        r = viewer_client.get('/api/v2/ssh/cas')
        assert r.status_code == 200

    def test_viewer_cannot_create_ssh_ca(self, viewer_client):
        r = post_json(viewer_client, '/api/v2/ssh/cas', VALID_USER_CA)
        assert r.status_code in (401, 403)

    def test_viewer_cannot_delete_ssh_ca(self, viewer_client):
        r = viewer_client.delete('/api/v2/ssh/cas/1')
        assert r.status_code in (401, 403, 404)

    def test_viewer_can_list_ssh_certificates(self, viewer_client):
        r = viewer_client.get('/api/v2/ssh/certificates')
        assert r.status_code == 200

    def test_viewer_cannot_sign_ssh_certificate(self, viewer_client):
        r = post_json(viewer_client, '/api/v2/ssh/certificates', {
            'ca_id': 1, 'public_key': 'x', 'cert_type': 'user', 'principals': ['u'],
        })
        assert r.status_code in (401, 403)

    def test_viewer_cannot_delete_ssh_certificate(self, viewer_client):
        r = viewer_client.delete('/api/v2/ssh/certificates/1')
        assert r.status_code in (401, 403, 404)

    def test_viewer_cannot_revoke_ssh_certificate(self, viewer_client):
        r = post_json(viewer_client, '/api/v2/ssh/certificates/1/revoke', {})
        assert r.status_code in (401, 403)

    def test_viewer_can_get_ssh_stats(self, viewer_client):
        r = viewer_client.get('/api/v2/ssh/stats')
        assert r.status_code == 200
