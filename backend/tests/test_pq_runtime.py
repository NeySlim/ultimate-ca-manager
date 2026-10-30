"""What the pinned cryptography does with post-quantum keys. The plan builds on
these facts: a test failing here means a premise changed, not that UCM broke."""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.backends.openssl.backend import backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import mldsa
from cryptography.hazmat.primitives.serialization import pkcs7, pkcs12
from cryptography.x509.oid import NameOID

NAME = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'pq-runtime.test')])
NOW = datetime.datetime.now(datetime.timezone.utc)
CLASSES = [mldsa.MLDSA44PrivateKey, mldsa.MLDSA65PrivateKey, mldsa.MLDSA87PrivateKey]


def _self_signed(key, digest=None):
    return (x509.CertificateBuilder().subject_name(NAME).issuer_name(NAME)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(NOW).not_valid_after(NOW + datetime.timedelta(days=1))
            .sign(key, digest))


def test_the_linked_libcrypto_has_ml_dsa():
    assert backend.mldsa_supported()


@pytest.mark.parametrize('cls', CLASSES)
def test_ml_dsa_generates_and_signs(cls):
    key = cls.generate()
    key.public_key().verify(key.sign(b'data'), b'data')


@pytest.mark.parametrize('cls', CLASSES)
def test_x509_signs_with_none_and_refuses_a_digest(cls):
    key = cls.generate()
    cert = _self_signed(key)
    cert.verify_directly_issued_by(cert)
    assert cert.signature_hash_algorithm is None
    with pytest.raises(ValueError, match='Algorithm must be None'):
        _self_signed(key, hashes.SHA256())


def test_pkcs12_refuses_an_ml_dsa_key(mldsa_key):
    with pytest.raises(TypeError):
        pkcs12.serialize_key_and_certificates(
            b'pq', mldsa_key, _self_signed(mldsa_key), None, serialization.NoEncryption())


def test_signed_pkcs7_refuses_an_ml_dsa_key(mldsa_key):
    with pytest.raises(TypeError):
        (pkcs7.PKCS7SignatureBuilder().set_data(b'data')
         .add_signer(_self_signed(mldsa_key), mldsa_key, hashes.SHA512())
         .sign(serialization.Encoding.DER, []))


def test_certificates_only_pkcs7_carries_an_ml_dsa_certificate(mldsa_key):
    cert = _self_signed(mldsa_key)
    der = pkcs7.serialize_certificates([cert], serialization.Encoding.DER)
    assert pkcs7.load_der_pkcs7_certificates(der) == [cert]


def test_slh_dsa_is_not_in_cryptography_yet():
    # Fails the day cryptography ships SLH-DSA: signing it natively becomes possible
    with pytest.raises(ImportError):
        from cryptography.hazmat.primitives.asymmetric import slhdsa  # noqa: F401
