"""Regression tests: sensitive-EKU policy on the sign-CSR path (issue audit
2.200, item M1).

- Protocol enrollees (default) never get OCSPSigning/timeStamping, and the
  extra_ekus re-merge must not resurrect them.
- The admin Sign-CSR path (allow_sensitive_ekus=True) issues them: it is the
  documented delegated-OCSP-responder workflow (key stays on the responder,
  operator signs its CSR).
"""
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID, NameOID

from services.trust_store.trust_store_service import TrustStoreService

OCSP_SIGNING = ExtendedKeyUsageOID.OCSP_SIGNING
CLIENT_AUTH = ExtendedKeyUsageOID.CLIENT_AUTH


def _make_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'EKU Policy CA')])
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                           critical=True)
            .sign(key, hashes.SHA256()))
    return cert, key


def _make_csr(ekus):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name(
                   [x509.NameAttribute(NameOID.COMMON_NAME, 'responder.test')])))
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(ekus),
                                        critical=False)
    return builder.sign(key, hashes.SHA256())


def _sign(csr, ca_cert, ca_key, **kwargs):
    pem = TrustStoreService.sign_csr(
        csr_pem=csr.public_bytes(serialization.Encoding.PEM),
        ca_cert=ca_cert,
        ca_private_key=ca_key,
        validity_days=30,
        **kwargs,
    )
    return x509.load_pem_x509_certificate(pem, default_backend())


def _ekus(cert):
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
    except x509.ExtensionNotFound:
        return set()
    return set(ext.value)


class TestSensitiveEkuPolicy:

    def test_protocol_path_strips_ocsp_signing(self, app):
        ca_cert, ca_key = _make_ca()
        csr = _make_csr([OCSP_SIGNING, CLIENT_AUTH])
        with app.app_context():
            cert = _sign(csr, ca_cert, ca_key)
        assert OCSP_SIGNING not in _ekus(cert)
        assert CLIENT_AUTH in _ekus(cert)

    def test_extra_ekus_does_not_resurrect_stripped_ekus(self, app):
        ca_cert, ca_key = _make_ca()
        csr = _make_csr([OCSP_SIGNING, CLIENT_AUTH])
        with app.app_context():
            cert = _sign(csr, ca_cert, ca_key,
                         extra_ekus=['1.3.6.1.5.5.7.3.1'])
        assert OCSP_SIGNING not in _ekus(cert)
        assert ExtendedKeyUsageOID.SERVER_AUTH in _ekus(cert)

    def test_admin_path_keeps_ocsp_signing(self, app):
        ca_cert, ca_key = _make_ca()
        csr = _make_csr([OCSP_SIGNING])
        with app.app_context():
            cert = _sign(csr, ca_cert, ca_key, allow_sensitive_ekus=True)
        assert OCSP_SIGNING in _ekus(cert)
