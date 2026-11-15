"""A valid PKCS#11 signature can also be a canonical DER pair of other integers."""
import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from models import db
from models.hsm import HsmKey
from services.hsm import HsmService
from services.hsm.pkcs11_provider import Pkcs11Provider
from tests.test_hsm_key_material import pem
from tests.test_hsm_sync_and_listing import (
    Attribute, KeyType, ObjectClass, _FakeObject, _FakeSession, _provider_with_keys,
)

P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551


def _add(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x, y = a
    u, v = b
    if x == u and (y + v) % P == 0:
        return None
    slope = ((3 * x * x - 3) * pow(2 * y, -1, P) if a == b
             else (v - y) * pow(u - x, -1, P)) % P
    nx = (slope * slope - x - u) % P
    return nx, (slope * (x - nx) - y) % P


def _mul(n, point):
    result = None
    while n:
        if n & 1:
            result = _add(result, point)
        point = _add(point, point)
        n >>= 1
    return result


def ambiguous_valid_signature(message):
    # Recover Q = r^-1(sR - zG); the known r||s then verifies for Q and this message.
    for i in range(256):
        raw = encode_dss_signature(int.from_bytes(b'\x01' * 29, 'big') + (i << 8),
                                   int.from_bytes(b'\x02' * 29, 'big'))
        assert len(raw) == 64
        try:
            r_point = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b'\x02' + raw[:32])
            break
        except ValueError:
            continue
    else:
        raise AssertionError('No P-256 point found')
    r, s = int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')
    rn = r_point.public_numbers()
    z = int.from_bytes(hashlib.sha256(message).digest(), 'big')
    minus_z = ec.derive_private_key((-z * pow(r, -1, N)) % N, ec.SECP256R1()).public_key().public_numbers()
    x, y = _add(_mul((s * pow(r, -1, N)) % N, (rn.x, rn.y)), (minus_z.x, minus_z.y))
    public = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    expected = encode_dss_signature(r, s)
    public.verify(expected, message, ec.ECDSA(hashes.SHA256()))
    assert expected != raw
    return raw, expected, public


def test_ambiguous_signature_through_real_pkcs11_sign_path(app, monkeypatch):
    message = b'PKCS11 signature provenance regression'
    raw, expected, public = ambiguous_valid_signature(message)
    with _provider_with_keys(app, 'ambiguous', ['01']) as (_, ids, _):
        with app.app_context():
            db.session.get(HsmKey, ids['01']).public_key_pem = pem(public)
            db.session.commit()
            provider = Pkcs11Provider.__new__(Pkcs11Provider)
            private = _FakeObject({Attribute.CLASS: ObjectClass.PRIVATE_KEY,
                                   Attribute.KEY_TYPE: KeyType.EC, Attribute.ID: b'\x01'})
            private.sign = lambda data, **kw: raw
            provider._session = _FakeSession([private])
            provider._connected = True
            monkeypatch.setattr(provider, 'connect', lambda: True)
            monkeypatch.setattr(provider, 'disconnect', lambda: None)
            monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: provider)
            got = HsmService.sign(ids['01'], message, hash_algorithm='sha256')
            assert got == expected
            public.verify(got, message, ec.ECDSA(hashes.SHA256()))
