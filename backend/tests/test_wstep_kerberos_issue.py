"""Interoperability tests for MS-WSTEP's Kerberos-bound CES endpoint (Phase 3).

Same constraint as test_xcep_kerberos_policy.py: no real KDC in a unit test
environment, so ``negotiate_auth.authenticate_negotiate`` is monkeypatched
for the "ticket already verified" path. Real end-to-end verification is a
lab AD exercise (see memory/project_xcep_wstep_lab_testing.md).
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID
from lxml import etree

from tests.ad_connector_support import clear_connectors, mount_connector
from models import CA, ADConnectorConfig, AuditLog, Certificate, db
from models.certificate_template import CertificateTemplate
from models.system_config import SystemConfig
from tests.fixtures.templates import delete_templates, template_ids_named, templates_created_here_removed
from services.ad_connector import lookup as ad_lookup
from services.kerberos import negotiate_auth
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WST_NS, WSSE_NS
from utils.upn_san import extract_upns_from_san_list
from tests.windows_profile_support import connectors_kept, restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

ISSUE_URL = '/ADCertificateService_CES_Kerberos/service.svc'
KERBEROS_PRINCIPAL = 'HOST$@HAGLAND.DOMAIN'


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


def _set_config(key, value):
    set_config(key, value)


@pytest.fixture(autouse=True)
def _connectors_put_back(app):
    with connectors_kept(app):
        yield


@pytest.fixture
def no_connector_serving(app):
    """No enabled connector, whatever another file left: none checks the requester's realm."""
    with app.app_context():
        ADConnectorConfig.query.update({'enabled': False})
        db.session.commit()


@pytest.fixture(scope='module')
def wstep_kerberos_config(app, create_ca):
    ca_data = create_ca(cn='WSTEP Kerberos CA')
    keys = ('wstep_enabled', 'wstep_ca_refid', 'wstep_validity_days', 'windows_realm')
    with app.app_context():
        previous = snapshot(keys)
        ca = db.session.get(CA, ca_data['id'])
        # The default profile serves the realm of the principals of this file
        _set_config('windows_realm', 'HAGLAND.DOMAIN')
        _set_config('wstep_enabled', 'true')
        _set_config('wstep_ca_refid', ca.refid)
        _set_config('wstep_validity_days', '30')

    yield ca_data

    with app.app_context():
        restore(previous)


def _make_csr(common_name='machine.hagland.domain'):
    """A manual request asking for clientAuth, the EKU of the Enroll ACL template."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ).add_extension(
        x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False,
    ).sign(key, hashes.SHA256())
    return csr, key


def _make_naked_csr():
    """No CN, no SAN -- what real Windows GPO machine autoenrollment
    submits, trusting the CA to derive the subject from AD."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([])
    ).sign(key, hashes.SHA256())
    return csr, key


def _build_rst(csr, message_id='urn:uuid:test-krb-rst-1'):
    NSMAP = {'s': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS, 'wsse': WSSE_NS}
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = message_id
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    etree.SubElement(rst, '{%s}TokenType' % WST_NS).text = (
        'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3'
    )
    etree.SubElement(rst, '{%s}RequestType' % WST_NS).text = (
        'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'
    )
    bst = etree.SubElement(
        rst, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType='http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10',
        EncodingType='base64',
    )
    bst.text = base64.b64encode(csr.public_bytes(Encoding.DER)).decode()
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def _issued_cert_from_rstr(response_bytes):
    root = etree.fromstring(response_bytes)
    bst_el = root.find(f'.//{{{WST_NS}}}RequestedSecurityToken/{{{WSSE_NS}}}BinarySecurityToken')
    assert bst_el is not None and bst_el.text
    return x509.load_der_x509_certificate(base64.b64decode(bst_el.text))


def _authenticated_result(token_b64=None):
    return negotiate_auth.NegotiateResult(
        status='authenticated', client_principal=KERBEROS_PRINCIPAL, response_token_b64=token_b64,
    )


def test_issue_503_when_not_configured(client, wstep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: False)
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers={'Authorization': 'Negotiate dG9rZW4='})
    assert r.status_code == 503


def test_issue_challenges_without_authorization_header(client, wstep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr))
    assert r.status_code == 401, r.data
    assert r.headers.get('WWW-Authenticate') == 'Negotiate'


