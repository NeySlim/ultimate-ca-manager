"""Interoperability tests for the MS-WSTEP UsernamePassword-bound issue endpoint."""
import base64

import pytest
from asn1crypto import algos as asn1_algos
from asn1crypto import csr as asn1_csr
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID
from lxml import etree

from models import CA, db
from models.certificate_template import CertificateTemplate
from models.system_config import SystemConfig
from tests.fixtures.templates import delete_templates, template_ids_named, templates_created_here_removed
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS, WST_NS
from tests.windows_profile_support import restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401


ISSUE_URL = '/ADCertificateService_CES_UsernamePassword/service.svc'
WSTEP_USER = 'wstep-test'
WSTEP_PASSWORD = 'wstep-password'


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


def _set_config(key, value):
    set_config(key, value)


@pytest.fixture(scope='module')
def wstep_config(app, create_ca):
    ca_data = create_ca(cn='WSTEP Issue CA')
    # The issuing CA is the mTLS anchor too: native TLS renewal needs it (A5)
    keys = ('wstep_enabled', 'wstep_ca_refid', 'wstep_username', 'wstep_password', 'wstep_validity_days',
            'mtls_enabled', 'mtls_trusted_ca_id')
    with app.app_context():
        previous = snapshot(keys)
        ca = db.session.get(CA, ca_data['id'])
        _set_config('wstep_enabled', 'true')
        _set_config('wstep_ca_refid', ca.refid)
        _set_config('mtls_enabled', 'true')
        _set_config('mtls_trusted_ca_id', ca.refid)
        _set_config('wstep_username', WSTEP_USER)
        _set_config('wstep_password', WSTEP_PASSWORD)
        _set_config('wstep_validity_days', '30')

    yield ca_data

    with app.app_context():
        restore(previous)


