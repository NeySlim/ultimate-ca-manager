"""ACME client account: external key import (#277) and upstream deactivation (#278)."""
from unittest.mock import patch
from tests.acme_rows import delete_client_accounts

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec

from api.v2.acme_client.accounts import _validate_imported_account_key
from models import db, AcmeClientAccount


def _pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def fresh_account_table(app):
    with app.app_context():
        delete_client_accounts(AcmeClientAccount.query)
        db.session.commit()
        yield


# --- _validate_imported_account_key ------------------------------------------

class TestImportKeyValidation:
    def test_rsa_2048_maps_to_rs256(self):
        assert _validate_imported_account_key(_pem(rsa.generate_private_key(65537, 2048))) == 'RS256'

    def test_unsupported_key_type_rejected(self):
        # Only plain RSA/ECDSA keys expressible as JWS algs are accepted.
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        with pytest.raises(ValueError, match='Unsupported key type'):
            _validate_imported_account_key(_pem(Ed25519PrivateKey.generate()))

    def test_ec_p256_maps_to_es256(self):
        assert _validate_imported_account_key(_pem(ec.generate_private_key(ec.SECP256R1()))) == 'ES256'

    def test_ec_p384_maps_to_es384(self):
        assert _validate_imported_account_key(_pem(ec.generate_private_key(ec.SECP384R1()))) == 'ES384'

    def test_ec_secp521_is_rejected(self):
        with pytest.raises(ValueError):
            _validate_imported_account_key(_pem(ec.generate_private_key(ec.SECP521R1())))

    def test_rsa_too_small_rejected(self):
        with pytest.raises(ValueError, match='2048'):
            _validate_imported_account_key(_pem(rsa.generate_private_key(65537, 1024)))

    def test_garbage_rejected(self):
        with pytest.raises(ValueError):
            _validate_imported_account_key('not a key at all')


# --- POST create with account_key_pem (#277) ---------------------------------

class TestCreateWithImportedKey:
    def test_create_imports_key_and_derives_algorithm(self, auth_client, fresh_account_table, app):
        pem = _pem(ec.generate_private_key(ec.SECP256R1()))
        res = auth_client.post('/api/v2/acme/client/accounts', json={
            'directory_url': 'https://acme.example.com/directory',
            'label': 'Imported CA',
            'email': 'ops@example.com',
            'account_key_algorithm': 'RS256',  # ignored — key wins
            'account_key_pem': pem,
        })
        assert res.status_code == 201
        data = res.get_json()['data']
        assert data['account_key_algorithm'] == 'ES256'
        assert data['account_key_set'] is True
        with app.app_context():
            from security.encryption import decrypt_text, key_encryption
            acct = AcmeClientAccount.query.filter_by(label='Imported CA').one()
            stored = acct.account_key or ''
            if key_encryption.is_string_encrypted(stored):
                stored = decrypt_text(stored)
            assert 'PRIVATE KEY' in stored

    def test_create_rejects_invalid_key(self, auth_client, fresh_account_table):
        res = auth_client.post('/api/v2/acme/client/accounts', json={
            'directory_url': 'https://acme.example.com/directory',
            'label': 'Bad Key CA',
            'email': 'ops@example.com',
            'account_key_pem': 'junk',
        })
        assert res.status_code == 400

    def test_create_rejects_oversized_key_blob(self, auth_client, fresh_account_table):
        res = auth_client.post('/api/v2/acme/client/accounts', json={
            'directory_url': 'https://acme.example.com/directory',
            'label': 'Huge CA',
            'email': 'ops@example.com',
            'account_key_pem': 'x' * (64 * 1024 + 1),
        })
        assert res.status_code == 413


# --- legacy PEM container formats (#285) -------------------------------------

def _pem_traditional(key):
    """SEC1 for EC, PKCS#1 for RSA (TraditionalOpenSSL serialization)."""
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()


class TestLegacyPemContainers:
    """X9.62 / SEC1 and PKCS#1 wraps must be importable — the validator must not
    demand a PKCS8 BEGIN PRIVATE KEY envelope."""

    def test_x962_p256_map_to_es256(self):
        pem = _pem_traditional(ec.generate_private_key(ec.SECP256R1()))
        assert 'BEGIN EC PRIVATE KEY' in pem
        assert _validate_imported_account_key(pem) == 'ES256'

    def test_x962_p384_map_to_es384(self):
        pem = _pem_traditional(ec.generate_private_key(ec.SECP384R1()))
        assert _validate_imported_account_key(pem) == 'ES384'

    def test_pkcs1_rsa_map_to_rs256(self):
        pem = _pem_traditional(rsa.generate_private_key(65537, 2048))
        assert 'BEGIN RSA PRIVATE KEY' in pem
        assert _validate_imported_account_key(pem) == 'RS256'

    def test_x962_crlf_endings_accepted(self):
        pem = _pem_traditional(ec.generate_private_key(ec.SECP256R1())).replace('\n', '\r\n')
        assert _validate_imported_account_key(pem) == 'ES256'

    def test_create_imports_x962_key(self, auth_client, fresh_account_table, app):
        pem = _pem_traditional(ec.generate_private_key(ec.SECP256R1()))
        res = auth_client.post('/api/v2/acme/client/accounts', json={
            'directory_url': 'https://acme.example.com/directory',
            'label': 'X962 CA',
            'email': 'ops@example.com',
            'account_key_pem': pem,
        })
        assert res.status_code == 201, res.get_json()
        assert res.get_json()['data']['account_key_algorithm'] == 'ES256'


