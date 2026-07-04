"""Tests for utils.key_type CSR key parsing."""
import pytest

from utils.key_type import normalize_ec_curve, parse_csr_key_type


class TestNormalizeEcCurve:
    @pytest.mark.parametrize('raw,expected', [
        ('EC P-256', 'prime256v1'),
        ('P-256', 'prime256v1'),
        ('NIST P-256', 'prime256v1'),
        ('secp256r1', 'prime256v1'),
        ('prime256v1', 'prime256v1'),
        ('EC P-384', 'secp384r1'),
        ('secp384r1', 'secp384r1'),
        ('EC P-521', 'secp521r1'),
        ('secp521r1', 'secp521r1'),
    ])
    def test_aliases(self, raw, expected):
        assert normalize_ec_curve(raw) == expected

    def test_unknown_curve_raises(self):
        with pytest.raises(ValueError, match='P-256'):
            normalize_ec_curve('secp256k1')


class TestParseCsrKeyType:
    def test_rsa_2048(self):
        assert parse_csr_key_type('RSA 2048') == '2048'

    def test_rsa_4096(self):
        assert parse_csr_key_type('RSA 4096') == '4096'

    def test_ec_ui_label(self):
        assert parse_csr_key_type('EC P-256') == 'prime256v1'

    def test_invalid_rsa_size(self):
        with pytest.raises(ValueError, match='2048'):
            parse_csr_key_type('RSA 1024')
