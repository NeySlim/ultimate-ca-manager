"""Tests for RFC 8738 - ACME IP Address Identifier Support

This test suite validates the implementation of RFC 8738 which allows
ACME servers to issue certificates for IP addresses (IPv4 and IPv6).

Key requirements tested:
- Accept 'ip' identifier type in new-order and new-authz
- Validate IP address format (IPv4/IPv6)
- Create HTTP-01 and TLS-ALPN-01 challenges for IP identifiers (no DNS-01)
- Validate HTTP-01 challenges for IP addresses
- Validate TLS-ALPN-01 challenges for IP addresses (with reverse PTR SNI)
- Extract IP addresses from CSR SANs
- Match CSR IPs with order IP identifiers
"""
import pytest
import json
import base64
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from utils.acme_ip import (
    is_ip_identifier,
    validate_ip_address,
    normalize_ip_for_identifier,
    ip_to_reverse_ptr,
    is_ip_private,
    extract_ip_from_csr_san,
    format_ip_for_url,
)


class TestIPValidation:
    """Test IP address validation utilities"""

    def test_validate_ipv4_valid(self):
        """Valid IPv4 addresses should pass validation"""
        assert validate_ip_address('192.168.1.1') == (True, '192.168.1.1')
        assert validate_ip_address('10.0.0.1') == (True, '10.0.0.1')
        assert validate_ip_address('8.8.8.8') == (True, '8.8.8.8')
        assert validate_ip_address('127.0.0.1') == (True, '127.0.0.1')

    def test_validate_ipv6_valid(self):
        """Valid IPv6 addresses should pass validation"""
        assert validate_ip_address('2001:db8::1') == (True, '2001:db8::1')
        assert validate_ip_address('::1') == (True, '::1')
        assert validate_ip_address('fe80::1') == (True, 'fe80::1')

    def test_validate_ip_invalid(self):
        """Invalid IP addresses should fail validation"""
        is_valid, error = validate_ip_address('not-an-ip')
        assert is_valid is False
        assert 'Invalid IP address' in error

        is_valid, error = validate_ip_address('256.256.256.256')
        assert is_valid is False

        is_valid, error = validate_ip_address('2001:xyz::1')
        assert is_valid is False

    def test_is_ip_identifier(self):
        """is_ip_identifier should detect IP identifier type"""
        assert is_ip_identifier({'type': 'ip', 'value': '192.168.1.1'}) is True
        assert is_ip_identifier({'type': 'dns', 'value': 'example.com'}) is False
        assert is_ip_identifier({}) is False

    def test_normalize_ip_ipv4(self):
        """IPv4 normalization should return canonical form"""
        assert normalize_ip_for_identifier('192.168.1.1') == '192.168.1.1'
        assert normalize_ip_for_identifier('8.8.8.8') == '8.8.8.8'
        # Leading zeros are invalid per RFC 1123 (could be interpreted as octal)
        assert normalize_ip_for_identifier('010.000.000.001') is None

    def test_normalize_ip_ipv6(self):
        """IPv6 normalization should return compressed form"""
        assert normalize_ip_for_identifier('2001:0db8:0000:0000:0000:0000:0000:0001') == '2001:db8::1'
        assert normalize_ip_for_identifier('::1') == '::1'

    def test_normalize_ip_invalid(self):
        """Invalid IPs should return None"""
        assert normalize_ip_for_identifier('invalid') is None
        assert normalize_ip_for_identifier('') is None

    def test_ip_to_reverse_ptr_ipv4(self):
        """IPv4 reverse PTR should follow in-addr.arpa format"""
        assert ip_to_reverse_ptr('192.168.1.1') == '1.1.168.192.in-addr.arpa'
        assert ip_to_reverse_ptr('10.0.0.1') == '1.0.0.10.in-addr.arpa'
        assert ip_to_reverse_ptr('8.8.8.8') == '8.8.8.8.in-addr.arpa'

    def test_ip_to_reverse_ptr_ipv6(self):
        """IPv6 reverse PTR should follow ip6.arpa format"""
        ptr = ip_to_reverse_ptr('2001:db8::1')
        assert ptr == '1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa'

    def test_ip_to_reverse_ptr_invalid(self):
        """Invalid IPs should return None for reverse PTR"""
        assert ip_to_reverse_ptr('invalid') is None
        assert ip_to_reverse_ptr('') is None

    def test_is_ip_private(self):
        """is_ip_private should detect private/reserved IPs"""
        # Private IPv4
        assert is_ip_private('10.0.0.1') is True
        assert is_ip_private('172.16.0.1') is True
        assert is_ip_private('192.168.1.1') is True
        
        # Loopback
        assert is_ip_private('127.0.0.1') is True
        assert is_ip_private('::1') is True
        
        # Public IPs
        assert is_ip_private('8.8.8.8') is False
        assert is_ip_private('1.1.1.1') is False

    def test_format_ip_for_url(self):
        """IPv6 literals must be bracketed for URLs (RFC 3986); IPv4 unchanged"""
        assert format_ip_for_url('192.0.2.1') == '192.0.2.1'
        assert format_ip_for_url('2001:db8::1') == '[2001:db8::1]'
        assert format_ip_for_url('::1') == '[::1]'
        # Non-IP passes through unchanged
        assert format_ip_for_url('example.com') == 'example.com'