def test_issue_rejects_failed_negotiation(client, wstep_kerberos_config, monkeypatch):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(
        negotiate_auth, 'authenticate_negotiate',
        lambda auth_header, connection_key: negotiate_auth.NegotiateResult(status='failed', error='bad ticket'),
    )
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers={'Authorization': 'Negotiate dG9rZW4='})
    assert r.status_code == 401, r.data


def test_issue_succeeds_with_authenticated_negotiation(client, app, wstep_kerberos_config, monkeypatch,
                                                       no_connector_serving):
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(
        negotiate_auth, 'authenticate_negotiate',
        lambda auth_header, connection_key: _authenticated_result('bXV0dWFsLXRva2Vu'),
    )
    # Strong cert mapping (KB5014754) is unconditional whenever AD Connector
    # is configured+enabled; no_connector_serving turns off any left by another file.
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

    # A template whose subject the client supplies: a machine template's comes from AD
    _configure_acl_template(app, None, wstep_kerberos_config['id'])
    try:
        csr, key = _make_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
    finally:
        _clear_acl_template(app)
    assert r.status_code == 200
    assert r.headers.get('WWW-Authenticate') == 'Negotiate bXV0dWFsLXRva2Vu'

    cert = _issued_cert_from_rstr(r.data)
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()

    with app.app_context():
        log = (AuditLog.query
               .filter_by(action='certificate.issued', username=KERBEROS_PRINCIPAL)
               .order_by(AuditLog.id.desc())
               .first())
        assert log is not None


def test_issue_resolves_the_requester_in_the_connector_of_the_default_profile(client, app, wstep_kerberos_config,
                                                                              monkeypatch, no_connector_serving):
    from tests.ad_connector_support import add_connector
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: _authenticated_result('bXV0dWFsLXRva2Vu'))
    asked = []
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid',
                        lambda config, sam_account_name: asked.append(config.id) or 'S-1-5-21-1-2-3-1000')
    with app.app_context():
        # The lowest id is a foreign realm: using it would refuse the requester
        mount_connector(name='forest-a', server='dc.a.example', base_dn='DC=a,DC=example', bind_dn='svc', enabled=True)
        second = add_connector('forest-b', server='dc1.hagland.domain', base_dn='DC=hagland,DC=domain',
                               bind_dn='svc', enabled=True, link=True)
        second_id = second.id
    _configure_acl_template(app, None, wstep_kerberos_config['id'])
    try:
        csr, _key = _make_csr()
        r = client.post(ISSUE_URL, data=_build_rst(csr),
                        headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    finally:
        _clear_acl_template(app)
    assert r.status_code == 200, r.data
    assert asked == [second_id]


def _configure_ad_connector(app):
    with app.app_context():
        mount_connector(server='dc1.hagland.domain', base_dn='DC=hagland,DC=domain',
                        bind_dn='svc-ucm', enabled=True)


def _clear_ad_derived_templates(app):
    """Remove any leftover ad_derived_subject template from an earlier test
    in this module-scoped app/db -- without this, a test asserting
    derivation is rejected when nothing has opted in could false-pass/fail
    depending on test execution order."""
    with app.app_context():
        delete_templates(template_ids_named('Test AD User Template'))
        db.session.commit()


def _configure_ad_derived_user_template(app, ca_id):
    """An active template with ad_derived_subject=True -- the per-template
    opt-in wstep_service._user_ad_derivation_enabled gates user-branch
    derivation on -- pinned to ``ca_id`` beside the class's anchor."""
    from models import CATemplatePin

    with app.app_context():
        delete_templates(template_ids_named('Test AD User Template'))
        template = CertificateTemplate(
            name='Test AD User Template', template_type='client_auth',
            extensions_template='{}', is_active=True, ad_derived_subject=True,
        )
        db.session.add(template)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=ca_id, template_id=template.id))
        db.session.commit()


_NAKED_ANCHOR = 'Test Naked CSR Anchor'


