"""
Regression test for #105 sub-bug: ``KeyEncryption.decrypt()`` must round-trip
PEM-formatted input that was never encrypted by us.

Before the fix, ``decrypt()`` called ``base64.b64decode(data)`` and the
resulting ``binascii.Error`` (or any exception) bubbled up. When the ACME
proxy account key migration was introduced (#105), every read of a
legacy plaintext-stored key crashed with ``binascii.Error: Invalid base64-encoded string``.

The fix splits the probe (``b64decode``) from the actual fernet decryption:
  - non-base64 input  → return as-is (passthrough)
  - base64 but no marker → return as-is (passthrough)
  - base64 + marker     → fernet decrypt; only fernet failures raise

This test covers both the static behaviour and the exact PEM case that
broke the ACME proxy decrypt path.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def keyenc():
    # Force encryption enabled with a deterministic key so encrypt+decrypt round-trip works.
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing")
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing")
    from cryptography.fernet import Fernet
    os.environ["KEY_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    from security import encryption as enc_mod
    # Singleton — reload to pick up the env var.
    inst = enc_mod.KeyEncryption()
    inst.reload()
    assert inst.is_enabled, "KeyEncryption did not initialise with KEY_ENCRYPTION_KEY"
    return inst


PEM_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj\n"
    "MzEfYyjiWA4R4/M2bS1GB4t7NXp98C3SC6dVMvDuictGeurT8jNbvJZHtCSuYEvu\n"
    "NMoSfm76oqFvAp8Gy0iz5sxjZmSnXyCdPEovGhLa0VzMaQ8s+CLOyS56YyCFGeJZ\n"
    "-----END PRIVATE KEY-----\n"
)

PEM_RSA_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIEogIBAAKCAQEAyzG8H7iKj9RZbb0p3mJp9WRG+MxGmGfJ8CYQnHUFYAFYQHwa\n"
    "-----END RSA PRIVATE KEY-----\n"
)


def test_decrypt_passthrough_pkcs8_pem(keyenc):
    """PKCS#8 PEM (legacy plaintext) must round-trip unchanged through decrypt()."""
    out = keyenc.decrypt(PEM_PRIVATE_KEY)
    assert out == PEM_PRIVATE_KEY, "PKCS#8 PEM should pass through decrypt() untouched"


def test_decrypt_passthrough_rsa_pem(keyenc):
    """Legacy 'RSA PRIVATE KEY' PEM block must also pass through cleanly."""
    out = keyenc.decrypt(PEM_RSA_PRIVATE_KEY)
    assert out == PEM_RSA_PRIVATE_KEY


def test_decrypt_passthrough_arbitrary_text(keyenc):
    """Any non-base64 string must pass through (defensive contract)."""
    text = "not base64 at all !!! @@@"
    assert keyenc.decrypt(text) == text


def test_decrypt_passthrough_empty(keyenc):
    """Empty/None must pass through."""
    assert keyenc.decrypt("") == ""
    assert keyenc.decrypt(None) is None


def test_decrypt_passthrough_base64_without_marker(keyenc):
    """Valid base64 that wasn't produced by us (no marker) must pass through unchanged.

    This is the second half of the probe contract: b64decode succeeds, but the
    decoded bytes don't start with ENCRYPTED_MARKER, so we must NOT attempt
    fernet decryption (which would raise) — just return the input.
    """
    import base64
    arbitrary = base64.b64encode(b"hello world").decode()
    assert keyenc.decrypt(arbitrary) == arbitrary


def test_encrypt_decrypt_round_trip(keyenc):
    """Sanity: encrypt(b64(x)) must decrypt back to b64(x).

    encrypt() expects base64-encoded input (raw bytes are b64-decoded inside);
    decrypt() returns base64-encoded plaintext bytes.
    """
    import base64
    raw = b"some_secret_payload_value"
    payload = base64.b64encode(raw).decode("ascii")
    encrypted = keyenc.encrypt(payload)
    assert encrypted != payload, "encrypt() should change the payload"
    decrypted = keyenc.decrypt(encrypted)
    assert base64.b64decode(decrypted) == raw


def test_decrypt_does_not_raise_binascii_on_pem(keyenc):
    """Direct guard against the #105 sub-bug: never raise binascii.Error on PEM input."""
    import binascii
    try:
        keyenc.decrypt(PEM_PRIVATE_KEY)
    except binascii.Error as exc:  # pragma: no cover -- regression
        pytest.fail(f"decrypt() raised binascii.Error on PEM input: {exc}")


def test_decrypt_private_key_helper_passes_pem_through():
    """Module-level decrypt_private_key() (used by ACME proxy) must also pass PEM through."""
    from security.encryption import decrypt_private_key
    assert decrypt_private_key(PEM_PRIVATE_KEY) == PEM_PRIVATE_KEY