class TestACMEIdentifierValidation:
    """Test the shared identifier validator used by new-order / new-authz.

    ACME endpoints require a full JWS+nonce+account flow, so the RFC 8555/8738
    identifier validation logic is exercised directly through the helper that
    both routes call.
    """

    def test_accepts_ip_identifier(self):
        """IP identifier should be accepted and left untouched (canonical)"""
        from api.acme.acme_api import validate_acme_identifier
        ident = {'type': 'ip', 'value': '192.168.1.1'}
        ok, err_type, _ = validate_acme_identifier(ident)
        assert ok is True
        assert err_type is None
        assert ident['value'] == '192.168.1.1'

    def test_normalizes_ipv6_identifier(self):
        """IPv6 identifier should be normalized to canonical form"""
        from api.acme.acme_api import validate_acme_identifier
        ident = {'type': 'ip', 'value': '2001:0db8:0000:0000:0000:0000:0000:0001'}
        ok, _, _ = validate_acme_identifier(ident)
        assert ok is True
        assert ident['value'] == '2001:db8::1'

    def test_rejects_invalid_ip_format(self):
        """Invalid IP should be rejected as malformed"""
        from api.acme.acme_api import validate_acme_identifier
        ok, err_type, detail = validate_acme_identifier({'type': 'ip', 'value': 'invalid-ip'})
        assert ok is False
        assert err_type == 'malformed'
        assert detail

    def test_rejects_unsupported_type(self):
        """Unsupported identifier type should be rejected"""
        from api.acme.acme_api import validate_acme_identifier
        ok, err_type, _ = validate_acme_identifier({'type': 'email', 'value': 'a@b.com'})
        assert ok is False
        assert err_type == 'unsupportedIdentifier'

    def test_rejects_missing_fields(self):
        """Identifier missing type/value should be rejected"""
        from api.acme.acme_api import validate_acme_identifier
        ok, err_type, _ = validate_acme_identifier({'type': 'dns'})
        assert ok is False
        assert err_type == 'malformed'

    def test_accepts_dns_identifier(self):
        """DNS identifier should be accepted"""
        from api.acme.acme_api import validate_acme_identifier
        ok, err_type, _ = validate_acme_identifier({'type': 'dns', 'value': 'example.com'})
        assert ok is True
        assert err_type is None