@pytest.fixture(scope='class')
def _ca_offers_only_its_templates(app, wstep_kerberos_config):
    """Pins a clientAuth template, which a naked CSR does not match, to the CA:
    the CA then offers only what the class pins, not every active template of the database."""
    import json

    from models import CATemplatePin

    with app.app_context():
        delete_templates(template_ids_named(_NAKED_ANCHOR))
        anchor = CertificateTemplate(
            name=_NAKED_ANCHOR, template_type='client_auth', is_active=True,
            extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}),
        )
        db.session.add(anchor)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=wstep_kerberos_config['id'], template_id=anchor.id))
        db.session.commit()
    yield
    with app.app_context():
        delete_templates(template_ids_named(_NAKED_ANCHOR, 'Test AD User Template'))
        db.session.commit()


@pytest.mark.usefixtures('_ca_offers_only_its_templates')
class TestNakedCsrSubjectDerivation:
    """Real Windows GPO machine autoenrollment submits a CSR with no CN and
    no SAN for machine templates, trusting the CA to derive the subject
    from AD -- see services/ad_connector/lookup.py and
    wstep_service.issue's kerberos_principal handling."""

    def test_naked_csr_with_successful_ad_lookup_gets_derived_subject(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        _configure_ad_connector(app)
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(
            ad_lookup, 'lookup_computer_dns_hostname',
            lambda _config, sam_account_name: 'win11.hagland.domain',
        )
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        csr, key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 200

        cert = _issued_cert_from_rstr(r.data)
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'win11.hagland.domain'
        assert cert.public_key().public_numbers() == key.public_key().public_numbers()

        with app.app_context():
            db_cert = Certificate.query.filter_by(serial_number=str(cert.serial_number)).first()
            assert db_cert is not None
            assert db_cert.subject_cn == 'win11.hagland.domain'

    def test_naked_csr_with_failed_ad_lookup_still_rejected(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname', lambda _config, sam_account_name: None)

        csr, _key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 400

    def test_naked_csr_with_realm_mismatch_still_rejected(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """A principal from a realm other than the one the AD Connector is
        configured against must never reach the AD lookup at all --
        sAMAccountName alone isn't globally unique across realms, so
        skipping this check could map a cross-realm principal onto a
        same-named account in the wrong domain. lookup_computer_dns_hostname
        is deliberately left unmocked (would error if called) so this test
        actually proves the realm check short-circuits before it, not just
        that the lookup happens to fail on its own."""
        _configure_ad_connector(app)  # HAGLAND.DOMAIN
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
                status='authenticated', client_principal='HOST$@OTHER.DOMAIN',
            ),
        )

        csr, _key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 400

    # Golden reference: a real ADCS-issued User certificate pulled from the
    # lab (dc1.hagland.domain's "Active Directory Enrollment Policy",
    # enrolled interactively as roy.hagland). Confirms the exact subject
    # RDN order and UPN SAN shape a byte-equivalent UCM-issued cert must
    # reproduce -- ``Subject: CN=Roy Hagland, CN=Users, DC=hagland,
    # DC=domain`` / ``SAN: Other Name:Principal Name=roy.hagland@hagland.domain``.
    _GOLDEN_USER_DN_COMPONENTS = [
        ('CN', 'Roy Hagland'),
        ('CN', 'Users'),
        ('DC', 'hagland'),
        ('DC', 'domain'),
    ]
    _GOLDEN_USER_UPN = 'roy.hagland@hagland.domain'

    def test_naked_csr_from_user_principal_with_successful_ad_lookup_gets_derived_subject_and_upn(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """A user Kerberos principal (no trailing $) submitting a naked CSR
        gets a subject and SAN derived from AD, matching real ADCS's own
        User-template enrollment shape."""
        _configure_ad_connector(app)
        _configure_ad_derived_user_template(app, wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
                status='authenticated', client_principal='roy.hagland@HAGLAND.DOMAIN',
            ),
        )
        monkeypatch.setattr(
            ad_lookup, 'lookup_user_ad_identity',
            lambda _config, sam_account_name: {
                'dn_components': self._GOLDEN_USER_DN_COMPONENTS,
                'upn': self._GOLDEN_USER_UPN,
            },
        )
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        csr, key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 200

        cert = _issued_cert_from_rstr(r.data)
        assert cert.public_key().public_numbers() == key.public_key().public_numbers()

        # rfc4514_string() is leaf-first (RFC4514/LDAP display convention,
        # matching how AD's own distinguishedName and PowerShell's cert
        # Subject display read) -- byte-for-byte the golden ADCS cert's
        # own displayed subject. The underlying DER SEQUENCE order is the
        # reverse (root-first); see wstep_service._x509_name_from_dn_components.
        assert cert.subject.rfc4514_string() == 'CN=Roy Hagland,CN=Users,DC=hagland,DC=domain'

        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        assert extract_upns_from_san_list(list(san_ext.value)) == [self._GOLDEN_USER_UPN]

        with app.app_context():
            db_cert = Certificate.query.filter_by(serial_number=str(cert.serial_number)).first()
            assert db_cert is not None
            assert db_cert.subject_cn == 'Roy Hagland'
            assert json.loads(db_cert.san_upn) == [self._GOLDEN_USER_UPN]

    def test_naked_csr_from_user_with_mail_attribute_includes_email(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """A user AD object with a mail attribute gets it included as a
        leaf-most subject RDN and an SAN RFC822Name -- opportunistic, never
        a hard requirement (unlike real ADCS's CT_FLAG_SUBJECT_REQUIRE_EMAIL,
        which would decline enrollment outright for any user without one)."""
        _configure_ad_connector(app)
        _configure_ad_derived_user_template(app, wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
                status='authenticated', client_principal='roy.hagland@HAGLAND.DOMAIN',
            ),
        )
        monkeypatch.setattr(
            ad_lookup, 'lookup_user_ad_identity',
            lambda _config, sam_account_name: {
                'dn_components': self._GOLDEN_USER_DN_COMPONENTS,
                'upn': self._GOLDEN_USER_UPN,
                'mail': self._GOLDEN_USER_UPN,
            },
        )
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        csr, key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 200

        cert = _issued_cert_from_rstr(r.data)
        subject_attrs = list(cert.subject)
        assert subject_attrs[-1].oid == NameOID.EMAIL_ADDRESS
        assert subject_attrs[-1].value == self._GOLDEN_USER_UPN
        # CN extraction ([-1] of COMMON_NAME-typed attrs specifically) must
        # stay unaffected by the trailing email RDN, which is a different
        # attribute type entirely.
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[-1].value == 'Roy Hagland'

        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        assert extract_upns_from_san_list(list(san_ext.value)) == [self._GOLDEN_USER_UPN]
        assert list(san_ext.value.get_values_for_type(x509.RFC822Name)) == [self._GOLDEN_USER_UPN]

        with app.app_context():
            db_cert = Certificate.query.filter_by(serial_number=str(cert.serial_number)).first()
            assert db_cert is not None
            assert db_cert.subject_cn == 'Roy Hagland'
            assert json.loads(db_cert.san_email) == [self._GOLDEN_USER_UPN]

    def test_naked_csr_from_user_principal_with_failed_ad_lookup_still_rejected(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """Same fail-closed guarantee as the machine path: no AD identity
        found (account missing, no userPrincipalName, LDAP unreachable,
        ...) means the naked CSR falls through to the pre-existing
        rejection, never a crash or a bypass."""
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
        _configure_ad_derived_user_template(app, wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
                status='authenticated', client_principal='alice@HAGLAND.DOMAIN',
            ),
        )
        monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity', lambda _config, sam_account_name: None)

        csr, _key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 400

    def test_naked_csr_from_user_principal_rejected_when_no_template_opted_in(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """The per-template toggle is the gate, not just AD Connector config
        + a successful lookup -- without any ad_derived_subject template,
        derivation must not fire even if AD would have resolved the user."""
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
        _clear_ad_derived_templates(app)
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
                status='authenticated', client_principal='roy.hagland@HAGLAND.DOMAIN',
            ),
        )
        monkeypatch.setattr(
            ad_lookup, 'lookup_user_ad_identity',
            lambda _config, sam_account_name: {
                'dn_components': self._GOLDEN_USER_DN_COMPONENTS,
                'upn': self._GOLDEN_USER_UPN,
            },
        )

        csr, _key = _make_naked_csr()
        r = client.post(
            ISSUE_URL, data=_build_rst(csr),
            headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
        )
        assert r.status_code == 400
        assert b'CSR subject must include a non-empty CN or a SubjectAltName' in r.data, r.data