# --- POST deactivate (#278) ----------------------------------------------------

def _registered_account(app):
    with app.app_context():
        acct = AcmeClientAccount(
            directory_url='https://acme.example.com/directory',
            label='Registered CA',
            email='ops@example.com',
            account_url='https://acme.example.com/acct/1',
            account_key='ENC:fake',
            is_default=False,
        )
        db.session.add(acct)
        db.session.commit()
        return acct.id


class TestDeactivate:
    def test_deactivate_unregistered_is_400(self, auth_client, fresh_account_table, app):
        with app.app_context():
            acct = AcmeClientAccount(
                directory_url='https://acme.example.com/directory',
                label='NoReg', email='o@e.com',
            )
            db.session.add(acct)
            db.session.commit()
            acct_id = acct.id
        res = auth_client.post(f'/api/v2/acme/client/accounts/{acct_id}/deactivate')
        assert res.status_code == 400
        with app.app_context():
            assert AcmeClientAccount.query.get(acct_id) is not None

    def test_deactivate_success_removes_row(self, auth_client, fresh_account_table, app):
        acct_id = _registered_account(app)
        with patch('api.v2.acme_client.accounts.AcmeClientService') as svc_cls:
            svc_cls.return_value.deactivate_account.return_value = (True, 'Account deactivated')
            res = auth_client.post(f'/api/v2/acme/client/accounts/{acct_id}/deactivate')
        assert res.status_code == 200
        with app.app_context():
            assert AcmeClientAccount.query.get(acct_id) is None

    def test_deactivate_failure_keeps_row(self, auth_client, fresh_account_table, app):
        acct_id = _registered_account(app)
        with patch('api.v2.acme_client.accounts.AcmeClientService') as svc_cls:
            svc_cls.return_value.deactivate_account.return_value = (False, 'server said no')
            res = auth_client.post(f'/api/v2/acme/client/accounts/{acct_id}/deactivate')
        assert res.status_code == 502
        with app.app_context():
            assert AcmeClientAccount.query.get(acct_id) is not None

    def test_deactivate_missing_account_404(self, auth_client, fresh_account_table):
        assert auth_client.post('/api/v2/acme/client/accounts/4242/deactivate').status_code == 404


# --- service.deactivate_account payload ----------------------------------------

class TestServiceDeactivateAccount:
    def test_not_registered_short_circuits(self, app, fresh_account_table):
        from services.acme.acme_client_service import AcmeClientService
        with app.app_context():
            acct = AcmeClientAccount(
                directory_url='https://acme.example.com/directory',
                label='X', email='o@e.com',
            )
            svc = AcmeClientService(account=acct)
            ok, msg = svc.deactivate_account()
            assert ok is False
            assert 'not registered' in msg.lower()

    def test_posts_deactivated_status(self, app, fresh_account_table):
        from services.acme.acme_client_service import AcmeClientService
        calls = {}

        class _Resp:
            status_code = 200
            def json(self):
                return {'status': 'deactivated'}

        with app.app_context():
            acct = AcmeClientAccount(
                directory_url='https://acme.example.com/directory',
                label='X', email='o@e.com',
                account_url='https://acme.example.com/acct/9',
                account_key='ENC:fake',
            )
            svc = AcmeClientService(account=acct)

            def fake_post(url, payload, use_jwk=False):
                calls['url'] = url
                calls['payload'] = payload
                return _Resp()

            svc._post = fake_post
            ok, _ = svc.deactivate_account()
            assert ok is True
            assert calls['url'] == 'https://acme.example.com/acct/9'
            assert calls['payload'] == {'status': 'deactivated'}

    def test_acknowledge_with_wrong_status_fails(self, app, fresh_account_table):
        from services.acme.acme_client_service import AcmeClientService

        class _Resp:
            status_code = 200
            def json(self):
                return {'status': 'valid'}

        with app.app_context():
            acct = AcmeClientAccount(
                directory_url='https://acme.example.com/directory',
                label='X', email='o@e.com',
                account_url='https://acme.example.com/acct/9',
                account_key='ENC:fake',
            )
            svc = AcmeClientService(account=acct)
            svc._post = lambda *a, **k: _Resp()
            ok, msg = svc.deactivate_account()
            assert ok is False
            assert 'acknowledged' in msg
