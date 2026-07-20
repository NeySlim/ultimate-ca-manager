"""ACME proxy ARI (RFC 9773) — directory advertisement + renewal-info route.

Regression coverage for:
  * get_directory() advertises renewalInfo when upstream does
  * get_directory() omits renewalInfo when upstream does not
  * GET /acme/proxy/renewal-info/<certID> serves a local suggestedWindow
  * GET /acme/proxy/<slug>/renewal-info/<certID> works for slug-scoped CAs
  * Malformed / unknown certID → problem+json error
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from models import db, AcmeClientAccount, Certificate
from services.acme.acme_proxy_service import AcmeProxyService
from tests.acme_proxy_upstream_stub import stub_acme_proxy_upstream


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


@pytest.fixture
def proxy_account(app):
    with app.app_context():
        AcmeClientAccount.query.delete()
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url='https://acme-ari-stub.example/directory',
            label='ARI test',
            email='ari@example.com',
            proxy_enabled=True,
            proxy_slug='ari-test',
        )
        db.session.add(acct)
        db.session.commit()
        yield acct
        AcmeClientAccount.query.delete()
        db.session.commit()


def _make_proxy(monkeypatch, fake_directory, account_id=None):
    stub_acme_proxy_upstream(monkeypatch, fake_directory=fake_directory)
    base = 'https://ucm.example/acme/proxy'
    if account_id is not None:
        return AcmeProxyService(base_url=base, account_id=account_id)
    return AcmeProxyService(base_url=base)


class TestDirectoryRenewalInfo:
    def test_advertises_renewal_info_when_upstream_has_it(self, proxy_account, monkeypatch):
        # Actalis-style directory with renewalInfo
        d = {
            'newNonce': 'https://acme-ari-stub.example/acme/newnonce',
            'newAccount': 'https://acme-ari-stub.example/acme/newaccount',
            'newOrder': 'https://acme-ari-stub.example/acme/neworders',
            'revokeCert': 'https://acme-ari-stub.example/acme/revokecert',
            'keyChange': 'https://acme-ari-stub.example/acme/key-change',
            'renewalInfo': 'https://acme-ari-stub.example/acme/renewal-info',
            'meta': {'externalAccountRequired': True, 'name': 'acme-server'},
        }
        svc = _make_proxy(monkeypatch, d, account_id=proxy_account.id)
        out = svc.get_directory()
        assert 'renewalInfo' in out
        # RFC 9773 §3/§4.1: directory publishes the BASE URL; clients append
        # "/<certID>". No literal placeholder in the value.
        assert out['renewalInfo'] == 'https://ucm.example/acme/proxy/renewal-info'

    def test_omits_renewal_info_when_upstream_lacks_it(self, proxy_account, monkeypatch):
        # Let's Encrypt-style directory without top-level renewalInfo
        d = {
            'newNonce': 'https://acme-ari-stub.example/new-nonce',
            'newAccount': 'https://acme-ari-stub.example/new-account',
            'newOrder': 'https://acme-ari-stub.example/new-order',
            'revokeCert': 'https://acme-ari-stub.example/revoke-cert',
            'keyChange': 'https://acme-ari-stub.example/key-change',
            'meta': {},
        }
        svc = _make_proxy(monkeypatch, d, account_id=proxy_account.id)
        out = svc.get_directory()
        assert 'renewalInfo' not in out


def _import_cert_for_ari(app, aki_hex: str, serial_int: int):
    """Insert a minimal Certificate row with aki + serial matching a certID."""
    with app.app_context():
        from uuid import uuid4
        cert = Certificate(
            refid=str(uuid4()),
            descr='ARI proxy test',
            crt=base64.b64encode(b'FAKEPEM').decode(),
            subject='CN=ari-test',
            subject_cn='ari-test',
            issuer='CN=ari-test-ca',
            serial_number=str(serial_int),
            valid_from=datetime.now(timezone.utc) - timedelta(days=10),
            valid_to=datetime.now(timezone.utc) + timedelta(days=80),
            key_algo='RSA 2048',
            aki=aki_hex,
            imported_from='acme_client',
            source='acme_client',
        )
        db.session.add(cert)
        db.session.commit()
        return cert.id


class TestRenewalInfoRoute:
    def _certid(self, aki_hex: str, serial_int: int) -> str:
        aki_bytes = bytes.fromhex(aki_hex.replace(':', ''))
        serial_bytes = serial_int.to_bytes((serial_int.bit_length() + 7) // 8, 'big')
        return f"{_b64url(aki_bytes)}.{_b64url(serial_bytes)}"

    def test_default_route_serves_window(self, app, client, proxy_account, monkeypatch):
        aki_hex = 'A8:4A:94:24:3A:1E:82:11'
        serial_int = 0x1234567890ABCDEF
        _import_cert_for_ari(app, aki_hex, serial_int)
        certid = self._certid(aki_hex, serial_int)

        # No directory fetch needed for the route — but stub anyway for safety.
        stub_acme_proxy_upstream(monkeypatch)

        r = client.get(f'/acme/proxy/renewal-info/{certid}')
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert 'suggestedWindow' in body
        assert 'start' in body['suggestedWindow']
        assert 'end' in body['suggestedWindow']
        assert r.headers.get('Retry-After')
        assert 'public' in r.headers.get('Cache-Control', '')

    def test_slug_route_serves_window(self, app, client, proxy_account, monkeypatch):
        aki_hex = 'B1:C2:D3:E4'
        serial_int = 0x42
        _import_cert_for_ari(app, aki_hex, serial_int)
        certid = self._certid(aki_hex, serial_int)

        stub_acme_proxy_upstream(monkeypatch)

        r = client.get(f'/acme/proxy/ari-test/renewal-info/{certid}')
        assert r.status_code == 200, r.get_data(as_text=True)
        assert 'suggestedWindow' in r.get_json()

    def test_malformed_certid_returns_400(self, app, client, monkeypatch):
        stub_acme_proxy_upstream(monkeypatch)
        r = client.get('/acme/proxy/renewal-info/not-a-valid-certid')
        assert r.status_code == 400
        assert r.headers['Content-Type'] == 'application/problem+json'

    def test_unknown_certid_returns_404(self, app, client, monkeypatch):
        stub_acme_proxy_upstream(monkeypatch)
        # Valid shape, no matching cert in DB
        certid = self._certid('AA:BB:CC:DD', 999999)
        r = client.get(f'/acme/proxy/renewal-info/{certid}')
        assert r.status_code == 404


class TestImportPopulatesAki:
    def test_import_certificate_sets_aki_and_ski(self, app):
        """Proxy-issued certs must have aki populated so ARI lookups match."""
        from services.cert_service import CertificateService
        # Self-signed cert with AKI==SKI (generated via cryptography)
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ari-import-test')])
        builder = (x509.CertificateBuilder()
                   .subject_name(subject)
                   .issuer_name(issuer)
                   .public_key(key.public_key())
                   .serial_number(0x1234)
                   .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
                   .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30)))
        cert_obj = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        ).add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        ).sign(key, hashes.SHA256(), default_backend())
        pem = cert_obj.public_bytes(serialization.Encoding.PEM).decode()

        with app.app_context():
            imported = CertificateService.import_certificate(
                descr='ari-aki-test', cert_pem=pem, source='acme_client', username='test'
            )
            assert imported.aki is not None and ':' in imported.aki
            assert imported.ski is not None and ':' in imported.ski
            # Cleanup
            db.session.delete(imported)
            db.session.commit()
