"""Kerberos requests routed by realm (SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL): a principal is
served by the enabled profile of its own realm, on the CEP as on the CES, never by the default;
each refusal is an env:Sender fault (never a 401) and an audit entry."""
import ast
import base64
import json
import types
import uuid
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from lxml import etree

from models import (CA, AuditLog, CATemplatePin, Certificate, CertificateTemplate, WindowsEnrollmentProfile,
                    WindowsProfileTemplate, db)
from services.ad_connector import lookup as ad_lookup
from services.kerberos import negotiate_auth
from services.wstep import CES_CERTIFICATE_PATH, CES_KERBEROS_PATH, CES_USERNAME_PASSWORD_PATH
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS
from services.xcep.policy_builder import _policy_id_for_ca, _policy_oid_for_template
from tests.ad_connector_support import add_connector
from tests.fixtures.templates import delete_templates
from tests.protocol_approval_support import approval_policy, approve, requests_of
from tests.test_wstep_kerberos_issue import _build_rst, _issued_cert_from_rstr
from tests.test_wstep_renew_tls import _cmc_renewal, _renewal_csr, _rst
from tests.windows_profile_support import connectors_kept, default_profile, restore, set_config, snapshot

CEP_KERBEROS = '/ADPolicyProvider_CEP_Kerberos/service.svc'
CEP_USERNAME = '/ADPolicyProvider_CEP_UsernamePassword/service.svc'
XCEP_NS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollmentpolicy'
NEGOTIATE = {'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'}
REALM_NOT_SERVED = "The requester's realm is not served"
SID = 'S-1-5-21-1-2-3-1104'
BACKEND = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _get_policies(message_id='urn:uuid:c04-0000-4000-8000-000000000001', username=None, password=None):
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap={'s': SOAP_NS, 'a': ADDRESSING_NS, 'wsse': WSSE_NS})
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = message_id
    if username:
        token = etree.SubElement(etree.SubElement(header, '{%s}Security' % WSSE_NS),
                                 '{%s}UsernameToken' % WSSE_NS)
        etree.SubElement(token, '{%s}Username' % WSSE_NS).text = username
        etree.SubElement(token, '{%s}Password' % WSSE_NS).text = password
    etree.SubElement(etree.SubElement(envelope, '{%s}Body' % SOAP_NS), '{%s}GetPolicies' % XCEP_NS)
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def _csr(cn, key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))


def _fault(response):
    root = etree.fromstring(response.data)
    return (response.status_code, root.find(f'.//{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Value').text,
            root.find(f'.//{{{SOAP_NS}}}Reason/{{{SOAP_NS}}}Text').text)


def _policy(response):
    """(policyID, template names) of a GetPoliciesResponse."""
    assert response.status_code == 200, response.data
    root = etree.fromstring(response.data)
    return (root.find(f'.//{{{XCEP_NS}}}policyID').text,
            sorted(e.text for e in root.iter(f'{{{XCEP_NS}}}commonName')))


def _template_oid(cert):
    return cert.extensions.get_extension_for_class(x509.MSCertificateTemplate).value.template_id.dotted_string


def _profile(name):
    return WindowsEnrollmentProfile.query.filter_by(name=name).one()


