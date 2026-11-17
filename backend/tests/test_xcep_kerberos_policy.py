"""Interoperability tests for MS-XCEP's Kerberos-bound CEP endpoint (Phase 3).

No real KDC is available in a unit test environment, so these exercise the
HTTP Negotiate plumbing (config gating, 401 challenge shape, CAURI
advertising) and monkeypatch ``negotiate_auth.authenticate_negotiate`` for
the "ticket already verified" path, rather than minting a real Kerberos
ticket. See ``services/kerberos/negotiate_auth.py``'s module docstring and
memory/project_xcep_wstep_lab_testing.md for the real end-to-end check
against a lab AD domain.
"""
import base64
import json

import pytest
from lxml import etree

from models import CA, CATemplatePin, CertificateTemplate, db
from models.system_config import SystemConfig
from tests.fixtures.templates import delete_templates
from services.kerberos import negotiate_auth
from services.wstep.soap_envelope import SOAP_NS
from tests.windows_profile_support import restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

XCEP_KRB_URL = '/ADPolicyProvider_CEP_Kerberos/service.svc'
XCEP_USERPASS_URL = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
XCEP_USER = 'xcep-krb-test'
XCEP_PASSWORD = 'xcep-krb-password'


def _set_config(key, value):
    set_config(key, value)


@pytest.fixture(scope='module')
def xcep_kerberos_config(app, create_ca):
    ca_data = create_ca(cn='XCEP Kerberos CA')
    keys = ('xcep_enabled', 'xcep_ca_refid', 'xcep_username', 'xcep_password', 'windows_realm')
    with app.app_context():
        previous = snapshot(keys)
        ca = db.session.get(CA, ca_data['id'])
        # The default profile serves the realm of the principals of this file
        _set_config('windows_realm', 'HAGLAND.DOMAIN')
        _set_config('xcep_enabled', 'true')
        _set_config('xcep_ca_refid', ca.refid)
        _set_config('xcep_username', XCEP_USER)
        _set_config('xcep_password', XCEP_PASSWORD)

        template = CertificateTemplate(
            name='XCEP Kerberos Web Server',
            template_type='web_server',
            key_type='RSA-2048',
            validity_days=365,
            digest='sha256',
            dn_template=json.dumps({'CN': '{hostname}'}),
            extensions_template=json.dumps({
                'key_usage': ['digitalSignature', 'keyEncipherment'],
                'extended_key_usage': ['serverAuth'],
            }),
            is_active=True,
        )
        db.session.add(template)
        db.session.commit()
        pin = CATemplatePin(ca_id=ca.id, template_id=template.id)
        db.session.add(pin)
        db.session.commit()
        template_id = template.id

    yield {'ca': ca_data}

    with app.app_context():
        delete_templates([template_id])
        db.session.commit()
        restore(previous)


def _cauri_auth_values(response_bytes):
    root = etree.fromstring(response_bytes)
    cauris = root.findall(f'.//{{{XCEP_NS}}}cAURI')
    return {c.find(f'{{{XCEP_NS}}}clientAuthentication').text for c in cauris}


def test_kerberos_endpoint_503_when_not_configured(client, xcep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: False)
    r = client.post(XCEP_KRB_URL)
    assert r.status_code == 503


def test_kerberos_endpoint_503_when_library_unavailable(client, xcep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: False)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    r = client.post(XCEP_KRB_URL)
    assert r.status_code == 503


def test_kerberos_endpoint_challenges_without_authorization_header(client, xcep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    r = client.post(XCEP_KRB_URL)
    assert r.status_code == 401, r.data
    assert r.headers.get('WWW-Authenticate') == 'Negotiate'


def test_kerberos_endpoint_rejects_failed_negotiation(client, xcep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(
        negotiate_auth, 'authenticate_negotiate',
        lambda auth_header, connection_key: negotiate_auth.NegotiateResult(status='failed', error='bad ticket'),
    )
    r = client.post(XCEP_KRB_URL, headers={'Authorization': 'Negotiate bm90YXJlYWx0b2tlbg=='})
    assert r.status_code == 401, r.data
    assert r.headers.get('WWW-Authenticate') == 'Negotiate'


def test_kerberos_get_policies_succeeds_and_echoes_mutual_auth_token(client, xcep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(
        negotiate_auth, 'authenticate_negotiate',
        lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
            status='authenticated', client_principal='HOST$@HAGLAND.DOMAIN',
            response_token_b64='bXV0dWFsLXRva2Vu',
        ),
    )

    body = f'<s:Envelope xmlns:s="{SOAP_NS}"><s:Body/></s:Envelope>'.encode()
    r = client.post(
        XCEP_KRB_URL, data=body,
        headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
    )
    assert r.status_code == 200
    assert r.headers.get('WWW-Authenticate') == 'Negotiate bXV0dWFsLXRva2Vu'

    auth_values = _cauri_auth_values(r.data)
    assert '2' in auth_values  # AUTH_KERBEROS
    assert '4' in auth_values  # AUTH_USERNAME_PASSWORD, still advertised too
    # The CA builds a machine template's subject from AD on this binding
    flags = etree.fromstring(r.data).find(f'.//{{{XCEP_NS}}}subjectNameFlags')
    assert int(flags.text) == 0x18000000


def _basic_auth():
    token = base64.b64encode(f'{XCEP_USER}:{XCEP_PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def test_kerberos_cauri_omitted_when_not_configured(client, xcep_kerberos_config, monkeypatch):
    """The primary (UsernamePassword) CEP endpoint's CAURI collection
    should not include the Kerberos entry when Kerberos isn't configured --
    it's shared response-building logic (`_handle_get_policies`), so this
    also guards the conditional against regressing for every CEP binding."""
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: False)

    body = f'<s:Envelope xmlns:s="{SOAP_NS}"><s:Body/></s:Envelope>'.encode()
    r = client.post(
        XCEP_USERPASS_URL, data=body,
        headers={**_basic_auth(), 'Content-Type': 'application/soap+xml'},
    )
    assert r.status_code == 200
    assert '2' not in _cauri_auth_values(r.data)  # AUTH_KERBEROS


def test_kerberos_cauri_present_via_userpass_endpoint_when_configured(client, xcep_kerberos_config, monkeypatch):
    """CAURI advertises every configured binding from any CEP endpoint that
    served the response, regardless of which binding authenticated this
    particular request -- matches real ADCS."""
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)

    body = f'<s:Envelope xmlns:s="{SOAP_NS}"><s:Body/></s:Envelope>'.encode()
    r = client.post(
        XCEP_USERPASS_URL, data=body,
        headers={**_basic_auth(), 'Content-Type': 'application/soap+xml'},
    )
    assert r.status_code == 200
    assert '2' in _cauri_auth_values(r.data)  # AUTH_KERBEROS


def test_kerberos_malformed_request_is_a_sender_fault(client, xcep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate', lambda auth_header, connection_key:
                        negotiate_auth.NegotiateResult(status='authenticated', client_principal='HOST$@HAGLAND.DOMAIN'))
    r = client.post(XCEP_KRB_URL, data=b'<s:Envelope', headers={
        'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    assert r.status_code == 400
    fault = etree.fromstring(r.data).find(f'.//{{{SOAP_NS}}}Fault')
    assert fault.find(f'{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Value').text == 's:Sender'
