"""Tests for utils/key_codec.py — PEM load/store helpers."""
import base64
import os
import pytest

from utils.key_codec import load_pem_bytes, store_pem_bytes
from security.encryption import key_encryption


SAMPLE_PEM = b"""-----BEGIN PRIVATE KEY-----
MIICdwIBADANBgkqhkiG9w0BAQEFAASCAmEwggJdAgEAAoGBAL1+test+key+bytes+
-----END PRIVATE KEY-----
"""


@pytest.fixture
def encryption_disabled(monkeypatch):
    """Run with KEY_ENCRYPTION_KEY unset (no Fernet)."""
    monkeypatch.delenv('KEY_ENCRYPTION_KEY', raising=False)
    monkeypatch.delenv('KEY_ENCRYPTION_KEY_FILE', raising=False)
    key_encryption.reload()
    yield
    key_encryption.reload()


@pytest.fixture
def encryption_enabled(monkeypatch):
    """Run with a fresh KEY_ENCRYPTION_KEY env var."""
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode('ascii')
    monkeypatch.setenv('KEY_ENCRYPTION_KEY', key)
    monkeypatch.delenv('KEY_ENCRYPTION_KEY_FILE', raising=False)
    key_encryption.reload()
    yield key
    monkeypatch.delenv('KEY_ENCRYPTION_KEY', raising=False)
    key_encryption.reload()


class TestRoundTripDisabled:
    """Without encryption, store→load is base64 round-trip."""

    def test_round_trip_bytes(self, encryption_disabled):
        stored = store_pem_bytes(SAMPLE_PEM)
        loaded = load_pem_bytes(stored)
        assert loaded == SAMPLE_PEM

    def test_round_trip_via_str_b64(self, encryption_disabled):
        b64_str = base64.b64encode(SAMPLE_PEM).decode('ascii')
        stored = store_pem_bytes(b64_str)
        loaded = load_pem_bytes(stored)
        assert loaded == SAMPLE_PEM


class TestRoundTripEnabled:
    """With encryption, store→load survives the Fernet wrapping."""

    def test_round_trip_bytes_encrypted(self, encryption_enabled):
        stored = store_pem_bytes(SAMPLE_PEM)
        # Stored value MUST be encrypted (start with ENC: marker after b64-decode)
        decoded = base64.b64decode(stored)
        assert decoded.startswith(b'ENC:'), "Storage layer must encrypt when KEY_ENCRYPTION_KEY is set"
        # And load_pem_bytes transparently decrypts
        loaded = load_pem_bytes(stored)
        assert loaded == SAMPLE_PEM


class TestErrors:
    def test_empty_raises(self, encryption_disabled):
        with pytest.raises(ValueError, match="No private key stored"):
            load_pem_bytes(None, context="CA 42")
        with pytest.raises(ValueError, match="No private key stored"):
            load_pem_bytes("", context="CA 42")

    def test_malformed_raises_with_context(self, encryption_disabled):
        with pytest.raises(ValueError, match="CA 'Root'"):
            load_pem_bytes("not%%%base64%%%", context="CA 'Root'")

    def test_store_rejects_bad_type(self):
        with pytest.raises(TypeError, match="bytes or str"):
            store_pem_bytes(12345)


class TestEquivalenceWithLegacyPattern:
    """The helper must be a drop-in replacement for the inline pattern.

    Inline pattern (what we're replacing across 26 sites):
        base64.b64decode(decrypt_private_key(model.prv))
    """

    def test_matches_inline_pattern_disabled(self, encryption_disabled):
        from security.encryption import decrypt_private_key
        stored = store_pem_bytes(SAMPLE_PEM)
        # Inline
        inline = base64.b64decode(decrypt_private_key(stored))
        # Helper
        helper = load_pem_bytes(stored)
        assert inline == helper == SAMPLE_PEM

    def test_matches_inline_pattern_enabled(self, encryption_enabled):
        from security.encryption import decrypt_private_key
        stored = store_pem_bytes(SAMPLE_PEM)
        inline = base64.b64decode(decrypt_private_key(stored))
        helper = load_pem_bytes(stored)
        assert inline == helper == SAMPLE_PEM
