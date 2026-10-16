"""A PKCS#11 RSA public key is exported as a SubjectPublicKeyInfo: python-pkcs11
encodes PKCS#1, and a CA on a new RSA HSM key failed with "Could not
deserialize key data" when the "PUBLIC KEY" PEM was parsed."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

pkcs11 = pytest.importorskip('pkcs11')

from services.hsm.pkcs11_provider import Pkcs11Provider  # noqa: E402


def test_rsa_public_key_pem_is_spki():
    from pkcs11 import Attribute
    numbers = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key().public_numbers()
    token_key = {Attribute.MODULUS: numbers.n.to_bytes(256, 'big'),
                 Attribute.PUBLIC_EXPONENT: numbers.e.to_bytes(3, 'big')}
    provider = Pkcs11Provider.__new__(Pkcs11Provider)  # no token needed to encode
    pem = provider._export_rsa_public_key(token_key)
    loaded = serialization.load_pem_public_key(pem.encode())
    assert loaded.public_numbers() == numbers
