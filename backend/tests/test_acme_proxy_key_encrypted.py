"""
Regression test for #105: ACME proxy upstream account private key MUST be
encrypted at rest on the linked ``AcmeClientAccount`` row.

The proxy now delegates key load/generate to ``AcmeClientService`` (same path
as the ACME client). Keys live on ``acme_client_accounts.account_key``, not
legacy ``system_config`` proxy keys.
"""
from __future__ import annotations

import inspect

import pytest


def test_load_or_create_account_key_delegates_to_client_service():
    """Proxy key load must go through AcmeClientService on the linked account."""
    from services.acme.acme_client_service import AcmeClientService
    from services.acme.acme_proxy_service import AcmeProxyService

    src = inspect.getsource(AcmeProxyService._load_or_create_account_key)
    assert "AcmeClientService" in src
    assert "_get_account_key" in src

    client_src = inspect.getsource(AcmeClientService._get_account_key)
    assert "encrypt_text(" in client_src
    assert "decrypt_text(" in client_src


@pytest.fixture
def encryption_enabled(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    from security import encryption as enc_mod
    enc_mod.KeyEncryption().reload()
    assert enc_mod.KeyEncryption().is_enabled
    yield


def test_proxy_account_key_encrypted_at_rest(app, encryption_enabled):
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

    from models import db, AcmeClientAccount, SystemConfig
    from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY
    from services.acme.acme_proxy_service import AcmeProxyService

    with app.app_context():
        AcmeClientAccount.query.delete()
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        db.session.commit()

        acct = AcmeClientAccount(
            directory_url='https://proxy-encrypt-test.example/directory',
            label='Staging',
            email='ops@example.com',
        )
        db.session.add(acct)
        db.session.commit()

        db.session.add(SystemConfig(
            key=PROXY_ACCOUNT_ID_KEY,
            value=str(acct.id),
            description='test',
        ))
        db.session.commit()

        svc = AcmeProxyService(base_url='https://test.invalid')
        priv, _jwk = svc._load_or_create_account_key()
        assert isinstance(priv, (RSAPrivateKey, EllipticCurvePrivateKey))

        db.session.refresh(acct)
        stored = acct.account_key
        assert stored
        assert '-----BEGIN' not in stored

        priv2, _jwk2 = svc._load_or_create_account_key()
        assert isinstance(priv2, (RSAPrivateKey, EllipticCurvePrivateKey))
        if isinstance(priv, RSAPrivateKey) and isinstance(priv2, RSAPrivateKey):
            assert priv.private_numbers().public_numbers.n == priv2.private_numbers().public_numbers.n

        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        db.session.commit()


def test_acme_client_eab_hmac_encrypted_at_rest(app, encryption_enabled):
    from sqlalchemy import text
    from models import db, AcmeClientAccount
    from security.encryption import key_encryption

    plaintext = 'test-eab-hmac-key-base64url'
    with app.app_context():
        acct = AcmeClientAccount(
            directory_url='https://eab-encrypt-test.example/directory',
            label='EAB encryption test',
            email='ops@example.com',
            eab_kid='kid-test',
            eab_hmac_key=plaintext,
        )
        db.session.add(acct)
        db.session.commit()

        raw = db.session.execute(
            text('SELECT eab_hmac_key FROM acme_client_accounts WHERE id = :id'),
            {'id': acct.id},
        ).scalar_one()
        assert raw != plaintext
        assert key_encryption.is_string_encrypted(raw)
        assert acct.eab_hmac_key == plaintext


def test_acme_client_eab_legacy_plaintext_still_loads(app, encryption_enabled):
    from sqlalchemy import text
    from models import db, AcmeClientAccount

    plaintext = 'legacy-eab-hmac-key'
    with app.app_context():
        acct = AcmeClientAccount(
            directory_url='https://eab-legacy-test.example/directory',
            label='Legacy EAB test',
            email='ops@example.com',
        )
        db.session.add(acct)
        db.session.flush()
        db.session.execute(
            text('UPDATE acme_client_accounts SET eab_hmac_key = :value WHERE id = :id'),
            {'value': plaintext, 'id': acct.id},
        )
        db.session.commit()
        db.session.expire_all()

        reloaded = db.session.get(AcmeClientAccount, acct.id)
        assert reloaded.eab_hmac_key == plaintext


def test_legacy_system_config_eab_hmac_encrypted_at_rest(
    app, auth_client, encryption_enabled
):
    from models import SystemConfig, db
    from security.encryption import key_encryption

    r = auth_client.patch('/api/v2/acme/client/settings', json={
        'eab_hmac_key': 'client-system-config-secret',
        'proxy_eab_hmac_key': 'proxy-system-config-secret',
    })
    assert r.status_code == 200

    with app.app_context():
        client_raw = SystemConfig.query.filter_by(
            key='acme.client.eab_hmac_key'
        ).one().value
        proxy_raw = SystemConfig.query.filter_by(
            key='acme.proxy.eab_hmac_key'
        ).one().value
        assert key_encryption.is_string_encrypted(client_raw)
        assert key_encryption.is_string_encrypted(proxy_raw)


def test_proxy_account_key_legacy_plaintext_still_loads(app, encryption_enabled):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from cryptography.hazmat.backends import default_backend

    from models import db, AcmeClientAccount, SystemConfig
    from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY
    from services.acme.acme_proxy_service import AcmeProxyService

    with app.app_context():
        AcmeClientAccount.query.filter_by(
            directory_url='https://proxy-plaintext-test.example/directory'
        ).delete()
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        db.session.commit()

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        plaintext_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        acct = AcmeClientAccount(
            directory_url='https://proxy-plaintext-test.example/directory',
            label='Staging',
            email='ops@example.com',
            account_key=plaintext_pem,
            account_key_algorithm='RS256',
        )
        db.session.add(acct)
        db.session.commit()

        db.session.add(SystemConfig(
            key=PROXY_ACCOUNT_ID_KEY,
            value=str(acct.id),
            description='test',
        ))
        db.session.commit()

        svc = AcmeProxyService(base_url='https://test.invalid')
        priv2, _jwk = svc._load_or_create_account_key()
        assert isinstance(priv2, RSAPrivateKey)
        assert priv.private_numbers().public_numbers.n == priv2.private_numbers().public_numbers.n

        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        db.session.commit()