@pytest.fixture
def world(app, create_ca, monkeypatch):
    """Profiles A and B (realms C04A.TEST, C04B.TEST), each with its CA, template and
    connector; a CA S offering two templates of the same EKU. The directory is simulated:
    ``state['asked']`` lists (connector id, what) for each question it answers."""
    cas = {k: create_ca(cn=f'C04 {k} CA') for k in ('A', 'B', 'S')}
    state = {'principal': None, 'groups': set(), 'asked': []}
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate', lambda header, key: negotiate_auth.NegotiateResult(
        status='authenticated', client_principal=state['principal']))
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid',
                        lambda config, sam: state['asked'].append((config.id, 'sid')) or SID)
    monkeypatch.setattr(ad_lookup, 'is_member_of_group', lambda config, sam, group: state['asked'].append(
        (config.id, group)) or group in state['groups'])
    template_ids = []
    with connectors_kept(app):
        with app.app_context():
            saved = snapshot(('xcep_enabled', 'wstep_enabled', 'xcep_ca_refid', 'wstep_ca_refid', 'windows_realm'))
            set_config('xcep_enabled', 'true', commit=False)
            set_config('wstep_enabled', 'true', commit=False)
            # A default that could serve, so that falling back to it would be seen
            for key in ('xcep_ca_refid', 'wstep_ca_refid'):
                set_config(key, cas['S']['refid'], commit=False)
            set_config('windows_realm', None, commit=False)
            default = default_profile()
            was_enabled, default.enabled = default.enabled, True
            names = {}
            for key, template_names in (('A', ['A User']), ('B', ['B User']), ('S', ['S One', 'S Two'])):
                for name in template_names:
                    t = CertificateTemplate(name=f'C04 {name}', template_type='usr_cert', key_type='RSA-2048',
                                            validity_days=30, digest='sha256', is_active=True,
                                            extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
                    db.session.add(t)
                    db.session.flush()
                    db.session.add(CATemplatePin(ca_id=cas[key]['id'], template_id=t.id))
                    template_ids.append(t.id)
                    names[name] = t.id
            connectors = {k: add_connector(f'c04-{k.lower()}', server=f'dc.c04{k.lower()}.test',
                                           base_dn=f'DC=c04{k.lower()},DC=test', bind_dn='svc', enabled=True).id
                          for k in ('A', 'B')}
            for k in ('A', 'B'):
                db.session.add(WindowsEnrollmentProfile(
                    name=f'c04-{k.lower()}', realm=f'C04{k}.TEST', enabled=True, connector_id=connectors[k],
                    issuing_ca_refid=cas[k]['refid'], validity_days=30))
            db.session.commit()
        state.update(cas=cas, templates=names, connectors=connectors)
        try:
            yield state
        finally:
            with app.app_context():
                ids = [p.id for p in WindowsEnrollmentProfile.query.filter(
                    WindowsEnrollmentProfile.name.like('c04-%'))]
                Certificate.query.filter(Certificate.windows_profile_id.in_(ids)).update(
                    {'windows_profile_id': None}, synchronize_session=False)
                WindowsProfileTemplate.query.filter(WindowsProfileTemplate.profile_id.in_(ids)).delete(
                    synchronize_session=False)
                WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.id.in_(ids)).delete(
                    synchronize_session=False)
                CATemplatePin.query.filter(CATemplatePin.template_id.in_(template_ids)).delete(
                    synchronize_session=False)
                db.session.commit()
                delete_templates(template_ids)
                default_profile().enabled = was_enabled
                db.session.commit()
                restore(saved)


def _as(state, principal):
    state['principal'] = principal


def _issue(client, state, principal, cn='c04-host'):
    _as(state, principal)
    return client.post(CES_KERBEROS_PATH, data=_build_rst(_csr(cn)), headers=NEGOTIATE)


def _policy_of(client, state, principal):
    _as(state, principal)
    return client.post(CEP_KERBEROS, data=_get_policies(), headers=NEGOTIATE)


def _ca(state, key):
    return db.session.get(CA, state['cas'][key]['id'])


def test_each_realm_gets_the_policy_and_the_ca_of_its_own_profile(app, client, world):
    """Criterion 1: CA, policyID and templates of A for A's principal, of B for B's."""
    for key, other in (('A', 'B'), ('B', 'A')):
        policy_id, names = _policy(_policy_of(client, world, f'host{key}$@C04{key}.TEST'))
        with app.app_context():
            assert policy_id == _policy_id_for_ca(_ca(world, key)) != _policy_id_for_ca(_ca(world, other))
        assert names == [f'C04 {key} User']
        r = _issue(client, world, f'user{key}@C04{key}.TEST')
        cert = _issued_cert_from_rstr(r.data)
        with app.app_context():
            ca = _ca(world, key)
            assert cert.issuer == x509.load_pem_x509_certificate(base64.b64decode(ca.crt)).subject
            template = db.session.get(CertificateTemplate, world['templates'][f'{key} User'])
            assert _template_oid(cert) == _policy_oid_for_template(ca, template)
        assert world['asked'] == [(world['connectors'][key], 'sid')]
        world['asked'].clear()


@pytest.mark.parametrize('principal', ['hostc$@C04C.TEST', 'hosta$@c04a.test', 'hosta$@C04a.TEST', 'hosta$'],
                         ids=['realm-without-profile', 'lowercase', 'mixed-case', 'no-realm'])
