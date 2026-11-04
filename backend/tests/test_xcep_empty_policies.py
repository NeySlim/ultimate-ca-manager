"""A CA with nothing to announce: PolicyCollection and OIDCollection need one child, or nil."""
import json
from types import SimpleNamespace

import pytest
from lxml import etree

from services.xcep import policy_builder

XCEP_NS = policy_builder.XCEP_NS
XSI_NIL = f'{{{policy_builder.XSI_NS}}}nil'
NS = {'x': XCEP_NS}


def _template(tid=1, key_type='RSA-2048', is_active=True):
    return SimpleNamespace(
        id=tid, name=f'T{tid}', template_type='client_auth', key_type=key_type,
        digest='sha256', validity_days=365, autoenroll_enabled=False, ad_derived_subject=False,
        is_active=is_active,
        extensions_template=json.dumps({'key_usage': ['digitalSignature'],
                                        'extended_key_usage': ['clientAuth']}),
    )


def _build(templates, pins=()):
    ca = SimpleNamespace(refid='ca1', descr='Test CA', crt=None, template_pins=list(pins))
    return etree.fromstring(policy_builder.build_get_policies_response(ca, templates))


def _collections(root):
    response = root.find('.//x:GetPoliciesResponse', NS)
    return response.find('x:response/x:policies', NS), response.find('x:oIDs', NS)


@pytest.mark.parametrize('templates,pins', [
    pytest.param([], [], id='no-template'),
    pytest.param([_template(key_type='Ed25519')], [], id='every-template-left-out'),
    pytest.param([_template(2)], [SimpleNamespace(template=_template(is_active=False))], id='pin-deactivated'),
])
def test_nothing_to_announce_is_nil(templates, pins):
    policies, oids = _collections(_build(templates, pins))
    assert policies.get(XSI_NIL) == 'true' and len(policies) == 0
    assert oids.get(XSI_NIL) == 'true' and len(oids) == 0


def test_announced_policy_is_not_nil():
    policies, oids = _collections(_build([_template()]))
    assert policies.get(XSI_NIL) is None and len(policies) == 1
    assert oids.get(XSI_NIL) is None and len(oids) > 0


def test_nil_keeps_the_rest_of_the_response():
    root = _build([])
    response = root.find('.//x:GetPoliciesResponse', NS)
    assert [etree.QName(c).localname for c in response] == ['response', 'cAs', 'oIDs']
    assert response.findtext('x:response/x:policyID', namespaces=NS)
    assert response.find('x:cAs/x:cA/x:cAReferenceID', NS).text == '1'
