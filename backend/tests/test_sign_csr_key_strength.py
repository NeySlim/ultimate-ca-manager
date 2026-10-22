"""Regression tests: key-strength floor on every issuance path
(security audit v2.203, item #2).

``validate_enrollment_public_key`` (RSA >= 2048, NIST P-256/384/521, Ed25519/
Ed448) existed and was called from SCEP and EST only. Its docstring claimed
parity with UI/API issuance, but ``TrustStoreService.sign_csr`` — the choke
point every other path goes through, including the admin sign-CSR endpoint and
ACME finalize — never called it. A CSR built on a 1024-bit RSA key or a weak
curve was signed without complaint.

The fix moves the check into sign_csr so all paths inherit the floor.
"""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from services.trust_store.trust_store_service import TrustStoreService


@pytest.fixture(scope='module')
def ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Key Floor CA')])
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


def _csr(private_key, hash_alg=hashes.SHA256()):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'weak.example.com')])
    )
    # Ed25519/Ed448 self-sign with algorithm=None
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return builder.sign(private_key, None)
    return builder.sign(private_key, hash_alg)


def _sign(ca, csr, **kwargs):
    ca_cert, ca_key = ca
    return TrustStoreService.sign_csr(
        csr_pem=csr.public_bytes(serialization.Encoding.PEM),
        ca_cert=ca_cert,
        ca_private_key=ca_key,
        validity_days=30,
        **kwargs,
    )


# --- strong keys still sign ------------------------------------------------

def test_rsa_2048_is_accepted(ca):
    assert _sign(ca, _csr(rsa.generate_private_key(65537, 2048)))


def test_p256_is_accepted(ca):
    assert _sign(ca, _csr(ec.generate_private_key(ec.SECP256R1())))


def test_p384_is_accepted(ca):
    assert _sign(ca, _csr(ec.generate_private_key(ec.SECP384R1())))


def test_ed25519_is_accepted(ca):
    assert _sign(ca, _csr(ed25519.Ed25519PrivateKey.generate()))


# --- weak keys are refused --------------------------------------------------

def test_rsa_1024_is_rejected(ca):
    """Below the 2048-bit floor — previously signed without complaint."""
    csr = _csr(rsa.generate_private_key(65537, 1024), hashes.SHA256())
    with pytest.raises(ValueError, match='RSA key too small'):
        _sign(ca, csr)


def test_weak_curve_secp192r1_is_rejected(ca):
    csr = _csr(ec.generate_private_key(ec.SECP192R1()))
    with pytest.raises(ValueError, match='Unsupported EC curve'):
        _sign(ca, csr)


def test_brainpool_curve_is_accepted(ca):
    """Brainpool is in the registry: signed outside FIPS mode."""
    _sign(ca, _csr(ec.generate_private_key(ec.BrainpoolP256R1())))


def test_secp256k1_curve_is_rejected(ca):
    """Non-registry curve outside the allow-list."""
    with pytest.raises(ValueError, match='Unsupported EC curve'):
        _sign(ca, _csr(ec.generate_private_key(ec.SECP256K1())))


def test_weak_key_rejected_for_intermediate_ca_too(ca):
    """The floor is not bypassable by asking for a CA certificate."""
    csr = _csr(rsa.generate_private_key(65537, 1024))
    with pytest.raises(ValueError, match='RSA key too small'):
        _sign(ca, csr, cert_type='intermediate_ca')


def test_weak_key_rejected_even_on_admin_sensitive_eku_path(ca):
    """allow_sensitive_ekus relaxes EKU policy, never key strength."""
    csr = _csr(rsa.generate_private_key(65537, 1024))
    with pytest.raises(ValueError, match='RSA key too small'):
        _sign(ca, csr, allow_sensitive_ekus=True)
