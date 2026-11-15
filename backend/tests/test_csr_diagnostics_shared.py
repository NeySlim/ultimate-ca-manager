"""The weak-hash diagnosis is written once, and key strength has a ceiling.

``cryptography`` reports ``is_signature_valid`` False for a SHA-1 CSR even when
the signature verifies -- it refuses to vouch for the hash, not the request.
EST and WSTEP each carried a byte-identical copy of the helper that says so,
and the other doors said only "CSR signature is invalid", which reads as if the
request were corrupted. The key-strength floor was already shared; the ceiling
did not exist, so a CSR built on a 65536-bit RSA key was signable.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from utils import key_type
from utils.csr_diagnostics import WEAK_CSR_HASH_ALGORITHMS, weak_csr_hash_algorithm


@pytest.fixture(scope='module')
def sha1_csr():
    """A real SHA-1 CSR. cryptography refuses to sign one, so openssl makes it."""
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / 'k.pem'
        csr_path = Path(tmp) / 'c.pem'
        result = subprocess.run([
            'openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', str(key_path), '-out', str(csr_path), '-sha1',
            '-subj', '/CN=sha1.example.com',
        ], capture_output=True)
        if result.returncode != 0:
            pytest.skip('openssl cannot produce a SHA-1 CSR here')
        return x509.load_pem_x509_csr(csr_path.read_bytes())


def test_the_helper_names_the_weak_hash(sha1_csr):
    assert sha1_csr.is_signature_valid is False
    assert weak_csr_hash_algorithm(sha1_csr) == 'sha1'


def test_a_strong_hash_is_not_diagnosed():
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ok.example.com')])
    ).sign(key, hashes.SHA256())

    assert weak_csr_hash_algorithm(csr) is None


def test_an_unreadable_algorithm_is_not_diagnosed():
    """Contract kept: Ed25519 has no hash algorithm and must not raise."""
    class _NoAlgorithm:
        @property
        def signature_hash_algorithm(self):
            raise ValueError('Ed25519 has none')

    assert weak_csr_hash_algorithm(_NoAlgorithm()) is None
    assert weak_csr_hash_algorithm(MagicMock(signature_hash_algorithm=None)) is None


def test_est_uses_the_shared_helper(sha1_csr):
    from api import est_protocol

    assert est_protocol._weak_csr_hash_algorithm is weak_csr_hash_algorithm
    assert est_protocol._weak_csr_hash_algorithm(sha1_csr) == 'sha1'


def test_the_table_is_unchanged():
    assert WEAK_CSR_HASH_ALGORITHMS == {'md5', 'sha1'}


@pytest.mark.parametrize('bits,rejected', [
    (1024, True),
    (2048, False),
    (4096, False),
    (8192, False),
    (16384, True),
    (65536, True),
])
def test_rsa_key_size_has_both_a_floor_and_a_ceiling(bits, rejected):
    public_key = MagicMock(spec=rsa.RSAPublicKey)
    public_key.key_size = bits

    problem = key_type.validate_enrollment_public_key(public_key)

    assert (problem is not None) is rejected
    if rejected and bits > key_type.MAX_RSA_BITS:
        assert 'maximum' in problem


def test_the_floor_message_is_unchanged():
    """Contract kept: the message the existing tests read."""
    public_key = MagicMock(spec=rsa.RSAPublicKey)
    public_key.key_size = 1024

    assert key_type.validate_enrollment_public_key(public_key) == (
        'RSA key too small (1024 bits); minimum is 2048')


def test_the_microsoft_csr_header_is_accepted():
    """certreq.exe writes NEW CERTIFICATE REQUEST; the DER is the same."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    from utils.acme_csr import load_pem_csr

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ms.example.com')])
    ).sign(key, hashes.SHA256())
    pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    microsoft = (pem.replace('BEGIN CERTIFICATE REQUEST',
                             'BEGIN NEW CERTIFICATE REQUEST')
                 .replace('END CERTIFICATE REQUEST',
                          'END NEW CERTIFICATE REQUEST'))

    parsed = load_pem_csr(microsoft)

    assert parsed.public_bytes(serialization.Encoding.DER) == \
        csr.public_bytes(serialization.Encoding.DER)


@pytest.mark.parametrize('text', ['', '   ', 'not a csr at all',
                                  '-----BEGIN CERTIFICATE-----\nAA\n-----END CERTIFICATE-----'])
def test_a_non_csr_is_still_refused(text):
    """Contract kept: everything that was refused still is."""
    from utils.acme_csr import load_pem_csr

    with pytest.raises(ValueError):
        load_pem_csr(text)
