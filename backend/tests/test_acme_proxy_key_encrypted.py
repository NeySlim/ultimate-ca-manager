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
