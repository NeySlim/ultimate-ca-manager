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


def test_a_cached_pkcs1_key_is_repaired_on_read(app):
    """Keys generated or synced before the fix carry the PKCS#1 body in the
    cache; the read hands back a SubjectPublicKeyInfo and stores it."""
    import base64
    import json
    from models import db
    from models.hsm import HsmKey, HsmProvider
    from services.hsm import HsmService
    public_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    body = base64.encodebytes(public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.PKCS1)).decode()
    legacy = f'-----BEGIN PUBLIC KEY-----\n{body}-----END PUBLIC KEY-----\n'
    with app.app_context():
        provider = HsmProvider(name='pkcs1-cache', type='pkcs11')
        provider.config = json.dumps({})
        db.session.add(provider)
        db.session.commit()
        key = HsmKey(provider_id=provider.id, key_identifier='ab01', label='pkcs1-cache',
                     algorithm='RSA-2048', key_type='rsa', purpose='signing',
                     public_key_pem=legacy)
        db.session.add(key)
        db.session.commit()
        try:
            pem = HsmService.get_public_key(key.id)
            assert serialization.load_pem_public_key(pem.encode()).public_numbers() == \
                public_key.public_numbers()
            db.session.commit()
            assert db.session.get(HsmKey, key.id).public_key_pem == pem
        finally:
            db.session.delete(db.session.get(HsmKey, key.id))
            db.session.delete(db.session.get(HsmProvider, provider.id))
            db.session.commit()
