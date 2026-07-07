"""Regression tests for protocol-endpoint signing guards (lot-4 review).

  - TSA (/tsa): refuses to sign when no TSA CA is explicitly configured
    (no silent fallback to an arbitrary CA key) and when the configured CA
    is offline.
  - SCEP auto-approve: refuses to issue a certificate when the CA is offline,
    consistent with the CSR/CRL/EST signing paths.
"""
import json
import pytest

from models import db, CA
from models.system_config import SystemConfig


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _clear_config(key):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        db.session.delete(row)
        db.session.commit()


class TestTsaConfigGuard:
    """TSA must be an explicit opt-in; no signing with an arbitrary CA."""

    def test_tsa_unconfigured_returns_503(self, app, client):
        with app.app_context():
            _clear_config('tsa_ca_refid')
        # A minimal but well-formed-enough body; we must get 503 *before*
        # any CA key is selected, regardless of payload.
        r = client.post('/tsa', data=b'\x30\x03\x02\x01\x01',
                        content_type='application/timestamp-query')
        assert r.status_code == 503
        assert b'not configured' in r.data.lower()

    def test_tsa_offline_ca_returns_503(self, app, client, create_ca):
        ca = create_ca(cn='TSA Offline CA')
        with app.app_context():
            ca_obj = db.session.get(CA, ca['id'])
            ca_obj.offline = True
            ca_obj.offline_reason = 'test'
            db.session.commit()
            _set_config('tsa_ca_refid', ca_obj.refid)
        try:
            r = client.post('/tsa', data=b'\x30\x03\x02\x01\x01',
                            content_type='application/timestamp-query')
            assert r.status_code == 503
            assert b'unavailable' in r.data.lower()
        finally:
            with app.app_context():
                _clear_config('tsa_ca_refid')


class TestScepOfflineGuard:
    """SCEP auto-approve must not sign with an offline CA."""

    def test_auto_approve_refuses_offline_ca(self, app, create_ca):
        ca = create_ca(cn='SCEP Offline CA')
        with app.app_context():
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID
            from services.scep.scep_service import SCEPService

            ca_obj = db.session.get(CA, ca['id'])
            ca_obj.offline = True
            ca_obj.offline_reason = 'maintenance'
            db.session.commit()

            svc = SCEPService(ca_refid=ca_obj.refid, auto_approve=True)

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'device.example.com')]))
                .sign(key, hashes.SHA256())
            )

            class _Req:
                id = 1
            with pytest.raises(ValueError, match='offline'):
                svc._auto_approve_request(_Req(), csr)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestCsrExtensionPolicy:
    """A crafted CSR must never confer CA powers on a leaf certificate
    (EST/SCEP/ACME enrollees call the shared TrustStoreService.sign_csr)."""

    @staticmethod
    def _ca():
        import datetime
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(65537, 2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Guard Root CA')])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime(2020, 1, 1))
                .not_valid_after(datetime.datetime(2035, 1, 1))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        return cert, key

    @staticmethod
    def _malicious_csr():
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        k = rsa.generate_private_key(65537, 2048)
        return (x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'evil.example.com')]))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(
                    digital_signature=True, key_cert_sign=True, crl_sign=True,
                    content_commitment=False, key_encipherment=True, data_encipherment=False,
                    key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
                .sign(k, hashes.SHA256()))

    def _issue(self, cert_type):
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from services.trust_store import TrustStoreService
        ca_cert, ca_key = self._ca()
        pem = TrustStoreService.sign_csr(
            csr_pem=self._malicious_csr().public_bytes(serialization.Encoding.PEM),
            ca_cert=ca_cert, ca_private_key=ca_key, validity_days=90, cert_type=cert_type)
        return x509.load_pem_x509_certificate(pem if isinstance(pem, bytes) else pem.encode())

    def test_leaf_cannot_become_ca_via_crafted_csr(self):
        from cryptography import x509
        cert = self._issue('server_cert')
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        assert bc.ca is False
        assert ku.key_cert_sign is False
        assert ku.crl_sign is False

    def test_intermediate_ca_signing_still_confers_ca(self):
        from cryptography import x509
        cert = self._issue('intermediate_ca')
        bc = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        assert bc.ca is True