def _clear_acl_template(app):
    with app.app_context():
        delete_templates(template_ids_named('Test Enroll ACL Template'))
        db.session.commit()


def _configure_acl_template(app, allowed_ad_group, ca_id, extended_key_usage=('clientAuth',)):
    """An active template with an Enroll ACL group set, PINNED to ``ca_id``.

    Pinning matters here specifically: ``_resolve_templates_for_ca`` falls
    back to *every* active template in the whole database when nothing is
    pinned to a CA -- fine for the derivation tests above, which only care
    that at least one qualifying template exists, but wrong for these ACL
    tests, which need ``_match_template``/``_required_enroll_acl_groups``
    to see *only* this template. Running the full suite leaves other test
    modules' throwaway templates behind (they don't all clean up), and an
    unrelated leftover template with an equal-or-better EKU score and a
    lower id would silently win the tie-break instead of this one --
    exactly the failure mode this pin closes off.

    The clientAuth template matches ``_make_csr``'s clientAuth request (the
    confident-match branch of the ACL gate) and scores negative against a
    naked CSR, which then takes the CA-wide fallback branch (see
    _required_enroll_acl_groups). A template whose subject the request names
    must configure its EKUs, or issuance is refused.

    Also clears 'Test AD User Template' (used by the derivation tests
    above), since an empty-EKU variant of it would otherwise tie-break
    unpredictably against this one."""
    import json

    from models import CATemplatePin

    _clear_ad_derived_templates(app)
    _clear_acl_template(app)
    with app.app_context():
        extensions = {'extended_key_usage': list(extended_key_usage)}
        template = CertificateTemplate(
            name='Test Enroll ACL Template', template_type='client_auth',
            extensions_template=json.dumps(extensions), is_active=True,
            allowed_ad_group=allowed_ad_group,
        )
        db.session.add(template)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=ca_id, template_id=template.id))
        db.session.commit()


