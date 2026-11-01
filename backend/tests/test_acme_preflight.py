"""Tests for ACME preflight / dry-run — issue #162."""
import json

from tests.conftest import get_json

CONTENT_JSON = 'application/json'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


class TestAcmePreflightAuth:
    def test_preflight_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/preflight', {
            'domains': ['example.com'],
            'email': 'a@example.com',
        })
        assert r.status_code == 401, r.data


class TestAcmePreflightValidateOnly:
    def test_validate_only_reports_domain_step(self, auth_client, monkeypatch):
        from services.acme.acme_preflight_service import AcmePreflightService

        def fake_run(**kwargs):
            return {
                'ok': True,
                'mode': kwargs.get('mode', 'validate_only'),
                'staging_environment': 'staging',
                'steps': [
                    {'name': 'domains', 'label': 'Domain validation', 'status': 'pass', 'detail': 'OK', 'data': {}},
                ],
                'txt_records': [],
            }

        monkeypatch.setattr(AcmePreflightService, 'run', staticmethod(lambda **kw: fake_run(**kw)))

        r = post_json(auth_client, '/api/v2/acme/client/preflight', {
            'domains': ['preflight.example.com'],
            'email': 'admin@example.com',
            'challenge_type': 'http-01',
            'mode': 'validate_only',
        })
        assert r.status_code == 200
        body = get_json(r)
        assert body['data']['ok'] is True
        assert any(s['name'] == 'domains' for s in body['data']['steps'])

    def test_preflight_invalid_mode(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/preflight', {
            'domains': ['example.com'],
            'email': 'admin@example.com',
            'mode': 'invalid',
        })
        assert r.status_code == 400


class TestAcmePreflightServiceUnit:
    def test_domain_validation_fails_on_bad_syntax(self, app, monkeypatch):
        from services.acme.acme_preflight_service import AcmePreflightService

        def offline(*args, **kwargs):
            raise ConnectionError('no network in tests')
        monkeypatch.setattr('utils.ssrf_protection.safe_request_get', offline)
        with app.app_context():
            report = AcmePreflightService.run(
                domains=['not a domain!!!'],
                email='admin@example.com',
                mode='validate_only',
            )
        assert report['ok'] is False
        dom_step = next(s for s in report['steps'] if s['name'] == 'domains')
        assert dom_step['status'] == 'fail'


def _ed25519_csr_pem(cn='fips-preflight.example.com'):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.x509.oid import NameOID
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
           .sign(ed25519.Ed25519PrivateKey.generate(), None))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


class TestAcmePreflightFips:
    """An external CSR is refused by the preflight as the order route refuses it."""

    @staticmethod
    def _csr_step(app, monkeypatch, fips, csr_pem):
        import fips_mode
        from services.acme.acme_client_service import AcmeClientService
        from services.acme.acme_preflight_service import AcmePreflightService

        def offline(self):
            raise ConnectionError('no network in tests')
        monkeypatch.setattr(AcmeClientService, '_fetch_directory', offline)
        monkeypatch.setattr(fips_mode, 'enabled', lambda: fips)
        with app.app_context():
            report = AcmePreflightService.run(
                domains=['fips-preflight.example.com'], email='admin@example.com',
                key_source='csr', csr_pem=csr_pem, mode='validate_only')
        return next(s for s in report['steps'] if s['name'] == 'csr')

    def test_fips_mode_refuses_an_ed25519_csr(self, app, monkeypatch):
        step = self._csr_step(app, monkeypatch, True, _ed25519_csr_pem())
        assert step['status'] == 'fail'
        assert step['detail'] == 'Ed25519 keys not available in FIPS mode'

    def test_without_fips_the_same_csr_passes(self, app, monkeypatch):
        step = self._csr_step(app, monkeypatch, False, _ed25519_csr_pem())
        assert step['status'] == 'pass', step

    def test_an_unreadable_key_is_named_readably(self, monkeypatch):
        import fips_mode
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from services.acme.acme_client_service import fips_csr_refusal
        der = x509.load_pem_x509_csr(_ed25519_csr_pem().encode()).public_bytes(
            serialization.Encoding.DER)
        # 1.3.101.112 (Ed25519) becomes 1.3.101.127, a key no provider loads
        csr = x509.load_der_x509_csr(der.replace(b'\x06\x03\x2b\x65\x70', b'\x06\x03\x2b\x65\x7f'))
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        refusal = fips_csr_refusal(csr)
        assert refusal.startswith('The CSR key (algorithm 1.3.101.127) cannot be read'), refusal
        assert 'unreadable key' not in refusal
