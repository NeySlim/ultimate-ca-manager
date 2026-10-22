"""utils.qc_statements: template validation, DER encoding and decoding."""
import datetime
import shutil
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from utils import qc_statements as qc

FULL = {
    'compliance': True, 'type': 'esign', 'sscd': True,
    'pds': [{'url': 'https://pki.example.test/pds_en.pdf', 'language': 'en'},
            {'url': 'https://pki.example.test/pds_fr.pdf', 'language': 'fr'}],
    'retention_period': 20,
    'limit_value': {'currency': 'EUR', 'amount': 5000, 'exponent': 0},
    'semantics': 'eidas-natural',
}


def _cert(ext):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'qc.example.test')])
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime(2026, 1, 1))
            .not_valid_after(datetime.datetime(2027, 1, 1))
            .add_extension(ext, critical=False).sign(key, hashes.SHA256()))


class TestValidation:
    def test_full_payload_is_valid(self):
        assert qc.validate_qc_statements(FULL) == []

    def test_unset_is_valid(self):
        assert qc.validate_qc_statements(None) == []
        assert qc.validate_qc_statements({}) == []

    @pytest.mark.parametrize('payload,needle', [
        ('x', 'must be an object'),
        ({'bogus': 1}, 'Unknown qc_statements key: bogus'),
        ({'compliance': 'yes'}, 'compliance'),
        ({'sscd': 1}, 'sscd'),
        ({'type': 'web2'}, 'type'),
        ({'semantics': 'x'}, 'semantics'),
        ({'cc_legislation': []}, 'cc_legislation'),
        ({'cc_legislation': ['fr']}, 'cc_legislation'),
        ({'cc_legislation': ['FR', 'FR']}, 'duplicate'),
        ({'compliance': True, 'cc_legislation': ['FR']}, 'mutually exclusive'),
        ({'pds': []}, 'pds'),
        ({'pds': [{'url': 'http://x.test/p', 'language': 'en'}]}, 'https'),
        ({'pds': [{'url': 'https://x.test/p', 'language': 'EN'}]}, 'language'),
        ({'pds': [{'url': 'https://x.test/p', 'language': 'fr'}]}, 'English'),
        ({'pds': [{'url': 'https://x.test/p', 'language': 'en', 'x': 1}]}, 'url, language'),
        ({'retention_period': 0}, 'retention_period'),
        ({'retention_period': True}, 'retention_period'),
        ({'limit_value': {'currency': 'eur', 'amount': 1, 'exponent': 0}}, 'limit_value'),
        ({'limit_value': {'currency': 'EUR', 'amount': -1, 'exponent': 0}}, 'limit_value'),
        ({'limit_value': {'currency': 'EUR', 'amount': 1}}, 'limit_value'),
    ])
    def test_refusals(self, payload, needle):
        errors = qc.validate_qc_statements(payload)
        assert errors and any(needle in e for e in errors), errors

    def test_cc_legislation_alone_is_valid(self):
        assert qc.validate_qc_statements({'cc_legislation': ['FR', 'DE']}) == []

    @pytest.mark.parametrize('value', ['0.4.0.194112.1.2', '1.2.3'])
    def test_policy_oids_valid(self, value):
        assert qc.validate_policy_oids([value]) == []

    @pytest.mark.parametrize('value', ['abc', '1', '3.1.2', '1.2.', '1..2', 5, ''])
    def test_policy_oids_invalid(self, value):
        assert qc.validate_policy_oids([value])

    def test_policy_oids_shape(self):
        assert qc.validate_policy_oids('1.2.3')
        assert qc.validate_policy_oids(['1.2.3', '1.2.3'])
        assert qc.validate_policy_oids(['1.2.3'] * 21)


class TestEncoding:
    def test_roundtrip(self):
        decoded = qc.decode_qc_statements(qc.build_qc_statements_der(FULL))
        assert decoded == FULL

    def test_cc_legislation_roundtrip(self):
        d = qc.decode_qc_statements(qc.build_qc_statements_der({'cc_legislation': ['FR', 'DE']}))
        assert d == {'cc_legislation': ['FR', 'DE']}

    def test_unknown_statement_is_listed_and_garbage_refused(self):
        der = bytes.fromhex('3007300506032a0304')  # one statement, OID 1.2.3.4
        assert qc.decode_qc_statements(der) == {'other': ['1.2.3.4']}
        assert qc.decode_qc_statements(b'garbage') is None

    def test_extension_is_non_critical_and_openssl_names_it(self):
        ext = qc.qc_statements_extension({'qc_statements': FULL})
        assert ext.oid.dotted_string == '1.3.6.1.5.5.7.1.3'
        cert = _cert(ext)
        if not shutil.which('openssl'):
            pytest.skip('openssl not installed')
        pem = cert.public_bytes(serialization.Encoding.PEM)
        out = subprocess.run(['openssl', 'x509', '-noout', '-text'], input=pem,
                             capture_output=True, check=True).stdout.decode()
        assert 'qcStatements' in out

    def test_invalid_template_yields_no_extension(self):
        assert qc.qc_statements_extension({'qc_statements': {'type': 'bogus'}}) is None
        assert qc.qc_statements_extension({'qc_statements': {}}) is None
        assert qc.qc_statements_extension({}) is None
        assert qc.qc_statements_extension(None) is None


class TestPolicies:
    def test_ca_policy_first_then_template_deduplicated(self):
        ext = qc.build_certificate_policies(
            'https://ca.example.test/cps', '1.2.3.4', ['0.4.0.194112.1.2', '1.2.3.4'])
        oids = [p.policy_identifier.dotted_string for p in ext]
        assert oids == ['1.2.3.4', '0.4.0.194112.1.2']
        assert ext[0].policy_qualifiers == ['https://ca.example.test/cps']
        assert ext[1].policy_qualifiers is None

    def test_template_oids_without_cps(self):
        ext = qc.build_certificate_policies(None, None, ['0.4.0.194112.1.0'])
        assert [p.policy_identifier.dotted_string for p in ext] == ['0.4.0.194112.1.0']

    def test_nothing_to_add(self):
        assert qc.build_certificate_policies(None, None, []) is None
