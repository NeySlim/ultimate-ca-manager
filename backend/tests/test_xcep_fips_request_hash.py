"""XCEP in FIPS mode never leaves the request hash to the client's SHA-1 default."""
import json
from types import SimpleNamespace

import pytest
from lxml import etree

import fips_mode
from services.xcep import policy_builder

XCEP_NS = policy_builder.XCEP_NS
NS = {'x': XCEP_NS}
SHA1_OID = '1.3.14.3.2.26'


def _template(tid, key_type='RSA-2048', digest='sha256', template_type='client_auth'):
    return SimpleNamespace(
        id=tid, name=f'T{tid}', template_type=template_type, key_type=key_type,
        digest=digest, validity_days=365, autoenroll_enabled=True, ad_derived_subject=False,
        extensions_template=json.dumps({'key_usage': ['digitalSignature'],
                                        'extended_key_usage': ['clientAuth']}),
    )


def _build(templates):
    ca = SimpleNamespace(refid='ca1', descr='Test CA', crt=None, template_pins=[])
    xml = policy_builder.build_get_policies_response(ca, templates)
    root = etree.fromstring(xml)
    oids = {o.findtext('x:oIDReferenceID', namespaces=NS): (o.findtext('x:value', namespaces=NS),
                                                            o.findtext('x:group', namespaces=NS))
            for o in root.iter(f'{{{XCEP_NS}}}oID')}
    return root, oids


def _policies(root):
    return list(root.iter(f'{{{XCEP_NS}}}policy'))


@pytest.mark.parametrize('digest,expected', [
    ('sha256', '2.16.840.1.101.3.4.2.1'),
    ('sha384', '2.16.840.1.101.3.4.2.2'),
    ('SHA-512', '2.16.840.1.101.3.4.2.3'),
    ('sha1', '2.16.840.1.101.3.4.2.1'),   # never advertised, falls back
    (None, '2.16.840.1.101.3.4.2.1'),
])
def test_fips_pins_non_sha1_request_hash(monkeypatch, digest, expected):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    root, oids = _build([_template(1, digest=digest)])
    policy = _policies(root)[0]
    ref = policy.findtext('x:attributes/x:hashAlgorithmOIDReference', namespaces=NS)
    assert ref, 'hashAlgorithmOIDReference must not be nil in FIPS mode'
    value, group = oids[ref]
    assert value == expected and group == '1'
    assert all(v != SHA1_OID for v, _ in oids.values())
    assert policy.findtext('x:attributes/x:policySchema', namespaces=NS) == '3'
    providers = [p.text for p in policy.iterfind('.//x:cryptoProviders/x:provider', NS)]
    assert providers == ['Microsoft Software Key Storage Provider']
    assert policy.find('.//x:privateKeyAttributes/x:keySpec', NS).get(
        f'{{{policy_builder.XSI_NS}}}nil') == 'true'


def test_fips_shared_hash_oid_listed_once(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    root, oids = _build([_template(1), _template(2), _template(3, key_type='EC-P256')])
    refs = {p.findtext('x:attributes/x:hashAlgorithmOIDReference', namespaces=NS) for p in _policies(root)}
    assert len(refs) == 1
    assert sum(1 for v, g in oids.values() if g == '1') == 1


def test_non_fips_unchanged(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    root, oids = _build([_template(1)])
    policy = _policies(root)[0]
    href = policy.find('x:attributes/x:hashAlgorithmOIDReference', NS)
    assert href.get(f'{{{policy_builder.XSI_NS}}}nil') == 'true'
    assert policy.findtext('x:attributes/x:policySchema', namespaces=NS) == '2'
    providers = [p.text for p in policy.iterfind('.//x:cryptoProviders/x:provider', NS)]
    assert providers == ['Microsoft Enhanced RSA and AES Cryptographic Provider']
    assert policy.findtext('.//x:privateKeyAttributes/x:keySpec', namespaces=NS) == '1'
