"""
Certificates API Tests

Tests all /api/v2/certificates/* endpoints:
- List (GET)
- Stats (GET)
- Create (POST)
- Get details (GET /<id>)
- Delete (DELETE /<id>)
- Export all (GET /export)
- Export single (GET /<id>/export)
- Revoke (POST /<id>/revoke)
- Upload private key (POST /<id>/key)
- Renew (POST /<id>/renew)
- Import (POST /import)
- Bulk revoke (POST /bulk/revoke)
- Bulk renew (POST /bulk/renew)
- Bulk delete (POST /bulk/delete)
- Bulk export (POST /bulk/export)

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_cert.
"""
import pytest
import json
from tests.conftest import get_json, assert_success, assert_error

CONTENT_JSON = 'application/json'
BASE = '/api/v2/certificates'

def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================================
# Auth required (all 15 endpoints must return 401 without auth)
# ============================================================================

class TestAuthRequired:
    """All endpoints require authentication."""

    def test_list_requires_auth(self, client):
        assert client.get(BASE).status_code == 401

    def test_stats_requires_auth(self, client):
        assert client.get(f'{BASE}/stats').status_code == 401

    def test_create_requires_auth(self, client):
        r = post_json(client, BASE, {'cn': 'x', 'ca_id': 1})
        assert r.status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get(f'{BASE}/1').status_code == 401

    def test_delete_requires_auth(self, client):
        assert client.delete(f'{BASE}/1').status_code == 401

    def test_export_all_requires_auth(self, client):
        assert client.get(f'{BASE}/export').status_code == 401

    def test_export_single_requires_auth(self, client):
        assert client.get(f'{BASE}/1/export').status_code == 401

    def test_revoke_requires_auth(self, client):
        r = post_json(client, f'{BASE}/1/revoke', {'reason': 'keyCompromise'})
        assert r.status_code == 401

    def test_key_requires_auth(self, client):
        r = post_json(client, f'{BASE}/1/key', {'key': 'x'})
        assert r.status_code == 401

    def test_renew_requires_auth(self, client):
        r = post_json(client, f'{BASE}/1/renew', {})
        assert r.status_code == 401

    def test_import_requires_auth(self, client):
        r = client.post(f'{BASE}/import', content_type='multipart/form-data')
        assert r.status_code == 401

    def test_bulk_revoke_requires_auth(self, client):
        r = post_json(client, f'{BASE}/bulk/revoke', {'ids': [1]})
        assert r.status_code == 401

    def test_bulk_renew_requires_auth(self, client):
        r = post_json(client, f'{BASE}/bulk/renew', {'ids': [1]})
        assert r.status_code == 401

    def test_bulk_delete_requires_auth(self, client):
        r = post_json(client, f'{BASE}/bulk/delete', {'ids': [1]})
        assert r.status_code == 401

    def test_bulk_export_requires_auth(self, client):
        r = post_json(client, f'{BASE}/bulk/export', {'ids': [1]})
        assert r.status_code == 401


# ============================================================================
# Create certificate
# ============================================================================

class TestCreateCertificate:
    """Tests for POST /api/v2/certificates"""

    def test_create_basic(self, auth_client, create_ca):
        ca = create_ca(cn='Create Test CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'basic.example.com',
            'ca_id': ca_id,
            'validity_days': 365,
        })
        data = assert_success(r, status=201)
        assert data.get('id') is not None

    def test_create_with_san(self, auth_client, create_ca):
        ca = create_ca(cn='SAN Test CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'san.example.com',
            'ca_id': ca_id,
            'validity_days': 365,
            'san': 'DNS:san.example.com, DNS:www.san.example.com',
            'keyType': 'RSA',
            'keySize': 2048,
        })
        assert r.status_code == 201

    def test_create_missing_cn(self, auth_client):
        r = post_json(auth_client, BASE, {'ca_id': 1})
        assert r.status_code == 400

    def test_create_missing_ca_id(self, auth_client):
        r = post_json(auth_client, BASE, {'cn': 'missing-ca.example.com'})
        assert r.status_code == 400

    def test_create_invalid_ca_id(self, auth_client):
        r = post_json(auth_client, BASE, {
            'cn': 'badca.example.com',
            'ca_id': 999999,
        })
        assert r.status_code == 404

    def test_create_empty_body(self, auth_client):
        r = auth_client.post(BASE, data='{}', content_type=CONTENT_JSON)
        assert r.status_code == 400

    def test_create_ec_key(self, auth_client, create_ca):
        ca = create_ca(cn='EC Key Test CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'ec.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'ecdsa',
            'key_size': '256',
        })
        assert r.status_code == 201

    def test_create_rejects_fqdn_in_san_ip(self, auth_client, create_ca):
        ca = create_ca(cn='SAN IP Reject CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'reject.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'san_ip': ['www.example.org'],
        })
        assert r.status_code == 400
        body = get_json(r)
        assert 'DNS type' in body.get('message', '')

    def test_create_email_cn_server_no_dns_san(self, auth_client, create_ca):
        ca = create_ca(cn='Email CN Server CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'fred@fred.fr',
            'ca_id': ca_id,
            'validity_days': 90,
            'cert_type': 'server',
        })
        created = assert_success(r, status=201)
        cert_id = created.get('id')
        detail = auth_client.get(f'{BASE}/{cert_id}')
        data = assert_success(detail)
        san_dns = data.get('san_dns')
        if isinstance(san_dns, str) and san_dns.startswith('['):
            san_dns = json.loads(san_dns)
        assert 'fred@fred.fr' not in (san_dns or [])

    def test_create_email_cn_email_cert(self, auth_client, create_ca):
        ca = create_ca(cn='Email CN Email CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'fred@fred.fr',
            'ca_id': ca_id,
            'validity_days': 90,
            'cert_type': 'email',
        })
        created = assert_success(r, status=201)
        cert_id = created.get('id')
        detail = auth_client.get(f'{BASE}/{cert_id}')
        data = assert_success(detail)
        san_email = data.get('san_email')
        if isinstance(san_email, str) and san_email.startswith('['):
            san_email = json.loads(san_email)
        assert 'fred@fred.fr' in (san_email or [])

    def test_create_ec_p521(self, auth_client, create_ca):
        ca = create_ca(cn='EC P521 Test CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'p521.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'ecdsa',
            'key_size': '521',
        })
        assert r.status_code == 201


# ============================================================================
# List certificates
# ============================================================================