def _basic_auth():
    token = base64.b64encode(f'{WSTEP_USER}:{WSTEP_PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def _make_csr(common_name='device.example.test', key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ).sign(key, hashes.SHA256())
    return csr, key


def _make_sha1_csr(common_name='device.example.test'):
    """A SHA-1-signed CSR. ``cryptography``'s own CSR builder refuses to
    sign with SHA-1 at all (UnsupportedAlgorithm), so this reuses a
    normally-built CSR's TBS bytes (hash-algorithm-independent) and signs
    them directly with the RSA private key primitive, which still permits
    SHA-1 -- matching how a real client like certreq.exe (default
    HashAlgorithm) actually produces one."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr_sha256 = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ).sign(key, hashes.SHA256())
    tbs = csr_sha256.tbs_certrequest_bytes
    signature = key.sign(tbs, padding.PKCS1v15(), hashes.SHA1())
    new_csr = asn1_csr.CertificationRequest({
        'certification_request_info': asn1_csr.CertificationRequestInfo.load(tbs),
        'signature_algorithm': asn1_algos.SignedDigestAlgorithm({'algorithm': 'sha1_rsa'}),
        'signature': signature,
    })
    return x509.load_der_x509_csr(new_csr.dump()), key


def _build_rst(csr, message_id='urn:uuid:test-rst-1'):
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


def _build_rst_with_username_token(csr, username, password, message_id='urn:uuid:test-rst-token'):
    """Real client behavior: credentials in a WS-Security UsernameToken
    inside the RST's ``wsse:Security`` header, not an HTTP Authorization
    header — see MS-XCEP's published GetPolicies example, which uses the
    same mechanism for this auth binding."""
    NSMAP = {'s': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS, 'wsse': WSSE_NS}
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = message_id
    security = etree.SubElement(header, '{%s}Security' % WSSE_NS)
    token = etree.SubElement(security, '{%s}UsernameToken' % WSSE_NS)
    etree.SubElement(token, '{%s}Username' % WSSE_NS).text = username
    etree.SubElement(token, '{%s}Password' % WSSE_NS).text = password
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    etree.SubElement(rst, '{%s}RequestType' % WST_NS).text = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'
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


def test_issue_disabled_returns_503(client, app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='wstep_enabled').first()
        previous = row.value if row else None
        _set_config('wstep_enabled', 'false')
    try:
        csr, _key = _make_csr()
        r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
        assert r.status_code == 503
    finally:
        with app.app_context():
            if previous is None:
                SystemConfig.query.filter_by(key='wstep_enabled').delete()
                db.session.commit()
            else:
                _set_config('wstep_enabled', previous)


def test_issue_requires_authentication(client, wstep_config):
    """Auth failure is a SOAP fault, not an HTTP 401/WWW-Authenticate
    challenge — real credentials arrive as a WS-Security UsernameToken
    inside the RST body, and a client configured for that binding refuses
    to respond to a Basic challenge at all (WS_E_SERVER_REQUIRES_BASIC_AUTH),
    so this endpoint never issues one."""
    csr, _key = _make_csr()
    r = client.post(ISSUE_URL, data=_build_rst(csr))
    assert r.status_code == 400
    assert 'WWW-Authenticate' not in r.headers


def test_issue_rejects_bad_credentials(client, wstep_config):
    token = base64.b64encode(b'wstep-test:wrong-password').decode()
    csr, _key = _make_csr()
    r = client.post(
        ISSUE_URL, data=_build_rst(csr),
        headers={'Authorization': f'Basic {token}'},
    )
    assert r.status_code == 400


def test_issue_rejects_non_ascii_credentials_without_crashing(client, wstep_config):
    """hmac.compare_digest on two `str` operands raises TypeError for
    non-ASCII input -- a wrong-but-non-ASCII Basic-auth credential must
    still get the normal SOAP auth-failed fault (400), not an unhandled
    500."""
    token = base64.b64encode('wstep-test:wröng-pässwörd'.encode('utf-8')).decode()
    csr, _key = _make_csr()
    r = client.post(
        ISSUE_URL, data=_build_rst(csr),
        headers={'Authorization': f'Basic {token}'},
    )
    assert r.status_code == 400
    assert 'WWW-Authenticate' not in r.headers


def test_issue_returns_certificate(client, wstep_config):
    csr, _key = _make_csr(common_name='wstep-issue.example.test')
    r = client.post(ISSUE_URL, data=_build_rst(csr, message_id='urn:uuid:happy-path'), headers=_basic_auth())
    assert r.status_code == 200
    assert r.content_type.startswith('application/soap+xml')

    root = etree.fromstring(r.data)
    relates_to = root.find(f'.//{{{ADDRESSING_NS}}}RelatesTo')
    assert relates_to is not None and relates_to.text == 'urn:uuid:happy-path'

    cert = _issued_cert_from_rstr(r.data)
    assert cert.subject.rfc4514_string() == 'CN=wstep-issue.example.test'


def test_issue_authenticates_via_username_token(client, wstep_config):
    """Regression test for the bug where this endpoint only accepted HTTP
    Basic, causing a real Windows client (configured for message-level
    auth) to report WS_E_SERVER_REQUIRES_BASIC_AUTH and refuse to enroll."""
    csr, _key = _make_csr(common_name='wstep-token-auth.example.test')
    r = client.post(
        ISSUE_URL,
        data=_build_rst_with_username_token(csr, WSTEP_USER, WSTEP_PASSWORD),
    )
    assert r.status_code == 200
    cert = _issued_cert_from_rstr(r.data)
    assert cert.subject.rfc4514_string() == 'CN=wstep-token-auth.example.test'


def test_issue_rejects_invalid_csr_pop(client, wstep_config):
    """A CSR whose self-signature doesn't verify must be refused (proof
    of possession), mirroring EST's ``_validate_est_csr``."""
    csr, _key = _make_csr()
    csr_der = bytearray(csr.public_bytes(Encoding.DER))
    csr_der[-1] ^= 0xFF  # corrupt the trailing signature byte
    envelope = etree.fromstring(_build_rst(csr))
    bst_el = envelope.find(f'.//{{{WSSE_NS}}}BinarySecurityToken')
    bst_el.text = base64.b64encode(bytes(csr_der)).decode()
    tampered = etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')

    r = client.post(ISSUE_URL, data=tampered, headers=_basic_auth())
    assert r.status_code == 400


