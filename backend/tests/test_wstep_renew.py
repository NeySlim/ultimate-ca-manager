"""Interoperability tests for the MS-WSTEP Certificate-bound renewal endpoint."""
import base64
import datetime

import pytest
import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from models import CA, Certificate, db
from models.system_config import SystemConfig
from services.ca_service import CAService
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS, WST_NS, WSU_NS
from tests.windows_profile_support import restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401


RENEW_URL = '/ADCertificateService_CES_Certificate/service.svc'


def _set_config(key, value):
    set_config(key, value)


@pytest.fixture(scope='module')
def wstep_renew_config(app, create_ca):
    ca_data = create_ca(cn='WSTEP Renewal CA')
    # The renewing CA is the mTLS anchor too: native TLS renewal needs it (A5)
    keys = ('wstep_enabled', 'wstep_ca_refid', 'wstep_validity_days', 'mtls_enabled', 'mtls_trusted_ca_id')
    with app.app_context():
        previous = snapshot(keys)
        ca = db.session.get(CA, ca_data['id'])
        _set_config('wstep_enabled', 'true')
        _set_config('wstep_ca_refid', ca.refid)
        _set_config('wstep_validity_days', '30')
        _set_config('mtls_enabled', 'true')
        _set_config('mtls_trusted_ca_id', ca.refid)

    yield ca_data

    with app.app_context():
        restore(previous)


def _issue_test_cert(app, ca_data, common_name='wstep-renew.example.test'):
    """Issue a real cert through CAService (not the HTTP endpoint) so
    each test gets its own already-issued cert/key pair to renew from."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ).sign(key, hashes.SHA256())
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        cert_pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=30, source='wstep',
        )
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    return cert, key


def _build_signed_rst(signing_cert, signing_key, csr, message_id='urn:uuid:renew-1', corrupt_signature=False,
                      token_der=None, value_type=None):
    """``token_der``/``value_type`` replace the PKCS#10 token, e.g. with a CMC request."""
    NSMAP = {'s': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS, 'wsse': WSSE_NS, 'wsu': WSU_NS}
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = message_id
    security = etree.SubElement(header, '{%s}Security' % WSSE_NS)
    sec_bst = etree.SubElement(
        security, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType='http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3',
        EncodingType='base64',
    )
    sec_bst.text = base64.b64encode(
        signing_cert.public_bytes(serialization.Encoding.DER)
    ).decode()

    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    body.set('{%s}Id' % WSU_NS, 'body-1')
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    etree.SubElement(rst, '{%s}TokenType' % WST_NS).text = (
        'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3'
    )
    etree.SubElement(rst, '{%s}RequestType' % WST_NS).text = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'
    bst = etree.SubElement(
        rst, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType=value_type or 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10',
        EncodingType='base64',
    )
    bst.text = base64.b64encode(token_der or csr.public_bytes(serialization.Encoding.DER)).decode()

    sig_node = xmlsec.template.create(
        security, xmlsec.constants.TransformExclC14N, xmlsec.constants.TransformRsaSha256
    )
    security.append(sig_node)
    ref = xmlsec.template.add_reference(sig_node, xmlsec.constants.TransformSha256, uri='#body-1')
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformExclC14N)

    ctx = xmlsec.SignatureContext()
    ctx.register_id(body, id_attr='Id', id_ns=WSU_NS)
    key_pem = signing_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    ctx.key = xmlsec.Key.from_memory(key_pem, xmlsec.constants.KeyDataFormatPem)
    ctx.sign(sig_node)

    xml_bytes = etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')
    if corrupt_signature:
        csr_b64 = base64.b64encode(csr.public_bytes(serialization.Encoding.DER))
        xml_bytes = xml_bytes.replace(csr_b64, csr_b64[:-4] + b'XXXX')
    return xml_bytes


def _renewal_csr(subject, key):
    return x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA256())


