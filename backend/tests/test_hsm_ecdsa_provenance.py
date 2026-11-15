"""A valid PKCS#11 signature can also be a canonical DER pair of other integers."""
import base64
import hashlib
from types import SimpleNamespace

import pytest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    Prehashed, decode_dss_signature, encode_dss_signature,
)

from models import db
from models.hsm import HsmKey
from services.hsm import HsmService
from services.hsm.openbao_provider import OpenBaoProvider
from services.hsm.pkcs11_provider import AwsCloudHsmProvider, Pkcs11Provider
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


def _azure(key, monkeypatch):
    import services.hsm.azure_provider as azure
    from azure.keyvault.keys import KeyType as AzureKeyType

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def sign(self, algorithm, digest):
            r, s = decode_dss_signature(key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256()))))
            return SimpleNamespace(signature=r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))  # JWS R || S
    monkeypatch.setattr(azure, 'CryptographyClient', _Client)
    provider = azure.AzureKeyVaultProvider.__new__(azure.AzureKeyVaultProvider)
    provider._key_client = SimpleNamespace(get_key=lambda name: SimpleNamespace(key_type=AzureKeyType.ec))
    provider._credential = None
    return provider


def _gcp(key, monkeypatch):
    from services.hsm.gcp_provider import GcpKmsProvider
    provider = GcpKmsProvider.__new__(GcpKmsProvider)
    provider._client = SimpleNamespace(
        get_crypto_key=lambda **kw: SimpleNamespace(primary=SimpleNamespace(name='v/1')),
        get_crypto_key_version=lambda **kw: SimpleNamespace(algorithm='EC_SIGN_P256_SHA256'),
        asymmetric_sign=lambda **kw: SimpleNamespace(signature=key.sign(  # DER
            kw['digest']['sha256'], ec.ECDSA(Prehashed(hashes.SHA256())))))
    return provider


def _openbao(key, monkeypatch):
    provider = OpenBaoProvider.__new__(OpenBaoProvider)

    def api(method, path, json=None):
        if method == 'GET':
            return {'data': {'type': 'ecdsa-p256'}}
        der = key.sign(base64.b64decode(json['input']), ec.ECDSA(hashes.SHA256()))  # asn1 marshaling
        return {'data': {'signature': 'vault:v1:' + base64.b64encode(der).decode()}}
    provider._api = api
    return provider


def _pkcs11(key, monkeypatch, cls=Pkcs11Provider):
    provider = cls.__new__(cls)
    private = _FakeObject({Attribute.CLASS: ObjectClass.PRIVATE_KEY,
                           Attribute.KEY_TYPE: KeyType.EC, Attribute.ID: b'\x01'})

    def sign(data, **kw):
        r, s = decode_dss_signature(key.sign(data, ec.ECDSA(hashes.SHA256())))
        return r.to_bytes(32, 'big') + s.to_bytes(32, 'big')  # PKCS#11 CKM_ECDSA_SHA256
    private.sign = sign
    provider._session = _FakeSession([private])
    provider._connected = True
    return provider


@pytest.mark.parametrize('build', [_azure, _gcp, _openbao, _pkcs11,
                                   lambda k, m: _pkcs11(k, m, AwsCloudHsmProvider)],
                         ids=['azure', 'gcp', 'openbao', 'pkcs11', 'aws-cloudhsm'])
def test_each_provider_declares_the_ecdsa_encoding_its_service_returns(app, monkeypatch, build):
    key = ec.generate_private_key(ec.SECP256R1())
    message = b'provider contract'
    provider = build(key, monkeypatch)
    monkeypatch.setattr(provider, 'connect', lambda: True, raising=False)
    monkeypatch.setattr(provider, 'disconnect', lambda: None, raising=False)
    monkeypatch.setattr(HsmService, '_get_provider_instance', lambda *a: provider)
    with _provider_with_keys(app, f'contract-{build.__name__}', ['01']) as (_, ids, _):
        with app.app_context():
            db.session.get(HsmKey, ids['01']).public_key_pem = pem(key.public_key())
            db.session.commit()
            signature = HsmService.sign(ids['01'], message, hash_algorithm='sha256')
    key.public_key().verify(signature, message, ec.ECDSA(hashes.SHA256()))
