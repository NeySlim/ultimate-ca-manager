"""Interoperability tests for the MS-XCEP GetPolicies endpoint (Phase 1)."""
import base64
import json

import pytest
from lxml import etree

from models import CA, CATemplatePin, CertificateTemplate, db
from models.system_config import SystemConfig
from tests.fixtures.templates import delete_templates
from services.wstep.soap_envelope import SOAP_NS
from tests.windows_profile_support import get_config, restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401


XCEP_URL = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_USER = 'xcep-test'
XCEP_PASSWORD = 'xcep-password'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
# The CAs this file creates are removed after it
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _set_config(key, value):
    set_config(key, value)


@pytest.fixture(scope='module')
def xcep_config(app, create_ca):
    ca_data = create_ca(cn='XCEP Policy CA')
    keys = ('xcep_enabled', 'xcep_ca_refid', 'xcep_username', 'xcep_password')
    with app.app_context():
        previous = snapshot(keys)
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

    yield {'ca': ca_data, 'template_id': template_id}

    with app.app_context():
        delete_templates([template_id])
        db.session.commit()
        restore(previous)


def _basic_auth():
    token = base64.b64encode(f'{XCEP_USER}:{XCEP_PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def test_get_policies_disabled_returns_503(client, app):
    with app.app_context():
        previous = get_config('xcep_enabled')
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
    """Auth failure is a SOAP fault, not an HTTP 401/WWW-Authenticate
    challenge — a real Windows client configured for this UsernamePassword
    binding (WS-Security UsernameToken, not transport-level HTTP Basic)
    refuses to respond to a Basic challenge at all
    (reports WS_E_SERVER_REQUIRES_BASIC_AUTH) rather than retrying with
    credentials, so this endpoint never issues one."""
    r = client.post(XCEP_URL, data=b'<GetPolicies/>')
    assert r.status_code == 400
    assert 'WWW-Authenticate' not in r.headers
    root = etree.fromstring(r.data)
    assert root.find(f'.//{{{SOAP_NS}}}Fault') is not None


def test_get_policies_rejects_bad_credentials(client, xcep_config):
    token = base64.b64encode(b'xcep-test:wrong-password').decode()
    r = client.post(
        XCEP_URL, data=b'<GetPolicies/>',
        headers={'Authorization': f'Basic {token}'},
    )
    assert r.status_code == 400
    assert 'WWW-Authenticate' not in r.headers


def test_get_policies_rejects_non_ascii_credentials_without_crashing(client, xcep_config):
    """hmac.compare_digest on two `str` operands raises TypeError for
    non-ASCII input -- a wrong-but-non-ASCII Basic-auth credential must
    still get the normal SOAP auth-failed fault (400), not an unhandled
    500."""
    token = base64.b64encode('xcep-test:wröng-pässwörd'.encode('utf-8')).decode()
    r = client.post(
        XCEP_URL, data=b'<GetPolicies/>',
        headers={'Authorization': f'Basic {token}'},
    )
    assert r.status_code == 400


def _get_policies_request_with_username_token(username, password, message_id='urn:uuid:test-1'):
    """Build a real GetPolicies request authenticated via WS-Security
    UsernameToken in the SOAP header — the actual mechanism a real
    Windows client uses for this binding (see MS-XCEP's published
    "Initial GetPolicies Client Request" example), as opposed to the
    HTTP Basic fallback ``_basic_auth()`` exercises elsewhere in this file."""
    from services.wstep.soap_envelope import ADDRESSING_NS, WSSE_NS
    envelope = etree.Element(
        '{%s}Envelope' % SOAP_NS,
        nsmap={'s': SOAP_NS, 'a': ADDRESSING_NS, 'wsse': WSSE_NS},
    )
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = message_id
    security = etree.SubElement(header, '{%s}Security' % WSSE_NS)
    token = etree.SubElement(security, '{%s}UsernameToken' % WSSE_NS)
    etree.SubElement(token, '{%s}Username' % WSSE_NS).text = username
    etree.SubElement(token, '{%s}Password' % WSSE_NS).text = password
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    etree.SubElement(body, '{%s}GetPolicies' % XCEP_NS)
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def test_get_policies_authenticates_via_username_token(client, xcep_config):
    """The real mechanism: credentials in a WS-Security UsernameToken in
    the SOAP header, no Authorization header at all. Regression test for
    the bug where this endpoint only accepted HTTP Basic, causing a real
    Windows client (configured for message-level auth) to report
    WS_E_SERVER_REQUIRES_BASIC_AUTH and refuse to enroll."""
    r = client.post(
        XCEP_URL,
        data=_get_policies_request_with_username_token(XCEP_USER, XCEP_PASSWORD),
    )
    assert r.status_code == 200
    root = etree.fromstring(r.data)
    assert len(root.findall(f'.//{{{XCEP_NS}}}policy')) == 1


def test_get_policies_rejects_bad_username_token_credentials(client, xcep_config):
    r = client.post(
        XCEP_URL,
        data=_get_policies_request_with_username_token(XCEP_USER, 'wrong-password'),
    )
    assert r.status_code == 400
    assert 'WWW-Authenticate' not in r.headers


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

    # Real X.509 ExtendedKeyUsage extension DER, referenced by the
    # extension OID (2.5.29.37), not by the EKU purpose OID directly —
    # the purpose OID (serverAuth) is embedded inside the DER value.
    ext_oid_ref = policies[0].find(f'.//{{{XCEP_NS}}}extensions/{{{XCEP_NS}}}extension/{{{XCEP_NS}}}oIDReference')
    assert ext_oid_ref is not None
    ext_value = policies[0].find(f'.//{{{XCEP_NS}}}extensions/{{{XCEP_NS}}}extension/{{{XCEP_NS}}}value')
    assert ext_value is not None and ext_value.text
    import base64 as _b64
    from asn1crypto import x509 as _asn1_x509
    decoded = _asn1_x509.ExtKeyUsageSyntax.load(_b64.b64decode(ext_value.text))
    assert '1.3.6.1.5.5.7.3.1' in [oid.dotted for oid in decoded]  # serverAuth

    # oIDs/oID/group must be an integer per the real schema.
    for group_el in root.findall(f'.//{{{XCEP_NS}}}oID/{{{XCEP_NS}}}group'):
        int(group_el.text)  # raises if not integer-parseable

    # algorithmOIDReference is always nil, confirmed against a real ADCS
    # server's own GetPoliciesResponse (see policy_builder.py's module
    # docstring) -- no RSA algorithm OID entry should appear in the oIDs
    # table at all.
    algo_oid_ref = policies[0].find(
        f'.//{{{XCEP_NS}}}privateKeyAttributes/{{{XCEP_NS}}}algorithmOIDReference'
    )
    assert algo_oid_ref is not None
    assert algo_oid_ref.get('{http://www.w3.org/2001/XMLSchema-instance}nil') == 'true'
    oid_values = {el.text for el in root.findall(f'.//{{{XCEP_NS}}}oID/{{{XCEP_NS}}}value')}
    assert '1.2.840.113549.1.1.1' not in oid_values  # RSA

    # keySpec and cryptoProviders ARE populated (not nil) for an RSA
    # template, per the same real-ADCS trace — leaving these nil let a
    # real Windows client silently fall back to a legacy provider that
    # defaulted to a 1024-bit key regardless of minimalKeyLength.
    key_spec = policies[0].find(f'.//{{{XCEP_NS}}}privateKeyAttributes/{{{XCEP_NS}}}keySpec')
    assert key_spec is not None
    assert key_spec.get('{http://www.w3.org/2001/XMLSchema-instance}nil') != 'true'
    assert key_spec.text == '1'  # AT_KEYEXCHANGE

    providers = policies[0].findall(
        f'.//{{{XCEP_NS}}}privateKeyAttributes/{{{XCEP_NS}}}cryptoProviders/{{{XCEP_NS}}}provider'
    )
    assert len(providers) >= 1
    assert all(p.text for p in providers)

    # cAs/cAReference is an int pointing at cAReferenceID, not the CA's refid.
    ca_reference = policies[0].find(f'.//{{{XCEP_NS}}}cAs/{{{XCEP_NS}}}cAReference')
    assert ca_reference is not None
    ca_reference_id = root.find(f'.//{{{XCEP_NS}}}cA/{{{XCEP_NS}}}cAReferenceID')
    assert ca_reference_id is not None
    assert ca_reference.text == ca_reference_id.text

    # The UsernamePassword binding has no AD identity to build a subject from:
    # every template, machine ones included, announces a client-supplied
    # subject there (0x00010001). The Kerberos binding announces 0x18000000
    # for machine templates (test_wstep_subject_source).
    subject_name_flags = policies[0].find(f'.//{{{XCEP_NS}}}subjectNameFlags')
    assert int(subject_name_flags.text) == (0x00000001 | 0x00010000)

    # generalFlags/GeneralMachineType (0x40) must be set for a web_server
    # template -- real-client regression: leaving this nil made Windows
    # default the template to user-type, which then refused to enroll
    # from a Computer-context request ("This type of certificate can be
    # issued only to a user").
    general_flags = policies[0].find(f'.//{{{XCEP_NS}}}generalFlags')
    assert general_flags is not None
    assert general_flags.get('{http://www.w3.org/2001/XMLSchema-instance}nil') is None
    assert int(general_flags.text) == 0x00000040

    # enroll and autoEnroll are two separate permission bits, mirroring
    # real ADCS's ACL model -- a template not opted into autoenroll_enabled
    # must still allow manual enrollment (enroll=true) but must NOT be
    # offered for unattended autoenrollment (autoEnroll=false), matching
    # this fixture's template which never set autoenroll_enabled.
    permission = policies[0].find(f'.//{{{XCEP_NS}}}permission')
    assert permission.find(f'{{{XCEP_NS}}}enroll').text == 'true'
    assert permission.find(f'{{{XCEP_NS}}}autoEnroll').text == 'false'

    # CAURI is always advertised now, regardless of whether WSTEP is
    # currently enabled -- CAURICollection requires at least one entry
    # (minOccurs="1"), so an empty uris/CAURICollection would itself be
    # schema-invalid. Hitting a disabled WSTEP endpoint just 503s, same as
    # EST/SCEP's "advertised but not configured" pattern.
    cauris = root.findall(f'.//{{{XCEP_NS}}}cAURI')
    assert len(cauris) == 2
    auth_values = {c.find(f'{{{XCEP_NS}}}clientAuthentication').text for c in cauris}
    assert auth_values == {'4', '8'}  # UsernamePassword, ClientCertificate

    # cAs/cA/certificate must be the real CA cert's DER bytes, not empty.
    # CA.crt is stored base64-encoded PEM in the DB -- getting that wrong
    # produces an empty element, which a real Windows client refuses to
    # enroll against (CERTSRV_E_PROPERTY_EMPTY, "The requested property
    # value is empty").
    cert_el = root.find(f'.//{{{XCEP_NS}}}cA/{{{XCEP_NS}}}certificate')
    assert cert_el is not None and cert_el.text
    cert_der = base64.b64decode(cert_el.text)
    from cryptography import x509 as _x509
    parsed_cert = _x509.load_der_x509_certificate(cert_der)
    assert 'XCEP Policy CA' in parsed_cert.subject.rfc4514_string()


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
        previous_value = get_config('xcep_ca_refid')
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
            delete_templates([template_id])
            db.session.commit()
            restore({'xcep_ca_refid': previous_value})


def test_get_policies_autoenroll_reflects_per_template_flag(client, app, create_ca, xcep_config):
    """autoEnroll must be per-template (autoenroll_enabled), independent of
    enroll -- a template with it on gets autoEnroll=true; one without still
    gets enroll=true (can be requested manually) but autoEnroll=false (not
    offered for unattended autoenrollment). Mirrors real ADCS's separate
    Enroll/Autoenroll ACL permission bits."""
    ca_data = create_ca(cn='XCEP Autoenroll CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        previous_value = get_config('xcep_ca_refid')
        _set_config('xcep_ca_refid', ca.refid)

        auto_template = CertificateTemplate(
            name='XCEP Autoenroll Template',
            template_type='client_auth',
            extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}),
            is_active=True,
            autoenroll_enabled=True,
        )
        manual_template = CertificateTemplate(
            name='XCEP Manual-Only Template',
            template_type='client_auth',
            extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}),
            is_active=True,
            autoenroll_enabled=False,
        )
        db.session.add_all([auto_template, manual_template])
        db.session.commit()
        auto_id, manual_id = auto_template.id, manual_template.id

    try:
        r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
        assert r.status_code == 200
        root = etree.fromstring(r.data)
        policies = root.findall(f'.//{{{XCEP_NS}}}policy')
        by_name = {p.find(f'.//{{{XCEP_NS}}}commonName').text: p for p in policies}

        auto_permission = by_name['XCEP Autoenroll Template'].find(f'.//{{{XCEP_NS}}}permission')
        assert auto_permission.find(f'{{{XCEP_NS}}}enroll').text == 'true'
        assert auto_permission.find(f'{{{XCEP_NS}}}autoEnroll').text == 'true'

        manual_permission = by_name['XCEP Manual-Only Template'].find(f'.//{{{XCEP_NS}}}permission')
        assert manual_permission.find(f'{{{XCEP_NS}}}enroll').text == 'true'
        assert manual_permission.find(f'{{{XCEP_NS}}}autoEnroll').text == 'false'
    finally:
        with app.app_context():
            delete_templates([auto_id, manual_id])
            db.session.commit()
            restore({'xcep_ca_refid': previous_value})