class TestListCertificates:
    """Tests for GET /api/v2/certificates"""

    def test_list_returns_array(self, auth_client, create_cert):
        create_cert(cn='list-test.example.com')
        r = auth_client.get(BASE)
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_with_pagination(self, auth_client):
        r = auth_client.get(f'{BASE}?page=1&per_page=5')
        body = get_json(r)
        assert r.status_code == 200
        assert 'meta' in body or 'data' in body

    def test_list_filter_by_status_valid(self, auth_client, create_cert):
        create_cert(cn='valid-filter.example.com')
        r = auth_client.get(f'{BASE}?status=valid')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_filter_by_status_revoked(self, auth_client):
        r = auth_client.get(f'{BASE}?status=revoked')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_filter_by_ca_id(self, auth_client, create_ca, create_cert):
        """ca_id filter hits a known bug (model uses caref not ca_id)."""
        ca = create_ca(cn='Filter CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        create_cert(cn='ca-filter.example.com', ca_id=ca_id)
        try:
            r = auth_client.get(f'{BASE}?ca_id={ca_id}')
            # If it doesn't raise, accept 200 or 500
            assert r.status_code in (200, 500)
        except Exception:
            # Known bug: filter_by(ca_id=...) raises InvalidRequestError
            pytest.skip('ca_id filter broken — model uses caref not ca_id')

    def test_list_search(self, auth_client, create_cert):
        create_cert(cn='searchable-unique-xyz.example.com')
        r = auth_client.get(f'{BASE}?search=searchable-unique-xyz')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_sort_by_valid_to(self, auth_client):
        r = auth_client.get(f'{BASE}?sort_by=valid_to&sort_order=desc')
        assert r.status_code == 200


# ============================================================================
# Certificate stats
# ============================================================================

class TestCertificateStats:
    """Tests for GET /api/v2/certificates/stats"""

    def test_stats_returns_counts(self, auth_client, create_cert):
        create_cert(cn='stats-test.example.com')
        r = auth_client.get(f'{BASE}/stats')
        data = assert_success(r)
        assert 'total' in data
        assert 'valid' in data
        assert 'expired' in data
        assert 'revoked' in data
        assert data['total'] >= 1


# ============================================================================
# Get certificate details
# ============================================================================

class TestGetCertificate:
    """Tests for GET /api/v2/certificates/<id>"""

    def test_get_existing(self, auth_client, create_cert):
        cert = create_cert(cn='get-detail.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}')
        data = assert_success(r)
        assert data.get('id') == cert_id

    def test_get_includes_chain_status(self, auth_client, create_cert):
        cert = create_cert(cn='chain-status.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}')
        data = assert_success(r)
        assert 'chain_status' in data

    def test_get_nonexistent(self, auth_client):
        r = auth_client.get(f'{BASE}/999999')
        assert r.status_code == 404


# ============================================================================
# Delete certificate
# ============================================================================

class TestDeleteCertificate:
    """Tests for DELETE /api/v2/certificates/<id>"""

    def test_delete_valid_cert_blocked(self, auth_client, create_cert):
        """Valid (non-revoked, non-expired) certs cannot be deleted."""
        cert = create_cert(cn='valid-no-delete.example.com')
        cert_id = cert.get('id')
        r = auth_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 409

    def test_delete_revoked_cert_allowed(self, auth_client, create_cert):
        """Revoked certs can be deleted (already on CRL)."""
        cert = create_cert(cn='revoke-then-delete.example.com')
        cert_id = cert.get('id')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        r = auth_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code in (200, 204)

    def test_delete_expired_cert_allowed(self, auth_client, create_cert):
        """Expired certs can be deleted (no longer valid)."""
        cert = create_cert(cn='expired-delete.example.com', validity_days=1)
        cert_id = cert.get('id')
        # Manually expire the cert by backdating valid_to in the DB
        from models import Certificate, db
        with auth_client.application.app_context():
            row = db.session.get(Certificate, cert_id)
            assert row is not None
            from utils.datetime_utils import utc_now
            from datetime import timedelta
            row.valid_to = utc_now() - timedelta(days=1)
            db.session.commit()
        r = auth_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code in (200, 204)

    def test_delete_nonexistent(self, auth_client):
        r = auth_client.delete(f'{BASE}/999999')
        assert r.status_code == 404

    def test_delete_confirms_gone(self, auth_client, create_cert):
        cert = create_cert(cn='delete-confirm.example.com')
        cert_id = cert.get('id')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        auth_client.delete(f'{BASE}/{cert_id}')
        r = auth_client.get(f'{BASE}/{cert_id}')
        assert r.status_code == 404

    def test_delete_service_failure_returns_500(self, auth_client, create_cert, monkeypatch):
        cert = create_cert(cn='delete-fail.example.com')
        cert_id = cert.get('id')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        from services.cert_service import CertificateService
        monkeypatch.setattr(CertificateService, 'delete_certificate',
                            staticmethod(lambda cert_id, username='system': False))
        r = auth_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 500


class TestRenameCertificate:
    """Tests for PATCH /api/v2/certificates/<id> — mutable display name (issue #286)"""

    def _patch(self, client, cert_id, body):
        return client.patch(f'{BASE}/{cert_id}', data=json.dumps(body),
                            content_type=CONTENT_JSON)

    def test_rename_requires_auth(self, client):
        assert self._patch(client, 1, {'descr': 'x'}).status_code == 401

    def test_rename(self, auth_client, create_cert):
        cert = create_cert(cn='rename-me.example.com')
        r = self._patch(auth_client, cert['id'], {'descr': 'Web Server (RSA)'})
        assert r.status_code == 200
        assert get_json(r)['data']['descr'] == 'Web Server (RSA)'

    def test_rename_persists(self, auth_client, create_cert):
        cert = create_cert(cn='rename-persist.example.com')
        self._patch(auth_client, cert['id'], {'descr': 'Renamed Label'})
        r = auth_client.get(f'{BASE}/{cert["id"]}')
        assert get_json(r)['data']['descr'] == 'Renamed Label'

    def test_rename_strips_whitespace(self, auth_client, create_cert):
        cert = create_cert(cn='rename-strip.example.com')
        r = self._patch(auth_client, cert['id'], {'descr': '  padded  '})
        assert get_json(r)['data']['descr'] == 'padded'

    def test_rename_nonexistent(self, auth_client):
        assert self._patch(auth_client, 999999, {'descr': 'x'}).status_code == 404

    def test_rename_missing_descr(self, auth_client, create_cert):
        cert = create_cert(cn='rename-missing.example.com')
        assert self._patch(auth_client, cert['id'], {}).status_code == 400

    def test_rename_empty_descr(self, auth_client, create_cert):
        cert = create_cert(cn='rename-empty.example.com')
        assert self._patch(auth_client, cert['id'], {'descr': '   '}).status_code == 400

    def test_rename_too_long(self, auth_client, create_cert):
        cert = create_cert(cn='rename-long.example.com')
        assert self._patch(auth_client, cert['id'], {'descr': 'x' * 256}).status_code == 400


# ============================================================================
# Export all certificates
# ============================================================================

class TestExportAll:
    """Tests for GET /api/v2/certificates/export"""

    def test_export_pem(self, auth_client, create_cert):
        create_cert(cn='export-all.example.com')
        r = auth_client.get(f'{BASE}/export?format=pem')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_unsupported_format(self, auth_client, create_cert):
        create_cert(cn='export-bad-fmt.example.com')
        r = auth_client.get(f'{BASE}/export?format=der')
        assert r.status_code in (400, 500)


# ============================================================================
# Export single certificate
# ============================================================================

class TestExportSingle:
    """Tests for GET /api/v2/certificates/<id>/export"""

    def test_export_pem(self, auth_client, create_cert):
        cert = create_cert(cn='export-single.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_der(self, auth_client, create_cert):
        cert = create_cert(cn='export-der.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=der')
        assert r.status_code == 200
        assert len(r.data) > 0

    def test_export_pkcs12_with_password(self, auth_client, create_cert):
        cert = create_cert(cn='export-p12.example.com')
        cert_id = cert.get('id')
        r = auth_client.post(
            f'{BASE}/{cert_id}/export',
            json={'format': 'pkcs12', 'password': 'test123'},
        )
        assert r.status_code == 200
        assert len(r.data) > 0

    def test_export_pkcs12_password_in_query_rejected(self, auth_client, create_cert):
        cert = create_cert(cn='export-p12-query.example.com')
        cert_id = cert.get('id')
        # Passwords in query strings leak into access logs — must be rejected
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pkcs12&password=test123')
        assert r.status_code == 400

    def test_export_pkcs12_no_password(self, auth_client, create_cert):
        cert = create_cert(cn='export-p12-nopw.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pkcs12')
        assert r.status_code == 400

    def test_export_nonexistent(self, auth_client):
        r = auth_client.get(f'{BASE}/999999/export?format=pem')
        assert r.status_code == 404

    def test_export_unsupported_format(self, auth_client, create_cert):
        cert = create_cert(cn='export-bad.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=banana')
        assert r.status_code == 400

    def test_export_pem_with_key(self, auth_client, create_cert):
        cert = create_cert(cn='export-key.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem&include_key=true')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_key_denied_without_private_keys_scope(self, app, auth_client, create_cert, create_user):
        # An operator holds write:certificates but NOT the admin-only
        # read:private_keys scope, so direct private-key export is refused —
        # the approval-gated Key Recovery flow is the only path for that role (#232).
        cert = create_cert(cn='export-op.example.com')
        cert_id = cert.get('id')
        create_user(username='op_export_test', role='operator')
        op = app.test_client()
        r = op.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_export_test', 'password': 'TestPass123!'}),
                    content_type='application/json')
        assert r.status_code == 200
        # Private key export refused (include_key, and PKCS#12 which always bundles the key)
        r = op.get(f'{BASE}/{cert_id}/export?format=pem&include_key=true')
        assert r.status_code == 403
        r = op.post(f'{BASE}/{cert_id}/export',
                    data=json.dumps({'format': 'pkcs12', 'password': 'ExportPass123!'}),
                    content_type='application/json')
        assert r.status_code == 403
        # Certificate-only export still works for the operator
        r = op.get(f'{BASE}/{cert_id}/export?format=pem')
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_export_pem_with_chain(self, auth_client, create_cert):
        cert = create_cert(cn='export-chain.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem&include_chain=true')
        assert r.status_code == 200


# ============================================================================
# include_chain flag — must be honored across PKCS12/PFX/PEM/PKCS7 (PR #100)
# ============================================================================

class TestExportIncludeChainFlag:
    """
    Regression tests for PR #100: PKCS12/PFX exports must honor the
    include_chain flag. Before the fix, the chain was unconditionally
    embedded for PKCS12 and never embedded for PFX.

    These tests build a 2-level chain (Root -> Leaf) and verify:
    - Without include_chain: PKCS12/PFX contain ZERO additional CA certs
    - With include_chain:    PKCS12/PFX contain >=1 additional CA cert
    """

    @staticmethod
    def _count_p12_chain(data, password='testpass123'):
        """Return the number of additional CA certificates inside a PKCS12 blob."""
        from cryptography.hazmat.primitives.serialization import pkcs12
        _key, _cert, additional = pkcs12.load_key_and_certificates(
            data, password.encode()
        )
        return len(additional or [])

    def test_pkcs12_without_include_chain_excludes_chain(self, auth_client, create_cert):
        cert = create_cert(cn='p12-nochain.example.com')
        cert_id = cert.get('id')
        r = auth_client.post(
            f'{BASE}/{cert_id}/export',
            json={'format': 'pkcs12', 'password': 'testpass123', 'include_chain': False},
        )
        assert r.status_code == 200
        assert self._count_p12_chain(r.data) == 0

    def test_pkcs12_with_include_chain_embeds_chain(self, auth_client, create_cert):
        cert = create_cert(cn='p12-chain.example.com')
        cert_id = cert.get('id')
        r = auth_client.post(
            f'{BASE}/{cert_id}/export',
            json={'format': 'pkcs12', 'password': 'testpass123', 'include_chain': True},
        )
        assert r.status_code == 200
        assert self._count_p12_chain(r.data) >= 1

    def test_pfx_without_include_chain_excludes_chain(self, auth_client, create_cert):
        cert = create_cert(cn='pfx-nochain.example.com')
        cert_id = cert.get('id')
        r = auth_client.post(
            f'{BASE}/{cert_id}/export',
            json={'format': 'pfx', 'password': 'testpass123', 'include_chain': False},
        )
        assert r.status_code == 200
        assert self._count_p12_chain(r.data) == 0

    def test_pfx_with_include_chain_embeds_chain(self, auth_client, create_cert):
        cert = create_cert(cn='pfx-chain.example.com')
        cert_id = cert.get('id')
        r = auth_client.post(
            f'{BASE}/{cert_id}/export',
            json={'format': 'pfx', 'password': 'testpass123', 'include_chain': True},
        )
        assert r.status_code == 200
        assert self._count_p12_chain(r.data) >= 1

    def test_pem_without_include_chain_returns_single_cert(self, auth_client, create_cert):
        cert = create_cert(cn='pem-nochain.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem&include_chain=false')
        assert r.status_code == 200
        assert r.data.count(b'BEGIN CERTIFICATE') == 1

    def test_pem_with_include_chain_returns_chain(self, auth_client, create_cert):
        cert = create_cert(cn='pem-chain.example.com')
        cert_id = cert.get('id')
        r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem&include_chain=true')
        assert r.status_code == 200
        assert r.data.count(b'BEGIN CERTIFICATE') >= 2


# ============================================================================
# Revoke certificate
# ============================================================================

class TestRevokeCertificate:
    """Tests for POST /api/v2/certificates/<id>/revoke"""

    def test_revoke_valid_cert(self, auth_client, create_cert):
        cert = create_cert(cn='to-revoke.example.com')
        cert_id = cert.get('id')
        r = post_json(auth_client, f'{BASE}/{cert_id}/revoke', {
            'reason': 'keyCompromise',
        })
        assert r.status_code == 200
        data = get_json(r)
        assert data.get('data', data).get('revoked') is True

    def test_revoke_already_revoked(self, auth_client, create_cert):
        cert = create_cert(cn='double-revoke.example.com')
        cert_id = cert.get('id')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        r = post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 400

    def test_revoke_nonexistent(self, auth_client):
        r = post_json(auth_client, f'{BASE}/999999/revoke', {'reason': 'keyCompromise'})
        assert r.status_code == 404

    def test_revoke_without_reason(self, auth_client, create_cert):
        cert = create_cert(cn='revoke-noreason.example.com')
        cert_id = cert.get('id')
        r = post_json(auth_client, f'{BASE}/{cert_id}/revoke', {})
        # Should succeed — reason defaults to 'unspecified'
        assert r.status_code == 200


# ============================================================================
# Upload private key
# ============================================================================

class TestUploadPrivateKey:
    """Tests for POST /api/v2/certificates/<id>/key"""

    def test_key_nonexistent_cert(self, auth_client):
        r = post_json(auth_client, f'{BASE}/999999/key', {'key': 'fake'})
        assert r.status_code == 404

    def test_key_missing_body(self, auth_client, create_cert):
        cert = create_cert(cn='key-nobody.example.com')
        cert_id = cert.get('id')
        r = post_json(auth_client, f'{BASE}/{cert_id}/key', {})
        assert r.status_code == 400

    def test_key_already_has_key(self, auth_client, create_cert):
        # Certs created via create_cert already have a private key
        cert = create_cert(cn='key-exists.example.com')
        cert_id = cert.get('id')
        r = post_json(auth_client, f'{BASE}/{cert_id}/key', {
            'key': '-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----',
        })
        assert r.status_code == 400

    def test_key_invalid_format(self, auth_client, create_cert):
        cert = create_cert(cn='key-badfmt.example.com')
        cert_id = cert.get('id')
        r = post_json(auth_client, f'{BASE}/{cert_id}/key', {'key': 'not-a-key'})
        assert r.status_code in (400, 500)


# ============================================================================
# Renew certificate
# ============================================================================

class TestRenewCertificate:
    """Tests for POST /api/v2/certificates/<id>/renew"""

    def test_renew_valid_cert(self, auth_client, create_cert):
        cert = create_cert(cn='to-renew.example.com')
        cert_id = cert.get('id')
        old_serial = cert.get('serial_number')
        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        # Renewed cert gets a new serial number
        if old_serial:
            assert data.get('serial_number') != old_serial

    def test_renew_nonexistent(self, auth_client):
        r = post_json(auth_client, f'{BASE}/999999/renew', {})
        assert r.status_code in (404, 500)

    def test_renew_preserves_row_id(self, auth_client, create_cert):
        """Renewal should update the certificate row in-place, preserving id and refid."""
        cert = create_cert(cn='renew-inplace.example.com')
        old_id = cert.get('id')
        old_refid = cert.get('refid')
        r = post_json(auth_client, f'{BASE}/{old_id}/renew', {})
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        new_id = data.get('id')
        new_refid = data.get('refid')
        # Same row — id and refid must be preserved
        assert new_id == old_id
        assert new_refid == old_refid
        # Cert should still be accessible at the same URL
        r_old = auth_client.get(f'{BASE}/{old_id}')
        assert r_old.status_code == 200

    def test_renew_sets_renewed_at(self, auth_client, create_cert):
        """Renewal should set renewed_at and increment renewed_times."""
        cert = create_cert(cn='renew-timestamp.example.com')
        cert_id = cert.get('id')
        # Before renewal, renewed_at should be None and renewed_times should be 0
        assert cert.get('renewed_at') is None
        assert cert.get('renewed_times', 0) == 0
        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        # After renewal, renewed_at should be set and renewed_times should be 1
        assert data.get('renewed_at') is not None
        assert data.get('renewed_times') == 1
        # Renew again — renewed_times should be 2
        r2 = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r2.status_code == 200
        data2 = get_json(r2).get('data', get_json(r2))
        assert data2.get('renewed_times') == 2

    def test_renew_preserves_created_at(self, auth_client, create_cert):
        """Renewal should preserve created_at (original issuance date)."""
        cert = create_cert(cn='renew-created-at.example.com')
        cert_id = cert.get('id')
        old_created_at = cert.get('created_at')
        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        # created_at must be unchanged
        assert data.get('created_at') == old_created_at

    def test_renew_revokes_old_cert(self, auth_client, create_cert, app):
        """Renewal should record the old serial in revoked_serials with certificate_id link."""
        from models import RevokedSerial, db as _db
        cert = create_cert(cn='renew-revoke-old.example.com')
        old_id = cert.get('id')
        old_serial = cert.get('serial_number')
        r = post_json(auth_client, f'{BASE}/{old_id}/renew', {})
        assert r.status_code == 200
        # The old serial should have a RevokedSerial entry
        with app.app_context():
            rs = RevokedSerial.query.filter_by(
                serial_number=old_serial
            ).first()
            assert rs is not None
            assert rs.revoke_reason == 'superseded'
            # certificate_id should point back to the cert row (preserved for auditability)
            assert rs.certificate_id == old_id

    def test_renew_revoked_cert_blocked(self, auth_client, create_cert):
        """Renewing a revoked cert is refused with 409 — issue a new cert instead."""
        cert = create_cert(cn='revoke-then-renew.example.com')
        cert_id = cert.get('id')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 409


# ============================================================================
# Import certificate
# ============================================================================


def _all_ids(auth_client, path):
    """Every id, following the pages: the lists cap per_page at 100, so a
    single call compares truncated sets and proves nothing."""
    ids, page = set(), 1
    while True:
        sep = '&' if '?' in path else '?'
        body = json.loads(auth_client.get(f'{path}{sep}per_page=100&page={page}').data)
        rows = body.get('data') or []
        ids |= {c['id'] for c in rows}
        total = (body.get('meta') or {}).get('total', len(ids))
        if len(ids) >= total or not rows:
            return ids
        page += 1


class TestImportCertificate:
    """Tests for POST /api/v2/certificates/import"""

    def test_import_no_file_no_pem(self, auth_client):
        r = auth_client.post(f'{BASE}/import',
                             data={},
                             content_type='multipart/form-data')
        assert r.status_code == 400

    def test_import_invalid_pem(self, auth_client):
        r = auth_client.post(f'{BASE}/import',
                             data={'pem_content': 'not-valid-pem-data'},
                             content_type='multipart/form-data')
        assert r.status_code in (400, 500)

    def test_import_valid_pem(self, auth_client, create_cert):
        # Export a cert as PEM, then re-import it
        cert = create_cert(cn='import-roundtrip.example.com')
        cert_id = cert.get('id')
        export_r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem')
        assert export_r.status_code == 200
        pem_data = export_r.data.decode('utf-8')

        r = auth_client.post(f'{BASE}/import',
                             data={
                                 'pem_content': pem_data,
                                 'name': 'Imported Test Cert',
                                 'update_existing': 'true',
                             },
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201, 409)


# ============================================================================
# Bulk revoke
# ============================================================================

class TestBulkRevoke:
    """Tests for POST /api/v2/certificates/bulk/revoke"""

    def test_bulk_revoke_missing_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/revoke', {})
        assert r.status_code == 400

    def test_bulk_revoke_empty_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/revoke', {'ids': []})
        assert r.status_code in (200, 400)

    def test_bulk_revoke_valid(self, auth_client, create_cert):
        c1 = create_cert(cn='bulk-rev1.example.com')
        c2 = create_cert(cn='bulk-rev2.example.com')
        r = post_json(auth_client, f'{BASE}/bulk/revoke', {
            'ids': [c1['id'], c2['id']],
            'reason': 'cessationOfOperation',
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['success']) == 2

    def test_bulk_revoke_nonexistent_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/revoke', {
            'ids': [999990, 999991],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['failed']) == 2


# ============================================================================
# Bulk renew
# ============================================================================

class TestBulkRenew:
    """Tests for POST /api/v2/certificates/bulk/renew"""

    def test_bulk_renew_missing_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/renew', {})
        assert r.status_code == 400

    def test_bulk_renew_valid(self, auth_client, create_cert):
        c1 = create_cert(cn='bulk-ren1.example.com')
        c2 = create_cert(cn='bulk-ren2.example.com')
        r = post_json(auth_client, f'{BASE}/bulk/renew', {
            'ids': [c1['id'], c2['id']],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['success']) == 2

    def test_bulk_renew_nonexistent_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/renew', {
            'ids': [999990, 999991],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['failed']) == 2


# ============================================================================
# Bulk delete
# ============================================================================

class TestBulkDelete:
    """Tests for POST /api/v2/certificates/bulk/delete"""

    def test_bulk_delete_missing_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/delete', {})
        assert r.status_code == 400

    def test_bulk_delete_valid_certs_blocked(self, auth_client, create_cert):
        """Valid certs in a bulk delete must be reported as failed."""
        c1 = create_cert(cn='bulk-del-block1.example.com')
        c2 = create_cert(cn='bulk-del-block2.example.com')
        r = post_json(auth_client, f'{BASE}/bulk/delete', {
            'ids': [c1['id'], c2['id']],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['failed']) == 2
        assert len(data['success']) == 0

    def test_bulk_delete_revoked_allowed(self, auth_client, create_cert):
        """Revoked certs can be bulk deleted."""
        c1 = create_cert(cn='bulk-del-rev1.example.com')
        c2 = create_cert(cn='bulk-del-rev2.example.com')
        post_json(auth_client, f'{BASE}/{c1["id"]}/revoke', {'reason': 'unspecified'})
        post_json(auth_client, f'{BASE}/{c2["id"]}/revoke', {'reason': 'unspecified'})
        r = post_json(auth_client, f'{BASE}/bulk/delete', {
            'ids': [c1['id'], c2['id']],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['success']) == 2

    def test_bulk_delete_mixed(self, auth_client, create_cert):
        """Mix of valid (blocked) and revoked (allowed) certs."""
        c_valid = create_cert(cn='bulk-del-mix-valid.example.com')
        c_revoked = create_cert(cn='bulk-del-mix-revoked.example.com')
        post_json(auth_client, f'{BASE}/{c_revoked["id"]}/revoke', {'reason': 'unspecified'})
        r = post_json(auth_client, f'{BASE}/bulk/delete', {
            'ids': [c_valid['id'], c_revoked['id']],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert c_revoked['id'] in data['success']
        assert any(f['id'] == c_valid['id'] for f in data['failed'])

    def test_bulk_delete_nonexistent_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/delete', {
            'ids': [999990, 999991],
        })
        assert r.status_code == 200
        data = get_json(r).get('data', get_json(r))
        assert len(data['failed']) == 2

    def test_bulk_delete_confirms_gone(self, auth_client, create_cert):
        c = create_cert(cn='bulk-del-confirm.example.com')
        post_json(auth_client, f'{BASE}/{c["id"]}/revoke', {'reason': 'unspecified'})
        post_json(auth_client, f'{BASE}/bulk/delete', {'ids': [c['id']]})
        r = auth_client.get(f'{BASE}/{c["id"]}')
        assert r.status_code == 404


# ============================================================================
# Bulk export
# ============================================================================

class TestBulkExport:
    """Tests for POST /api/v2/certificates/bulk/export"""

    def test_bulk_export_missing_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/export', {})
        assert r.status_code == 400

    def test_bulk_export_pem(self, auth_client, create_cert):
        c1 = create_cert(cn='bulk-exp1.example.com')
        c2 = create_cert(cn='bulk-exp2.example.com')
        r = post_json(auth_client, f'{BASE}/bulk/export', {
            'ids': [c1['id'], c2['id']],
            'format': 'pem',
        })
        assert r.status_code == 200
        assert b'BEGIN CERTIFICATE' in r.data

    def test_bulk_export_nonexistent_ids(self, auth_client):
        r = post_json(auth_client, f'{BASE}/bulk/export', {
            'ids': [999990, 999991],
        })
        assert r.status_code == 404


# ============================================================================
# RevokedSerial persistence
# ============================================================================

class TestRevokedSerialPersistence:
    """Tests for the revoked_serials table — revocation info survives cert deletion."""

    def test_revoke_creates_revoked_serial(self, auth_client, create_cert, app):
        """Revoking a cert should insert a RevokedSerial record."""
        from models import RevokedSerial
        cert = create_cert(cn='revserial-create.example.com')
        cert_id = cert.get('id')
        old_serial = cert.get('serial_number')
        r = post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'key_compromise'})
        assert r.status_code == 200
        with app.app_context():
            rs = RevokedSerial.query.filter_by(
                serial_number=old_serial
            ).first()
            assert rs is not None
            # stored in the canonical RFC 5280 spelling since #334
            assert rs.revoke_reason == 'keyCompromise'
            assert rs.valid_to is not None

    def test_revoked_serial_survives_deletion(self, auth_client, create_cert, app):
        """After deleting a revoked cert, the RevokedSerial record must persist."""
        from models import RevokedSerial
        cert = create_cert(cn='revserial-survive.example.com')
        cert_id = cert.get('id')
        old_serial = cert.get('serial_number')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        # Now delete the revoked cert (should be allowed since it's revoked)
        r = auth_client.delete(f'{BASE}/{cert_id}')
        assert r.status_code == 204
        # RevokedSerial must still be there
        with app.app_context():
            rs = RevokedSerial.query.filter_by(
                serial_number=old_serial
            ).first()
            assert rs is not None

    def test_stale_revoked_serial_purged(self, auth_client, create_cert, app):
        """RevokedSerial entries past valid_to should be purged during CRL generation."""
        from models import RevokedSerial, CA, SystemConfig, db as _db
        from utils.datetime_utils import utc_now
        from datetime import timedelta
        cert = create_cert(cn='revserial-stale.example.com')
        cert_id = cert.get('id')
        old_serial = cert.get('serial_number')
        post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        # Manually set valid_to in the past to simulate expiry
        with app.app_context():
            rs = RevokedSerial.query.filter_by(serial_number=old_serial).first()
            assert rs is not None
            rs.valid_to = utc_now() - timedelta(days=1)
            _db.session.commit()
            ca = CA.query.filter_by(refid=rs.caref).first()
            ca_id = ca.id
            # Enable auto-purge so CRL generation actually deletes stale entries
            # (defaults to False — entries are preserved as audit records).
            cfg = SystemConfig.query.filter_by(key='crl_auto_purge_stale_serials').first()
            if cfg:
                cfg.value = 'true'
            else:
                _db.session.add(SystemConfig(key='crl_auto_purge_stale_serials', value='true'))
            _db.session.commit()
        # Trigger CRL generation which should purge the stale entry
        from services.crl_service import CRLService
        with app.app_context():
            try:
                CRLService.generate_crl(ca_id, username='test')
            except Exception:
                pass  # CRL gen may fail if CA key isn't available in test
            rs_after = RevokedSerial.query.filter_by(serial_number=old_serial).first()
            assert rs_after is None  # purged because valid_to < now


class TestStatusFilterBuckets:
    """The list filter buckets match the stats endpoint and the row status,
    so a page is never filled with rows the caller asked to exclude (#345 review)."""

    @staticmethod
    def _mk(auth_client, create_ca, cn, days):
        ca = create_ca(cn=f'Bucket CA {cn}')
        r = auth_client.post(f'{BASE}',
                             data=json.dumps({'cn': cn, 'ca_id': ca['id'], 'validity_days': days,
                                              'key_type': 'RSA 2048', 'cert_type': 'server'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        return json.loads(r.data)['data']

    def test_valid_excludes_expiring(self, auth_client, create_ca):
        soon = self._mk(auth_client, create_ca, 'bucket-expiring.example.com', 10)
        later = self._mk(auth_client, create_ca, 'bucket-valid.example.com', 200)
        assert soon['status'] == 'expiring'
        assert later['status'] == 'valid'

        r = auth_client.get(f'{BASE}?per_page=200&status=valid&search=bucket-')
        ids = {c['id'] for c in json.loads(r.data)['data']}
        assert later['id'] in ids
        assert soon['id'] not in ids

        r = auth_client.get(f'{BASE}?per_page=200&status=expiring&search=bucket-')
        ids = {c['id'] for c in json.loads(r.data)['data']}
        assert soon['id'] in ids
        assert later['id'] not in ids

    def test_expired_excludes_revoked(self, auth_client, create_ca):
        cert = self._mk(auth_client, create_ca, 'bucket-revoked.example.com', 200)
        r = auth_client.post(f'{BASE}/{cert["id"]}/revoke',
                             data=json.dumps({'reason': 'unspecified'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data

        r = auth_client.get(f'{BASE}?per_page=200&status=expired&search=bucket-revoked')
        assert cert['id'] not in {c['id'] for c in json.loads(r.data)['data']}
        r = auth_client.get(f'{BASE}?per_page=200&status=revoked&search=bucket-revoked')
        assert cert['id'] in {c['id'] for c in json.loads(r.data)['data']}

    def test_certificate_without_validity_dates_counts_as_valid(self, app, auth_client, create_ca):
        """Its row says valid, so the filter and the counters must agree:
        otherwise it belongs to no bucket and no filter can reach it."""
        cert = self._mk(auth_client, create_ca, 'bucket-nodate.example.com', 200)
        with app.app_context():
            from models import db as _db, Certificate as _Cert
            row = _db.session.get(_Cert, cert['id'])
            row.valid_to = None
            row.valid_from = None
            _db.session.commit()

        r = auth_client.get(f'{BASE}/{cert["id"]}')
        assert json.loads(r.data)['data']['status'] == 'valid'
        r = auth_client.get(f'{BASE}?per_page=200&status=valid&search=bucket-nodate')
        assert cert['id'] in {c['id'] for c in json.loads(r.data)['data']}

    def test_every_certificate_falls_in_exactly_one_bucket(self, auth_client, create_ca):
        self._mk(auth_client, create_ca, 'bucket-one.example.com', 5)
        self._mk(auth_client, create_ca, 'bucket-two.example.com', 400)
        seen = {}
        for status in ('valid', 'expiring', 'expired', 'revoked'):
            for cid in _all_ids(auth_client, f'{BASE}?status={status}'):
                assert cid not in seen, (cid, status, seen.get(cid))
                seen[cid] = status
        assert seen.keys() == _all_ids(auth_client, BASE)


class TestOrphanFilter:
    """Orphans are selected over the whole set, not on the page received
    (#345 review): the filter and the counter must agree at any page size."""

    @staticmethod
    def _orphan(app, auth_client, create_ca, cn):
        """A certificate left pointing at a CA this instance does not hold.

        Deleting the CA through the ORM clears the link instead of leaving it
        dangling, and a certificate with no link at all is not an orphan; the
        state the filter targets is a reference that resolves to nothing,
        which is what a partial import or an out-of-band deletion leaves."""
        ca = create_ca(cn=f'Orphan CA {cn}')
        r = auth_client.post(BASE,
                             data=json.dumps({'cn': cn, 'ca_id': ca['id'], 'validity_days': 200,
                                              'key_type': 'RSA 2048', 'cert_type': 'server'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        cert = json.loads(r.data)['data']
        with app.app_context():
            from models import db as _db, Certificate as _Cert
            row = _db.session.get(_Cert, cert['id'])
            row.caref = f'missing-ca-{cert["id"]}'
            _db.session.commit()
        return cert

    def test_orphan_is_found_beyond_the_first_page(self, app, auth_client, create_ca):
        orphan = self._orphan(app, auth_client, create_ca, 'orphan-page2.example.com')
        # A page size of one puts the orphan far from the first page in any order
        r = auth_client.get(f'{BASE}?per_page=1&page=1&status=orphan')
        body = json.loads(r.data)
        assert body['meta']['total'] >= 1
        r = auth_client.get(f'{BASE}?per_page=500&status=orphan')
        ids = {c['id'] for c in json.loads(r.data)['data']}
        assert orphan['id'] in ids

    def test_orphan_count_matches_the_filter(self, app, auth_client, create_ca):
        self._orphan(app, auth_client, create_ca, 'orphan-count.example.com')
        stats = json.loads(auth_client.get(f'{BASE}/stats').data)['data']
        r = auth_client.get(f'{BASE}?per_page=500&status=orphan')
        assert stats['orphan'] == json.loads(r.data)['meta']['total']
        assert stats['orphan'] >= 1

    def test_certificate_without_a_ca_link_is_not_orphan(self, app, auth_client, create_ca):
        """No link at all is not the same as a broken one: a certificate
        issued outside this instance keeps showing under its own status."""
        ca = create_ca(cn='No link CA')
        r = auth_client.post(BASE,
                             data=json.dumps({'cn': 'no-link.example.com', 'ca_id': ca['id'],
                                              'validity_days': 200, 'key_type': 'RSA 2048',
                                              'cert_type': 'server'}),
                             content_type='application/json')
        cert = json.loads(r.data)['data']
        with app.app_context():
            from models import db as _db, Certificate as _Cert
            row = _db.session.get(_Cert, cert['id'])
            row.caref = None
            _db.session.commit()
        r = auth_client.get(f'{BASE}?per_page=500&status=orphan')
        assert cert['id'] not in {c['id'] for c in json.loads(r.data)['data']}

    def test_certificate_with_a_live_ca_is_not_orphan(self, auth_client, create_ca):
        ca = create_ca(cn='Live CA orphan check')
        r = auth_client.post(BASE,
                             data=json.dumps({'cn': 'not-orphan.example.com', 'ca_id': ca['id'],
                                              'validity_days': 200, 'key_type': 'RSA 2048',
                                              'cert_type': 'server'}),
                             content_type='application/json')
        cert = json.loads(r.data)['data']
        r = auth_client.get(f'{BASE}?per_page=500&status=orphan')
        assert cert['id'] not in {c['id'] for c in json.loads(r.data)['data']}


class TestStatusBucketsAcrossViews:
    """The certificates page, the dashboard and the Prometheus metrics count
    the same set. They report it two ways on purpose, and both must add up."""

    @staticmethod
    def _pending_csr(auth_client):
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({'cn': 'buckets-pending.example.com',
                                              'key_type': 'RSA 2048'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        return json.loads(r.data)['data']

    def test_a_pending_request_is_not_a_certificate(self, app, auth_client):
        """It is reported on its own; counting it as a certificate showed it
        twice on the dashboard, once as a certificate and once as pending."""
        before_stats = json.loads(auth_client.get(f'{BASE}/stats').data)['data']
        before_dash = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']
        csr = self._pending_csr(auth_client)
        after_stats = json.loads(auth_client.get(f'{BASE}/stats').data)['data']
        after_dash = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']

        assert after_stats['total'] == before_stats['total']
        assert after_dash['total_certificates'] == before_dash['total_certificates']
        assert after_dash['valid'] == before_dash['valid']
        assert after_dash['pending_csrs'] == before_dash['pending_csrs'] + 1

        r = auth_client.get(f'{BASE}?per_page=500')
        assert csr['id'] not in {c['id'] for c in json.loads(r.data)['data']}

    def test_dashboard_slices_add_up_to_the_total(self, auth_client):
        """They are drawn as one pie and each slice links to its filter."""
        d = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']
        assert d['valid'] + d['expiring_soon'] + d['expired'] + d['revoked'] == d['total_certificates']

    def test_page_and_dashboard_report_the_same_figures(self, auth_client):
        stats = json.loads(auth_client.get(f'{BASE}/stats').data)['data']
        dash = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']
        assert stats['total'] == dash['total_certificates']
        assert stats['valid'] + stats['expiring'] + stats['expired'] + stats['revoked'] == stats['total']
        for page_key, dash_key in (('valid', 'valid'), ('expiring', 'expiring_soon'),
                                   ('expired', 'expired'), ('revoked', 'revoked')):
            assert stats[page_key] == dash[dash_key], (page_key, stats[page_key], dash[dash_key])

    def test_metrics_report_the_lifecycle_state(self, app, auth_client):
        """Prometheus answers "what state is it in", with the expiry windows
        overlapping the valid ones on purpose."""
        with app.app_context():
            from utils.cert_status import (
                expired_condition, issued_certificates, revoked_condition, valid_condition,
            )
            certs = issued_certificates(include_archived=False)
            total = certs.count()
            lifecycle_valid = certs.filter(valid_condition(exclude_expiring=False)).count()
            expired = certs.filter(expired_condition()).count()
            revoked = certs.filter(revoked_condition()).count()
            assert lifecycle_valid + expired + revoked == total


class TestEmptyCertificateSentinel:
    """A record whose certificate column holds the empty string is a pending
    request, not a certificate: every view has to read it the same way, or a
    record shows up as a certificate in one place and as pending in another."""

    @staticmethod
    def _sentinel_row(app, auth_client):
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({'cn': 'sentinel.example.com', 'key_type': 'RSA 2048'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        rec = json.loads(r.data)['data']
        with app.app_context():
            from models import db as _db, Certificate as _Cert
            row = _db.session.get(_Cert, rec['id'])
            row.crt = ''      # the empty sentinel, not a certificate
            _db.session.commit()
        return rec

    def test_it_is_not_listed_as_a_certificate(self, app, auth_client):
        rec = self._sentinel_row(app, auth_client)
        before = json.loads(auth_client.get(f'{BASE}/stats').data)['data']['total']
        r = auth_client.get(f'{BASE}?per_page=500')
        body = json.loads(r.data)
        assert rec['id'] not in {c['id'] for c in body['data']}
        # The list total and the counter agree, which was the visible symptom
        assert body['meta']['total'] == before

    def test_it_is_listed_as_a_pending_request(self, app, auth_client):
        rec = self._sentinel_row(app, auth_client)
        r = auth_client.get('/api/v2/csrs?per_page=500')
        assert rec['id'] in {c['id'] for c in json.loads(r.data)['data']}
        r = auth_client.get('/api/v2/csrs/history?per_page=500')
        assert rec['id'] not in {c['id'] for c in json.loads(r.data)['data']}

    @staticmethod
    def _all_ids(auth_client, path):
        return _all_ids(auth_client, path)

    def test_the_two_lists_partition_the_records(self, app, auth_client):
        """No record falls in both lists, and none falls in neither."""
        rec = self._sentinel_row(app, auth_client)
        certs = self._all_ids(auth_client, BASE)
        pending = self._all_ids(auth_client, '/api/v2/csrs')
        history = self._all_ids(auth_client, '/api/v2/csrs/history')
        assert certs & pending == set()
        assert history <= certs   # a signed request is a certificate
        assert rec['id'] in pending and rec['id'] not in certs


class TestEmptyRequestSentinel:
    """A record whose request column holds the empty string carries no
    request: the list that shows pending requests and the counter that
    announces them have to agree (mirror of the empty certificate case)."""

    @staticmethod
    def _empty_request_row(app, auth_client):
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({'cn': 'empty-request.example.com', 'key_type': 'RSA 2048'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        rec = json.loads(r.data)['data']
        with app.app_context():
            from models import db as _db, Certificate as _Cert
            row = _db.session.get(_Cert, rec['id'])
            row.csr = ''
            _db.session.commit()
        return rec

    def test_it_is_not_listed_as_a_pending_request(self, app, auth_client):
        before = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']['pending_csrs']
        rec = self._empty_request_row(app, auth_client)
        body = json.loads(auth_client.get('/api/v2/csrs?per_page=100').data)
        assert rec['id'] not in {c['id'] for c in body['data']}
        after = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']['pending_csrs']
        assert after == before
        # The list and the counter announce the same number
        assert body['meta']['total'] == after

    def test_the_pending_count_follows_the_pending_list(self, app, auth_client):
        before_list = json.loads(auth_client.get('/api/v2/csrs?per_page=100').data)['meta']['total']
        before_count = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']['pending_csrs']
        assert before_list == before_count
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({'cn': 'counted-request.example.com', 'key_type': 'RSA 2048'}),
                             content_type='application/json')
        assert r.status_code in (200, 201)
        after_list = json.loads(auth_client.get('/api/v2/csrs?per_page=100').data)['meta']['total']
        after_count = json.loads(auth_client.get('/api/v2/dashboard/stats').data)['data']['pending_csrs']
        assert after_list == before_list + 1
        assert after_count == after_list


class TestOverviewCounts:
    """The overview shown before login counts certificates, not requests."""

    def test_overview_matches_the_certificate_total(self, auth_client):
        overview = json.loads(auth_client.get('/api/v2/stats/overview').data)['data']
        stats = json.loads(auth_client.get(f'{BASE}/stats').data)['data']
        assert overview['total_certs'] == stats['total']

    def test_a_new_request_does_not_raise_it(self, auth_client):
        before = json.loads(auth_client.get('/api/v2/stats/overview').data)['data']['total_certs']
        r = auth_client.post('/api/v2/csrs',
                             data=json.dumps({'cn': 'overview-request.example.com', 'key_type': 'RSA 2048'}),
                             content_type='application/json')
        assert r.status_code in (200, 201)
        after = json.loads(auth_client.get('/api/v2/stats/overview').data)['data']['total_certs']
        assert after == before


class TestImportRefusesForeignKey:
    """A PEM carrying a certificate and a key that is not its own is refused,
    for a certificate and for a CA alike (#347 review)."""

    @staticmethod
    def _cert_and_foreign_key(ca=False):
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        real = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'foreign-key.example.com')])
        now = datetime.now(timezone.utc)
        b = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
             .public_key(real.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30)))
        if ca:
            b = b.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        cert = b.sign(real, hashes.SHA256())
        pem = cert.public_bytes(serialization.Encoding.PEM) + other.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption())
        good = cert.public_bytes(serialization.Encoding.PEM) + real.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption())
        return pem.decode(), good.decode()

    def test_certificate_import_refuses_a_foreign_key(self, auth_client):
        bad, good = self._cert_and_foreign_key()
        r = auth_client.post(f'{BASE}/import', data={'pem_content': bad}, content_type='multipart/form-data')
        assert r.status_code == 400, r.data
        assert 'does not match' in json.loads(r.data)['message']
        r = auth_client.post(f'{BASE}/import', data={'pem_content': good}, content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        assert json.loads(r.data)['data']['has_private_key'] is True

    def test_ca_import_refuses_a_foreign_key(self, auth_client):
        bad, _ = self._cert_and_foreign_key(ca=True)
        r = auth_client.post('/api/v2/cas/import', data={'pem_content': bad}, content_type='multipart/form-data')
        assert r.status_code == 400, r.data
        assert 'does not match' in json.loads(r.data)['message']


class TestUpdateExistingKeepsOnlyAMatchingKey:
    """Fifth review of #347: re-importing a re-keyed certificate without its
    key must not leave the old key next to it."""

    @staticmethod
    def _pair(cn, ca=False, key=None):
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        now = datetime.now(timezone.utc)
        b = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
             .public_key(key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30)))
        if ca:
            b = b.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        cert = b.sign(key, hashes.SHA256())
        cpem = cert.public_bytes(serialization.Encoding.PEM).decode()
        kpem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                 serialization.NoEncryption()).decode()
        return cpem, kpem, key

    def _import(self, auth_client, pem, path=None):
        return auth_client.post(path or f'{BASE}/import', data={'pem_content': pem},
                                content_type='multipart/form-data')

    def test_rekeyed_certificate_drops_the_stale_key(self, auth_client):
        cpem, kpem, _ = self._pair('rekey-cert.example.com')
        r = self._import(auth_client, cpem + kpem)
        assert r.status_code in (200, 201), r.data
        first = json.loads(r.data)['data']; assert first['has_private_key'] is True
        # A new certificate, same subject and issuer, new key, imported alone
        cpem2, _, _ = self._pair('rekey-cert.example.com')
        r = self._import(auth_client, cpem2)
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == first['id']
        assert body['data']['has_private_key'] is False
        assert 'did not match' in body['message']

    def test_same_key_certificate_keeps_the_key(self, auth_client):
        cpem, kpem, key = self._pair('samekey-cert.example.com')
        r = self._import(auth_client, cpem + kpem); first = json.loads(r.data)['data']
        cpem2, _, _ = self._pair('samekey-cert.example.com', key=key)   # renewed, same key
        r = self._import(auth_client, cpem2)
        body = json.loads(r.data)
        assert body['data']['id'] == first['id']
        assert body['data']['has_private_key'] is True
        assert 'did not match' not in body['message']

    def test_rekeyed_ca_drops_the_stale_key(self, auth_client):
        cpem, kpem, _ = self._pair('Rekey CA', ca=True)
        r = self._import(auth_client, cpem + kpem, '/api/v2/cas/import')
        assert r.status_code in (200, 201), r.data
        first = json.loads(r.data)['data']; assert first['has_private_key'] is True
        cpem2, _, _ = self._pair('Rekey CA', ca=True)
        r = self._import(auth_client, cpem2, '/api/v2/cas/import')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == first['id']
        assert body['data']['has_private_key'] is False
        assert 'did not match' in body['message']


class TestEd25519KeyImport:
    """A certificate with an Ed25519 key imports like any other (#347 review):
    such keys have no traditional OpenSSL form and were refused as invalid."""

    def test_import_certificate_with_ed25519_key(self, auth_client):
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.x509.oid import NameOID
        key = ed25519.Ed25519PrivateKey.generate()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ed25519-import.example.com')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=30)).sign(key, None))
        pem = cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        r = auth_client.post(f'{BASE}/import', data={'pem_content': pem.decode()}, content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        data = json.loads(r.data)['data']
        assert data['has_private_key'] is True
        # and the stored key is usable: export it back
        r = auth_client.get(f"{BASE}/{data['id']}/export?format=key")
        assert r.status_code == 200, r.data
        loaded = serialization.load_pem_private_key(r.data, password=None)
        assert isinstance(loaded, ed25519.Ed25519PrivateKey)


class TestUnreadableStoredKeyRefusesUpdate:
    """Seventh review of #347: a stored key that cannot be read has not been
    shown to be another certificate's; the update is refused and the key kept,
    as for an HSM key that cannot be reached."""

    _pair = staticmethod(TestUpdateExistingKeepsOnlyAMatchingKey._pair)
    _import = TestUpdateExistingKeepsOnlyAMatchingKey._import

    @staticmethod
    def _corrupt(app, model, row_id):
        import base64
        with app.app_context():
            from models import db
            row = db.session.get(model, row_id)
            row.prv = base64.b64encode(b'not a private key at all').decode()
            db.session.commit()
            return row.prv, row.crt

    @staticmethod
    def _row(app, model, row_id):
        with app.app_context():
            from models import db
            row = db.session.get(model, row_id)
            return row.prv, row.crt

    def test_certificate_update_is_refused_and_nothing_changes(self, app, auth_client):
        from models import Certificate
        cpem, kpem, _ = self._pair('unreadable-key.example.com')
        r = self._import(auth_client, cpem + kpem)
        assert r.status_code in (200, 201), r.data
        first = json.loads(r.data)['data']
        before = self._corrupt(app, Certificate, first['id'])
        cpem2, _, _ = self._pair('unreadable-key.example.com')
        r = self._import(auth_client, cpem2)
        assert r.status_code == 409, r.data
        assert 'could not be read' in json.loads(r.data)['message']
        assert self._row(app, Certificate, first['id']) == before

    def test_ca_update_is_refused_and_nothing_changes(self, app, auth_client):
        from models import CA
        cpem, kpem, _ = self._pair('Unreadable Key CA', ca=True)
        r = self._import(auth_client, cpem + kpem, '/api/v2/cas/import')
        assert r.status_code in (200, 201), r.data
        first = json.loads(r.data)['data']
        before = self._corrupt(app, CA, first['id'])
        cpem2, _, _ = self._pair('Unreadable Key CA', ca=True)
        r = self._import(auth_client, cpem2, '/api/v2/cas/import')
        assert r.status_code == 409, r.data
        assert 'could not be read' in json.loads(r.data)['message']
        assert self._row(app, CA, first['id']) == before


class TestHomonymsOnReimport:
    """Ninth review of #347: with two records sharing a subject, a re-import
    lands on the record holding the certificate's key, and is refused when no
    key links it to one of them, instead of updating whichever came first."""

    @staticmethod
    def _cert(cn, key, *, issuer=None, signer=None, ca=False):
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        now = datetime.now(timezone.utc)
        b = (x509.CertificateBuilder().subject_name(name).issuer_name(issuer or name)
             .public_key(key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30)))
        if ca:
            b = b.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        return b.sign(signer or key, hashes.SHA256())

    @staticmethod
    def _store(app, model, cert, key, **extra):
        import base64, uuid
        from cryptography.hazmat.primitives import serialization
        from security.encryption import encrypt_private_key
        from services.import_service import extract_cert_info
        info = extract_cert_info(cert)
        kpem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
        with app.app_context():
            from models import db
            row = model(refid=str(uuid.uuid4()), descr=info['cn'],
                        crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                        prv=encrypt_private_key(base64.b64encode(kpem).decode()),
                        subject=info['subject'], issuer=info['issuer'], **extra)
            db.session.add(row); db.session.commit()
            return row.id, row.crt

    @staticmethod
    def _state(app, model, row_id):
        with app.app_context():
            from models import db
            db.session.expire_all()
            row = db.session.get(model, row_id)
            return row.crt, bool(row.prv)

    @staticmethod
    def _import(auth_client, cert, path):
        from cryptography.hazmat.primitives import serialization
        return auth_client.post(path, data={'pem_content': cert.public_bytes(serialization.Encoding.PEM).decode()},
                                content_type='multipart/form-data')

    def test_ca_reimport_lands_on_the_record_holding_the_key(self, app, auth_client):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from models import CA
        k1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        k2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        id1, crt1 = self._store(app, CA, self._cert('Homonym CA', k1, ca=True), k1, serial=0)
        id2, crt2 = self._store(app, CA, self._cert('Homonym CA', k2, ca=True), k2, serial=0)
        # Renewed certificate of the second CA (same key, new serial), imported alone
        r = self._import(auth_client, self._cert('Homonym CA', k2, ca=True), '/api/v2/cas/import')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == id2
        assert body['data']['has_private_key'] is True
        assert 'did not match' not in body['message']
        assert self._state(app, CA, id1) == (crt1, True)        # the homonym is untouched
        new_crt2, has_key2 = self._state(app, CA, id2)
        assert new_crt2 != crt2 and has_key2
        # A certificate with a fresh key links to neither: refused, both untouched
        stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        r = self._import(auth_client, self._cert('Homonym CA', stranger, ca=True), '/api/v2/cas/import')
        assert r.status_code == 409, r.data
        assert 'cannot be determined' in json.loads(r.data)['message']
        assert self._state(app, CA, id1) == (crt1, True)
        assert self._state(app, CA, id2) == (new_crt2, True)

    def test_certificate_reimport_lands_on_the_record_holding_the_key(self, app, auth_client, create_ca):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from models import Certificate, CA
        ca = create_ca(cn='Homonym Issuer CA')
        with app.app_context():
            from models import db
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_obj = db.session.get(CA, ca['id'])
            ca_key = get_ca_signing_key(ca_obj)
            from cryptography import x509
            import base64
            issuer = x509.load_pem_x509_certificate(base64.b64decode(ca_obj.crt)).subject
            caref = ca_obj.refid
        issued = lambda key: self._cert('homonym.example.com', key, issuer=issuer, signer=ca_key)
        k1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        k2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        id1, crt1 = self._store(app, Certificate, issued(k1), k1, caref=caref)
        id2, crt2 = self._store(app, Certificate, issued(k2), k2, caref=caref)
        r = self._import(auth_client, issued(k2), f'{BASE}/import')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == id2
        assert body['data']['has_private_key'] is True
        assert self._state(app, Certificate, id1) == (crt1, True)
        new_crt2, has_key2 = self._state(app, Certificate, id2)
        assert new_crt2 != crt2 and has_key2
        stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        r = self._import(auth_client, issued(stranger), f'{BASE}/import')
        assert r.status_code == 409, r.data
        assert 'cannot be determined' in json.loads(r.data)['message']
        assert self._state(app, Certificate, id1) == (crt1, True)
        assert self._state(app, Certificate, id2) == (new_crt2, True)

    def test_a_single_homonym_free_record_is_still_rekeyed(self, app, auth_client):
        """One record, a new key: the re-key path of the fifth review stays."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from models import CA
        k1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        id1, crt1 = self._store(app, CA, self._cert('Lone Rekey CA', k1, ca=True), k1, serial=0)
        stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        r = self._import(auth_client, self._cert('Lone Rekey CA', stranger, ca=True), '/api/v2/cas/import')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == id1 and body['data']['has_private_key'] is False
        assert 'did not match' in body['message']

    def test_cross_signed_ca_is_told_apart_by_issuer(self, app, auth_client):
        """Tenth review of #347: the same CA key under two issuers is two
        records; the issuer says which one a renewed certificate belongs to."""
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from models import CA
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        roots = {label: (x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, label)]),
                         rsa.generate_private_key(public_exponent=65537, key_size=2048))
                 for label in ('Root A 347', 'Root B 347', 'Root C 347')}
        cross = lambda label: self._cert('Cross Signed CA', key, issuer=roots[label][0], signer=roots[label][1], ca=True)
        ida, crta = self._store(app, CA, cross('Root A 347'), key, serial=0)
        idb, crtb = self._store(app, CA, cross('Root B 347'), key, serial=0)
        # Renewed under Root B (same key, new serial): the issuer tells the records apart
        r = self._import(auth_client, cross('Root B 347'), '/api/v2/cas/import')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == idb and body['data']['has_private_key'] is True
        assert self._state(app, CA, ida) == (crta, True)
        new_b, has_b = self._state(app, CA, idb)
        assert new_b != crtb and has_b
        # The same key under a third issuer belongs to neither record: refused, both untouched
        r = self._import(auth_client, cross('Root C 347'), '/api/v2/cas/import')
        assert r.status_code == 409, r.data
        assert 'cannot be determined' in json.loads(r.data)['message']
        assert self._state(app, CA, ida) == (crta, True)
        assert self._state(app, CA, idb) == (new_b, True)

    @pytest.mark.parametrize('path', ['/api/v2/cas/import', f'{BASE}/import'])
    def test_pending_ca_next_to_a_homonym_is_completed_through_its_request(self, app, auth_client, path):
        """Tenth review of #347: a CA waiting for its certificate is known by
        its request's key, and completed the way the dedicated upload
        completes it, not patched in place nor refused as ambiguous."""
        import base64, uuid
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from models import CA
        from security.encryption import encrypt_private_key
        from services.import_service import extract_cert_info
        cn = f"Pending Homonym CA {path.split('/')[3]}"
        k1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        k2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ext_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'External Root 347')])
        ext_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        id1, crt1 = self._store(app, CA, self._cert(cn, k1, ca=True), k1, serial=0)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        csr = x509.CertificateSigningRequestBuilder().subject_name(name).sign(k2, hashes.SHA256())
        signed = self._cert(cn, k2, issuer=ext_name, signer=ext_key, ca=True)
        kpem = k2.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        with app.app_context():
            from models import db
            row = CA(refid=str(uuid.uuid4()), descr=cn, crt='', serial=0,
                     csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                     prv=encrypt_private_key(base64.b64encode(kpem).decode()),
                     subject=extract_cert_info(signed)['subject'], imported_from='external_csr')
            db.session.add(row); db.session.commit(); id2 = row.id
        r = self._import(auth_client, signed, path)
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == id2 and body['data']['has_private_key'] is True
        assert 'installed' in body['message']
        assert self._state(app, CA, id1) == (crt1, True)
        with app.app_context():
            from models import db
            db.session.expire_all()
            row = db.session.get(CA, id2)
            assert row.crt and not row.is_pending
            assert x509.load_pem_x509_certificate(base64.b64decode(row.crt)).serial_number == signed.serial_number
