"""The key-and-certificate check of a backup compares public keys, without validating RSA keys.

A backup checks each stored key against its certificate. Loading an RSA key
also ran OpenSSL's consistency check of the private numbers, which cost
several milliseconds a key: most of a backup of a large installation. The
check only compares public keys, so the validation is skipped there.
"""
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from services.backup import key_material


def _pair(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'key-check.example.com')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return pem, cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture
def loads(monkeypatch):
    seen = []
    original = serialization.load_pem_private_key

    def spy(data, password, *args, **kwargs):
        seen.append(kwargs)
        return original(data, password, *args, **kwargs)

    monkeypatch.setattr(serialization, 'load_pem_private_key', spy)
    return seen


def test_an_rsa_key_is_loaded_without_its_validation(loads):
    pem, cert = _pair(rsa.generate_private_key(public_exponent=65537, key_size=2048))

    assert key_material.key_matches_certificate(pem, cert, label='rsa') is True
    assert loads and all(kw.get('unsafe_skip_rsa_key_validation') is True for kw in loads)


@pytest.mark.parametrize('make', [
    lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048),
    lambda: ec.generate_private_key(ec.SECP256R1()),
])
def test_a_key_of_another_certificate_is_still_a_mismatch(make):
    pem, _cert = _pair(make())
    _other_pem, other_cert = _pair(make())

    assert key_material.key_matches_certificate(pem, other_cert, label='other') is False
