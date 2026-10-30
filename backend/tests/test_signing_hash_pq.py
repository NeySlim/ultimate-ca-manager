"""signing_hash_for follows the registry's needs_digest: no digest for keys whose
signature scheme fixes its own (Ed25519, Ed448, ML-DSA), whatever was requested."""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, mldsa, rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID

from services.trust_store.csr_operations_mixin import CSROperationsMixin
from services.trust_store.key_operations_mixin import KeyOperationsMixin
from utils.signing_hash import signing_hash_for

NAME = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'pq-signing.test')])
NOW = datetime.datetime.now(datetime.timezone.utc)

DIGESTLESS = {
    'ML-DSA-44': mldsa.MLDSA44PrivateKey.generate,
    'ML-DSA-65': mldsa.MLDSA65PrivateKey.generate,
    'ML-DSA-87': mldsa.MLDSA87PrivateKey.generate,
    'ED25519': ed25519.Ed25519PrivateKey.generate,
    'ED448': ed448.Ed448PrivateKey.generate,
}


class _WrappedMLDSA65:
    """An HSM-style key: signs through its provider, registered as the pyca type."""

    def __init__(self):
        self._key = mldsa.MLDSA65PrivateKey.generate()

    def sign(self, data, context=None):
        return self._key.sign(data)

    def public_key(self):
        return self._key.public_key()


mldsa.MLDSA65PrivateKey.register(_WrappedMLDSA65)


def _certificate(key, digest):
    return (x509.CertificateBuilder().subject_name(NAME).issuer_name(NAME)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(NOW).not_valid_after(NOW + datetime.timedelta(days=1))
            .sign(key, digest))


@pytest.mark.parametrize('label', DIGESTLESS)
@pytest.mark.parametrize('requested', [None, hashes.SHA256(), hashes.SHA512()])
def test_no_digest_whatever_was_requested(label, requested):
    assert signing_hash_for(DIGESTLESS[label](), requested) is None


@pytest.mark.parametrize('label', DIGESTLESS)
def test_csr_crl_certificate_and_ocsp_sign(label):
    key = DIGESTLESS[label]()
    digest = signing_hash_for(key, hashes.SHA256())

    csr = x509.CertificateSigningRequestBuilder().subject_name(NAME).sign(key, digest)
    assert csr.is_signature_valid

    cert = _certificate(key, digest)
    cert.verify_directly_issued_by(cert)

    crl = (x509.CertificateRevocationListBuilder().issuer_name(NAME)
           .last_update(NOW).next_update(NOW + datetime.timedelta(days=1)).sign(key, digest))
    assert crl.is_signature_valid(key.public_key())

    response = (ocsp.OCSPResponseBuilder()
                .add_response(cert=cert, issuer=cert, algorithm=hashes.SHA256(),
                              cert_status=ocsp.OCSPCertStatus.GOOD, this_update=NOW,
                              next_update=NOW + datetime.timedelta(hours=1),
                              revocation_time=None, revocation_reason=None)
                .responder_id(ocsp.OCSPResponderEncoding.HASH, cert)
                .sign(key, digest))
    assert response.signature_hash_algorithm is None


def test_a_provider_held_mldsa_key_takes_no_digest():
    key = _WrappedMLDSA65()
    assert signing_hash_for(key, hashes.SHA384()) is None
    _certificate(key, signing_hash_for(key)).verify_directly_issued_by(_certificate(key, None))


@pytest.mark.parametrize('key,expected', [
    (rsa.generate_private_key(public_exponent=65537, key_size=2048), 'sha256'),
    (ec.generate_private_key(ec.SECP384R1()), 'sha256'),
    (ec.generate_private_key(ec.BrainpoolP384R1()), 'sha384'),
])
def test_keys_that_take_a_digest_keep_the_registry_default(key, expected):
    assert signing_hash_for(key).name == expected
    assert signing_hash_for(key, hashes.SHA512()).name == 'sha512'


@pytest.mark.parametrize('label', ['ED25519', 'ML-DSA-65'])
def test_generate_csr_signs_a_digestless_key(label, monkeypatch):
    key = DIGESTLESS[label]()
    monkeypatch.setattr(KeyOperationsMixin, 'generate_private_key', staticmethod(lambda _kt: key))
    csr_pem, key_pem = CSROperationsMixin.generate_csr(NAME, key_type='2048', digest='sha256')
    csr = x509.load_pem_x509_csr(csr_pem)
    assert csr.is_signature_valid
    assert csr.signature_hash_algorithm is None
    assert serialization.load_pem_private_key(key_pem, None).public_key() == key.public_key()