def test_issue_rejects_empty_cn(client, wstep_config):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(key, hashes.SHA256())
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
    assert r.status_code == 400


def test_issue_rejects_sha1_csr_with_specific_message(client, wstep_config):
    """A SHA-1-signed CSR is genuinely proof-of-possession-valid (confirmed
    by manually verifying the signature), but ``cryptography``'s
    ``is_signature_valid`` refuses to vouch for it -- real-world clients
    hit this via certreq.exe, which defaults to SHA-1 unless an INF
    explicitly sets HashAlgorithm=sha256. The rejection message should
    name the actual cause rather than the generic PoP-failure wording."""
    csr, _key = _make_sha1_csr('sha1-csr.example.test')
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
    assert r.status_code == 400
    assert b'sha1' in r.data.lower()
    assert b'SHA-256' in r.data


def test_issue_ignores_enroll_acl_on_username_password_path(client, app, wstep_config):
    """Per-template Enroll ACL (CertificateTemplate.allowed_ad_group) only
    gates the Kerberos-bound CES endpoint -- the UsernamePassword path
    authenticates a single shared SystemConfig credential with no
    per-request principal, so there's no identity to check group
    membership for. A template restricted to a group must still issue
    normally here, matching pre-feature behavior exactly."""
    with app.app_context():
        delete_templates(template_ids_named('Test UsernamePassword ACL Template'))
        template = CertificateTemplate(
            name='Test UsernamePassword ACL Template', template_type='client_auth',
            extensions_template='{}', is_active=True, allowed_ad_group='VPN-Enroll',
        )
        db.session.add(template)
        db.session.commit()

    try:
        csr, _key = _make_csr(common_name='wstep-acl-unaffected.example.test')
        r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
        assert r.status_code == 200
        cert = _issued_cert_from_rstr(r.data)
        assert cert.subject.rfc4514_string() == 'CN=wstep-acl-unaffected.example.test'
    finally:
        with app.app_context():
            delete_templates(template_ids_named('Test UsernamePassword ACL Template'))
            db.session.commit()


