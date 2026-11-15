"""
Regression tests for #105-class bug: arbitrary-text PEM blobs stored in
``system_config`` MUST go through ``encrypt_text``/``decrypt_text``, NOT
through ``encrypt_private_key``/``decrypt_private_key``.

The latter pair is reserved for the ``CA.prv`` / ``Certificate.prv``
columns which already store base64-encoded DER payloads. Passing raw PEM
to ``encrypt_private_key`` triggers an internal ``base64.b64decode`` on
the PEM header (``-----BEGIN PRIVATE KEY-----``) and crashes with
``Incorrect padding`` whenever encryption is enabled.

Affected sites (originally only #105 was patched, this test also guards):

  - ``services/acme/acme_proxy_service.py`` (#105)
  - ``services/acme/acme_client_service.py`` (latent: ACME client account key)
  - ``api/v2/acme/accounts.py``              (latent: server-side ACME account key)
"""
from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# Behavioural — confirm the helpers really round-trip PEM
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def encryption_enabled(tmp_path_factory):
    from cryptography.fernet import Fernet
    from security import encryption as enc_mod

    patch = pytest.MonkeyPatch()
    patch.setattr(
        enc_mod,
        "MASTER_KEY_PATH",
        tmp_path_factory.mktemp("pem-encryption") / "master.key",
    )
    patch.setenv("KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc_mod.KeyEncryption().reload()
    assert enc_mod.KeyEncryption().is_enabled
    yield
    patch.undo()
    enc_mod.KeyEncryption().reload()


def test_encrypt_text_round_trips_pem(encryption_enabled):
    from security.encryption import encrypt_text, decrypt_text

    pem = (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDc...\n"
        "-----END PRIVATE KEY-----\n"
    )

    encrypted = encrypt_text(pem)
    assert encrypted != pem, "encrypt_text must transform the input"
    assert "-----BEGIN" not in encrypted, "encrypted blob must not contain raw PEM headers"

    assert decrypt_text(encrypted) == pem, "round-trip must return the exact PEM"


def test_decrypt_text_passes_legacy_plaintext_through(encryption_enabled):
    """Backward compat: rows written before encryption was enabled (raw PEM)
    must still load without errors."""
    from security.encryption import decrypt_text

    pem = "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n"
    assert decrypt_text(pem) == pem


def test_encrypt_text_is_noop_when_encryption_disabled(monkeypatch, tmp_path):
    """When KeyEncryption isn't enabled, encrypt_text must not transform input
    (so existing installs without master.key keep working)."""
    from security import encryption as enc_mod
    monkeypatch.delenv("KEY_ENCRYPTION_KEY", raising=False)
    # Point MASTER_KEY_PATH to a nonexistent file so _initialize() falls through
    monkeypatch.setattr(enc_mod, "MASTER_KEY_PATH", tmp_path / "nope.key")
    # Force a reload with no key material
    enc_mod.KeyEncryption().reload()
    assert not enc_mod.KeyEncryption().is_enabled

    pem = "-----BEGIN PRIVATE KEY-----\nXYZ\n-----END PRIVATE KEY-----\n"
    assert enc_mod.encrypt_text(pem) == pem
    assert enc_mod.decrypt_text(pem) == pem


def test_acme_server_account_key_is_stored_encrypted(app, auth_client, encryption_enabled):
    """Created through the route, the account key is encrypt_text output and reads back.

    The ACME client account key goes through the same helper: see
    test_acme_proxy_key_encrypted.test_proxy_account_key_encrypted_at_rest.
    """
    import json
    import uuid

    from cryptography.hazmat.primitives import serialization

    from api.v2.acme.accounts import _public_jwk
    from models import AcmeAccount, SystemConfig, db
    from security.encryption import decrypt_text

    from security import encryption as enc_mod
    # The no-op test above reloads without a key: load this module's one again
    enc_mod.KeyEncryption().reload()
    assert enc_mod.KeyEncryption().is_enabled

    email = f'pem-{uuid.uuid4().hex[:8]}@example.test'
    r = auth_client.post('/api/v2/acme/accounts', json={'email': email, 'agree_tos': True})
    assert r.status_code == 200, r.data
    account_id = r.get_json()['data']['account_id']
    key = f'acme.account.{account_id}.private_key'
    try:
        with app.app_context():
            stored = SystemConfig.query.filter_by(key=key).one().value
            jwk = json.loads(AcmeAccount.query.filter_by(account_id=account_id).one().jwk)
        assert '-----BEGIN' not in stored, 'the account key is stored in clear'
        private = serialization.load_pem_private_key(decrypt_text(stored).encode(), None)
        # The stored key is the one the account's JWK publishes
        assert _public_jwk(private) == jwk
    finally:
        # Encrypted under a key this module discards: nothing may outlive it
        with app.app_context():
            SystemConfig.query.filter_by(key=key).delete()
            AcmeAccount.query.filter_by(account_id=account_id).delete()
            db.session.commit()