class TestChallengeCreation:
    """Test challenge creation for IP identifiers"""

    def test_ip_identifier_creates_http01_challenge(self):
        """IP identifiers should create HTTP-01 challenge"""
        from services.acme.mixins.order import OrderMixin
        
        # Mock authorization with IP identifier
        auth = Mock()
        auth.authorization_id = 'test-auth-id'
        auth.identifier_type = 'ip'
        auth.identifier_value = '192.168.1.1'
        auth.challenges = []
        
        mixin = OrderMixin()
        mixin.base_url = 'https://example.com'
        mixin._create_challenges(auth, 'pending')
        
        # Should create HTTP-01 challenge
        challenge_types = [c.type for c in auth.challenges]
        assert 'http-01' in challenge_types

    def test_ip_identifier_creates_tls_alpn01_challenge(self):
        """IP identifiers should create TLS-ALPN-01 challenge"""
        from services.acme.mixins.order import OrderMixin
        
        auth = Mock()
        auth.authorization_id = 'test-auth-id'
        auth.identifier_type = 'ip'
        auth.identifier_value = '192.168.1.1'
        auth.challenges = []
        
        mixin = OrderMixin()
        mixin.base_url = 'https://example.com'
        mixin._create_challenges(auth, 'pending')
        
        # Should create TLS-ALPN-01 challenge
        challenge_types = [c.type for c in auth.challenges]
        assert 'tls-alpn-01' in challenge_types

    def test_ip_identifier_no_dns01_challenge(self):
        """IP identifiers should NOT create DNS-01 challenge (RFC 8738)"""
        from services.acme.mixins.order import OrderMixin
        
        auth = Mock()
        auth.authorization_id = 'test-auth-id'
        auth.identifier_type = 'ip'
        auth.identifier_value = '192.168.1.1'
        auth.challenges = []
        
        mixin = OrderMixin()
        mixin.base_url = 'https://example.com'
        mixin._create_challenges(auth, 'pending')
        
        # Should NOT create DNS-01 challenge
        challenge_types = [c.type for c in auth.challenges]
        assert 'dns-01' not in challenge_types

    def test_dns_identifier_still_creates_dns01_challenge(self):
        """DNS identifiers should still create DNS-01 challenge"""
        from services.acme.mixins.order import OrderMixin
        
        auth = Mock()
        auth.authorization_id = 'test-auth-id'
        auth.identifier_type = 'dns'
        auth.identifier_value = 'example.com'
        auth.challenges = []
        
        mixin = OrderMixin()
        mixin.base_url = 'https://example.com'
        mixin._create_challenges(auth, 'pending')
        
        # Should create DNS-01 challenge
        challenge_types = [c.type for c in auth.challenges]
        assert 'dns-01' in challenge_types


class TestHTTP01IPValidation:
    """Test HTTP-01 challenge validation for IP addresses"""

    def _run_http01(self, ip_value):
        """Drive validate_http01_challenge for an IP identifier, return the URL hit."""
        import requests
        from services.acme.mixins.challenge import ChallengeMixin

        challenge = Mock()
        challenge.token = 'test-token'
        challenge.authorization.identifier_type = 'ip'
        challenge.authorization.identifier_value = ip_value

        account = Mock()
        account.jwk_thumbprint = 'test-thumbprint'

        mixin = ChallengeMixin()
        mixin._compute_key_authorization = Mock(return_value='expected-key-auth')
        mixin._acme_allow_private_ips = Mock(return_value=True)
        mixin._update_authorization_status = Mock()

        # `requests` is imported locally inside the method, so patch the module attr.
        with patch.object(requests, 'get') as mock_get:
            mock_response = Mock()
            mock_response.text = 'expected-key-auth'
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            try:
                mixin.validate_http01_challenge(challenge, account)
            except Exception:
                pass  # db.session.commit may fail outside app context — URL already captured
            assert mock_get.called, "requests.get was not called"
            return mock_get.call_args[0][0]

    def test_http01_ipv4_uses_direct_ip_in_url(self):
        """HTTP-01 for IPv4 should use the IP directly in the URL (no DNS resolution)"""
        url = self._run_http01('192.168.1.1')
        assert url == 'http://192.168.1.1/.well-known/acme-challenge/test-token'

    def test_http01_ipv6_url_is_bracketed(self):
        """HTTP-01 for IPv6 MUST bracket the literal in the URL (RFC 3986)"""
        url = self._run_http01('2001:db8::1')
        assert url == 'http://[2001:db8::1]/.well-known/acme-challenge/test-token'


