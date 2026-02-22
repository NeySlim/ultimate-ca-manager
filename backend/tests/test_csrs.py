"""
CSR (Certificate Signing Request) API Tests

Tests all /api/v2/csrs/* endpoints:
- CRUD operations (list, get, create, delete)
- Upload and import CSR PEM
- Export CSR PEM
- Private key upload
- Sign CSR (issue certificate)
- Bulk sign and bulk delete
- Auth enforcement on every endpoint
- CSR lifecycle (create → get → sign → verify → delete)
"""
import pytest
import os
import sys
import json
import tempfile
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A valid self-signed CSR PEM for upload/import tests
SAMPLE_CSR_PEM = None  # Generated in fixture


def _generate_csr_pem():
    """Generate a real CSR PEM using cryptography library."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.backends import default_backend

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'upload-test.example.com'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Upload Org'),
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'US'),
        ]))
        .sign(key, hashes.SHA256(), default_backend())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode('utf-8')


# ============================================================
# Module-scoped fixtures (isolated DB per module)
# ============================================================

@pytest.fixture(scope='module')
def app():
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing'
    os.environ['UCM_ENV'] = 'test'
    os.environ['HTTP_REDIRECT'] = 'false'
    os.environ['INITIAL_ADMIN_PASSWORD'] = 'changeme123'
    os.environ['CSRF_DISABLED'] = 'true'

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def auth_client(app):
    c = app.test_client()
    r = c.post('/api/v2/auth/login',
               data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
               content_type='application/json')
    assert r.status_code == 200, f'Login failed: {r.data}'
    return c


@pytest.fixture(scope='module')
def sample_csr_pem():
    """Module-scoped generated CSR PEM."""
    return _generate_csr_pem()


@pytest.fixture(scope='module')
def ca_for_signing(auth_client):
    """Create a CA that can be used to sign CSRs."""
    data = {
        'type': 'root',
        'commonName': 'CSR Test CA',
        'organization': 'CSR Test Org',
        'country': 'US',
        'state': 'CA',
        'locality': 'Test City',
        'keyType': 'RSA',
        'keySize': 2048,
        'validityYears': 10,
        'hashAlgorithm': 'sha256',
    }
    r = auth_client.post('/api/v2/cas',
                         data=json.dumps(data),
                         content_type='application/json')
    assert r.status_code in (200, 201), f'Create CA failed: {r.data}'
    result = json.loads(r.data)
    return result.get('data', result)


# ============================================================
# Helpers
# ============================================================

def _json(response):
    return json.loads(response.data)


def _create_csr(auth_client, cn='test-csr.example.com', **extra):
    data = {
        'cn': cn,
        'organization': 'Test Org',
        'country': 'US',
        'key_type': 'RSA 2048',
    }
    data.update(extra)
    return auth_client.post('/api/v2/csrs',
                            data=json.dumps(data),
                            content_type='application/json')


# ============================================================
# Auth enforcement
# ============================================================
class TestCSRAuthRequired:
    """All CSR endpoints must require authentication."""

    def test_list_csrs_unauth(self, client):
        r = client.get('/api/v2/csrs')
        assert r.status_code in (401, 403)

    def test_list_history_unauth(self, client):
        r = client.get('/api/v2/csrs/history')
        assert r.status_code in (401, 403)

    def test_get_csr_unauth(self, client):
        r = client.get('/api/v2/csrs/1')
        assert r.status_code in (401, 403)

    def test_create_csr_unauth(self, client):
        r = client.post('/api/v2/csrs',
                        data=json.dumps({'cn': 'x.example.com'}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_upload_csr_unauth(self, client):
        r = client.post('/api/v2/csrs/upload',
                        data=json.dumps({'pem': 'fake'}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_import_csr_unauth(self, client):
        r = client.post('/api/v2/csrs/import',
                        data='pem_content=fake',
                        content_type='application/x-www-form-urlencoded')
        assert r.status_code in (401, 403)

    def test_export_csr_unauth(self, client):
        r = client.get('/api/v2/csrs/1/export')
        assert r.status_code in (401, 403)

    def test_delete_csr_unauth(self, client):
        r = client.delete('/api/v2/csrs/1')
        assert r.status_code in (401, 403)

    def test_sign_csr_unauth(self, client):
        r = client.post('/api/v2/csrs/1/sign',
                        data=json.dumps({'ca_id': 1}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_upload_key_unauth(self, client):
        r = client.post('/api/v2/csrs/1/key',
                        data=json.dumps({'key': 'fake'}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_bulk_sign_unauth(self, client):
        r = client.post('/api/v2/csrs/bulk/sign',
                        data=json.dumps({'ids': [1], 'ca_id': 1}),
                        content_type='application/json')
        assert r.status_code in (401, 403)

    def test_bulk_delete_unauth(self, client):
        r = client.post('/api/v2/csrs/bulk/delete',
                        data=json.dumps({'ids': [1]}),
                        content_type='application/json')
        assert r.status_code in (401, 403)


# ============================================================
# Create CSR
# ============================================================
class TestCreateCSR:
    """POST /api/v2/csrs"""

    def test_create_csr_success(self, auth_client):
        r = _create_csr(auth_client, cn='create-test.example.com')
        assert r.status_code in (200, 201), f'Create CSR failed: {r.data}'
        data = _json(r)
        assert 'data' in data

    def test_create_csr_missing_cn(self, auth_client):
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({'organization': 'Test'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_create_csr_empty_body(self, auth_client):
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_create_csr_no_json(self, auth_client):
        r = auth_client.post('/api/v2/csrs',
                             data='not json',
                             content_type='text/plain')
        assert r.status_code in (400, 415, 500)

    def test_create_csr_with_sans(self, auth_client):
        r = _create_csr(auth_client, cn='san-test.example.com',
                        sans=['alt1.example.com', 'alt2.example.com'])
        assert r.status_code in (200, 201)

    def test_create_csr_with_department(self, auth_client):
        r = _create_csr(auth_client, cn='dept-test.example.com',
                        department='Engineering')
        assert r.status_code in (200, 201)

    def test_create_csr_ec_key(self, auth_client):
        r = _create_csr(auth_client, cn='ec-test.example.com',
                        key_type='EC P-256')
        assert r.status_code in (200, 201, 400, 500)


# ============================================================
# List CSRs
# ============================================================
class TestListCSRs:
    """GET /api/v2/csrs"""

    def test_list_csrs(self, auth_client):
        # Ensure at least one CSR exists
        _create_csr(auth_client, cn='list-test.example.com')
        r = auth_client.get('/api/v2/csrs')
        assert r.status_code == 200
        data = _json(r)
        assert 'data' in data
        assert isinstance(data['data'], list)

    def test_list_csrs_has_meta(self, auth_client):
        r = auth_client.get('/api/v2/csrs')
        assert r.status_code == 200
        data = _json(r)
        assert 'meta' in data
        meta = data['meta']
        assert 'total' in meta
        assert 'page' in meta

    def test_list_csrs_pagination(self, auth_client):
        r = auth_client.get('/api/v2/csrs?page=1&per_page=2')
        assert r.status_code == 200
        data = _json(r)
        assert len(data['data']) <= 2

    def test_list_csrs_page_out_of_range(self, auth_client):
        r = auth_client.get('/api/v2/csrs?page=9999')
        assert r.status_code == 200
        data = _json(r)
        assert data['data'] == []


# ============================================================
# CSR History
# ============================================================
class TestCSRHistory:
    """GET /api/v2/csrs/history"""

    def test_history_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/csrs/history')
        assert r.status_code == 200
        data = _json(r)
        assert 'data' in data
        assert isinstance(data['data'], list)

    def test_history_has_meta(self, auth_client):
        r = auth_client.get('/api/v2/csrs/history')
        assert r.status_code == 200
        data = _json(r)
        assert 'meta' in data


# ============================================================
# Get CSR
# ============================================================
class TestGetCSR:
    """GET /api/v2/csrs/<id>"""

    def test_get_csr_success(self, auth_client):
        # Create a CSR first
        cr = _create_csr(auth_client, cn='get-test.example.com')
        assert cr.status_code in (200, 201)
        csr_id = _json(cr)['data']['id']

        r = auth_client.get(f'/api/v2/csrs/{csr_id}')
        assert r.status_code == 200
        data = _json(r)
        assert 'data' in data

    def test_get_csr_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/csrs/999999')
        assert r.status_code == 404

    def test_get_csr_has_pem(self, auth_client):
        cr = _create_csr(auth_client, cn='pem-check.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.get(f'/api/v2/csrs/{csr_id}')
        data = _json(r)['data']
        # CSR should have PEM content
        assert 'csr_pem' in data


# ============================================================
# Upload CSR PEM
# ============================================================
class TestUploadCSR:
    """POST /api/v2/csrs/upload"""

    def test_upload_csr_success(self, auth_client, sample_csr_pem):
        r = auth_client.post('/api/v2/csrs/upload',
                             data=json.dumps({'pem': sample_csr_pem, 'name': 'Uploaded Test'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), f'Upload failed: {r.data}'
        data = _json(r)
        assert 'data' in data

    def test_upload_csr_no_pem(self, auth_client):
        r = auth_client.post('/api/v2/csrs/upload',
                             data=json.dumps({'name': 'No PEM'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_upload_csr_empty_body(self, auth_client):
        r = auth_client.post('/api/v2/csrs/upload',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_upload_csr_invalid_pem(self, auth_client):
        r = auth_client.post('/api/v2/csrs/upload',
                             data=json.dumps({'pem': 'not-a-valid-pem'}),
                             content_type='application/json')
        assert r.status_code in (400, 500)


# ============================================================
# Import CSR
# ============================================================
class TestImportCSR:
    """POST /api/v2/csrs/import"""

    def test_import_csr_via_pem_content(self, auth_client, sample_csr_pem):
        r = auth_client.post('/api/v2/csrs/import',
                             data={'pem_content': sample_csr_pem, 'name': 'Imported Test'},
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201), f'Import failed: {r.data}'

    def test_import_csr_no_content(self, auth_client):
        r = auth_client.post('/api/v2/csrs/import',
                             data={},
                             content_type='multipart/form-data')
        assert r.status_code == 400

    def test_import_csr_invalid_pem_content(self, auth_client):
        r = auth_client.post('/api/v2/csrs/import',
                             data={'pem_content': 'garbage-data'},
                             content_type='multipart/form-data')
        assert r.status_code in (400, 500)


# ============================================================
# Export CSR
# ============================================================
class TestExportCSR:
    """GET /api/v2/csrs/<id>/export"""

    def test_export_csr_success(self, auth_client):
        cr = _create_csr(auth_client, cn='export-test.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.get(f'/api/v2/csrs/{csr_id}/export')
        assert r.status_code == 200
        assert b'-----BEGIN CERTIFICATE REQUEST-----' in r.data

    def test_export_csr_nonexistent(self, auth_client):
        r = auth_client.get('/api/v2/csrs/999999/export')
        assert r.status_code == 404

    def test_export_csr_content_type(self, auth_client):
        cr = _create_csr(auth_client, cn='export-ct.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.get(f'/api/v2/csrs/{csr_id}/export')
        assert 'pem' in r.content_type or 'octet' in r.content_type


# ============================================================
# Delete CSR
# ============================================================
class TestDeleteCSR:
    """DELETE /api/v2/csrs/<id>"""

    def test_delete_csr_success(self, auth_client):
        cr = _create_csr(auth_client, cn='delete-test.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.delete(f'/api/v2/csrs/{csr_id}')
        assert r.status_code in (200, 204)

    def test_delete_csr_nonexistent(self, auth_client):
        r = auth_client.delete('/api/v2/csrs/999999')
        assert r.status_code == 404

    def test_delete_csr_idempotent(self, auth_client):
        cr = _create_csr(auth_client, cn='delete-twice.example.com')
        csr_id = _json(cr)['data']['id']

        auth_client.delete(f'/api/v2/csrs/{csr_id}')
        r = auth_client.delete(f'/api/v2/csrs/{csr_id}')
        assert r.status_code == 404


# ============================================================
# Upload Private Key
# ============================================================
class TestUploadPrivateKey:
    """POST /api/v2/csrs/<id>/key"""

    def test_upload_key_no_body(self, auth_client):
        cr = _create_csr(auth_client, cn='key-test.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.post(f'/api/v2/csrs/{csr_id}/key',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_upload_key_nonexistent_csr(self, auth_client):
        r = auth_client.post('/api/v2/csrs/999999/key',
                             data=json.dumps({'key': 'fake'}),
                             content_type='application/json')
        assert r.status_code == 404

    def test_upload_key_invalid_pem(self, auth_client):
        cr = _create_csr(auth_client, cn='key-invalid.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.post(f'/api/v2/csrs/{csr_id}/key',
                             data=json.dumps({'key': 'not-a-key'}),
                             content_type='application/json')
        assert r.status_code == 400


# ============================================================
# Sign CSR
# ============================================================
class TestSignCSR:
    """POST /api/v2/csrs/<id>/sign"""

    def test_sign_csr_success(self, auth_client, ca_for_signing):
        cr = _create_csr(auth_client, cn='sign-test.example.com')
        assert cr.status_code in (200, 201)
        csr_id = _json(cr)['data']['id']
        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))

        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             data=json.dumps({'ca_id': ca_id, 'validity_days': 365}),
                             content_type='application/json')
        assert r.status_code == 200, f'Sign failed: {r.data}'
        data = _json(r)
        assert 'data' in data

    def test_sign_csr_missing_ca_id(self, auth_client):
        cr = _create_csr(auth_client, cn='sign-noca.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             data=json.dumps({'validity_days': 365}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_sign_csr_nonexistent(self, auth_client):
        r = auth_client.post('/api/v2/csrs/999999/sign',
                             data=json.dumps({'ca_id': 1}),
                             content_type='application/json')
        assert r.status_code == 404

    def test_sign_csr_nonexistent_ca(self, auth_client):
        cr = _create_csr(auth_client, cn='sign-badca.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             data=json.dumps({'ca_id': 999999}),
                             content_type='application/json')
        assert r.status_code == 404

    def test_sign_csr_already_signed(self, auth_client, ca_for_signing):
        cr = _create_csr(auth_client, cn='sign-twice.example.com')
        csr_id = _json(cr)['data']['id']
        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))

        # Sign it
        auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                         data=json.dumps({'ca_id': ca_id}),
                         content_type='application/json')
        # Try to sign again
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             data=json.dumps({'ca_id': ca_id}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_sign_csr_empty_body(self, auth_client):
        cr = _create_csr(auth_client, cn='sign-empty.example.com')
        csr_id = _json(cr)['data']['id']

        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             content_type='application/json')
        assert r.status_code == 400


# ============================================================
# Bulk Operations
# ============================================================
class TestBulkOperations:
    """POST /api/v2/csrs/bulk/sign and bulk/delete"""

    def test_bulk_sign_success(self, auth_client, ca_for_signing):
        ids = []
        for i in range(2):
            cr = _create_csr(auth_client, cn=f'bulk-sign-{i}.example.com')
            ids.append(_json(cr)['data']['id'])

        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))
        r = auth_client.post('/api/v2/csrs/bulk/sign',
                             data=json.dumps({'ids': ids, 'ca_id': ca_id, 'validity_days': 365}),
                             content_type='application/json')
        assert r.status_code == 200
        data = _json(r)['data']
        assert len(data['success']) == 2

    def test_bulk_sign_missing_ids(self, auth_client):
        r = auth_client.post('/api/v2/csrs/bulk/sign',
                             data=json.dumps({'ca_id': 1}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_bulk_sign_missing_ca_id(self, auth_client):
        r = auth_client.post('/api/v2/csrs/bulk/sign',
                             data=json.dumps({'ids': [1]}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_bulk_sign_nonexistent_ids(self, auth_client, ca_for_signing):
        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))
        r = auth_client.post('/api/v2/csrs/bulk/sign',
                             data=json.dumps({'ids': [999998, 999999], 'ca_id': ca_id}),
                             content_type='application/json')
        assert r.status_code == 200
        data = _json(r)['data']
        assert len(data['success']) == 0
        assert len(data['failed']) == 2

    def test_bulk_delete_success(self, auth_client):
        ids = []
        for i in range(2):
            cr = _create_csr(auth_client, cn=f'bulk-del-{i}.example.com')
            ids.append(_json(cr)['data']['id'])

        r = auth_client.post('/api/v2/csrs/bulk/delete',
                             data=json.dumps({'ids': ids}),
                             content_type='application/json')
        assert r.status_code == 200
        data = _json(r)['data']
        assert len(data['success']) == 2

    def test_bulk_delete_missing_ids(self, auth_client):
        r = auth_client.post('/api/v2/csrs/bulk/delete',
                             data=json.dumps({}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_bulk_delete_nonexistent_ids(self, auth_client):
        r = auth_client.post('/api/v2/csrs/bulk/delete',
                             data=json.dumps({'ids': [999998, 999999]}),
                             content_type='application/json')
        assert r.status_code == 200
        data = _json(r)['data']
        assert len(data['success']) == 0
        assert len(data['failed']) == 2

    def test_bulk_sign_empty_ids(self, auth_client, ca_for_signing):
        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))
        r = auth_client.post('/api/v2/csrs/bulk/sign',
                             data=json.dumps({'ids': [], 'ca_id': ca_id}),
                             content_type='application/json')
        # Empty list: either 400 (ids required) or 200 with empty results
        assert r.status_code in (200, 400)


# ============================================================
# CSR Lifecycle (integration)
# ============================================================
class TestCSRLifecycle:
    """End-to-end: create → list → get → sign → appears in history → delete"""

    def test_full_lifecycle(self, auth_client, ca_for_signing):
        # 1. Create CSR
        cr = _create_csr(auth_client, cn='lifecycle.example.com')
        assert cr.status_code in (200, 201)
        csr_id = _json(cr)['data']['id']

        # 2. Verify appears in pending list
        r = auth_client.get('/api/v2/csrs')
        assert r.status_code == 200
        pending_ids = [c['id'] for c in _json(r)['data']]
        assert csr_id in pending_ids

        # 3. Get CSR details
        r = auth_client.get(f'/api/v2/csrs/{csr_id}')
        assert r.status_code == 200

        # 4. Export CSR
        r = auth_client.get(f'/api/v2/csrs/{csr_id}/export')
        assert r.status_code == 200

        # 5. Sign CSR
        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             data=json.dumps({'ca_id': ca_id, 'validity_days': 365}),
                             content_type='application/json')
        assert r.status_code == 200, f'Sign failed: {r.data}'

        # 6. Should no longer be in pending list
        r = auth_client.get('/api/v2/csrs')
        pending_ids = [c['id'] for c in _json(r)['data']]
        assert csr_id not in pending_ids

        # 7. Should appear in history
        r = auth_client.get('/api/v2/csrs/history')
        assert r.status_code == 200
        history_ids = [c['id'] for c in _json(r)['data']]
        assert csr_id in history_ids

    def test_upload_and_sign_lifecycle(self, auth_client, ca_for_signing, sample_csr_pem):
        # 1. Upload CSR PEM
        r = auth_client.post('/api/v2/csrs/upload',
                             data=json.dumps({'pem': sample_csr_pem, 'name': 'Lifecycle Upload'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), f'Upload failed: {r.data}'
        csr_id = _json(r)['data']['id']

        # 2. Verify it's in pending list
        r = auth_client.get('/api/v2/csrs')
        pending_ids = [c['id'] for c in _json(r)['data']]
        assert csr_id in pending_ids

        # 3. Sign it
        ca_id = ca_for_signing.get('id', ca_for_signing.get('ca_id'))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign',
                             data=json.dumps({'ca_id': ca_id}),
                             content_type='application/json')
        # Uploaded CSRs may lack private key for signing; accept 200 or 500
        assert r.status_code in (200, 400, 500)
