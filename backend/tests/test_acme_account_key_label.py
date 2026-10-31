"""The account detail and list name the key the stored JWK actually holds."""
import base64
import json
import uuid

import pytest

from models import db, AcmeAccount

ACCOUNTS = '/api/v2/acme/accounts'


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _rsa_jwk(bits):
    # Top bit set so the modulus is exactly `bits` long
    n = (1 << (bits - 1)) | 1
    return {'kty': 'RSA', 'e': 'AQAB', 'n': _b64(n.to_bytes(bits // 8, 'big'))}


@pytest.fixture
def make_account(app):
    def make(jwk):
        with app.app_context():
            a = AcmeAccount(jwk=jwk if isinstance(jwk, str) else json.dumps(jwk),
                            jwk_thumbprint=f'label-{uuid.uuid4().hex[:12]}',
                            status='valid', contact=json.dumps([]))
            db.session.add(a)
            db.session.commit()
            return a.account_id
    return make


@pytest.mark.parametrize('jwk,label', [
    (_rsa_jwk(2048), 'RSA-2048'),
    (_rsa_jwk(3072), 'RSA-3072'),
    ({'kty': 'EC', 'crv': 'P-256', 'x': 'AA', 'y': 'AA'}, 'EC-P256'),
    ({'kty': 'EC', 'crv': 'P-521', 'x': 'AA', 'y': 'AA'}, 'EC-P521'),
    ({'kty': 'OKP', 'crv': 'Ed25519', 'x': 'AA'}, 'ED25519'),
])
def test_detail_and_list_name_the_stored_key(auth_client, make_account, jwk, label):
    account_id = make_account(jwk)

    detail = auth_client.get(f'{ACCOUNTS}/{account_id}').get_json()['data']
    assert detail['key_type'] == label

    listed = auth_client.get(ACCOUNTS).get_json()['data']
    assert next(a for a in listed if a['account_id'] == account_id)['key_type'] == label


@pytest.mark.parametrize('jwk', ['{}', 'not json', {'kty': 'EC', 'crv': 'P-999'},
                                 {'kty': 'RSA', 'n': '!!'}, {'kty': 'oct', 'k': 'AA'},
                                 {'kty': 'EC', 'crv': 'Ed25519', 'x': 'AA'},
                                 {'kty': 'OKP', 'crv': 'P-256', 'x': 'AA'},
                                 {'kty': 'EC', 'crv': 'RSA-2048'}, {'kty': 'OKP', 'crv': 'ML-DSA-65'}])
def test_unreadable_key_has_no_label(auth_client, make_account, jwk):
    account_id = make_account(jwk)

    detail = auth_client.get(f'{ACCOUNTS}/{account_id}').get_json()['data']
    assert detail['key_type'] is None


@pytest.mark.parametrize('key_type', ['RSA-2048', 'EC-P384'])
def test_created_account_reads_back_its_key_type(auth_client, key_type):
    r = auth_client.post(ACCOUNTS, json={
        'email': f'label-{key_type}@example.test', 'key_type': key_type, 'agree_tos': True})
    account_id = r.get_json()['data']['account_id']

    detail = auth_client.get(f'{ACCOUNTS}/{account_id}').get_json()['data']
    assert detail['key_type'] == key_type
