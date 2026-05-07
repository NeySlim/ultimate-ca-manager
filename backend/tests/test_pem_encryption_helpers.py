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
  - ``migrations/029_encrypt_acme_account_keys.py``
    (latent: would crash on every DB upgrade with encryption enabled)
"""
from __future__ import annotations

import inspect
import os

import pytest


# ---------------------------------------------------------------------------
# Static guards — fast, no DB needed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module_path,must_use,must_not_use",
    [
        # ACME client service (latent #105-class bug)
        (
            "services.acme.acme_client_service",
            ["encrypt_text", "decrypt_text"],
            ["encrypt_private_key(", "decrypt_private_key("],
        ),
        # ACME server account creation (latent #105-class bug)
        (
            "api.v2.acme.accounts",
            ["encrypt_text"],
            ["encrypt_private_key("],
        ),
    ],
)
def test_module_uses_text_encryption_for_pem(module_path, must_use, must_not_use):
    import importlib
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)

    for needed in must_use:
        assert needed in src, (
            f"{module_path} must use security.encryption.{needed} for PEM at rest "
            f"(regression of #105-class bug)."
        )
    for forbidden in must_not_use:
        assert forbidden not in src, (
            f"{module_path} still uses {forbidden} on raw PEM. "
            f"That helper b64-decodes its input and crashes on PEM. "
            f"Use encrypt_text/decrypt_text instead."
        )


def test_migration_029_uses_text_encryption():
    """Migration 029 walks ACME PEM rows — must use the text helpers, otherwise
    the migration crashes on its own data when encryption is enabled."""
    import ast

    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "migrations",
        "029_encrypt_acme_account_keys.py",
    )
    src = open(path).read()
    tree = ast.parse(src)

    # Collect all imported names from security.encryption
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "security.encryption":
            for alias in node.names:
                imported.add(alias.asname or alias.name)

    assert "encrypt_text" in imported, (
        "Migration 029 must import encrypt_text from security.encryption"
    )
    assert "decrypt_text" in imported, (
        "Migration 029 must import decrypt_text from security.encryption"
    )
    assert "encrypt_private_key" not in imported, (
        "Migration 029 must NOT import encrypt_private_key (b64-decodes input, "
        "crashes on PEM)"
    )
    assert "decrypt_private_key" not in imported, (
        "Migration 029 must NOT import decrypt_private_key (wrong primitive for PEM)"
    )


# ---------------------------------------------------------------------------
# Behavioural — confirm the helpers really round-trip PEM
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def encryption_enabled():
    from cryptography.fernet import Fernet
    os.environ["KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    from security import encryption as enc_mod
    enc_mod.KeyEncryption().reload()
    assert enc_mod.KeyEncryption().is_enabled
    yield


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
