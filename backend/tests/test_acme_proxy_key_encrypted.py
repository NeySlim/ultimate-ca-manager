"""
Regression test for #105: ACME proxy account private key MUST be encrypted
at rest in `system_config`.

Bug: ``AcmeProxyService._load_or_create_account_key()`` previously stored
the freshly-generated PEM key as plaintext. Anyone with read access to
``system_config`` (DB dumps, backups, postgres replicas) could exfiltrate
the key.

Fix:
  - On generate → store ``encrypt_private_key(pem)`` in ``system_config``.
  - On read    → ``decrypt_private_key(value)`` before parsing PEM.
  - Existing plaintext rows transparently round-trip because
    ``decrypt_private_key`` is a no-op on non-encrypted input
    (see ``test_key_encryption_pem_passthrough.py``).

This test guards by:
  1. Static check: source of ``_load_or_create_account_key`` must call
     ``encrypt_private_key`` on the write path and ``decrypt_private_key``
     on the read path.
  2. Behavioural: with encryption enabled, after ``_load_or_create_account_key``
     runs, the row stored in ``system_config`` must NOT be a raw PEM block
     (it must be encrypted), but the loaded key MUST still be a usable
     RSA private key (round-trip works).
  3. Backward compat: if a row already exists in plaintext PEM (legacy
     install), the loader must accept it without crashing.
"""
from __future__ import annotations

import inspect
import os

import pytest


# ---------------------------------------------------------------------------
# Static guard
# ---------------------------------------------------------------------------

def test_load_or_create_account_key_uses_encryption_helpers():
    """Source must call encrypt_text (write) and decrypt_text (read)."""
    from services.acme.acme_proxy_service import AcmeProxyService

    src = inspect.getsource(AcmeProxyService._load_or_create_account_key)

    assert "encrypt_text(" in src, (
        "ACME proxy must encrypt the account key before persisting "
        "(regression of #105). Use security.encryption.encrypt_text — "
        "encrypt_private_key expects base64 input and is unsafe for PEM."
    )
    assert "decrypt_text(" in src, (
        "ACME proxy must decrypt the persisted key before loading "
        "(regression of #105)."
    )
    assert "encrypt_private_key(" not in src, (
        "Do not use encrypt_private_key for raw PEM — it b64-decodes input "
        "and crashes on PEM blobs. Use encrypt_text instead."
    )


def test_acme_proxy_imports_encryption_helpers():
    """The encryption helpers must actually be imported at module top
    (catches partial reverts where the call site is gone but the import
    remains, or vice versa)."""
    import services.acme.acme_proxy_service as mod

    assert hasattr(mod, "encrypt_text"), "encrypt_text not imported in acme_proxy_service"
    assert hasattr(mod, "decrypt_text"), "decrypt_text not imported in acme_proxy_service"


# ---------------------------------------------------------------------------
# Behavioural — needs the app+DB
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def encryption_enabled():
    """Enable KeyEncryption with a deterministic Fernet key for this test module."""
    from cryptography.fernet import Fernet
    os.environ["KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    from security import encryption as enc_mod
    enc_mod.KeyEncryption().reload()
    assert enc_mod.KeyEncryption().is_enabled
    yield


def test_account_key_encrypted_at_rest(app, encryption_enabled):
    """End-to-end: generated account key must be stored encrypted, but loadable."""
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

    from models import db, SystemConfig
    from services.acme.acme_proxy_service import AcmeProxyService

    with app.app_context():
        # Clean slate
        SystemConfig.query.filter_by(key='acme.proxy.account_key').delete()
        db.session.commit()

        # Trigger generate-and-store path
        svc = AcmeProxyService(base_url="https://test.invalid")
        priv, _jwk = svc._load_or_create_account_key()
        assert isinstance(priv, RSAPrivateKey), "loader must return an RSA private key"

        # Inspect what landed in the DB
        row = SystemConfig.query.filter_by(key='acme.proxy.account_key').first()
        assert row is not None, "account key row was not persisted"
        stored = row.value
        assert stored, "account key row is empty"

        # Regression #105: stored value must NOT be raw PEM text.
        assert "-----BEGIN" not in stored, (
            "ACME proxy account key was stored in plaintext PEM — "
            "regression of #105. It must be encrypted at rest."
        )

        # And it must be decryptable + parseable on the next read.
        priv2, _jwk2 = svc._load_or_create_account_key()
        assert isinstance(priv2, RSAPrivateKey)
        # Same key: same modulus
        assert priv.private_numbers().public_numbers.n == priv2.private_numbers().public_numbers.n


def test_account_key_legacy_plaintext_still_loads(app, encryption_enabled):
    """Backward-compat: a row written in plaintext before #105 must still load."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
    from cryptography.hazmat.backends import default_backend

    from models import db, SystemConfig
    from services.acme.acme_proxy_service import AcmeProxyService

    with app.app_context():
        # Manually plant a plaintext PEM row, simulating a pre-#105 install.
        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        plaintext_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        SystemConfig.query.filter_by(key='acme.proxy.account_key').delete()
        db.session.add(SystemConfig(
            key='acme.proxy.account_key',
            value=plaintext_pem,
            description="legacy plaintext key (test fixture)",
        ))
        db.session.commit()

        # Loader must accept it without crashing (this is the #105 sub-bug
        # in KeyEncryption.decrypt() rearing its head).
        svc = AcmeProxyService(base_url="https://test.invalid")
        priv2, _jwk = svc._load_or_create_account_key()
        assert isinstance(priv2, RSAPrivateKey)
        assert priv.private_numbers().public_numbers.n == priv2.private_numbers().public_numbers.n
