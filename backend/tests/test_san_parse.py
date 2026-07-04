"""Tests for CSR SAN entry parsing."""
import pytest

from utils.san_parse import (
    parse_csr_san_entries,
    validate_dns_san,
    validate_email_san,
    validate_ip_san,
    validate_uri_san,
    validate_upn_san,
)


class TestParseCsrSanEntries:
    def test_dns_fqdn(self):
        buckets, err = parse_csr_san_entries(['DNS:www.example.org'])
        assert err is None
        assert buckets['san_dns'] == ['www.example.org']

    def test_ip_address(self):
        buckets, err = parse_csr_san_entries(['IP:10.0.0.1'])
        assert err is None
        assert buckets['san_ip'] == ['10.0.0.1']

    def test_fqdn_in_ip_type_rejected(self):
        _, err = parse_csr_san_entries(['IP:www.example.org'])
        assert err and 'DNS type' in err

    def test_ip_in_dns_type_rejected(self):
        _, err = parse_csr_san_entries(['DNS:10.0.0.1'])
        assert err and 'IP type' in err

    def test_email_san(self):
        buckets, err = parse_csr_san_entries(['Email:admin@example.com'])
        assert err is None
        assert buckets['san_email'] == ['admin@example.com']

    def test_hostname_in_email_rejected(self):
        _, err = parse_csr_san_entries(['Email:www.example.org'])
        assert err and 'DNS type' in err

    def test_uri_san(self):
        buckets, err = parse_csr_san_entries(['URI:https://example.com/path'])
        assert err is None
        assert buckets['san_uri'] == ['https://example.com/path']

    def test_fqdn_in_uri_rejected(self):
        _, err = parse_csr_san_entries(['URI:www.example.org'])
        assert err and 'scheme' in err

    def test_upn_san(self):
        buckets, err = parse_csr_san_entries(['UPN:user@corp.local'])
        assert err is None
        assert buckets['san_upn'] == ['user@corp.local']

    def test_invalid_upn_rejected(self):
        _, err = parse_csr_san_entries(['UPN:not-a-upn'])
        assert err and 'UPN' in err

    def test_unprefixed_auto_detect(self):
        buckets, err = parse_csr_san_entries([
            'alt.example.com',
            '192.168.1.1',
            'user@example.com',
            'https://example.com',
        ])
        assert err is None
        assert buckets['san_dns'] == ['alt.example.com']
        assert buckets['san_ip'] == ['192.168.1.1']
        assert buckets['san_email'] == ['user@example.com']
        assert buckets['san_uri'] == ['https://example.com']


class TestValidateSanHelpers:
    @pytest.mark.parametrize('fn,ok,bad', [
        (validate_ip_san, '10.0.0.1', 'www.example.com'),
        (validate_dns_san, 'www.example.com', '10.0.0.1'),
        (validate_email_san, 'a@b.com', 'www.example.com'),
        (validate_uri_san, 'https://x.com', 'www.example.com'),
        (validate_upn_san, 'u@d.local', 'nodomain'),
    ])
    def test_helpers(self, fn, ok, bad):
        assert fn(ok) is None
        assert fn(bad) is not None