def test_issue_refusal_gives_its_reason(client, wstep_config):
    """A request the trunk refuses for its names tells the client why."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'reason.example.test')])
    ).add_extension(x509.SubjectAlternativeName([x509.DNSName('bad name.example')]),
                    critical=False).sign(key, hashes.SHA256())
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
    assert r.status_code == 400
    assert b'bad name.example' in r.data


@pytest.mark.parametrize('eku,cn,dns', [
    (x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH, 'jdoe', []),
    (x509.oid.ExtendedKeyUsageOID.SERVER_AUTH, 'intranet', ['intranet']),
])
def test_issue_cert_type_follows_the_template_eku(client, app, wstep_config, eku, cn, dns):
    """A user template's CN names a person, so CN=jdoe gives no DNS:jdoe; a machine's keeps it."""
    name = f'Test WSTEP profile {eku.dotted_string}'
    with app.app_context():
        delete_templates(template_ids_named(name))
        db.session.add(CertificateTemplate(
            name=name, template_type='custom', key_type='RSA-2048', is_active=True,
            extensions_template='{"extended_key_usage": ["%s"]}' % eku.dotted_string))
        db.session.commit()
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
               .sign(key, hashes.SHA256()))
        r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
        assert r.status_code == 200, r.data
        cert = _issued_cert_from_rstr(r.data)
        try:
            names = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            names = []
        assert names == dns
    finally:
        with app.app_context():
            delete_templates(template_ids_named(name))
            db.session.commit()


def _naming(name):
    """szOID_ENROLL_CERTTYPE: the request names its template, as CertEnroll does from XCEP."""
    from asn1crypto import core as asn1_core
    return x509.UnrecognizedExtension(x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2'),
                                      asn1_core.BMPString(name).dump())


_EFS = '1.3.6.1.4.1.311.10.3.4'
_SMARTCARD_LOGON = '1.3.6.1.4.1.311.20.2.2'


@pytest.mark.parametrize('ekus,ku', [
    # AD CS User, Smartcard Logon and Basic EFS: keyEncipherment for S/MIME, EFS and PKINIT
    (['1.3.6.1.5.5.7.3.2', '1.3.6.1.5.5.7.3.4', _EFS], {'key_encipherment', 'content_commitment'}),
    (['1.3.6.1.5.5.7.3.2', _SMARTCARD_LOGON], {'key_encipherment'}),
    ([_EFS], {'key_encipherment', 'content_commitment'}),
    (['1.3.6.1.5.5.7.3.4'], {'key_encipherment', 'content_commitment'}),
    (['1.3.6.1.5.5.7.3.2'], set()),
])
def test_user_template_key_usage_and_names(client, app, wstep_config, ekus, ku):
    """A request without Key Usage gets its template's profile; a person's CN gives no DNS name."""
    import json
    name = f'Test WSTEP user profile {"-".join(ekus)}'
    with app.app_context():
        delete_templates(template_ids_named(name))
        db.session.add(CertificateTemplate(
            name=name, template_type='custom', key_type='RSA-2048', is_active=True,
            extensions_template=json.dumps({'extended_key_usage': ekus})))
        db.session.commit()
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'jdoe')]))
               .add_extension(x509.ExtendedKeyUsage([x509.ObjectIdentifier(o) for o in ekus]),
                              critical=False)
               .add_extension(_naming(name), critical=False)
               .sign(key, hashes.SHA256()))
        r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
        assert r.status_code == 200, r.data
        cert = _issued_cert_from_rstr(r.data)
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        granted = {bit for bit in ('key_encipherment', 'content_commitment', 'key_agreement',
                                   'data_encipherment') if getattr(usage, bit)}
        assert usage.digital_signature and granted == ku, granted
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            assert san.get_values_for_type(x509.DNSName) == []
        except x509.ExtensionNotFound:
            pass
    finally:
        with app.app_context():
            delete_templates(template_ids_named(name))
            db.session.commit()


@pytest.mark.parametrize('ekus,configured,ku,dns', [
    # Built-in Client Authentication, Email Certificate (S/MIME) and VPN Client
    (['clientAuth'], ['digitalSignature', 'keyEncipherment'], {'key_encipherment'}, []),
    (['emailProtection'], ['digitalSignature', 'keyEncipherment', 'dataEncipherment'],
     {'key_encipherment', 'data_encipherment'}, []),
    (['clientAuth', 'ipsecUser'], ['digitalSignature', 'keyEncipherment'], {'key_encipherment'}, []),
    # No serverAuth: a user's VPN template is a client one, its CN names no host
    (['clientAuth', 'ipsecUser'], None, set(), []),
])
def test_a_request_without_key_usage_gets_the_template_s(client, app, wstep_config, ekus, configured, ku, dns):
    import json
    from utils.eku_validation import normalize_extra_ekus
    name = f'Test WSTEP configured KU {"-".join(ekus)} {bool(configured)}'
    ext = {'extended_key_usage': ekus, **({'key_usage': configured} if configured else {})}
    with app.app_context():
        delete_templates(template_ids_named(name))
        db.session.add(CertificateTemplate(name=name, template_type='custom', key_type='RSA-2048',
                                           is_active=True, extensions_template=json.dumps(ext)))
        db.session.commit()
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'jdoe')]))
               .add_extension(x509.ExtendedKeyUsage(
                   [x509.ObjectIdentifier(o) for o in normalize_extra_ekus(ekus)[0]]), critical=False)
               .add_extension(_naming(name), critical=False)
               .sign(key, hashes.SHA256()))
        r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
        assert r.status_code == 200, r.data
        cert = _issued_cert_from_rstr(r.data)
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        granted = {bit for bit in ('key_encipherment', 'content_commitment', 'key_agreement',
                                   'data_encipherment') if getattr(usage, bit)}
        assert usage.digital_signature and granted == ku, granted
        try:
            names = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            names = []
        assert names == dns
    finally:
        with app.app_context():
            delete_templates(template_ids_named(name))
            db.session.commit()


def test_the_request_s_key_usage_wins_over_the_template_s(client, app, wstep_config):
    """CertEnroll copies the Key Usage XCEP announced: the request's own is kept."""
    import json
    name = 'Test WSTEP configured KU, request KU'
    with app.app_context():
        delete_templates(template_ids_named(name))
        db.session.add(CertificateTemplate(
            name=name, template_type='custom', key_type='RSA-2048', is_active=True,
            extensions_template=json.dumps({'extended_key_usage': ['clientAuth'],
                                            'key_usage': ['digitalSignature', 'keyEncipherment']})))
        db.session.commit()
    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        asked = x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                              data_encipherment=False, key_agreement=False, key_cert_sign=False,
                              crl_sign=False, encipher_only=False, decipher_only=False)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'jdoe')]))
               .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                              critical=False)
               .add_extension(asked, critical=True)
               .add_extension(_naming(name), critical=False)
               .sign(key, hashes.SHA256()))
        r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
        assert r.status_code == 200, r.data
        assert _issued_cert_from_rstr(r.data).extensions.get_extension_for_class(x509.KeyUsage).value == asked
    finally:
        with app.app_context():
            delete_templates(template_ids_named(name))
            db.session.commit()


