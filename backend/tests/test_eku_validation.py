"""Tests for utils.eku_validation (issue #76)."""
from utils.eku_validation import (
    validate_oid,
    normalize_extra_ekus,
    merge_eku_lists,
    to_object_identifiers,
    EKU_NAMES,
    ANY_EXTENDED_KEY_USAGE,
    MAX_EKU_COUNT,
)
from cryptography import x509


class TestValidateOid:
    def test_valid_dotted(self):
        assert validate_oid('1.3.6.1.5.5.7.3.1') is None
        assert validate_oid('1.3.6.1.4.1.311.54.1.2') is None  # MS RDP

    def test_invalid_format(self):
        assert validate_oid('not.an.oid') is not None
        assert validate_oid('') is not None
        assert validate_oid('1') is not None  # too few arcs
        assert validate_oid('9.0.1') is not None  # bad first arc (>2)

    def test_rejects_any_eku(self):
        err = validate_oid(ANY_EXTENDED_KEY_USAGE)
        assert err is not None and 'anyExtendedKeyUsage' in err

    def test_too_long(self):
        long_oid = '1.' + '.'.join(['9'] * 40)
        assert validate_oid(long_oid) is not None


class TestNormalize:
    def test_dotted_oid(self):
        oids, err = normalize_extra_ekus(['1.3.6.1.4.1.311.54.1.2'])
        assert err is None
        assert oids == ['1.3.6.1.4.1.311.54.1.2']

    def test_well_known_name(self):
        oids, err = normalize_extra_ekus(['msRemoteDesktop'])
        assert err is None
        assert oids == ['1.3.6.1.4.1.311.54.1.2']

    def test_case_insensitive_name(self):
        oids, err = normalize_extra_ekus(['MSREMOTEDESKTOP'])
        assert err is None
        assert oids == ['1.3.6.1.4.1.311.54.1.2']

    def test_dedupe(self):
        oids, err = normalize_extra_ekus([
            'msRemoteDesktop', '1.3.6.1.4.1.311.54.1.2'
        ])
        assert err is None
        assert oids == ['1.3.6.1.4.1.311.54.1.2']

    def test_max_count(self):
        oids, err = normalize_extra_ekus(['1.2.3.4'] * (MAX_EKU_COUNT + 1))
        assert err is not None and 'max' in err.lower()

    def test_empty(self):
        assert normalize_extra_ekus(None) == ([], None)
        assert normalize_extra_ekus([]) == ([], None)

    def test_invalid_returns_error(self):
        oids, err = normalize_extra_ekus(['bogus'])
        assert err is not None
        assert oids == []


class TestMerge:
    def test_merge_dedupes(self):
        server = x509.oid.ExtendedKeyUsageOID.SERVER_AUTH
        rdp = x509.ObjectIdentifier('1.3.6.1.4.1.311.54.1.2')
        merged = merge_eku_lists([server], [server, rdp])
        assert len(merged) == 2
        oids = [m.dotted_string for m in merged]
        assert '1.3.6.1.5.5.7.3.1' in oids
        assert '1.3.6.1.4.1.311.54.1.2' in oids

    def test_to_object_identifiers(self):
        result = to_object_identifiers(['1.3.6.1.4.1.311.54.1.2'])
        assert len(result) == 1
        assert isinstance(result[0], x509.ObjectIdentifier)
        assert result[0].dotted_string == '1.3.6.1.4.1.311.54.1.2'


class TestEkuNames:
    def test_rdp_known(self):
        assert EKU_NAMES.get('1.3.6.1.4.1.311.54.1.2') == 'msRemoteDesktop'

    def test_server_auth_known(self):
        assert EKU_NAMES.get('1.3.6.1.5.5.7.3.1') == 'serverAuth'
