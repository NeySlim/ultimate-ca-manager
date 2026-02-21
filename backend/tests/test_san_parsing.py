"""
Tests for SAN string parsing in certificate creation.
"""
import pytest
import re
from ipaddress import ip_address


def parse_san_string(san_string):
    """
    Extract from certificates.py — parses raw SAN string into typed arrays.
    This mirrors the logic in POST /api/v2/certificates.
    """
    san_dns = []
    san_ip = []
    san_email = []
    raw_sans = [s.strip() for s in re.split(r'[,\n;]+', san_string) if s.strip()]
    for entry in raw_sans:
        entry_clean = re.sub(r'^(DNS|IP|EMAIL|URI):\s*', '', entry, flags=re.IGNORECASE)
        if not entry_clean:
            continue
        try:
            ip_address(entry_clean)
            san_ip.append(entry_clean)
        except ValueError:
            if '@' in entry_clean:
                san_email.append(entry_clean)
            else:
                san_dns.append(entry_clean)
    return san_dns, san_ip, san_email


class TestSANParsing:
    """SAN string parsing regression tests (issue #24)"""

    def test_basic_dns(self):
        dns, ip, email = parse_san_string("example.com, www.example.com")
        assert dns == ["example.com", "www.example.com"]
        assert ip == []
        assert email == []

    def test_basic_ip(self):
        dns, ip, email = parse_san_string("192.168.1.1, 10.0.0.1")
        assert dns == []
        assert ip == ["192.168.1.1", "10.0.0.1"]
        assert email == []

    def test_basic_email(self):
        dns, ip, email = parse_san_string("admin@example.com, user@test.org")
        assert dns == []
        assert ip == []
        assert email == ["admin@example.com", "user@test.org"]

    def test_mixed_types(self):
        dns, ip, email = parse_san_string(
            "example.com, *.example.com, 192.168.1.1, admin@example.com"
        )
        assert dns == ["example.com", "*.example.com"]
        assert ip == ["192.168.1.1"]
        assert email == ["admin@example.com"]

    def test_with_type_prefixes(self):
        dns, ip, email = parse_san_string(
            "DNS:example.com, IP:10.0.0.1, EMAIL:user@test.com"
        )
        assert dns == ["example.com"]
        assert ip == ["10.0.0.1"]
        assert email == ["user@test.com"]

    def test_newline_separator(self):
        dns, ip, email = parse_san_string("example.com\nwww.example.com\n10.0.0.1")
        assert dns == ["example.com", "www.example.com"]
        assert ip == ["10.0.0.1"]

    def test_semicolon_separator(self):
        dns, ip, email = parse_san_string("a.com; b.com; 1.1.1.1")
        assert dns == ["a.com", "b.com"]
        assert ip == ["1.1.1.1"]

    def test_whitespace_handling(self):
        dns, ip, email = parse_san_string("  example.com ,  *.example.com  , 10.0.0.1 ")
        assert dns == ["example.com", "*.example.com"]
        assert ip == ["10.0.0.1"]

    def test_ipv6(self):
        dns, ip, email = parse_san_string("example.com, ::1, fe80::1")
        assert dns == ["example.com"]
        assert ip == ["::1", "fe80::1"]

    def test_empty_string(self):
        dns, ip, email = parse_san_string("")
        assert dns == []
        assert ip == []
        assert email == []

    def test_only_commas(self):
        dns, ip, email = parse_san_string(",,,")
        assert dns == []
        assert ip == []
        assert email == []

    def test_wildcard_dns(self):
        dns, ip, email = parse_san_string("*.example.com, *.sub.example.com")
        assert dns == ["*.example.com", "*.sub.example.com"]

    def test_case_insensitive_prefix(self):
        dns, ip, email = parse_san_string("dns:example.com, ip:10.0.0.1, email:u@t.com")
        assert dns == ["example.com"]
        assert ip == ["10.0.0.1"]
        assert email == ["u@t.com"]
