"""An ES256/384/512 JWS signature is R||S of the curve's exact length (RFC 7518 section 3.4), on the
curve its alg names; a DER signature or a key of another curve is refused (RFC 8555 section 6.2)."""
import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from tests.test_acme_security_paths import _nonce

PATH = '/acme/new-account'
CURVES = {'P-256': (ec.SECP256R1, 32), 'P-384': (ec.SECP384R1, 48), 'P-521': (ec.SECP521R1, 66)}
HASHES = {'ES256': hashes.SHA256, 'ES384': hashes.SHA384, 'ES512': hashes.SHA512}


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _new_account(client, alg, crv, form='raw'):
    curve, size = CURVES[crv]
    key = ec.generate_private_key(curve())
    nums = key.public_key().public_numbers()
    jwk = {'kty': 'EC', 'crv': crv, 'x': _b64(nums.x.to_bytes(size, 'big')),
           'y': _b64(nums.y.to_bytes(size, 'big'))}
    protected = _b64(json.dumps({'alg': alg, 'nonce': _nonce(client), 'jwk': jwk,
                                 'url': f'http://localhost{PATH}'}).encode())
    payload = _b64(json.dumps({'termsOfServiceAgreed': True}).encode())
    der = key.sign(f'{protected}.{payload}'.encode(), ec.ECDSA(HASHES[alg]()))
    if form == 'der':
        signature = der
    else:
        r, s = decode_dss_signature(der)
        signature = r.to_bytes(size, 'big') + s.to_bytes(size, 'big')
        if form == 'short':
            signature = signature[1:]
    jws = {'protected': protected, 'payload': payload, 'signature': _b64(signature)}
    return client.post(PATH, data=json.dumps(jws), content_type='application/jose+json')


@pytest.mark.parametrize('alg,crv', [('ES256', 'P-256'), ('ES384', 'P-384'), ('ES512', 'P-521')])
def test_a_raw_signature_on_the_named_curve_is_accepted(client, alg, crv):
    r = _new_account(client, alg, crv)
    assert r.status_code == 201, r.get_json()


@pytest.mark.parametrize('alg,crv', [('ES256', 'P-256'), ('ES384', 'P-384'), ('ES512', 'P-521')])
def test_a_der_signature_is_refused(client, alg, crv):
    r = _new_account(client, alg, crv, form='der')
    assert r.status_code == 400, r.get_json()


def test_a_signature_one_byte_short_is_refused(client):
    assert _new_account(client, 'ES256', 'P-256', form='short').status_code == 400


@pytest.mark.parametrize('alg,crv', [('ES256', 'P-384'), ('ES384', 'P-256'), ('ES512', 'P-384')])
def test_a_key_on_another_curve_than_the_alg_names_is_refused(client, alg, crv):
    r = _new_account(client, alg, crv)
    assert r.status_code == 400, r.get_json()