def _build_signature_wrapping_attack_rst(signing_cert, signing_key, legit_csr, decoy_csr, message_id='urn:uuid:renew-attack'):
    """A signature-wrapping / key-substitution attack RST: the genuinely
    signed Body carries the victim's own ``legit_csr``, but a second,
    unsigned ``wst:RequestSecurityToken`` carrying ``decoy_csr`` (same
    subject, attacker's key) is spliced in as a sibling of Body — outside
    the signed subtree, so it doesn't touch the Body's content and the
    signature over it still verifies. Before the signature-wrapping fix,
    ``rst_parser.parse_rst``'s document-order-first search for the CSR
    BinarySecurityToken would resolve to this decoy instead of the
    element the signature actually covers, letting the attacker's key
    ride in under the victim's valid signature."""
    NSMAP = {'s': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS, 'wsse': WSSE_NS, 'wsu': WSU_NS}
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = message_id
    security = etree.SubElement(header, '{%s}Security' % WSSE_NS)
    sec_bst = etree.SubElement(
        security, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType='http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3',
        EncodingType='base64',
    )
    sec_bst.text = base64.b64encode(
        signing_cert.public_bytes(serialization.Encoding.DER)
    ).decode()

    # Decoy RST, sibling of Body, placed before it and never referenced
    # by the signature.
    decoy_rst = etree.SubElement(envelope, '{%s}RequestSecurityToken' % WST_NS)
    etree.SubElement(decoy_rst, '{%s}RequestType' % WST_NS).text = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'
    decoy_bst = etree.SubElement(
        decoy_rst, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType='http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10',
        EncodingType='base64',
    )
    decoy_bst.text = base64.b64encode(decoy_csr.public_bytes(serialization.Encoding.DER)).decode()

    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    body.set('{%s}Id' % WSU_NS, 'body-1')
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    bst = etree.SubElement(
        rst, '{%s}BinarySecurityToken' % WSSE_NS,
        ValueType='http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10',
        EncodingType='base64',
    )
    bst.text = base64.b64encode(legit_csr.public_bytes(serialization.Encoding.DER)).decode()
    etree.SubElement(rst, '{%s}RequestType' % WST_NS).text = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'

    sig_node = xmlsec.template.create(
        security, xmlsec.constants.TransformExclC14N, xmlsec.constants.TransformRsaSha256
    )
    security.append(sig_node)
    ref = xmlsec.template.add_reference(sig_node, xmlsec.constants.TransformSha256, uri='#body-1')
    xmlsec.template.add_transform(ref, xmlsec.constants.TransformExclC14N)

    ctx = xmlsec.SignatureContext()
    ctx.register_id(body, id_attr='Id', id_ns=WSU_NS)
    key_pem = signing_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    ctx.key = xmlsec.Key.from_memory(key_pem, xmlsec.constants.KeyDataFormatPem)
    ctx.sign(sig_node)

    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def test_renew_disabled_returns_503(client, app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='wstep_enabled').first()
        previous = row.value if row else None
        _set_config('wstep_enabled', 'false')
    try:
        r = client.post(RENEW_URL, data=b'<GetPolicies/>')
        assert r.status_code == 503
    finally:
        with app.app_context():
            if previous is None:
                SystemConfig.query.filter_by(key='wstep_enabled').delete()
                db.session.commit()
            else:
                _set_config('wstep_enabled', previous)


def test_renew_requires_signature(client, app, wstep_renew_config):
    cert, key = _issue_test_cert(app, wstep_renew_config)
    csr = _renewal_csr(cert.subject, key)
    # Build an RST with no wsse:Security header at all.
    NSMAP = {'s': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS, 'wsse': WSSE_NS}
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=NSMAP)
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    bst = etree.SubElement(rst, '{%s}BinarySecurityToken' % WSSE_NS, EncodingType='base64')
    bst.text = base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode()
    unsigned = etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')

    r = client.post(RENEW_URL, data=unsigned)
    assert r.status_code == 400


def test_renew_rejects_tampered_signature(client, app, wstep_renew_config):
    cert, key = _issue_test_cert(app, wstep_renew_config)
    csr = _renewal_csr(cert.subject, key)
    tampered = _build_signed_rst(cert, key, csr, corrupt_signature=True)
    r = client.post(RENEW_URL, data=tampered)
    assert r.status_code == 400


def test_renew_rejects_unrecognized_certificate(client, app, wstep_renew_config):
    """A certificate UCM never issued (self-signed, matching key pair,
    valid signature) must still be refused — cryptographic validity of
    the signature is not the same as trust."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'unknown-client.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    foreign_cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    csr = _renewal_csr(name, key)
    signed = _build_signed_rst(foreign_cert, key, csr)
    r = client.post(RENEW_URL, data=signed)
    assert r.status_code == 400


def test_renew_rejects_serial_substitution_attack(client, app, wstep_renew_config):
    """A self-signed certificate that reuses a real, UCM-issued cert's
    serial number and subject, but is signed by an attacker's own key,
    must be rejected. Serial numbers and subjects are public (visible on
    any copy of an issued cert), so before the stored-cert byte comparison
    a lookup keyed on serial number alone was enough to pass. That let an
    attacker forge a lookalike cert, sign the RST with their own key, and
    get a fresh certificate issued for the victim's identity bound to the
    attacker's key."""
    victim_cert, _victim_key = _issue_test_cert(
        app, wstep_renew_config, common_name='serial-substitution-victim.example.test'
    )
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    forged_cert = (
        x509.CertificateBuilder()
        .subject_name(victim_cert.subject).issuer_name(victim_cert.subject)
        .public_key(attacker_key.public_key())
        .serial_number(victim_cert.serial_number)
        .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
        .sign(attacker_key, hashes.SHA256())
    )
    csr = _renewal_csr(victim_cert.subject, attacker_key)

    with app.app_context():
        serials_before = {row.serial_number for row in Certificate.query.all()}

    signed = _build_signed_rst(forged_cert, attacker_key, csr)
    r = client.post(RENEW_URL, data=signed)
    assert r.status_code == 400
    assert b'not recognized' in r.data

    with app.app_context():
        serials_after = {row.serial_number for row in Certificate.query.all()}
        assert serials_after == serials_before, (
            'no certificate must be issued for the forged-serial attack'
        )


