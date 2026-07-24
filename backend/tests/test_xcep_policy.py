"""Interoperability tests for the MS-XCEP GetPolicies endpoint (Phase 1)."""
import base64
import json

import pytest
from lxml import etree

from models import CA, CATemplatePin, CertificateTemplate, db
from models.system_config import SystemConfig


XCEP_URL = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_USER = 'xcep-test'
XCEP_PASSWORD = 'xcep-password'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture(scope='module')
def xcep_config(app, create_ca):
    ca_data = create_ca(cn='XCEP Policy CA')
    keys = ('xcep_enabled', 'xcep_ca_refid', 'xcep_username', 'xcep_password')
    with app.app_context():
        previous = {
            key: (SystemConfig.query.filter_by(key=key).first().value
                  if SystemConfig.query.filter_by(key=key).first() else None)
            for key in keys
        }
        ca = db.session.get(CA, ca_data['id'])
        _set_config('xcep_enabled', 'true')
        _set_config('xcep_ca_refid', ca.refid)
        _set_config('xcep_username', XCEP_USER)
        _set_config('xcep_password', XCEP_PASSWORD)

        template = CertificateTemplate(
            name='XCEP Test Web Server',
            template_type='web_server',
            key_type='RSA-2048',
            validity_days=365,
            digest='sha256',
            dn_template=json.dumps({'CN': '{hostname}'}),
            extensions_template=json.dumps({
                'key_usage': ['digitalSignature', 'keyEncipherment'],
                'extended_key_usage': ['serverAuth'],
                'basic_constraints': {'ca': False},
            }),
            is_active=True,
        )
        db.session.add(template)
        db.session.commit()
        pin = CATemplatePin(ca_id=ca.id, template_id=template.id)
        db.session.add(pin)
        db.session.commit()
        template_id = template.id
        pin_id = pin.id

    yield {'ca': ca_data, 'template_id': template_id}

    with app.app_context():
        pin_row = db.session.get(CATemplatePin, pin_id)
        if pin_row:
            db.session.delete(pin_row)
        tmpl = db.session.get(CertificateTemplate, template_id)
        if tmpl:
            db.session.delete(tmpl)
        db.session.commit()
        for key, value in previous.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None:
                if row is not None:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=key, value=value))
            else:
                row.value = value
        db.session.commit()


def _basic_auth():
    token = base64.b64encode(f'{XCEP_USER}:{XCEP_PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def test_get_policies_disabled_returns_503(client, app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='xcep_enabled').first()
        previous = row.value if row else None
        _set_config('xcep_enabled', 'false')
    try:
        r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
        assert r.status_code == 503
    finally:
        with app.app_context():
            if previous is None:
                SystemConfig.query.filter_by(key='xcep_enabled').delete()
                db.session.commit()
            else:
                _set_config('xcep_enabled', previous)


def test_get_policies_requires_authentication(client, xcep_config):
    r = client.post(XCEP_URL, data=b'<GetPolicies/>')
    assert r.status_code == 401
    assert 'Basic' in r.headers.get('WWW-Authenticate', '')


def test_get_policies_rejects_bad_credentials(client, xcep_config):
    token = base64.b64encode(b'xcep-test:wrong-password').decode()
    r = client.post(
        XCEP_URL, data=b'<GetPolicies/>',
        headers={'Authorization': f'Basic {token}'},
    )
    assert r.status_code == 401


def test_get_policies_returns_pinned_template(client, xcep_config):
    r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
    assert r.status_code == 200
    assert r.content_type.startswith('application/soap+xml')

    root = etree.fromstring(r.data)
    policies = root.findall(f'.//{{{XCEP_NS}}}policy')
    assert len(policies) == 1

    common_name = policies[0].find(f'.//{{{XCEP_NS}}}commonName')
    assert common_name is not None
    assert common_name.text == 'XCEP Test Web Server'

    min_key_length = policies[0].find(f'.//{{{XCEP_NS}}}minimalKeyLength')
    assert min_key_length.text == '2048'

    validity_seconds = policies[0].find(f'.//{{{XCEP_NS}}}validityPeriodSeconds')
    assert int(validity_seconds.text) == 365 * 86400

    # EKU + key algorithm OIDs must be cross-referenced in the oIDs table.
    oid_values = {el.text for el in root.findall(f'.//{{{XCEP_NS}}}oID/{{{XCEP_NS}}}value')}
    assert '1.3.6.1.5.5.7.3.1' in oid_values  # serverAuth
    assert '1.2.840.113549.1.1.1' in oid_values  # RSA

    ca_ref = root.find(f'.//{{{XCEP_NS}}}CAReference/{{{XCEP_NS}}}authority')
    assert ca_ref is not None and ca_ref.text


def test_get_policies_falls_back_to_active_templates_when_unpinned(client, app, create_ca, xcep_config):
    """A CA with no pinned templates should still expose every active
    template, matching the Templates UI's own pin-then-show-all fallback.

    Depends on ``xcep_config`` only for shared username/password setup, not
    for its pinned template — this test creates and cleans up its own
    unpinned template so it doesn't rely on module test-ordering to find
    another test's data still present.
    """
    ca_data = create_ca(cn='XCEP Fallback CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        previous_refid = SystemConfig.query.filter_by(key='xcep_ca_refid').first()
        previous_value = previous_refid.value if previous_refid else None
        _set_config('xcep_ca_refid', ca.refid)

        template = CertificateTemplate(
            name='XCEP Fallback Template',
            template_type='client_auth',
            key_type='EC-P256',
            validity_days=90,
            digest='sha256',
            extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}),
            is_active=True,
        )
        db.session.add(template)
        db.session.commit()
        template_id = template.id

    try:
        r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
        assert r.status_code == 200
        root = etree.fromstring(r.data)
        policies = root.findall(f'.//{{{XCEP_NS}}}policy')
        names = {p.find(f'.//{{{XCEP_NS}}}commonName').text for p in policies}
        assert 'XCEP Fallback Template' in names
    finally:
        with app.app_context():
            tmpl = db.session.get(CertificateTemplate, template_id)
            if tmpl:
                db.session.delete(tmpl)
            db.session.commit()
            if previous_value is None:
                row = SystemConfig.query.filter_by(key='xcep_ca_refid').first()
                if row:
                    db.session.delete(row)
                db.session.commit()
            else:
                _set_config('xcep_ca_refid', previous_value)