def test_a_realm_without_its_own_profile_is_refused_on_cep_and_ces(app, client, world, principal):
    """Criteria 2 and 6: compared exactly (RFC 4120 §6.1), never served by another profile or the
    default; the authentication succeeded, so an env:Sender fault and never a 401 (RFC 4559)."""
    for response in (_policy_of(client, world, principal), _issue(client, world, principal)):
        assert _fault(response) == (400, 's:Sender', REALM_NOT_SERVED)
        assert b'policyID' not in response.data and b'BinarySecurityToken' not in response.data
    assert world['asked'] == []


def test_a_disabled_profile_refuses_its_realm_and_the_other_is_served(app, client, world):
    """Criterion 3."""
    with app.app_context():
        _profile('c04-b').enabled = False
        db.session.commit()
    for response in (_policy_of(client, world, 'hostb$@C04B.TEST'), _issue(client, world, 'userb@C04B.TEST')):
        assert _fault(response) == (400, 's:Sender', REALM_NOT_SERVED)
    assert _policy(_policy_of(client, world, 'hosta$@C04A.TEST'))[1] == ['C04 A User']
    _issued_cert_from_rstr(_issue(client, world, 'usera@C04A.TEST').data)


def test_the_group_and_pinned_fields_of_the_profile_replace_the_template_s(app, client, world):
    """Criterion 4 (A3): a host of A in B's group only is refused; B's pins land on B's certificates."""
    with app.app_context():
        _profile('c04-a').allowed_ad_group = 'C04 A Enroll'
        b = _profile('c04-b')
        b.allowed_ad_group, b.pinned_subject_fields = 'C04 B Enroll', json.dumps({'O': 'B Org', 'OU': 'B Site'})
        # The template's own group and pins are replaced, not added to
        template = db.session.get(CertificateTemplate, world['templates']['B User'])
        template.allowed_ad_group = 'Template Group'
        template.pinned_subject_fields = json.dumps({'O': 'Template Org', 'L': 'Template City'})
        db.session.commit()
    world['groups'] = {'C04 B Enroll'}
    assert _fault(_issue(client, world, 'usera@C04A.TEST')) == (
        400, 's:Sender', 'Requester is not authorized to enroll against this profile')
    assert (world['connectors']['A'], 'C04 A Enroll') in world['asked']
    world['asked'].clear()
    cert = _issued_cert_from_rstr(_issue(client, world, 'userb@C04B.TEST', cn='c04-b-host').data)
    assert (world['connectors']['B'], 'C04 B Enroll') in world['asked']
    assert all(group != 'Template Group' for _id, group in world['asked'])
    assert cert.subject.rfc4514_string() == 'CN=c04-b-host,OU=B Site,O=B Org'


def test_two_profiles_on_one_ca_never_lend_each_other_templates_groups_or_pins(app, client, world):
    """Criterion 7: A offers S One, B offers S Two (same EKU: without the profile's list both
    would match S One); B's group and pins never reach A."""
    with app.app_context():
        for name, template in (('c04-a', 'S One'), ('c04-b', 'S Two')):
            profile = _profile(name)
            profile.issuing_ca_refid = world['cas']['S']['refid']
            db.session.add(WindowsProfileTemplate(profile_id=profile.id, template_id=world['templates'][template]))
        b = _profile('c04-b')
        b.allowed_ad_group, b.pinned_subject_fields = 'C04 B Enroll', json.dumps({'O': 'B Org'})
        db.session.commit()
    world['groups'] = {'C04 B Enroll'}
    for key, template in (('A', 'S One'), ('B', 'S Two')):
        policy_id, names = _policy(_policy_of(client, world, f'host{key}$@C04{key}.TEST'))
        assert names == [f'C04 {template}']
        cert = _issued_cert_from_rstr(_issue(client, world, f'user{key}@C04{key}.TEST', cn=f'c04-{key}').data)
        with app.app_context():
            ca = _ca(world, 'S')
            assert policy_id == _policy_id_for_ca(ca)
            assert _template_oid(cert) == _policy_oid_for_template(
                ca, db.session.get(CertificateTemplate, world['templates'][template]))
        pinned = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
        assert [a.value for a in pinned] == (['B Org'] if key == 'B' else [])
        groups = [group for _id, group in world['asked'] if group != 'sid']
        assert groups == (['C04 B Enroll'] if key == 'B' else [])
        world['asked'].clear()