class TestEnrollAcl:
    """Per-template Enroll ACL: only gates the Kerberos-bound path (see
    wstep_service.issue's allowed_ad_group handling) -- checks the
    authenticated principal's AD group membership via
    ad_lookup.is_member_of_group before letting a group-restricted
    template issue."""

    def test_member_of_required_group_is_issued(self, client, app, wstep_kerberos_config, monkeypatch):
        _configure_ad_connector(app)
        _configure_acl_template(app, 'VPN-Enroll', wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(
            ad_lookup, 'is_member_of_group',
            lambda _config, sam_account_name, group: (sam_account_name, group) == ('HOST$', 'VPN-Enroll'),
        )
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        try:
            csr, key = _make_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            assert r.status_code == 200
            cert = _issued_cert_from_rstr(r.data)
            assert cert.public_key().public_numbers() == key.public_key().public_numbers()
        finally:
            _clear_acl_template(app)

    def test_non_member_is_rejected(self, client, app, wstep_kerberos_config, monkeypatch):
        _configure_ad_connector(app)
        _configure_acl_template(app, 'VPN-Enroll', wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(ad_lookup, 'is_member_of_group', lambda _config, sam_account_name, group: False)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        try:
            csr, _key = _make_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            assert r.status_code == 400
            assert b'Requester is not authorized to enroll against this template' in r.data, r.data
        finally:
            _clear_acl_template(app)

    def test_pinned_template_deactivated_refuses_instead_of_skipping_the_acl(self, client, app, wstep_kerberos_config, monkeypatch):
        """The CA's only pinned template switched off: it offers nothing, so no
        request slips through without a template and its Enroll ACL."""
        _configure_ad_connector(app)
        _configure_acl_template(app, 'VPN-Enroll', wstep_kerberos_config['id'])
        with app.app_context():
            CertificateTemplate.query.filter_by(name='Test Enroll ACL Template').update({'is_active': False})
            db.session.commit()
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(ad_lookup, 'is_member_of_group', lambda _config, sam_account_name, group: False)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        try:
            csr, _key = _make_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            assert r.status_code == 500
            assert _fault_text_and_code(r.data) == ('This CA offers no certificate template', 's:Receiver')
        finally:
            _clear_acl_template(app)

    def test_ad_lookup_failure_fails_closed(self, client, app, wstep_kerberos_config, monkeypatch):
        """is_member_of_group itself fails closed to False on every AD error
        mode (see test_ad_connector_lookup.py) -- this confirms issue()
        propagates that as a denial, not a silent bypass, when the
        connector/DC is unreachable."""
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
        _configure_acl_template(app, 'VPN-Enroll', wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(ad_lookup, '_connect', lambda config: (_ for _ in ()).throw(RuntimeError('DC unreachable')))

        try:
            csr, _key = _make_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            # Denied all the same, but as the server's failure (SOAP env:Receiver), not the requester's
            assert r.status_code == 500
            assert _fault_text_and_code(r.data) == (
                'The directory could not be reached to check enrollment rights', 's:Receiver')
            assert b'DC unreachable' not in r.data
        finally:
            _clear_acl_template(app)

    def test_unset_allowed_group_is_unrestricted(self, client, app, wstep_kerberos_config, monkeypatch):
        """No allowed_ad_group configured -- the default -- must issue
        exactly as before this feature existed, with no membership check at
        all. Proven by a spy that raises if is_member_of_group is ever
        called, not just by asserting 200 (which would also pass if the
        spy silently ran and happened to return truthy)."""
        _configure_ad_connector(app)
        _configure_acl_template(app, None, wstep_kerberos_config['id'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )

        def _fail_if_called(_config, sam_account_name, group):
            raise AssertionError('is_member_of_group must not be called when nothing is restricted')

        monkeypatch.setattr(ad_lookup, 'is_member_of_group', _fail_if_called)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        try:
            csr, key = _make_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            assert r.status_code == 200
            cert = _issued_cert_from_rstr(r.data)
            assert cert.public_key().public_numbers() == key.public_key().public_numbers()
        finally:
            _clear_acl_template(app)

    def test_naked_csr_falls_back_to_ca_wide_restricted_templates_and_denies(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """The real GPO machine-autoenrollment scenario: a naked CSR (no
        EKU extension at all) never confidently matches a template that
        itself declares an EKU (see _match_template's docstring), so
        _match_template returns None. Without the CA-wide fallback in
        _required_enroll_acl_groups, this template's allowed_ad_group would
        never be checked at all -- silently defeating the ACL for exactly
        the unattended-autoenrollment case it exists to restrict."""
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
        _configure_acl_template(app, 'VPN-Enroll', wstep_kerberos_config['id'], extended_key_usage=['clientAuth'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(
            ad_lookup, 'lookup_computer_dns_hostname',
            lambda _config, sam_account_name: 'win11.hagland.domain',
        )
        monkeypatch.setattr(ad_lookup, 'is_member_of_group', lambda _config, sam_account_name, group: False)

        try:
            csr, _key = _make_naked_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            assert r.status_code == 400
        finally:
            _clear_acl_template(app)

    def test_naked_csr_falls_back_to_ca_wide_restricted_templates_and_allows_member(
        self, client, app, wstep_kerberos_config, monkeypatch
    ):
        """Same unmatched-template scenario as above, but the principal IS
        a member of the restricted template's group -- confirms the
        fallback is a real gate, not an unconditional deny."""
        _configure_ad_connector(app)
        _configure_acl_template(app, 'VPN-Enroll', wstep_kerberos_config['id'], extended_key_usage=['clientAuth'])
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
        monkeypatch.setattr(
            negotiate_auth, 'authenticate_negotiate',
            lambda auth_header, connection_key: _authenticated_result(),
        )
        monkeypatch.setattr(
            ad_lookup, 'lookup_computer_dns_hostname',
            lambda _config, sam_account_name: 'win11.hagland.domain',
        )
        monkeypatch.setattr(
            ad_lookup, 'is_member_of_group',
            lambda _config, sam_account_name, group: (sam_account_name, group) == ('HOST$', 'VPN-Enroll'),
        )
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')

        try:
            csr, key = _make_naked_csr()
            r = client.post(
                ISSUE_URL, data=_build_rst(csr),
                headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'},
            )
            assert r.status_code == 200
            cert = _issued_cert_from_rstr(r.data)
            assert cert.public_key().public_numbers() == key.public_key().public_numbers()
        finally:
            _clear_acl_template(app)


def test_an_unreachable_directory_is_a_receiver_fault(client, app, wstep_kerberos_config, monkeypatch):
    """The SID lookup failing is the server's fault (SOAP env:Receiver, HTTP 500), not the client's."""
    _configure_ad_connector(app)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: _authenticated_result())
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: ad_lookup.UNREACHABLE)
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr),
                    headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    assert r.status_code == 500
    fault = etree.fromstring(r.data).find(f'.//{{{SOAP_NS}}}Fault')
    assert fault.find(f'.//{{{SOAP_NS}}}Text').text == (
        'Could not resolve requester identity for strong certificate mapping')
    assert fault.find(f'{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Value').text == 's:Receiver'


def test_a_requester_missing_from_the_directory_is_a_sender_fault(
        client, app, wstep_kerberos_config, monkeypatch):
    """The directory answered that the account does not exist: the request is refused (400)."""
    _configure_ad_connector(app)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: _authenticated_result())
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: None)
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr),
                    headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    assert r.status_code == 400
    assert _fault_text_and_code(r.data) == ('The requester was not found in the directory', 's:Sender')


def test_an_enabled_connector_without_a_server_is_a_receiver_fault(
        client, app, wstep_kerberos_config, monkeypatch):
    """The API accepts an enabled connector with no server: a configuration fault (500), not 400."""
    with app.app_context():
        mount_connector(server=None, base_dn='DC=hagland,DC=domain', bind_dn='svc-ucm', enabled=True)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: _authenticated_result())
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr),
                    headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    assert r.status_code == 500
    assert _fault_text_and_code(r.data) == (
        'Could not resolve requester identity for strong certificate mapping', 's:Receiver')


