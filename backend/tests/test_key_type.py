"""Tests for utils.key_type CSR key parsing."""
import pytest

from utils.key_type import normalize_ec_curve, parse_csr_key_type, parse_issue_key_type


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
        # Hyphen/underscore forms — same style as the ACME order key_type
        # enum ('EC-P256'): previously rejected by a dead alias table.
        ('EC-P256', 'prime256v1'),
        ('ec-p384', 'secp384r1'),
        ('EC-P521', 'secp521r1'),
        ('ecdsa-p256', 'prime256v1'),
        ('ECDSA-P384', 'secp384r1'),
        ('nist-p521', 'secp521r1'),
        ('EC_P-384', 'secp384r1'),
        ('P_521', 'secp521r1'),
    ])
    def test_aliases(self, raw, expected):
        assert normalize_ec_curve(raw) == expected

    def test_unknown_curve_raises(self):
        with pytest.raises(ValueError, match='P-256'):
            normalize_ec_curve('secp256k1')

    @pytest.mark.parametrize('bad', ['P-192', 'brainpoolP256r1', 'RSA', ''])
    def test_rejects_non_nist_and_empty(self, bad):
        with pytest.raises(ValueError):
            normalize_ec_curve(bad)


class TestParseCsrKeyType:
    def test_rsa_2048(self):
        assert parse_csr_key_type('RSA 2048') == '2048'

    def test_rsa_4096(self):
        assert parse_csr_key_type('RSA 4096') == '4096'

    def test_ec_ui_label(self):
        assert parse_csr_key_type('EC P-256') == 'prime256v1'

    def test_ec_hyphen_label(self):
        assert parse_csr_key_type('EC-P256') == 'prime256v1'

    def test_invalid_rsa_size(self):
        with pytest.raises(ValueError, match='2048'):
            parse_csr_key_type('RSA 1024')


class TestParseIssueKeyType:
    @pytest.mark.parametrize('key_type,key_size,expected', [
        ('rsa', '2048', '2048'),
        ('rsa', '4096', '4096'),
        ('ecdsa', '256', 'prime256v1'),
        ('ecdsa', '384', 'secp384r1'),
        ('ecdsa', '521', 'secp521r1'),
        ('EC', '256', 'prime256v1'),
        ('ecdsa', 'secp256r1', 'prime256v1'),
        ('ecdsa', 'NIST P-384', 'secp384r1'),
    ])
    def test_issue_form_fields(self, key_type, key_size, expected):
        assert parse_issue_key_type(key_type, key_size) == expected

    def test_combined_ec_label(self):
        assert parse_issue_key_type('EC P-256', None) == 'prime256v1'


class TestEnrollmentKeyStrength:
    """Key-strength floor shared by EST and SCEP enrollment."""

    def test_rejects_short_rsa(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from utils.key_type import validate_enrollment_public_key
        key = rsa.generate_private_key(65537, 1024)
        err = validate_enrollment_public_key(key.public_key())
        assert err and 'too small' in err

    def test_accepts_rsa_2048(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from utils.key_type import validate_enrollment_public_key
        key = rsa.generate_private_key(65537, 2048)
        assert validate_enrollment_public_key(key.public_key()) is None

    def test_accepts_p256(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from utils.key_type import validate_enrollment_public_key
        key = ec.generate_private_key(ec.SECP256R1())
        assert validate_enrollment_public_key(key.public_key()) is None

    def test_rejects_exotic_curve(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from utils.key_type import validate_enrollment_public_key
        key = ec.generate_private_key(ec.SECP192R1())
        err = validate_enrollment_public_key(key.public_key())
        assert err and 'curve' in err.lower()

    def test_accepts_ed25519(self):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from utils.key_type import validate_enrollment_public_key
        assert validate_enrollment_public_key(ed25519.Ed25519PrivateKey.generate().public_key()) is None