def test_renew_rejects_subject_mismatch(client, app, wstep_renew_config):
    cert, key = _issue_test_cert(app, wstep_renew_config, common_name='subject-match.example.test')
    mismatched_csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'someone-else.example.test')])
    ).sign(key, hashes.SHA256())
    signed = _build_signed_rst(cert, key, mismatched_csr)
    r = client.post(RENEW_URL, data=signed)
    assert r.status_code == 400


def test_renew_rejects_signature_wrapping_attack(client, app, wstep_renew_config):
    """A decoy, unsigned CSR spliced in alongside a genuinely victim-signed
    Body must not be able to ride in under that valid signature — the
    attacker's key must never end up bound to the victim's identity.
    Regression test for the ws_security.SignedContent.covers() fix."""
    cert, key = _issue_test_cert(app, wstep_renew_config, common_name='wrapping-victim.example.test')
    legit_csr = _renewal_csr(cert.subject, key)
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    decoy_csr = _renewal_csr(cert.subject, attacker_key)

    with app.app_context():
        serials_before = {row.serial_number for row in Certificate.query.all()}

    attack = _build_signature_wrapping_attack_rst(cert, key, legit_csr, decoy_csr)
    r = client.post(RENEW_URL, data=attack)
    assert r.status_code == 400
    assert b'not covered by the request signature' in r.data

    with app.app_context():
        serials_after = {row.serial_number for row in Certificate.query.all()}
        assert serials_after == serials_before, 'no certificate must be issued for the rejected attack request'


def test_renew_succeeds_and_reissues(client, app, wstep_renew_config):
    cert, key = _issue_test_cert(app, wstep_renew_config, common_name='renew-happy-path.example.test')
    csr = _renewal_csr(cert.subject, key)
    signed = _build_signed_rst(cert, key, csr, message_id='urn:uuid:renew-happy')

    r = client.post(RENEW_URL, data=signed)
    assert r.status_code == 200
    assert r.content_type.startswith('application/soap+xml')

    root = etree.fromstring(r.data)
    relates_to = root.find(f'.//{{{ADDRESSING_NS}}}RelatesTo')
    assert relates_to is not None and relates_to.text == 'urn:uuid:renew-happy'

    bst_el = root.find(f'.//{{{WST_NS}}}RequestedSecurityToken/{{{WSSE_NS}}}BinarySecurityToken')
    new_cert = x509.load_der_x509_certificate(base64.b64decode(bst_el.text))
    assert new_cert.subject == cert.subject
    assert new_cert.serial_number != cert.serial_number

    with app.app_context():
        db_row = Certificate.query.filter_by(serial_number=str(new_cert.serial_number)).first()
        assert db_row is not None


def test_renewal_csr_without_san_keeps_the_certificate_names(client, app, wstep_renew_config):
    """A renewal keeps its identity: a CSR without SAN renews the names, not the CN."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'renew-names.example.test')])
    names = [x509.DNSName('a.renew-names.test'), x509.DNSName('b.renew-names.test')]
    csr = x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA256())
    with app.app_context():
        ca = db.session.get(CA, wstep_renew_config['id'])
        cert_pem, _serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=30, source='wstep', override_san=names)
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    signed = _build_signed_rst(cert, key, _renewal_csr(subject, key),
                               message_id='urn:uuid:renew-names')
    r = client.post(RENEW_URL, data=signed)
    assert r.status_code == 200, r.data
    bst = etree.fromstring(r.data).find(
        f'.//{{{WST_NS}}}RequestedSecurityToken/{{{WSSE_NS}}}BinarySecurityToken')
    renewed = x509.load_der_x509_certificate(base64.b64decode(bst.text))
    san = renewed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(san.get_values_for_type(x509.DNSName)) == {'a.renew-names.test',
                                                           'b.renew-names.test'}


def test_renew_refusal_gives_its_reason(client, app, wstep_renew_config, monkeypatch):
    from utils.request_names import RequestRejected
    cert, key = _issue_test_cert(app, wstep_renew_config, common_name='renew-reason.example.test')
    signed = _build_signed_rst(cert, key, _renewal_csr(cert.subject, key),
                               message_id='urn:uuid:renew-reason')

    def refuse(**_kw):
        raise RequestRejected('Invalid DNS name(s) in the request: marker')
    monkeypatch.setattr(CAService, 'sign_csr_from_crypto', refuse)
    r = client.post(RENEW_URL, data=signed)
    assert r.status_code == 400
    assert b'marker' in r.data