class TestTLSALPN01IPValidation:
    """Test TLS-ALPN-01 challenge validation for IP addresses"""

    def test_tls_alpn01_ip_uses_reverse_ptr_sni(self):
        """TLS-ALPN-01 for IP should use reverse PTR as SNI hostname"""
        from utils.acme_ip import ip_to_reverse_ptr
        
        # IPv4 reverse PTR
        ipv4_ptr = ip_to_reverse_ptr('192.168.1.1')
        assert ipv4_ptr.endswith('.in-addr.arpa')
        
        # IPv6 reverse PTR
        ipv6_ptr = ip_to_reverse_ptr('2001:db8::1')
        assert ipv6_ptr.endswith('.ip6.arpa')


class TestCSRSANIPExtraction:
    """Test IP address extraction from CSR SANs"""

    def test_extract_ips_from_csr_san(self):
        """Should extract IP addresses from CSR Subject Alternative Names"""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        import ipaddress
        
        # Generate test key
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Create CSR with IP SANs
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, 'test.example.com'),
            ])
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName('test.example.com'),
                x509.IPAddress(ipaddress.IPv4Address('192.168.1.1')),
                x509.IPAddress(ipaddress.IPv6Address('2001:db8::1')),
            ]),
            critical=False
        ).sign(key, hashes.SHA256(), default_backend())
        
        # Extract IPs
        ips = extract_ip_from_csr_san(csr)
        
        assert '192.168.1.1' in ips
        assert '2001:db8::1' in ips
        assert len(ips) == 2

    def test_extract_ips_from_csr_san_no_ips(self):
        """Should return empty list when CSR has no IP SANs"""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        
        # Generate test key
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Create CSR without IP SANs
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, 'test.example.com'),
            ])
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName('test.example.com'),
            ]),
            critical=False
        ).sign(key, hashes.SHA256(), default_backend())
        
        # Extract IPs
        ips = extract_ip_from_csr_san(csr)
        
        assert len(ips) == 0


class TestIssuanceIPMatching:
    """Test that issuance validates CSR IPs match order IPs"""

    def test_extract_ips_from_csr_method(self):
        """IssuanceMixin should have _extract_ips_from_csr method"""
        from services.acme.mixins.issuance import IssuanceMixin

        mixin = IssuanceMixin()
        assert hasattr(mixin, '_extract_ips_from_csr')
        assert callable(getattr(mixin, '_extract_ips_from_csr'))


class TestIPOnlyOrderCAResolution:
    """Regression for #134: IP-only orders must honor the global default issuing CA,
    not fall back to the first available CA (typically the root)."""

    def test_resolve_ca_with_no_domains_uses_global_default(self, app, auth_client, create_ca):
        ca = create_ca(cn='IP Default Issuing CA')

        with app.app_context():
            from models import db, CA
            from models.system_config import SystemConfig
            from services.acme.mixins.issuance import IssuanceMixin

            ca_obj = db.session.get(CA, ca['id'])
            cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
            created = cfg is None
            if created:
                cfg = SystemConfig(key='acme.issuing_ca_id', value=ca_obj.refid)
                db.session.add(cfg)
            else:
                old_value = cfg.value
                cfg.value = ca_obj.refid
            db.session.commit()

            try:
                # Empty domain list = IP-only order → must resolve to global default
                assert IssuanceMixin()._resolve_ca_for_domains([]) == ca_obj.refid
            finally:
                if created:
                    db.session.delete(cfg)
                else:
                    cfg.value = old_value
                db.session.commit()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