def test_a_bare_csr_is_not_issued_under_a_template_of_capped_ekus_only(client, app, wstep_config):
    """`openssl req -new` with a CN alone: OCSP Signing, whose only EKU is never issued,
    scores as a perfect match but is no template for it; the server pair is kept."""
    from models import CA
    from services.xcep.policy_builder import _policy_oid_for_template
    with app.app_context():
        ca = db.session.get(CA, wstep_config['id'])
        ocsp = CertificateTemplate.query.filter_by(name='OCSP Signing').first()
        assert ocsp is not None and ocsp.is_active
        ocsp_oid = _policy_oid_for_template(ca, ocsp)
    csr, _key = _make_csr(common_name='bare.example.test')
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
    assert r.status_code == 200, r.data
    cert = _issued_cert_from_rstr(r.data)
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert usage.digital_signature and usage.key_encipherment
    ekus = {o.dotted_string for o in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value}
    assert ekus == {'1.3.6.1.5.5.7.3.1'}, ekus
    try:
        stamped = cert.extensions.get_extension_for_class(
            x509.MSCertificateTemplate).value.template_id.dotted_string
    except x509.ExtensionNotFound:
        stamped = None
    assert stamped != ocsp_oid


@pytest.fixture
def _ca_offers_only_ocsp_signing(app, wstep_config):
    """The CA offers OCSP Signing alone, whatever templates the database holds."""
    from models import CATemplatePin
    with app.app_context():
        ocsp = CertificateTemplate.query.filter_by(name='OCSP Signing').first()
        assert ocsp is not None and ocsp.is_active
        pin = CATemplatePin(ca_id=wstep_config['id'], template_id=ocsp.id)
        db.session.add(pin)
        db.session.commit()
        pin_id = pin.id
    yield
    with app.app_context():
        CATemplatePin.query.filter_by(id=pin_id).delete()
        db.session.commit()


@pytest.mark.parametrize('named', [False, True])
def test_a_template_of_capped_ekus_only_is_refused(client, app, wstep_config, _ca_offers_only_ocsp_signing, named):
    """OCSP Signing would be signed under the server profile, its only EKU dropped: the
    request asking for it, or naming it, is refused as the client's fault."""
    from models import CA
    from services.xcep.policy_builder import _policy_oid_for_template
    from tests.test_wstep_protocol_conformance import _fault, _fault_code
    with app.app_context():
        ca = db.session.get(CA, wstep_config['id'])
        ocsp_oid = _policy_oid_for_template(ca, CertificateTemplate.query.filter_by(name='OCSP Signing').first())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ocsp.example.test')]))
               .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING]), critical=False))
    if named:
        builder = builder.add_extension(
            x509.MSCertificateTemplate(x509.ObjectIdentifier(ocsp_oid), 100, 0), critical=False)
    r = client.post(ISSUE_URL, data=_build_rst(builder.sign(key, hashes.SHA256())), headers=_basic_auth())
    assert r.status_code == 400, r.data
    assert _fault(r.data)[0] == ("Template 'OCSP Signing' configures only Extended Key Usages "
                                 'this service does not issue')
    assert _fault_code(r.data) == 's:Sender'