def test_a_requester_without_a_usable_sid_is_told_apart_from_a_missing_one(
        client, app, wstep_kerberos_config, monkeypatch):
    _configure_ad_connector(app)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: _authenticated_result())
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: ad_lookup.UNUSABLE_SID)
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr),
                    headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    assert r.status_code == 400
    assert _fault_text_and_code(r.data) == ('The requester has no usable directory identity', 's:Sender')


def _fault_text_and_code(data):
    fault = etree.fromstring(data).find(f'.//{{{SOAP_NS}}}Fault')
    return (fault.find(f'.//{{{SOAP_NS}}}Text').text,
            fault.find(f'{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Value').text)


def test_a_naked_request_the_directory_cannot_answer_is_a_receiver_fault(
        client, app, wstep_kerberos_config, monkeypatch):
    """GPO autoenrollment with no DC bound: the CA, not the computer, failed to build the subject."""
    _configure_ad_connector(app)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: _authenticated_result())
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
    monkeypatch.setattr(ad_lookup, '_connect', lambda config: (_ for _ in ()).throw(RuntimeError('DC unreachable')))
    csr, _key = _make_naked_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr),
                    headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    assert r.status_code == 500
    assert _fault_text_and_code(r.data) == (
        'The directory that builds the certificate subject could not be reached', 's:Receiver')
    assert b'DC unreachable' not in r.data


