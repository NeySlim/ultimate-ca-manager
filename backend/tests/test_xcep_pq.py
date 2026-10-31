"""XCEP announces an ML-DSA template: its OID as a public-key algorithmOIDReference, no
minimal length, the software KSP and a signature-only key spec."""
import json

import pytest
from lxml import etree

from models import CA, CATemplatePin, CertificateTemplate, db
from models.system_config import SystemConfig
from services.xcep import policy_builder
from tests.test_xcep_policy import (
    XCEP_NS, XCEP_PASSWORD, XCEP_URL, XCEP_USER, _basic_auth, _set_config,
)
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

XSI_NIL = '{http://www.w3.org/2001/XMLSchema-instance}nil'
MLDSA_LABELS = key_algorithms.labels('ML-DSA')
# privateKeyAttributes is an xs:sequence in the MS-XCEP schema
PK_ATTRS_SEQUENCE = ['minimalKeyLength', 'keySpec', 'keyUsageProperty', 'permissions',
                     'algorithmOIDReference', 'cryptoProviders']
XCEP_KEYS = ('xcep_enabled', 'xcep_ca_refid', 'xcep_username', 'xcep_password')


@pytest.mark.parametrize('label', MLDSA_LABELS)
def test_key_type_info_announces_mldsa(label):
    assert policy_builder._key_type_info(label) == (label, 0)


def test_mldsa_is_left_out_in_fips_mode(monkeypatch):
    monkeypatch.setattr(policy_builder.fips_mode, 'enabled', lambda: True)
    assert policy_builder._key_type_info(MLDSA_LABELS[0]) is None


def _template(ca, name, key_type):
    t = CertificateTemplate(name=name, template_type='user', key_type=key_type,
                            validity_days=365, digest='sha256', is_active=True,
                            extensions_template=json.dumps({'key_usage': ['digitalSignature']}))
    db.session.add(t)
    db.session.commit()
    db.session.add(CATemplatePin(ca_id=ca.id, template_id=t.id))
    db.session.commit()
    return t.id


@pytest.fixture
def xcep_pq_policies(app, client, create_ca):
    """GetPolicies of an RSA CA pinned to one template per ML-DSA label plus an RSA one."""
    ca_data = create_ca(cn='XCEP RSA CA for ML-DSA')
    with app.app_context():
        previous = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None)
                    for k in XCEP_KEYS}
        ca = db.session.get(CA, ca_data['id'])
        for key, value in zip(XCEP_KEYS, ('true', ca.refid, XCEP_USER, XCEP_PASSWORD)):
            _set_config(key, value)
        ids = [_template(ca, f'XCEP PQ {label}', label) for label in MLDSA_LABELS]
        ids.append(_template(ca, 'XCEP PQ RSA neighbour', 'RSA-2048'))
    try:
        r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
        assert r.status_code == 200
        yield etree.fromstring(r.data)
    finally:
        with app.app_context():
            CATemplatePin.query.filter(CATemplatePin.template_id.in_(ids)).delete()
            CertificateTemplate.query.filter(CertificateTemplate.id.in_(ids)).delete()
            db.session.commit()
            for k, v in previous.items():
                if v is None:
                    SystemConfig.query.filter_by(key=k).delete()
                    db.session.commit()
                else:
                    _set_config(k, v)


def _private_key_attributes(root, name):
    for policy in root.findall(f'.//{{{XCEP_NS}}}policy'):
        if policy.find(f'.//{{{XCEP_NS}}}commonName').text == name:
            return policy.find(f'.//{{{XCEP_NS}}}privateKeyAttributes')
    raise AssertionError(f'{name} not announced')


def test_get_policies_announces_every_mldsa_template(xcep_pq_policies):
    root = xcep_pq_policies
    oids = {o.find(f'{{{XCEP_NS}}}oIDReferenceID').text: o
            for o in root.findall(f'.//{{{XCEP_NS}}}oIDs/{{{XCEP_NS}}}oID')}
    for label in MLDSA_LABELS:
        pk = _private_key_attributes(root, f'XCEP PQ {label}')
        assert [etree.QName(c).localname for c in pk] == PK_ATTRS_SEQUENCE
        assert pk.find(f'{{{XCEP_NS}}}minimalKeyLength').text == '0'
        assert pk.find(f'{{{XCEP_NS}}}keySpec').text == '2'          # AT_SIGNATURE
        providers = [p.text for p in pk.findall(f'{{{XCEP_NS}}}cryptoProviders/{{{XCEP_NS}}}provider')]
        assert providers == ['Microsoft Software Key Storage Provider']
        ref = pk.find(f'{{{XCEP_NS}}}algorithmOIDReference')
        assert ref.get(XSI_NIL) is None
        oid = oids[ref.text]
        assert oid.find(f'{{{XCEP_NS}}}value').text == key_algorithms.get(label).oid
        assert oid.find(f'{{{XCEP_NS}}}group').text == '3'               # public key
        assert oid.find(f'{{{XCEP_NS}}}defaultName').text == label
    # Every reference resolves, and no OID is listed twice
    values = [o.find(f'{{{XCEP_NS}}}value').text for o in oids.values()]
    assert len(values) == len(set(values))


def test_rsa_template_keeps_a_nil_algorithm_reference(xcep_pq_policies):
    pk = _private_key_attributes(xcep_pq_policies, 'XCEP PQ RSA neighbour')
    assert pk.find(f'{{{XCEP_NS}}}algorithmOIDReference').get(XSI_NIL) == 'true'
    assert pk.find(f'{{{XCEP_NS}}}keySpec').text == '1'