# The functions that recompute the templates of a CA or read a connector, with what calls them
_GUARDED = {'_match_template', '_named_template', '_ca_templates', '_policy_oid_cas', '_template_oid_for',
            '_renewal_template', '_required_enroll_acl_groups', '_required_pinned_subject_fields',
            '_user_ad_derivation_enabled', '_directory_subject', '_resolve_templates_for_ca', '_sign_renewal',
            'issue', 'renew', 'renew_with_client_certificate', 'make_gate', 'build_get_policies_response'}
_WSTEP_DEFS = _GUARDED - {'_resolve_templates_for_ca', 'make_gate', 'build_get_policies_response'}
_SOURCES = ('services/wstep/wstep_service.py', 'services/xcep/policy_builder.py', 'services/wstep/approval.py',
            'api/wstep_protocol.py', 'api/xcep_protocol.py')


def _called(node):
    func = node.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def test_every_call_that_recomputes_templates_or_reads_a_connector_names_its_profile():
    """Criterion 7, by the calls in the code (AST), never by the text of a function."""
    missing, fallback = [], []
    for source in _SOURCES:
        tree = ast.parse((BACKEND / source).read_text(), filename=source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called(node)
            # 'issue' and 'renew' of the WSTEP service only: other modules have their own
            service_call = not (name in ('issue', 'renew') and isinstance(node.func, ast.Attribute)
                                and getattr(node.func.value, 'id', None) != 'wstep_service')
            if name in _GUARDED and service_call and 'profile' not in {k.arg for k in node.keywords}:
                missing.append(f'{source}:{node.lineno} {name}')
            # The approval's own fallback names the default for a request held before profiles
            if source in _SOURCES[:2] and name in ('serving_profile', 'default_profile',
                                                           'default_connector', 'lowest_connector'):
                fallback.append(f'{source}:{node.lineno} {name}')
    assert missing == [] and fallback == []
    tree = ast.parse((BACKEND / _SOURCES[0]).read_text())
    defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in _WSTEP_DEFS:
        args = defs[name].args
        index = [a.arg for a in args.kwonlyargs].index('profile')
        assert args.kw_defaults[index] is None, f'{name}: the profile has a default'


@pytest.fixture
def held_on_b(app, world):
    with approval_policy(app, world['cas']['B']['id'], 'c04-held-on-b') as policy_id:
        yield policy_id


def test_an_approval_issues_under_the_profile_it_was_held_for(app, client, auth_client, world, held_on_b):
    """Criterion 5: held on B, approved: CA and connector of B; the profile gone meanwhile: refused."""
    r = _issue(client, world, 'userb@C04B.TEST', cn='c04-held')
    assert b'Pending' in r.data, r.data
    (approval_id, _status, data, _cert), = requests_of(app, held_on_b, 'wstep_request')
    with app.app_context():
        assert data['profile_id'] == _profile('c04-b').id
    world['asked'].clear()
    approve(auth_client, approval_id)
    (_id, status, _data, cert_id), = requests_of(app, held_on_b, 'wstep_request')
    with app.app_context():
        assert db.session.get(Certificate, cert_id).caref == world['cas']['B']['refid']
    assert world['asked'] == [(world['connectors']['B'], 'sid')]

    _issue(client, world, 'userb@C04B.TEST', cn='c04-held-gone')
    second = [row for row in requests_of(app, held_on_b, 'wstep_request') if row[1] == 'pending']
    with app.app_context():
        profile = _profile('c04-b')
        profile.name = 'c04-b-gone'
        db.session.delete(profile)
        db.session.commit()
    r = auth_client.post(f'/api/v2/approvals/{second[0][0]}/approve', json={'comment': 'ok'})
    body = r.get_json()
    assert body['message'] == 'Request closed', body
    assert body['data']['issue_error'] == 'The Windows enrollment profile c04-b no longer exists'


def test_a_request_held_before_profiles_were_recorded_replays_the_default(app, world):
    """No profile_id: held when the default served every request; a recorded one is never replaced."""
    from services.wstep.approval import _held_profile
    with app.app_context():
        assert _held_profile({}) is default_profile()
        assert _held_profile({'profile_id': _profile('c04-b').id}) is _profile('c04-b')
        assert _held_profile({'profile_id': None}) is None


@pytest.fixture
def default_profile_without_realm(app, world):
    """The default profile as A1 leaves it (no realm, the world sets its CA), its UsernamePassword account set."""
    from utils.password_hash import hash_password
    keys = ('xcep_username', 'xcep_password')
    with app.app_context():
        saved = snapshot(keys)
        set_config('xcep_username', 'c04-cep', commit=False)
        set_config('xcep_password', hash_password('c04-cep-password'))
    yield
    with app.app_context():
        restore(saved)


def test_a_default_profile_without_realm_refuses_kerberos_and_serves_its_account(
        app, client, world, default_profile_without_realm):
    """Criterion 8 (A1): the same fault as an unknown realm; UsernamePassword still served (A2)."""
    for principal in ('host$@C04C.TEST', 'host$@'):
        for response in (_policy_of(client, world, principal), _issue(client, world, principal)):
            assert _fault(response) == (400, 's:Sender', REALM_NOT_SERVED)
    r = client.post(CEP_USERNAME, data=_get_policies(username='c04-cep', password='c04-cep-password'))
    with app.app_context():
        assert _policy(r)[0] == _policy_id_for_ca(_ca(world, 'S'))
    # The Kerberos CES is not announced by a profile that serves no Kerberos client
    auths = {e.text for e in etree.fromstring(r.data).iter(f'{{{XCEP_NS}}}clientAuthentication')}
    assert auths == {'4', '8'}


def _audits(app, floor):
    with app.app_context():
        return [(a.action, a.username, a.resource_name, a.details, a.success)
                for a in AuditLog.query.filter(AuditLog.id > floor).order_by(AuditLog.id)]


def _top_audit(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def test_each_refusal_is_audited_with_realm_profile_and_reason(app, client, world, caplog):
    """Criterion 9: an unknown realm, a disabled profile and a group each give an entry; a policy
    served gives none, its principal goes to the INFO log."""
    import logging
    floor = _top_audit(app)
    with caplog.at_level(logging.INFO):
        _policy(_policy_of(client, world, 'hosta$@C04A.TEST'))
    assert _audits(app, floor) == []
    assert any(r.levelno == logging.INFO and 'hosta$@C04A.TEST' in r.getMessage() for r in caplog.records)

    _policy_of(client, world, 'hostc$@C04C.TEST')
    with app.app_context():
        _profile('c04-b').enabled = False
        _profile('c04-a').allowed_ad_group = 'C04 A Enroll'
        db.session.commit()
    _issue(client, world, 'userb@C04B.TEST')
    _issue(client, world, 'usera@C04A.TEST')
    rows = _audits(app, floor)
    assert [(action, user, name, ok) for action, user, name, _d, ok in rows] == [
        ('windows_enrollment.refused', 'hostc$@C04C.TEST', None, False),
        ('windows_enrollment.refused', 'userb@C04B.TEST', 'c04-b', False),
        ('windows_enrollment.refused', 'usera@C04A.TEST', 'c04-a', False)]
    details = [d for _a, _u, _n, d, _ok in rows]
    assert 'CEP' in details[0] and 'no profile serves this realm' in details[0] and 'realm C04C.TEST' in details[0]
    assert 'CES' in details[1] and 'disabled' in details[1] and 'realm C04B.TEST, profile c04-b' in details[1]
    assert 'not authorized' in details[2] and 'realm C04A.TEST, profile c04-a' in details[2]


def test_a_kerberos_renewal_is_audited_as_a_renewal(app, client, world):
    """A request signed by a certificate of the profile's CA renews it: certificate.renewed with
    the old serial; an initial enrollment stays certificate.issued, both with profile and realm."""
    from services.ca_service import CAService
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with app.app_context():
        pem, _serial = CAService.sign_csr_from_crypto(ca=_ca(world, 'A'), csr=_csr('c04-renewed', key),
                                                      validity_days=30, source='test')
    old = x509.load_pem_x509_certificate(pem.encode())
    floor = _top_audit(app)
    _as(world, 'usera@C04A.TEST')
    # As Windows renews: the new key signs by its identifier, the renewed certificate beside it
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    body = _rst(_cmc_renewal(_renewal_csr(old, new_key), [(new_key, None), (key, old)]))
    r = client.post(CES_KERBEROS_PATH, data=body, headers=NEGOTIATE)
    assert r.status_code == 200, r.data
    new = _issued_cert_from_rstr(r.data)
    _issued_cert_from_rstr(_issue(client, world, 'usera@C04A.TEST', cn='c04-first').data)
    (renewed, issued) = _audits(app, floor)
    assert renewed[0] == 'certificate.renewed' and renewed[1] == 'usera@C04A.TEST'
    assert f'old serial {old.serial_number}, new serial {new.serial_number}' in renewed[3]
    assert 'profile c04-a, realm C04A.TEST' in renewed[3]
    assert issued[0] == 'certificate.issued' and 'profile c04-a, realm C04A.TEST' in issued[3]


@pytest.fixture
def single_profile(app, create_ca):
    """An installation with one profile, the default, whose realm is that of its hosts."""
    from tests.windows_profile_support import default_profile
    ca = create_ca(cn='C04 single CA')
    keys = ('windows_realm', 'xcep_ca_refid', 'xcep_enabled', 'wstep_enabled')
    with app.app_context():
        saved = snapshot(keys)
        default_profile(create=True).enabled = True
        for key, value in (('windows_realm', 'C04ONE.TEST'), ('xcep_ca_refid', ca['refid']),
                           ('xcep_enabled', 'true'), ('wstep_enabled', 'true')):
            set_config(key, value, commit=False)
        t = CertificateTemplate(name='C04 single User', template_type='usr_cert', key_type='RSA-2048',
                                validity_days=30, digest='sha256', is_active=True,
                                extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
        db.session.add(t)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=ca['id'], template_id=t.id))
        db.session.commit()
        template_id = t.id
    yield ca
    with app.app_context():
        delete_templates([template_id])
        db.session.commit()
        restore(saved)


def test_a_single_profile_install_answers_get_policies_byte_for_byte_as_before(app, client, single_profile,
                                                                             monkeypatch):
    """Criterion 10: the bytes the code before routing built (api/xcep_protocol.py before C-04: the
    default's policy CA, every active template, the three CES URIs), with the same MessageID."""
    from services.wstep import soap_envelope
    from services.xcep.policy_builder import (AUTH_CLIENT_CERTIFICATE, AUTH_KERBEROS, AUTH_USERNAME_PASSWORD,
                                              build_get_policies_response)
    fixed = uuid.UUID('00000000-0000-4000-8000-000000000c04')
    monkeypatch.setattr(soap_envelope, 'uuid', types.SimpleNamespace(uuid4=lambda: fixed))
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate', lambda header, key: negotiate_auth.NegotiateResult(
        status='authenticated', client_principal='WS01$@C04ONE.TEST'))
    message_id = 'urn:uuid:c04-0000-4000-8000-0000000000aa'
    with app.test_request_context(CEP_KERBEROS, base_url='http://localhost'):
        from flask import request
        base = request.url_root.rstrip('/')
        uris = [(AUTH_USERNAME_PASSWORD, f'{base}{CES_USERNAME_PASSWORD_PATH}', False),
                (AUTH_CLIENT_CERTIFICATE, f'{base}{CES_CERTIFICATE_PATH}', True),
                (AUTH_KERBEROS, f'{base}{CES_KERBEROS_PATH}', False)]
        before = build_get_policies_response(
            db.session.get(CA, single_profile['id']), CertificateTemplate.query.filter_by(is_active=True).all(),
            enrollment_uris=uris, message_id=message_id, ad_identity=True)
    r = client.post(CEP_KERBEROS, data=_get_policies(message_id), headers=NEGOTIATE)
    assert r.status_code == 200, r.data
    assert r.data == before


def test_upgrade_note_says_other_realms_are_refused():
    """Criterion 11: the sentence C-01 took out of the Windows enrollment note, back as it was."""
    note = (BACKEND.parent / 'UPGRADE.md').read_text()
    assert REFUSAL_SENTENCE in note


REFUSAL_SENTENCE = ('Kerberos clients of any other realm, such as a trusted forest served while the connector '
                    'was disabled, are refused until a profile serves their realm.')


@pytest.mark.parametrize('raw', ['{}', '{"O": ""}', '{"CN": "x"}', 'not json', '[]', '"O"'])
def test_a_profile_pinning_nothing_usable_keeps_the_template_s_pins(raw):
    """A3: only parsed, known, non-empty fields replace the template's; anything else never raises."""
    from services.wstep.wstep_service import _required_pinned_subject_fields
    template = types.SimpleNamespace(pinned_subject_fields=json.dumps({'O': 'Template Org'}))
    profile = types.SimpleNamespace(pinned_subject_fields=raw)
    assert _required_pinned_subject_fields(None, template, profile=profile) == {'O': 'Template Org'}
