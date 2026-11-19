"""A CA account refuses what it cannot apply: no un-defaulting, no new algorithm on an existing key."""
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import db, AcmeClientAccount
from tests.seeded_rows import delete_client_accounts

URL = '/api/v2/acme/client/accounts'


@pytest.fixture
def accounts(app, auth_client):
    made = []

    def make(**extra):
        body = {'directory_url': 'https://rep24b.example/directory',
                'label': f'rep24b-{uuid.uuid4().hex[:8]}', 'email': 'ops@example.com', **extra}
        r = auth_client.post(URL, json=body)
        assert r.status_code == 201, r.data[:300]
        made.append(r.get_json()['data']['id'])
        return r.get_json()['data']
    yield make
    with app.app_context():
        delete_client_accounts(AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(made)))
        db.session.commit()


def _pem(curve):
    key = ec.generate_private_key(curve)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def test_unticking_the_default_account_is_refused(auth_client, accounts):
    a = accounts(is_default=True)
    accounts()
    r = auth_client.patch(f'{URL}/{a["id"]}', json={'is_default': False})
    assert r.status_code == 400
    assert 'is_default' in r.get_json()['message']
    assert auth_client.get(f'{URL}/{a["id"]}').get_json()['data']['is_default'] is True


def test_is_default_false_on_a_non_default_account_is_accepted(auth_client, accounts):
    accounts(is_default=True)
    b = accounts()
    r = auth_client.patch(f'{URL}/{b["id"]}', json={'is_default': False, 'email': 'new@example.com'})
    assert r.status_code == 200, r.data[:300]
    assert r.get_json()['data']['email'] == 'new@example.com'


def test_a_different_algorithm_than_the_existing_key_is_refused(auth_client, accounts):
    a = accounts(account_key_pem=_pem(ec.SECP256R1()))
    r = auth_client.patch(f'{URL}/{a["id"]}', json={'account_key_algorithm': 'ES384'})
    assert r.status_code == 400
    assert 'account_key_algorithm' in r.get_json()['message']
    assert auth_client.get(f'{URL}/{a["id"]}').get_json()['data']['account_key_algorithm'] == 'ES256'


def test_the_algorithm_of_the_existing_key_is_accepted(auth_client, accounts):
    a = accounts(account_key_pem=_pem(ec.SECP384R1()))
    r = auth_client.patch(f'{URL}/{a["id"]}', json={'account_key_algorithm': 'ES384', 'label': a['label'] + 'x'})
    assert r.status_code == 200, r.data[:300]


def test_the_algorithm_changes_while_no_key_exists(auth_client, accounts):
    a = accounts()
    r = auth_client.patch(f'{URL}/{a["id"]}', json={'account_key_algorithm': 'RS256'})
    assert r.status_code == 200, r.data[:300]
    assert r.get_json()['data']['account_key_algorithm'] == 'RS256'