def test_get_policies_template_oid_arcs_fit_uint32(client, app, create_ca, xcep_config):
    """A policy OID with a single arc holding a full 128-bit value (the
    ITU-T X.667 ``2.25.<uuid-as-decimal>`` form) makes a real Windows
    client's ``CX509EnrollmentPolicyWebService.GetTemplates()`` silently
    stop building the templates collection after the first policy --
    confirmed by enumerating the COM collection directly, bypassing
    ``get_ItemByName`` and any client-side cache.

    Asserts the structural property that actually matters: every arc of
    every group=9 (policy) OID must fit in 32 bits, matching the shape
    real ADCS's own template OIDs use. Two active templates so a
    regression back to a single giant arc, or any oversized arc, would be
    caught without needing a real client.
    """
    ca_data = create_ca(cn='XCEP OID Arc CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        previous_value = get_config('xcep_ca_refid')
        _set_config('xcep_ca_refid', ca.refid)

        templates = [
            CertificateTemplate(
                name=f'XCEP Arc Template {i}',
                template_type='client_auth',
                key_type='RSA-2048',
                validity_days=90,
                digest='sha256',
                extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}),
                is_active=True,
            )
            for i in range(2)
        ]
        db.session.add_all(templates)
        db.session.commit()
        template_ids = [t.id for t in templates]
        pins = [CATemplatePin(ca_id=ca.id, template_id=tid) for tid in template_ids]
        db.session.add_all(pins)
        db.session.commit()
        pin_ids = [p.id for p in pins]

    try:
        r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
        assert r.status_code == 200
        root = etree.fromstring(r.data)
        policies = root.findall(f'.//{{{XCEP_NS}}}policy')
        assert len(policies) == 2

        policy_oid_values = {
            el.find(f'{{{XCEP_NS}}}value').text
            for el in root.findall(f'.//{{{XCEP_NS}}}oID')
            if el.find(f'{{{XCEP_NS}}}group').text == '9'
        }
        assert len(policy_oid_values) == 2
        for oid in policy_oid_values:
            for arc in oid.split('.'):
                assert int(arc) < 2**32, f'arc {arc!r} in {oid!r} does not fit in uint32'
    finally:
        with app.app_context():
            for pid in pin_ids:
                pin_row = db.session.get(CATemplatePin, pid)
                if pin_row:
                    db.session.delete(pin_row)
            delete_templates(template_ids)
            db.session.commit()
            restore({'xcep_ca_refid': previous_value})


def _fault_code(data):
    return etree.fromstring(data).find(f'.//{{{SOAP_NS}}}Fault/{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Value').text


def test_client_faults_are_sender_faults(client, xcep_config):
    """SOAP 1.2: a fault the request causes is env:Sender, which its HTTP binding sends as 400."""
    for headers, body in (({}, b'<GetPolicies/>'), (_basic_auth(), b'<GetPolicies')):
        r = client.post(XCEP_URL, data=body, headers=headers)
        assert r.status_code == 400, body
        assert _fault_code(r.data) == 's:Sender', body


def test_a_server_failure_is_a_receiver_fault(client, xcep_config, monkeypatch):
    from services.xcep import policy_builder

    def _fail(*_args, **_kwargs):
        raise RuntimeError('database unreachable')
    monkeypatch.setattr(policy_builder, 'build_get_policies_response', _fail)
    r = client.post(XCEP_URL, data=b'<GetPolicies/>', headers=_basic_auth())
    assert r.status_code == 500
    assert _fault_code(r.data) == 's:Receiver'
