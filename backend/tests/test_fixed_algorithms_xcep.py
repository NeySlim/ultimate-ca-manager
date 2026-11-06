"""XCEP announces the request hash of every schema 3 (KSP) template (#397 follow-up)."""
import pytest

import fips_mode
from tests.test_xcep_fips_request_hash import NS, _build, _policies, _template

SHA256, SHA384, SHA512 = ('2.16.840.1.101.3.4.2.1', '2.16.840.1.101.3.4.2.2',
                          '2.16.840.1.101.3.4.2.3')


def _announced(policy, oids):
    ref = policy.findtext('x:attributes/x:hashAlgorithmOIDReference', namespaces=NS)
    assert ref, 'hashAlgorithmOIDReference is nil'
    value, group = oids[ref]
    assert group == '1'
    return value


@pytest.mark.parametrize('fips', [False, True])
@pytest.mark.parametrize('key_type,digest,expected', [
    ('EC-P256', 'sha256', SHA256),
    ('EC-P384', 'sha256', SHA384),
    ('EC-P384', 'sha512', SHA512),
    ('EC-P521', None, SHA512),
])
def test_ecdsa_templates_are_schema_3_with_the_key_hash(monkeypatch, fips, key_type, digest, expected):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: fips)
    root, oids = _build([_template(1, key_type=key_type, digest=digest)])
    policy = _policies(root)[0]
    assert policy.findtext('x:attributes/x:policySchema', namespaces=NS) == '3'
    assert _announced(policy, oids) == expected


def test_rsa_outside_fips_stays_schema_2_with_a_nil_hash(monkeypatch):
    # MS-XCEP 3.1.4.1.3.1: the hash of a schema 1 or 2 policy MUST be nil
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    root, _ = _build([_template(1, key_type='RSA-3072', digest='sha384')])
    policy = _policies(root)[0]
    assert policy.findtext('x:attributes/x:policySchema', namespaces=NS) == '2'
    assert policy.find('x:attributes/x:hashAlgorithmOIDReference', NS).get(
        '{http://www.w3.org/2001/XMLSchema-instance}nil') == 'true'
