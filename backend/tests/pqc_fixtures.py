"""Post-quantum test material, made once by OpenSSL 3.5 (``fixtures/pqc/regenerate.sh``)
and only read here: no test runs openssl."""
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

PQC_DIR = Path(__file__).parent / 'fixtures' / 'pqc'
P12_PASSWORD = b'pqc-fixture'   # as in regenerate.sh


def fixture_bytes(name: str) -> bytes:
    return (PQC_DIR / name).read_bytes()


def load_mldsa_key():
    """The fixture ML-DSA-65 private key (seed-only PKCS#8, the layout pyca reads)."""
    return serialization.load_pem_private_key(fixture_bytes('mldsa65-seed.pem'), None)


@pytest.fixture
def mldsa_key():
    return load_mldsa_key()


@pytest.fixture
def mldsa_csr():
    """CSR made by OpenSSL with ``mldsa_key``, subject CN=UCM PQC fixture ML-DSA-65."""
    return x509.load_pem_x509_csr(fixture_bytes('mldsa65-csr.pem'))
