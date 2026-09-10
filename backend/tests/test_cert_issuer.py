"""utils.cert_issuer: key ownership helpers (#347 review)."""
import base64
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from utils.cert_issuer import private_key_matches, stored_private_key_matches


def _selfsigned(key, cn='cert-issuer.example.com'):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))


def _column(key):
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    return base64.b64encode(pem).decode()


class TestStoredPrivateKeyMatches:
    def test_true_false_and_none(self, app):
        with app.app_context():
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            cert = _selfsigned(key)
            assert private_key_matches(key, cert) is True
            assert private_key_matches(other, cert) is False
            assert stored_private_key_matches(_column(key), cert) is True
            assert stored_private_key_matches(_column(other), cert) is False
            assert stored_private_key_matches(None, cert) is None
            assert stored_private_key_matches('', cert) is None

    def test_an_unreadable_key_is_undecided_not_foreign(self, app):
        """A key that cannot be read has not been shown to belong to another
        certificate: None, so callers refuse rather than drop it."""
        with app.app_context():
            cert = _selfsigned(rsa.generate_private_key(public_exponent=65537, key_size=2048))
            assert stored_private_key_matches(base64.b64encode(b'garbage').decode(), cert) is None
            assert stored_private_key_matches('not even base64 !!', cert) is None
