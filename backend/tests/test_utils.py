"""
Unit tests for utility functions
"""
import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBase64Utils:
    """Tests for base64 encoding utilities"""
    
    def test_base64url_encode_decode(self):
        # Import standalone functions
        from services.webauthn_service import base64url_decode, base64url_encode
        
        # Test round-trip encoding
        original = b'Hello WebAuthn!'
        encoded = base64url_encode(original)
        decoded = base64url_decode(encoded)
        
        assert decoded == original
        
    def test_base64url_handles_padding(self):
        from services.webauthn_service import base64url_decode
        
        # Test various padding scenarios
        test_cases = [
            ('YQ', b'a'),        # 1 byte, needs == padding
            ('YWI', b'ab'),      # 2 bytes, needs = padding
            ('YWJj', b'abc'),    # 3 bytes, no padding needed
            ('YWJjZA', b'abcd'), # 4 bytes, needs == padding
        ]
        
        for encoded, expected in test_cases:
            decoded = base64url_decode(encoded)
            assert decoded == expected, f"Failed for {encoded}"


class TestDateUtils:
    """Tests for date/time utilities"""
    
    def test_parse_iso_date(self):
        from datetime import datetime
        
        # Standard ISO format
        iso_date = "2025-12-31T23:59:59Z"
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        
        assert dt.year == 2025
        assert dt.month == 12
        assert dt.day == 31
