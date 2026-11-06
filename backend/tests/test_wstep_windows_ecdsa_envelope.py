"""WSTEP accepts the CMC envelope Windows CertEnroll signs with an ECDSA key.

Real requests captured on Server 2025 (06/11/2026): SignerInfo.signatureAlgorithm is
id-ecPublicKey, not ecdsa-with-SHA*, and the digest comes from digestAlgorithm."""
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from services.wstep.rst_parser import _unwrap_pkcs7_csr
from services.wstep.wstep_service import _load_csr, _verify_pkcs7_pop

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.mark.parametrize('name,curve,digest', [
    ('wstep_windows_ecdsa_p256.cmc.der', ec.SECP256R1, 'sha256'),
    ('wstep_windows_ecdsa_p384.cmc.der', ec.SECP384R1, 'sha384'),
])
def test_a_windows_ecdsa_envelope_proves_possession(name, curve, digest):
    csr_der, _, outer = _unwrap_pkcs7_csr((FIXTURES / name).read_bytes())
    csr, err = _load_csr(csr_der)
    assert err is None
    assert isinstance(csr.public_key().curve, curve)
    signer_info = outer['signer_infos'][0]
    assert signer_info['signature_algorithm']['algorithm'].dotted == '1.2.840.10045.2.1'
    assert signer_info['digest_algorithm']['algorithm'].native == digest
    assert _verify_pkcs7_pop(csr, outer) is None


def test_a_tampered_windows_envelope_is_refused():
    csr_der, _, outer = _unwrap_pkcs7_csr((FIXTURES / 'wstep_windows_ecdsa_p256.cmc.der').read_bytes())
    csr, _ = _load_csr(csr_der)
    signer_info = outer['signer_infos'][0]
    signature = bytearray(signer_info['signature'].native)
    signature[-1] ^= 0x01
    signer_info['signature'] = bytes(signature)
    assert _verify_pkcs7_pop(csr, outer) == 'PKCS#7 envelope signature invalid (proof of possession failed)'
