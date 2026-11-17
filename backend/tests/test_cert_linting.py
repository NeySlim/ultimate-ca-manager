"""Tests for certificate conformance linting (RFC 5280 / CABF)."""
import json

import pytest

from models import db, Certificate
from services import cert_linting_service as L

pkilint_available = L.linters_status()['pkilint']
needs_pkilint = pytest.mark.skipif(not pkilint_available, reason='pkilint not installed')


@pytest.fixture
def lintable_cert(app, create_cert):
    info = create_cert(cn='lint-test.example.com', validity_days=365)
    cert_id = info.get('id')
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        return {'id': cert_id, 'crt': cert.crt}


class TestService:
    def test_status_shape(self):
        st = L.linters_status()
        assert set(st.keys()) == {'pkilint', 'zlint'}
        assert all(isinstance(v, bool) for v in st.values())

    def test_invalid_profile_raises(self, lintable_cert):
        with pytest.raises(ValueError):
            L.lint_certificate_pem(lintable_cert['crt'], 'nonsense')

    @needs_pkilint
    def test_rfc5280_clean_or_informative(self, lintable_cert):
        r = L.lint_certificate_pem(lintable_cert['crt'], 'rfc5280')
        assert r['available'] is True
        assert 'pkilint' in r['linters']
        # A well-formed internal cert must not have RFC 5280 errors.
        assert r['summary']['error'] == 0
        assert r['summary']['fatal'] == 0

    @needs_pkilint
    def test_cabf_detects_type_and_findings(self, lintable_cert):
        r = L.lint_certificate_pem(lintable_cert['crt'], 'cabf')
        assert r['available'] is True
        # Internal certs trip Baseline-Requirements rules (e.g. validity, SAN).
        assert r.get('detected_type')
        assert r['summary']['error'] >= 1
        for f in r['findings']:
            assert f['severity'] in ('fatal', 'error', 'warning', 'notice', 'info')
            assert f['source'] in ('pkilint', 'zlint')
            assert f['code']

    def test_bad_pem_raises_valueerror(self):
        if not L.is_available():
            pytest.skip('no linter available')
        with pytest.raises(ValueError):
            L.lint_certificate_pem('not a certificate', 'rfc5280')


class TestEndpoint:
    def test_requires_auth(self, client, lintable_cert):
        r = client.get(f"/api/v2/certificates/{lintable_cert['id']}/lint")
        assert r.status_code == 401, r.data

    def test_status_endpoint(self, auth_client):
        r = auth_client.get('/api/v2/certificates/lint/status')
        assert r.status_code == 200
        data = json.loads(r.data)['data']
        assert 'linters' in data and 'pkilint' in data['linters']
        assert 'rfc5280' in data['profiles']

    def test_unknown_cert_404(self, auth_client):
        assert auth_client.get('/api/v2/certificates/999999/lint').status_code == 404

    def test_invalid_profile_400(self, auth_client, lintable_cert):
        r = auth_client.get(f"/api/v2/certificates/{lintable_cert['id']}/lint?profile=xyz")
        assert r.status_code == 400

    @needs_pkilint
    def test_lint_returns_findings(self, auth_client, lintable_cert):
        r = auth_client.get(f"/api/v2/certificates/{lintable_cert['id']}/lint?profile=cabf")
        assert r.status_code == 200
        data = json.loads(r.data)['data']
        assert data['available'] is True
        assert data['profile'] == 'cabf'
        assert isinstance(data['findings'], list)
        assert 'summary' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
