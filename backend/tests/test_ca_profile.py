"""Tests for CA profile helpers (RFC 5280 defaults)."""
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from utils.ca_profile import (
    default_digest_for_key_type,
    default_key_usage_for_ca,
    resolve_digest,
    validate_ca_key_usage,
    build_key_usage_extension,
    normalize_ca_eku,
)


class TestDefaultDigest:
    def test_p384_maps_sha384(self):
        assert default_digest_for_key_type('secp384r1') == 'sha384'

    def test_p256_maps_sha256(self):
        assert default_digest_for_key_type('prime256v1') == 'sha256'

    def test_resolve_auto(self):
        digest, err = resolve_digest('auto', 'secp384r1')
        assert err is None
        assert digest == 'sha384'

    def test_resolve_invalid(self):
        digest, err = resolve_digest('sha1', '2048')
        assert digest == ''
        assert err is not None


class TestKeyUsageDefaults:
    def test_root_default_no_digital_signature(self):
        ku = default_key_usage_for_ca(is_root=True)
        assert ku == ['keyCertSign', 'cRLSign']
        assert 'digitalSignature' not in ku

    def test_intermediate_default_includes_digital_signature(self):
        ku = default_key_usage_for_ca(is_root=False)
        assert 'digitalSignature' in ku
        assert 'keyCertSign' in ku
        assert 'cRLSign' in ku


class TestKeyUsageValidation:
    def test_rejects_missing_key_cert_sign(self):
        assert validate_ca_key_usage(['cRLSign']) is not None

    def test_rejects_leaf_ku(self):
        assert validate_ca_key_usage(['keyCertSign', 'keyEncipherment']) is not None

    def test_accepts_le_profile_root(self):
        assert validate_ca_key_usage(['keyCertSign', 'cRLSign']) is None


class TestEkuNormalization:
    def test_root_rejects_eku(self):
        oids, err = normalize_ca_eku(['serverAuth'], is_root=True)
        assert err is not None

    def test_intermediate_accepts_server_auth(self):
        oids, err = normalize_ca_eku(['serverAuth'], is_root=False)
        assert err is None
        assert oids == ['1.3.6.1.5.5.7.3.1']

    def test_none_uses_defaults_marker(self):
        oids, err = normalize_ca_eku(None, is_root=False)
        assert err is None
        assert oids is None


class TestBuildKeyUsage:
    def test_root_extension_flags(self):
        ku = build_key_usage_extension(['keyCertSign', 'cRLSign'])
        assert ku.key_cert_sign
        assert ku.crl_sign
        assert not ku.digital_signature
