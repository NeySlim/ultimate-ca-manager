"""
CA (Certificate Authority) API Tests — /api/v2/cas/*

Comprehensive tests for all CA management endpoints:
- List CAs (GET)
- Create CA — root & intermediate (POST)
- Import CA from PEM (POST)
- Get CA details (GET)
- Update CA metadata (PATCH)
- Delete CA (DELETE)
- Export all CAs / single CA (GET)
- List certificates under a CA (GET)
- Bulk delete / bulk export (POST)

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_cert.
"""
import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'

VALID_ROOT_CA = {
    'type': 'root',
    'commonName': 'Test Root CA',
    'organization': 'Test Org',
    'country': 'US',
    'state': 'CA',
    'locality': 'Test City',
    'keyAlgo': 'RSA',
    'keySize': 2048,
    'validityYears': 10,
    'hashAlgorithm': 'sha256',
}


def get_json(response):
    return json.loads(response.data)


def assert_success(response, status=200):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All CA endpoints must return 401 without authentication."""

    def test_list_cas_requires_auth(self, client):
        assert client.get('/api/v2/cas').status_code == 401

    def test_create_ca_requires_auth(self, client):
        r = post_json(client, '/api/v2/cas', VALID_ROOT_CA)
        assert r.status_code == 401

    def test_import_ca_requires_auth(self, client):
        r = client.post('/api/v2/cas/import', content_type='multipart/form-data')
        assert r.status_code == 401

    def test_get_ca_requires_auth(self, client):
        assert client.get('/api/v2/cas/1').status_code == 401

    def test_update_ca_requires_auth(self, client):
        r = patch_json(client, '/api/v2/cas/1', {'name': 'x'})
        assert r.status_code == 401

    def test_delete_ca_requires_auth(self, client):
        assert client.delete('/api/v2/cas/1').status_code == 401

    def test_export_all_requires_auth(self, client):
        assert client.get('/api/v2/cas/export').status_code == 401

    def test_export_single_requires_auth(self, client):
        assert client.get('/api/v2/cas/1/export').status_code == 401

    def test_ca_certificates_requires_auth(self, client):
        assert client.get('/api/v2/cas/1/certificates').status_code == 401

    def test_bulk_delete_requires_auth(self, client):
        r = post_json(client, '/api/v2/cas/bulk/delete', {'ids': [1]})
        assert r.status_code == 401

    def test_bulk_export_requires_auth(self, client):
        r = post_json(client, '/api/v2/cas/bulk/export', {'ids': [1]})
        assert r.status_code == 401


# ============================================================
# Create CA
# ============================================================

class TestCreateCA:
    """POST /api/v2/cas"""

    def test_create_root_ca(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas', VALID_ROOT_CA)
        data = assert_success(r, status=201)
        assert data['id'] is not None
        assert 'Test Root CA' in (data.get('common_name') or data.get('descr', ''))

    def test_create_root_ca_returns_certificate(self, auth_client):
        payload = {**VALID_ROOT_CA, 'commonName': 'CA With Cert Check'}
        r = post_json(auth_client, '/api/v2/cas', payload)
        data = assert_success(r, status=201)
        assert data.get('pem') and 'BEGIN CERTIFICATE' in data['pem']

    def test_create_ca_missing_common_name(self, auth_client):
        payload = {**VALID_ROOT_CA}
        del payload['commonName']
        r = post_json(auth_client, '/api/v2/cas', payload)
        assert_error(r, 400)

    def test_create_ca_empty_common_name(self, auth_client):
        payload = {**VALID_ROOT_CA, 'commonName': ''}
        r = post_json(auth_client, '/api/v2/cas', payload)
        assert_error(r, 400)

    def test_create_ca_empty_body(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas', {})
        assert_error(r, 400)

    def test_create_intermediate_ca(self, auth_client, create_ca):
        root = create_ca(cn='Intermediate Test Root')
        payload = {
            **VALID_ROOT_CA,
            'type': 'intermediate',
            'commonName': 'Test Intermediate CA',
            'parentCAId': root['id'],
        }
        r = post_json(auth_client, '/api/v2/cas', payload)
        data = assert_success(r, status=201)
        assert data['id'] is not None

    def test_create_intermediate_ca_invalid_parent(self, auth_client):
        payload = {
            **VALID_ROOT_CA,
            'type': 'intermediate',
            'commonName': 'Orphan Intermediate',
            'parentCAId': 999999,
        }
        r = post_json(auth_client, '/api/v2/cas', payload)
        assert_error(r, 400)

    def test_create_ca_with_ecdsa(self, auth_client):
        payload = {
            **VALID_ROOT_CA,
            'commonName': 'ECDSA Root CA',
            'keyAlgo': 'ECDSA',
            'keySize': 'prime256v1',
        }
        r = post_json(auth_client, '/api/v2/cas', payload)
        data = assert_success(r, status=201)
        assert data['id'] is not None


# ============================================================
# List CAs
# ============================================================

class TestListCAs:
    """GET /api/v2/cas"""

    def test_list_cas_returns_array(self, auth_client, create_ca):
        create_ca(cn='Listed CA')
        r = auth_client.get('/api/v2/cas')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_cas_contains_cert_count(self, auth_client, create_ca):
        create_ca(cn='Counted CA')
        r = auth_client.get('/api/v2/cas')
        data = assert_success(r)
        for ca in data:
            assert 'certs' in ca

    def test_list_cas_pagination(self, auth_client, create_ca):
        r = auth_client.get('/api/v2/cas?page=1&per_page=2')
        body = get_json(r)
        assert r.status_code == 200
        meta = body.get('meta', {})
        assert 'total' in meta
        assert 'page' in meta

    def test_list_cas_search_filter(self, auth_client, create_ca):
        create_ca(cn='UniqueSearchableName')
        r = auth_client.get('/api/v2/cas?search=UniqueSearchableName')
        data = assert_success(r)
        assert any('UniqueSearchableName' in (c.get('common_name') or c.get('descr', ''))
                    for c in data)

    def test_list_cas_page_beyond_results(self, auth_client):
        r = auth_client.get('/api/v2/cas?page=9999&per_page=20')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) == 0


# ============================================================
# Get CA
# ============================================================

class TestGetCA:
    """GET /api/v2/cas/<id>"""

    def test_get_ca_by_id(self, auth_client, create_ca):
        ca = create_ca(cn='GetMe CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}')
        data = assert_success(r)
        assert data['id'] == ca['id']

    def test_get_ca_includes_details(self, auth_client, create_ca):
        ca = create_ca(cn='Detailed CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}')
        data = assert_success(r)
        assert 'certs' in data

    def test_get_ca_not_found(self, auth_client):
        r = auth_client.get('/api/v2/cas/999999')
        assert_error(r, 404)


# ============================================================
# Update CA
# ============================================================

class TestUpdateCA:
    """PATCH /api/v2/cas/<id>"""

    def test_update_ca_name(self, auth_client, create_ca):
        ca = create_ca(cn='BeforeUpdate CA')
        r = patch_json(auth_client, f'/api/v2/cas/{ca["id"]}', {'name': 'AfterUpdate CA'})
        data = assert_success(r)
        assert data.get('descr') == 'AfterUpdate CA' or data.get('name') == 'AfterUpdate CA'

    def test_update_ca_ocsp_settings(self, auth_client, create_ca):
        ca = create_ca(cn='OCSP Update CA')
        r = patch_json(auth_client, f'/api/v2/cas/{ca["id"]}', {
            'ocsp_enabled': True,
            'ocsp_url': 'http://ocsp.test.local',
        })
        assert_success(r)

    def test_update_ca_cdp_settings(self, auth_client, create_ca):
        ca = create_ca(cn='CDP Update CA')
        r = patch_json(auth_client, f'/api/v2/cas/{ca["id"]}', {
            'cdp_enabled': True,
            'cdp_url': 'http://crl.test.local/crl.pem',
        })
        assert_success(r)

    def test_update_ca_active_status(self, auth_client, create_ca):
        ca = create_ca(cn='Active Toggle CA')
        r = patch_json(auth_client, f'/api/v2/cas/{ca["id"]}', {'is_active': False})
        assert_success(r)

    def test_update_ca_not_found(self, auth_client):
        r = patch_json(auth_client, '/api/v2/cas/999999', {'name': 'Ghost'})
        assert_error(r, 404)

    def test_update_ca_empty_body(self, auth_client, create_ca):
        ca = create_ca(cn='EmptyUpdate CA')
        r = patch_json(auth_client, f'/api/v2/cas/{ca["id"]}', {})
        assert_success(r)


# ============================================================
# Delete CA
# ============================================================

class TestDeleteCA:
    """DELETE /api/v2/cas/<id>"""

    def test_delete_ca(self, auth_client, create_ca):
        ca = create_ca(cn='DeleteMe CA')
        r = auth_client.delete(f'/api/v2/cas/{ca["id"]}')
        assert r.status_code in (200, 204)

    def test_delete_ca_is_gone(self, auth_client, create_ca):
        ca = create_ca(cn='GoneAfterDelete CA')
        auth_client.delete(f'/api/v2/cas/{ca["id"]}')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}')
        assert_error(r, 404)

    def test_delete_ca_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/cas/999999')
        assert_error(r, 404)


# ============================================================
# Export — All CAs
# ============================================================

class TestExportAllCAs:
    """GET /api/v2/cas/export"""

    def test_export_all_pem(self, auth_client, create_ca):
        create_ca(cn='ExportAll PEM CA')
        r = auth_client.get('/api/v2/cas/export?format=pem')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_all_default_format_is_pem(self, auth_client, create_ca):
        create_ca(cn='ExportAll Default CA')
        r = auth_client.get('/api/v2/cas/export')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_all_unsupported_format(self, auth_client, create_ca):
        create_ca(cn='ExportAll BadFormat CA')
        r = auth_client.get('/api/v2/cas/export?format=der')
        assert_error(r, 400)


# ============================================================
# Export — Single CA
# ============================================================

class TestExportSingleCA:
    """GET /api/v2/cas/<id>/export"""

    def test_export_pem(self, auth_client, create_ca):
        ca = create_ca(cn='ExportPEM CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/export?format=pem')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_der(self, auth_client, create_ca):
        ca = create_ca(cn='ExportDER CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/export?format=der')
        assert r.status_code == 200
        assert len(r.data) > 0

    def test_export_pkcs12_requires_password(self, auth_client, create_ca):
        ca = create_ca(cn='ExportPKCS12 NoPW CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/export?format=pkcs12')
        assert_error(r, 400)

    def test_export_pkcs12_with_password(self, auth_client, create_ca):
        ca = create_ca(cn='ExportPKCS12 CA')
        r = auth_client.get(
            f'/api/v2/cas/{ca["id"]}/export?format=pkcs12&password=testpass123'
        )
        assert r.status_code == 200
        assert len(r.data) > 0

    def test_export_not_found(self, auth_client):
        r = auth_client.get('/api/v2/cas/999999/export?format=pem')
        assert_error(r, 404)

    def test_export_unsupported_format(self, auth_client, create_ca):
        ca = create_ca(cn='ExportBadFmt CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/export?format=xml')
        assert_error(r, 400)

    def test_export_pem_with_chain(self, auth_client, create_ca):
        root = create_ca(cn='ChainExport Root')
        inter_payload = {
            **VALID_ROOT_CA,
            'type': 'intermediate',
            'commonName': 'ChainExport Intermediate',
            'parentCAId': root['id'],
        }
        r = post_json(auth_client, '/api/v2/cas', inter_payload)
        inter = assert_success(r, status=201)
        r = auth_client.get(
            f'/api/v2/cas/{inter["id"]}/export?format=pem&include_chain=true'
        )
        assert r.status_code == 200
        # Chain should contain at least 2 certificates
        cert_count = r.data.count(b'BEGIN CERTIFICATE')
        assert cert_count >= 2


# ============================================================
# CA Certificates
# ============================================================

class TestCACertificates:
    """GET /api/v2/cas/<id>/certificates"""

    def test_list_certificates_empty(self, auth_client, create_ca):
        ca = create_ca(cn='NoCerts CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/certificates')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_certificates_with_cert(self, auth_client, create_ca, create_cert):
        ca = create_ca(cn='WithCert CA')
        create_cert(cn='child.example.com', ca_id=ca['id'])
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/certificates')
        data = assert_success(r)
        assert len(data) >= 1

    def test_list_certificates_ca_not_found(self, auth_client):
        r = auth_client.get('/api/v2/cas/999999/certificates')
        assert_error(r, 404)

    def test_list_certificates_pagination(self, auth_client, create_ca):
        ca = create_ca(cn='PaginatedCerts CA')
        r = auth_client.get(f'/api/v2/cas/{ca["id"]}/certificates?page=1&per_page=5')
        body = get_json(r)
        assert r.status_code == 200
        meta = body.get('meta', {})
        assert 'total' in meta


# ============================================================
# Import CA
# ============================================================

class TestImportCA:
    """POST /api/v2/cas/import"""

    def test_import_no_file_or_pem(self, auth_client):
        r = auth_client.post('/api/v2/cas/import',
                             content_type='multipart/form-data',
                             data={})
        assert_error(r, 400)

    def test_import_invalid_pem(self, auth_client):
        r = auth_client.post('/api/v2/cas/import',
                             content_type='multipart/form-data',
                             data={'pem_content': 'not-a-valid-pem'})
        assert r.status_code in (400, 500)

    def test_import_valid_ca_pem(self, auth_client, create_ca):
        """Export a CA in PEM then re-import it."""
        ca = create_ca(cn='ImportRoundtrip CA')
        export_r = auth_client.get(f'/api/v2/cas/{ca["id"]}/export?format=pem')
        assert export_r.status_code == 200
        pem = export_r.data.decode('utf-8')
        r = auth_client.post('/api/v2/cas/import',
                             content_type='multipart/form-data',
                             data={'pem_content': pem, 'name': 'Re-Imported CA'})
        # Should succeed (201) or update existing (200)
        assert r.status_code in (200, 201)


# ============================================================
# Bulk Delete
# ============================================================

class TestBulkDelete:
    """POST /api/v2/cas/bulk/delete"""

    def test_bulk_delete(self, auth_client, create_ca):
        ca1 = create_ca(cn='BulkDel 1')
        ca2 = create_ca(cn='BulkDel 2')
        r = post_json(auth_client, '/api/v2/cas/bulk/delete',
                       {'ids': [ca1['id'], ca2['id']]})
        data = assert_success(r)
        assert len(data['success']) == 2

    def test_bulk_delete_missing_ids(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas/bulk/delete', {})
        assert_error(r, 400)

    def test_bulk_delete_empty_ids(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas/bulk/delete', {'ids': []})
        assert_error(r, 400)

    def test_bulk_delete_nonexistent(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas/bulk/delete',
                       {'ids': [999998, 999999]})
        data = assert_success(r)
        assert len(data['failed']) == 2

    def test_bulk_delete_mixed(self, auth_client, create_ca):
        ca = create_ca(cn='BulkDel Mixed')
        r = post_json(auth_client, '/api/v2/cas/bulk/delete',
                       {'ids': [ca['id'], 999999]})
        data = assert_success(r)
        assert len(data['success']) == 1
        assert len(data['failed']) == 1


# ============================================================
# Bulk Export
# ============================================================

class TestBulkExport:
    """POST /api/v2/cas/bulk/export"""

    def test_bulk_export_pem(self, auth_client, create_ca):
        ca1 = create_ca(cn='BulkExp 1')
        ca2 = create_ca(cn='BulkExp 2')
        r = post_json(auth_client, '/api/v2/cas/bulk/export',
                       {'ids': [ca1['id'], ca2['id']], 'format': 'pem'})
        assert r.status_code == 200
        cert_count = r.data.count(b'BEGIN CERTIFICATE')
        assert cert_count >= 2

    def test_bulk_export_missing_ids(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas/bulk/export', {})
        assert_error(r, 400)

    def test_bulk_export_nonexistent_ids(self, auth_client):
        r = post_json(auth_client, '/api/v2/cas/bulk/export',
                       {'ids': [999998, 999999], 'format': 'pem'})
        assert_error(r, 404)

    def test_bulk_export_unsupported_format(self, auth_client, create_ca):
        ca = create_ca(cn='BulkExp BadFmt')
        r = post_json(auth_client, '/api/v2/cas/bulk/export',
                       {'ids': [ca['id']], 'format': 'der'})
        assert_error(r, 400)

    def test_bulk_export_default_pem(self, auth_client, create_ca):
        ca = create_ca(cn='BulkExp Default')
        r = post_json(auth_client, '/api/v2/cas/bulk/export',
                       {'ids': [ca['id']]})
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data


# ============================================================
# Intermediate CA Chain
# ============================================================

class TestIntermediateChain:
    """Create root → intermediate → verify hierarchy."""

    def test_intermediate_linked_to_root(self, auth_client, create_ca):
        root = create_ca(cn='Hierarchy Root')
        payload = {
            **VALID_ROOT_CA,
            'type': 'intermediate',
            'commonName': 'Hierarchy Intermediate',
            'parentCAId': root['id'],
        }
        r = post_json(auth_client, '/api/v2/cas', payload)
        inter = assert_success(r, status=201)
        # Fetch intermediate and verify it references parent
        r2 = auth_client.get(f'/api/v2/cas/{inter["id"]}')
        inter_data = assert_success(r2)
        assert inter_data.get('caref') or inter_data.get('parent_id') or inter_data.get('issuer')

    def test_export_intermediate_with_full_chain(self, auth_client, create_ca):
        root = create_ca(cn='FullChain Root')
        payload = {
            **VALID_ROOT_CA,
            'type': 'intermediate',
            'commonName': 'FullChain Intermediate',
            'parentCAId': root['id'],
        }
        r = post_json(auth_client, '/api/v2/cas', payload)
        inter = assert_success(r, status=201)
        r2 = auth_client.get(
            f'/api/v2/cas/{inter["id"]}/export?format=pem&include_chain=true'
        )
        assert r2.status_code == 200
        assert r2.data.count(b'BEGIN CERTIFICATE') >= 2


# ============================================================
# Viewer Role — read-only access
# ============================================================

class TestViewerPermissions:
    """Viewer role can read but not write/delete CAs."""

    def test_viewer_can_list_cas(self, viewer_client):
        r = viewer_client.get('/api/v2/cas')
        assert r.status_code == 200

    def test_viewer_cannot_create_ca(self, viewer_client):
        r = post_json(viewer_client, '/api/v2/cas', VALID_ROOT_CA)
        assert r.status_code in (401, 403)

    def test_viewer_cannot_delete_ca(self, viewer_client):
        r = viewer_client.delete('/api/v2/cas/1')
        assert r.status_code in (401, 403)