@pytest.mark.parametrize('principal, base_dn, status, text, code', [
    (KERBEROS_PRINCIPAL, 'DC=other,DC=domain', 400,
     "The requester's realm is not served by the directory connector", 's:Sender'),
    ('HOST$@OTHER.DOMAIN', 'DC=hagland,DC=domain', 400, "The requester's realm is not served", 's:Sender'),
    (KERBEROS_PRINCIPAL, None, 500,
     'Could not resolve requester identity for strong certificate mapping', 's:Receiver'),
])
def test_an_enabled_connector_that_cannot_resolve_the_requester_faults(
        client, app, wstep_kerberos_config, monkeypatch, principal, base_dn, status, text, code):
    """Never issued without the SID extension: a foreign realm is the requester's fault, no base DN the CA's.
    A realm no profile serves is refused before the connector is asked."""
    with app.app_context():
        mount_connector(server='dc1.hagland.domain', base_dn=base_dn, bind_dn='svc-ucm', enabled=True)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate',
                        lambda auth_header, connection_key: negotiate_auth.NegotiateResult(
                            status='authenticated', client_principal=principal))
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam_account_name: 'S-1-5-21-1-2-3-1000')
    csr, _key = _make_csr()
    try:
        r = client.post(ISSUE_URL, data=_build_rst(csr),
                        headers={'Authorization': 'Negotiate dG9rZW4=', 'Content-Type': 'application/soap+xml'})
    finally:
        with app.app_context():
            clear_connectors()
    assert r.status_code == status
    assert _fault_text_and_code(r.data) == (text, code)
