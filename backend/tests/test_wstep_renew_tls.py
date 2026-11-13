"""WSTEP renewal as Windows sends it: no WS-Security, the TLS client certificate
authenticates, and the CMC request carries a SignerInfo per key (the renewed
certificate's, and the new key's own when the key changes). Both renewal paths
keep the renewed certificate's template, are audited and claim the renewed row once."""
import base64
import contextlib
import datetime
import json
import threading
import uuid
from unittest.mock import patch

import pytest
from asn1crypto import cms, core
from asn1crypto import csr as asn1_csr
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy import text, update
from sqlalchemy.orm.attributes import set_committed_value
from utils.serial_duplicates import INDEX as SERIAL_INDEX

from models import CA, AuditLog, CATemplatePin, Certificate, db
from models.certificate_template import CertificateTemplate
from tests.fixtures.templates import delete_templates
from services.ca.ca_signing import AlreadySuperseded
from services.ca_service import CAService
from services.cert_service import CertificateService
from services.wstep import wstep_service
from services.wstep.rst_parser import _PKIData, _TaggedRequest, _unwrap_pkcs7_csr, parse_rst
from tests.pqc_fixtures import fixture_bytes
from tests.windows_profile_support import default_profile
from tests.test_wstep_renew import RENEW_URL, _build_signed_rst, wstep_renew_config  # noqa: F401
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

PKIDATA_OID = '1.3.6.1.5.5.7.12.2'
PKCS7_VALUE_TYPE = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#PKCS7'


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _issue(app, ca_id, cn):
    key = _key()
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
           .sign(key, hashes.SHA256()))
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        cert_pem, _serial = CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='wstep')
    return x509.load_pem_x509_certificate(cert_pem.encode()), key


def _renewal_csr(cert, key):
    return (x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))


def _signer_info(key, sid, signed_attrs):
    signature = key.sign(b'\x31' + signed_attrs.dump()[1:], padding.PKCS1v15(), hashes.SHA256())
    return cms.SignerInfo({
        'version': 'v3' if 'subject_key_identifier' in sid else 'v1', 'sid': sid,
        'digest_algorithm': {'algorithm': 'sha256'}, 'signed_attrs': signed_attrs,
        'signature_algorithm': {'algorithm': 'rsassa_pkcs1v15'}, 'signature': signature,
    })


def _cmc_renewal(csr, signers):
    """CMC PKIData around ``csr``, signed by each ``(key, cert or None)``: a
    certificate is named by issuer and serial, a bare key by its identifier."""
    pki_data = _PKIData({
        'control_sequence': [],
        'req_sequence': [_TaggedRequest(name='tcr', value={
            'body_part_id': 1,
            'certification_request': asn1_csr.CertificationRequest.load(
                csr.public_bytes(serialization.Encoding.DER)),
        })],
        'cms_sequence': [], 'other_msg_sequence': [],
    }).dump()
    digest = hashes.Hash(hashes.SHA256())
    digest.update(pki_data)
    signed_attrs = cms.CMSAttributes([
        {'type': 'content_type', 'values': [PKIDATA_OID]},
        {'type': 'message_digest', 'values': [core.OctetString(digest.finalize())]},
    ])
    infos, certificates = [], []
    for key, cert in signers:
        if cert is None:
            sid = {'subject_key_identifier': x509.SubjectKeyIdentifier.from_public_key(key.public_key()).digest}
        else:
            parsed = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
            sid = {'issuer_and_serial_number': {'issuer': parsed.issuer, 'serial_number': parsed.serial_number}}
            certificates.append(parsed)
        infos.append(_signer_info(key, sid, signed_attrs))
    content = {
        'version': 'v3', 'digest_algorithms': [{'algorithm': 'sha256'}],
        'encap_content_info': {'content_type': PKIDATA_OID, 'content': pki_data},
        'signer_infos': infos,
    }
    if certificates:
        content['certificates'] = certificates
    return cms.ContentInfo({'content_type': 'signed_data', 'content': content}).dump()


def _rst(token_der):
    return (
        '<s:Envelope xmlns:a="http://www.w3.org/2005/08/addressing" '
        'xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Header>'
        '<a:Action s:mustUnderstand="1">http://schemas.microsoft.com/windows/pki/2009/01/enrollment/RST/wstep</a:Action>'
        '<a:MessageID>urn:uuid:7f1c0de8-0000-4000-8000-000000000001</a:MessageID></s:Header><s:Body>'
        '<RequestSecurityToken xmlns="http://docs.oasis-open.org/ws-sx/ws-trust/200512">'
        '<TokenType>http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3</TokenType>'
        '<RequestType>http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue</RequestType>'
        f'<BinarySecurityToken ValueType="{PKCS7_VALUE_TYPE}" '
        'xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        f'{base64.b64encode(token_der).decode()}</BinarySecurityToken>'
        '</RequestSecurityToken></s:Body></s:Envelope>'
    ).encode()


def _post(client, body, tls_cert=None):
    environ = {'peercert': tls_cert.public_bytes(serialization.Encoding.DER)} if tls_cert is not None else {}
    return client.post(RENEW_URL, data=body, environ_base=environ,
                       headers={'Content-Type': 'application/soap+xml; charset=utf-8'})


def _issued_from(response):
    return x509.load_der_x509_certificate(base64.b64decode(
        response.data.split(b'#X509v3"')[-1].split(b'>', 1)[1].split(b'<', 1)[0]))


def _issued_count(app):
    with app.app_context():
        return Certificate.query.count()


def test_windows_renewal_with_a_new_key_is_issued(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-new-key.example.test')
    new_key = _key()
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, new_key), [(new_key, None), (old_key, old_cert)]))

    r = _post(client, body, tls_cert=old_cert)

    assert r.status_code == 200, r.data
    issued = _issued_from(r)
    assert issued.public_key() == new_key.public_key()
    assert issued.subject == old_cert.subject
    with app.app_context():
        old_row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
        assert old_row.archived, 'the renewed certificate is superseded'


def test_windows_renewal_keeping_the_key_is_issued(client, app, wstep_renew_config):
    """Same key: the renewed certificate's signature proves both."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-same-key.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    assert _post(client, body, tls_cert=old_cert).status_code == 200


def test_superseded_certificate_cannot_renew_again(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-twice.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    assert _post(client, body, tls_cert=old_cert).status_code == 200
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'superseded' in r.data


def test_renewal_without_a_client_certificate_is_refused(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-no-cert.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    before = _issued_count(app)
    r = _post(client, body)
    assert r.status_code == 400
    assert b'TLS client certificate' in r.data
    assert _issued_count(app) == before


def test_request_signed_with_another_key_is_refused(client, app, wstep_renew_config):
    """The TLS certificate is genuine, but whoever signed the request does not hold its key."""
    old_cert, _old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-wrong-key.example.test')
    attacker = _key()
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, attacker), [(attacker, None), (attacker, old_cert)]))
    before = _issued_count(app)
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'proof of possession failed' in r.data
    assert _issued_count(app) == before


def test_request_signed_by_another_certificate_is_refused(client, app, wstep_renew_config):
    """A request signed by a second certificate of the same CA does not renew the TLS one."""
    tls_cert, _tls_key = _issue(app, wstep_renew_config['id'], 'tls-renew-bound.example.test')
    other_cert, other_key = _issue(app, wstep_renew_config['id'], 'tls-renew-bound.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(other_cert, other_key), [(other_key, other_cert)]))
    r = _post(client, body, tls_cert=tls_cert)
    assert r.status_code == 400
    assert b'not signed by the certificate being renewed' in r.data


def _broken_self_signature(csr):
    der = bytearray(csr.public_bytes(serialization.Encoding.DER))
    der[-1] ^= 0x01
    return x509.load_der_x509_csr(bytes(der))


def test_new_key_without_its_own_signature_is_refused(client, app, wstep_renew_config):
    """The old certificate vouches for the request, not for a key it never signed with."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-pop.example.test')
    foreign_key = _key()
    csr = _broken_self_signature(_renewal_csr(old_cert, foreign_key))
    body = _rst(_cmc_renewal(csr, [(old_key, old_cert)]))
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'does not identify itself by the request key' in r.data


def test_revoked_certificate_is_refused(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-revoked.example.test')
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
        CertificateService.revoke_certificate(row.id, reason='keyCompromise', username='test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'revoked' in r.data


def test_certificate_of_another_ca_is_refused(client, app, create_ca, wstep_renew_config):
    other_ca = create_ca(cn='WSTEP TLS renewal other CA')
    old_cert, old_key = _issue(app, other_ca['id'], 'tls-renew-other-ca.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'not recognized' in r.data


def test_expired_certificate_is_refused(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-expired.example.test')
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
        row.valid_to = datetime.datetime(2000, 1, 1)
        db.session.commit()
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'expired' in r.data


def test_ws_security_signature_still_takes_the_xml_path(client, app, wstep_renew_config):
    """A signed RST is judged on its XML signature even with a TLS certificate present."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-xmldsig.example.test')
    other_cert, _other_key = _issue(app, wstep_renew_config['id'], 'tls-renew-xmldsig-other.example.test')
    signed = _build_signed_rst(old_cert, old_key, _renewal_csr(old_cert, old_key), corrupt_signature=True)
    r = _post(client, signed, tls_cert=other_cert)
    assert r.status_code == 400
    # The XML signature's own refusal: the TLS path would name the signer instead
    assert b'Signature verification failed' in r.data, r.data


def test_forged_client_certificate_header_is_ignored(client, app, wstep_renew_config, monkeypatch):
    """SSL_CLIENT_CERT from a peer outside the trusted proxies authenticates nothing."""
    monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-forged.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    pem = old_cert.public_bytes(serialization.Encoding.PEM).decode().replace('\n', ' ').strip()
    before = _issued_count(app)
    r = client.post(RENEW_URL, data=body, environ_base={'REMOTE_ADDR': '203.0.113.7'}, headers={
        'Content-Type': 'application/soap+xml; charset=utf-8',
        'X-SSL-Client-Cert': pem, 'X-SSL-Client-Verify': 'SUCCESS',
    })
    assert r.status_code == 400
    assert b'TLS client certificate' in r.data, r.data
    assert _issued_count(app) == before


@pytest.mark.parametrize('new_key_size, key_signer_first', [(2048, True), (3072, False)])
def test_new_key_signer_is_found_in_either_der_order(client, app, wstep_renew_config,
                                                     new_key_size, key_signer_first):
    """DER sorts the SignerInfos: a longer new key puts the renewed certificate's first."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], f'tls-renew-order-{new_key_size}.example.test')
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=new_key_size)
    token = _cmc_renewal(_renewal_csr(old_cert, new_key), [(new_key, None), (old_key, old_cert)])
    first = cms.ContentInfo.load(token)['content']['signer_infos'][0]['sid'].name
    assert (first == 'subject_key_identifier') is key_signer_first
    r = _post(client, _rst(token), tls_cert=old_cert)
    assert r.status_code == 200, r.data


def test_slh_dsa_request_is_refused_by_key_policy(client, app, wstep_renew_config):
    """An unsupported key is refused by policy, never compared (UnsupportedAlgorithm)."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-slhdsa.example.test')
    slh_csr = x509.load_pem_x509_csr(fixture_bytes('slhdsa-sha2-128s-csr.pem'))
    r = _post(client, _rst(_cmc_renewal(slh_csr, [(old_key, old_cert)])), tls_cert=old_cert)
    assert r.status_code == 400
    assert b'not signable by this instance' in r.data, r.data


def test_renewal_signer_check_survives_an_unsupported_certificate_key():
    key = _key()
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'slh')]))
           .sign(key, hashes.SHA256()))
    _csr_der, _part, signed_data = _unwrap_pkcs7_csr(_cmc_renewal(csr, [(key, None)]))
    slh_cert = x509.load_pem_x509_certificate(fixture_bytes('slhdsa-sha2-128s-cert.pem'))
    assert wstep_service._verify_renewal_signer(signed_data, slh_cert) == 'Unsupported public key'


# XML-DSig renewal with a CMC-wrapped request: a new key proves itself too

def _xml_cmc(old_cert, old_key, csr, signers):
    return _build_signed_rst(old_cert, old_key, csr, token_der=_cmc_renewal(csr, signers),
                             value_type=PKCS7_VALUE_TYPE)


def test_xml_renewal_with_a_new_key_needs_its_proof(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'xml-renew-new-key.example.test')
    foreign = _key()
    before = _issued_count(app)
    csr = _broken_self_signature(_renewal_csr(old_cert, foreign))
    r = _post(client, _xml_cmc(old_cert, old_key, csr, [(old_key, old_cert)]))
    assert r.status_code == 400
    assert b'does not identify itself by the request key' in r.data, r.data
    assert _issued_count(app) == before


def test_xml_renewal_with_a_proven_new_key_is_issued(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'xml-renew-proven.example.test')
    new_key = _key()
    r = _post(client, _xml_cmc(old_cert, old_key, _renewal_csr(old_cert, new_key),
                               [(new_key, None), (old_key, old_cert)]))
    assert r.status_code == 200, r.data


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_new_key_proven_by_its_own_csr_signature_is_issued(client, app, wstep_renew_config, path):
    """RFC 5272: the PKCS#10 self-signature proves the new key, without a SignerInfo of its own."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], f'{path}-renew-p10-pop.example.test')
    csr = _renewal_csr(old_cert, _key())
    if path == 'tls':
        r = _post(client, _rst(_cmc_renewal(csr, [(old_key, old_cert)])), tls_cert=old_cert)
    else:
        r = _post(client, _xml_cmc(old_cert, old_key, csr, [(old_key, old_cert)]))
    assert r.status_code == 200, r.data
    assert _issued_from(r).public_key() == csr.public_key()


def test_xml_renewal_keeping_the_key_needs_no_other_proof(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'xml-renew-same-key.example.test')
    r = _post(client, _xml_cmc(old_cert, old_key, _renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    assert r.status_code == 200, r.data


# Audit

def _audit_rows(app, serial):
    with app.app_context():
        return [(a.username, a.success, a.details) for a in AuditLog.query.filter(
            AuditLog.action == 'certificate.renewed', AuditLog.details.contains(f'old serial {serial}')).all()]


def test_renewal_is_audited_with_both_serials(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-audit.example.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 200, r.data
    new_serial = _issued_from(r).serial_number
    assert _audit_rows(app, old_cert.serial_number) == [('wstep-client-cert', True, (
        f'WSTEP renewal from 127.0.0.1: old serial {old_cert.serial_number}, new serial {new_serial} '
        '(profile default)'))]


def test_refused_renewal_is_audited(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'xml-renew-audit-refused.example.test')
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
        CertificateService.revoke_certificate(row.id, reason='keyCompromise', username='test')
    signed = _build_signed_rst(old_cert, old_key, _renewal_csr(old_cert, old_key))
    assert _post(client, signed).status_code == 400
    assert _audit_rows(app, old_cert.serial_number) == [('wstep-ws-security', False, (
        'WSTEP renewal refused from 127.0.0.1: Signing certificate has been revoked '
        f'(old serial {old_cert.serial_number}, profile default)'))]


def _refusal_count(app):
    with app.app_context():
        return AuditLog.query.filter(AuditLog.action == 'certificate.renewed',
                                     AuditLog.details.contains('WSTEP renewal refused')).count()


def test_refusal_for_an_unknown_certificate_is_not_audited(client, app, wstep_renew_config):
    """An anonymous request, or a lookalike naming a real serial, does not write to the audit log."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-unaudited.example.test')
    lookalike_key = _key()
    lookalike = (x509.CertificateBuilder().subject_name(old_cert.subject).issuer_name(old_cert.subject)
                 .public_key(lookalike_key.public_key()).serial_number(old_cert.serial_number)
                 .not_valid_before(old_cert.not_valid_before_utc).not_valid_after(old_cert.not_valid_after_utc)
                 .sign(lookalike_key, hashes.SHA256()))
    before = _refusal_count(app)
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    assert _post(client, body).status_code == 400
    signed = _build_signed_rst(lookalike, lookalike_key, _renewal_csr(lookalike, lookalike_key))
    assert _post(client, signed).status_code == 400
    assert _refusal_count(app) == before


def test_lookalike_of_a_revoked_and_deleted_certificate_is_not_audited(client, app, wstep_renew_config):
    """The persistent revocation record matches a serial only, which anyone can copy."""
    from models.revoked_serial import RevokedSerial
    old_cert, _old_key = _issue(app, wstep_renew_config['id'], 'xml-renew-deleted.example.test')
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).one()
        db.session.add(RevokedSerial(caref=row.caref, serial_number=row.serial_number,
                                     valid_to=old_cert.not_valid_after_utc.replace(tzinfo=None)))
        db.session.delete(row)
        db.session.commit()
    key = _key()
    lookalike = (x509.CertificateBuilder().subject_name(old_cert.subject).issuer_name(old_cert.subject)
                 .public_key(key.public_key()).serial_number(old_cert.serial_number)
                 .not_valid_before(old_cert.not_valid_before_utc).not_valid_after(old_cert.not_valid_after_utc)
                 .sign(key, hashes.SHA256()))
    before = _refusal_count(app)
    r = _post(client, _build_signed_rst(lookalike, key, _renewal_csr(lookalike, key)))
    assert r.status_code == 400
    # Stored nowhere, it names no profile and so no CA: refused before any record is read
    assert b'not recognized' in r.data, r.data
    assert _refusal_count(app) == before


# Concurrent replay: the renewed row is claimed by compare-and-set

def test_second_renewal_loses_the_claim(client, app, wstep_renew_config, monkeypatch):
    """The row is archived between the check and the write, as by a concurrent renewal."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-race.example.test')
    checked = wstep_service._renewable_certificate

    def check_then_lose_the_race(ca, cert):
        row, err = checked(ca, cert)
        _archive_behind_the_session(row.id)
        return row, err

    monkeypatch.setattr(wstep_service, '_renewable_certificate', check_then_lose_the_race)
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    before = _issued_count(app)
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'superseded' in r.data, r.data
    assert _issued_count(app) == before


def _archive_behind_the_session(row_id):
    db.session.execute(update(Certificate).where(Certificate.id == row_id).values(archived=True)
                       .execution_options(synchronize_session=False))


@pytest.mark.parametrize('backend', [
    pytest.param('sqlite', marks=pytest.mark.sqlite_only(reason='the SQLite half runs on the session database')),
    pytest.param('postgresql', marks=pytest.mark.postgres)])
def test_supersede_is_a_compare_and_set(app, backend):
    """Of two signings superseding one row, only the first stores a certificate."""
    from tests.test_crl_persistent_revocations import _PG_URL, _make_ca, _on_postgresql
    if backend == 'postgresql' and not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set; skipping the PostgreSQL target')
    with (_on_postgresql(app) if backend == 'postgresql' else contextlib.nullcontext()), app.app_context():
        assert db.engine.dialect.name == backend
        ca, _ca_key, _ca_cert = _make_ca()
        key = _key()
        csr = _eku_csr(f'cas-{backend}.example.test', key, ExtendedKeyUsageOID.CLIENT_AUTH)
        CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='test')
        row = Certificate.query.filter_by(caref=ca.refid).one()
        CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='test', supersedes=row)
        assert db.session.get(Certificate, row.id).archived
        stale = db.session.get(Certificate, row.id)
        set_committed_value(stale, 'archived', False)
        with pytest.raises(AlreadySuperseded):
            CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='test', supersedes=stale)
        assert Certificate.query.filter_by(caref=ca.refid).count() == 2


@pytest.mark.postgres
def test_two_claims_never_lock_in_opposite_orders(app):
    """Listed in opposite orders, two claims still lock by id: one wins, neither deadlocks."""
    from services.ca.ca_signing import _claim_superseded
    from services.cert import issued_lookup
    from tests.test_crl_persistent_revocations import _PG_URL, _make_ca, _on_postgresql
    if not _PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set; skipping the PostgreSQL target')
    listed = issued_lookup._rows_holding
    both_hold_one = threading.Barrier(2, timeout=3)
    local, results, errors = threading.local(), [], []

    def rows_in_this_threads_order(*args, **kwargs):
        rows = sorted(listed(*args, **kwargs), key=lambda r: r.id)
        return rows if local.first else rows[::-1]

    with _on_postgresql(app):
        with app.app_context():
            ca, _ca_key, _ca_cert = _make_ca()
            csr = _eku_csr('claim-order.example.test', _key(), ExtendedKeyUsageOID.CLIENT_AUTH)
            CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='test')
            row = Certificate.query.filter_by(caref=ca.refid).one()
            columns = {c.name: getattr(row, c.name) for c in Certificate.__table__.columns
                       if c.name not in ('id', 'refid')}
            twin = Certificate(refid=str(uuid.uuid4()), **columns)
            # A twin exists only where migration 142 is pending; this schema is dropped afterwards
            db.session.execute(text(f'DROP INDEX IF EXISTS {SERIAL_INDEX}'))
            db.session.add(twin)
            db.session.commit()
            row_id = row.id
            real_execute = db.session.execute

        def execute_then_meet(*args, **kwargs):
            result = real_execute(*args, **kwargs)
            if not getattr(local, 'met', False):
                local.met = True
                try:
                    both_hold_one.wait()
                except threading.BrokenBarrierError:
                    pass  # the other one is waiting for this lock, as it should
            return result

        def claim(first):
            local.first = first
            with app.app_context():
                try:
                    results.append(_claim_superseded(db.session.get(Certificate, row_id)))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    errors.append(repr(e)[:200])
                finally:
                    db.session.remove()

        with patch.object(issued_lookup, '_rows_holding', rows_in_this_threads_order), \
                patch.object(db.session, 'execute', execute_then_meet):
            threads = [threading.Thread(target=claim, args=(first,)) for first in (True, False)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
    assert errors == []
    assert sorted(results) == [False, True]


# Template of the renewed certificate (MS-CRTD certificateTemplate, as AD CS)

@pytest.fixture
def templated_ca(app, create_ca):
    """A CA offering the given templates: {name: (EKU names, allowed AD group)}. The default
    profile its certificates are issued and renewed under exists for the test."""
    from tests.windows_profile_support import default_profile
    made = []
    with app.app_context():
        no_profile = default_profile() is None
        default_profile(create=True)
        db.session.commit()

    def _make(cn, templates):
        ca_data = create_ca(cn=cn)
        with app.app_context():
            for name, (ekus, group) in templates.items():
                t = CertificateTemplate(
                    name=f'{cn} {name}', template_type='usr_cert', key_type='RSA-2048',
                    validity_days=30, digest='sha256', is_active=True, allowed_ad_group=group,
                    extensions_template=json.dumps({'extended_key_usage': ekus}))
                db.session.add(t)
                db.session.flush()
                db.session.add(CATemplatePin(ca_id=ca_data['id'], template_id=t.id))
                db.session.commit()
                made.append(t.id)
        return ca_data['id']
    yield _make
    with app.app_context():
        delete_templates(made)
        if no_profile:
            Certificate.query.filter(Certificate.windows_profile_id == default_profile().id).update(
                {'windows_profile_id': None})
            db.session.delete(default_profile())
        db.session.commit()


USER_AND_CODESIGN = {'User': (['clientAuth'], None), 'CodeSign': (['codeSigning'], 'Domain Admins')}


def _eku_csr(cert_or_name, key, *ekus):
    name = cert_or_name.subject if isinstance(cert_or_name, x509.Certificate) else x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, cert_or_name)])
    return (x509.CertificateSigningRequestBuilder().subject_name(name)
            .add_extension(x509.ExtendedKeyUsage(list(ekus)), critical=False)
            .sign(key, hashes.SHA256()))


def _wstep_issued(app, ca_id, cn):
    """A certificate issued over WSTEP, so it names its template."""
    key = _key()
    csr = _eku_csr(cn, key, ExtendedKeyUsageOID.CLIENT_AUTH)
    with app.app_context():
        cert_pem, err = wstep_service.issue(db.session.get(CA, ca_id),
                                            csr.public_bytes(serialization.Encoding.DER), 30, profile=default_profile())
    assert err is None, err
    return x509.load_pem_x509_certificate(cert_pem.encode()), key


def _template_oid(cert):
    try:
        return cert.extensions.get_extension_for_class(x509.MSCertificateTemplate).value.template_id
    except x509.ExtensionNotFound:
        return None


def _ekus(cert):
    return set(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)


def _renew(app, ca_id, path, old_cert, old_key, csr):
    """Renew through the service on the TLS or the XML-DSig path: (certificate or None, error)."""
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        if path == 'tls':
            csr_der, _part, signed = _unwrap_pkcs7_csr(_cmc_renewal(csr, [(old_key, old_cert)]))
            pem, err = wstep_service.renew_with_client_certificate(
                ca, old_cert, csr_der, signed, 30, profile=default_profile())
        else:
            parsed = parse_rst(_build_signed_rst(old_cert, old_key, csr))
            signer, err = wstep_service.signed_request_certificate(parsed.security_header, parsed.csr_element)
            assert err is None, err
            pem, err = wstep_service.renew(ca, signer, parsed.csr_der, 30, profile=default_profile())
    return (x509.load_pem_x509_certificate(pem.encode()) if pem else None), err


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_renewal_cannot_move_to_another_template(app, templated_ca, path):
    """A clientAuth certificate from 'User' does not renew into the 'Domain Admins' code signing template."""
    ca_id = templated_ca(f'WSTEP renew template CA {path}', USER_AND_CODESIGN)
    old_cert, old_key = _wstep_issued(app, ca_id, f'template-move-{path}.example.test')
    before = _issued_count(app)
    cert, err = _renew(app, ca_id, path, old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CODE_SIGNING))
    assert cert is None
    assert err == (f"Renewal stays on template 'WSTEP renew template CA {path} User'; the request asks "
                   f"for template 'WSTEP renew template CA {path} CodeSign'"), err
    assert _issued_count(app) == before


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_renewal_keeps_the_template_and_its_ekus(app, templated_ca, path):
    ca_id = templated_ca(f'WSTEP renew same template CA {path}', USER_AND_CODESIGN)
    old_cert, old_key = _wstep_issued(app, ca_id, f'template-keep-{path}.example.test')
    cert, err = _renew(app, ca_id, path, old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert) == _template_oid(old_cert) is not None
    assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


@pytest.mark.parametrize('template_bound', [True, False])
def test_request_without_eku_gets_no_more_than_the_renewed_ekus(app, templated_ca, template_bound):
    """No EKU in the CSR: the template's EKUs (or the certificate's at par), not a default profile."""
    ca_id = templated_ca(f'WSTEP renew no-EKU CA {template_bound}', USER_AND_CODESIGN)
    issue = _wstep_issued if template_bound else _issue
    old_cert, old_key = issue(app, ca_id, f'no-eku-{template_bound}.example.test')
    csr = x509.CertificateSigningRequestBuilder().subject_name(old_cert.subject).sign(old_key, hashes.SHA256())
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key, csr)
    assert err is None, err
    assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


def test_renewal_keeps_the_key_family_of_its_template(app, templated_ca):
    from utils import key_algorithms
    if not key_algorithms.mldsa_supported():
        pytest.skip('this build has no ML-DSA')
    ca_id = templated_ca('WSTEP renew family CA', USER_AND_CODESIGN)
    old_cert, _old_key = _wstep_issued(app, ca_id, 'template-family.example.test')
    mldsa_csr = (x509.CertificateSigningRequestBuilder().subject_name(old_cert.subject)
                 .sign(key_algorithms.generate('ML-DSA-65'), None))
    with app.app_context():
        _template, _extra, _issued, err = wstep_service._renewal_template(
            db.session.get(CA, ca_id), old_cert, mldsa_csr, profile=None)
    assert err == "Template 'WSTEP renew family CA User' issues RSA-2048 keys, not ML-DSA-65", err


def test_template_no_longer_offered_refuses_the_renewal(app, templated_ca):
    ca_id = templated_ca('WSTEP renew withdrawn template CA', USER_AND_CODESIGN)
    old_cert, old_key = _wstep_issued(app, ca_id, 'template-withdrawn.example.test')
    with app.app_context():
        CertificateTemplate.query.filter_by(name='WSTEP renew withdrawn template CA User').update(
            {'is_active': False})
        db.session.commit()
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert cert is None
    assert err == 'The certificate template of the certificate being renewed is not offered by this CA'


def test_legacy_certificate_cannot_widen_its_ekus(app, templated_ca):
    """Without a template extension the request picks the template, never beyond the certificate's EKUs."""
    ca_id = templated_ca('WSTEP renew legacy CA', USER_AND_CODESIGN)
    old_cert, old_key = _issue(app, ca_id, 'legacy-widen.example.test')
    assert _template_oid(old_cert) is None
    csr = _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.CODE_SIGNING)
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key, csr)
    assert cert is None
    assert err == 'Renewal cannot add Extended Key Usages the certificate being renewed does not carry'


def test_legacy_certificate_is_not_stamped_with_a_broader_template(app, templated_ca):
    ca_id = templated_ca('WSTEP renew legacy broad CA',
                         {'Broad': (['clientAuth', 'emailProtection'], None)})
    old_cert, old_key = _issue(app, ca_id, 'legacy-broad.example.test')
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert) is None
    assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


def test_legacy_certificate_takes_a_fitting_template(app, templated_ca):
    ca_id = templated_ca('WSTEP renew legacy fit CA', USER_AND_CODESIGN)
    old_cert, old_key = _issue(app, ca_id, 'legacy-fit.example.test')
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert) is not None
    assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


def test_restored_duplicate_beside_an_archived_original_still_renews(client, app, wstep_renew_config, no_serial_index):
    """The live duplicate answers the status and is the row the renewal claims."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-duplicate.example.test')
    with app.app_context():
        original = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).one()
        columns = {c.name: getattr(original, c.name) for c in Certificate.__table__.columns
                   if c.name not in ('id', 'refid')}
        duplicate = Certificate(refid=f'{original.refid}-restored', **columns)
        db.session.add(duplicate)
        original.archived = True
        db.session.commit()
        duplicate_id = duplicate.id
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(Certificate, duplicate_id).archived is True


def test_legacy_certificate_with_any_eku_renews_at_par(app, templated_ca):
    """anyExtendedKeyUsage on the renewed certificate (admin Sign-CSR) is never carried over, nor a failure."""
    ca_id = templated_ca('WSTEP renew legacy any-EKU CA', {'Broad': (['clientAuth', 'emailProtection'], None)})
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'legacy-any-eku.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    # Only its extensions are read: the template is chosen before the signature
    renewed = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now)
               .not_valid_after(now + datetime.timedelta(days=30))
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH,
                                                     ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE]), critical=False)
               .sign(key, hashes.SHA256()))
    csr = _eku_csr(renewed, key, ExtendedKeyUsageOID.CLIENT_AUTH)
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        template, extra, issued, err = wstep_service._renewal_template(ca, renewed, csr, profile=None)
        assert (template, err) == (None, None)
        pem, _serial = CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='wstep',
                                                      extra_ekus=extra, template_ekus=issued)
    assert _ekus(x509.load_pem_x509_certificate(pem.encode())) == {ExtendedKeyUsageOID.CLIENT_AUTH}


def test_legacy_certificate_is_refused_when_the_ca_offers_no_template(app, templated_ca):
    """Its pinned templates all deactivated, a CA renews nothing without a template."""
    ca_id = templated_ca('WSTEP renew legacy deactivated CA', {'Gone': (['clientAuth'], None)})
    key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'legacy-deactivated.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    renewed = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now)
               .not_valid_after(now + datetime.timedelta(days=30))
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
               .sign(key, hashes.SHA256()))
    csr = _eku_csr(renewed, key, ExtendedKeyUsageOID.CLIENT_AUTH)
    with app.app_context():
        for pin in CATemplatePin.query.filter_by(ca_id=ca_id):
            pin.template.is_active = False
        db.session.commit()
        _template, _extra, _issued, err = wstep_service._renewal_template(db.session.get(CA, ca_id), renewed, csr, profile=None)
    assert err == 'This CA offers no certificate template'
    assert isinstance(err, wstep_service.ServerError)


def test_renewal_may_ask_for_what_xcep_advertised(app, templated_ca):
    """A request naming a capped EKU of its template is renewed as issuance treats it: without it."""
    ca_id = templated_ca('WSTEP renew advertised CA', {'Stamp': (['clientAuth', 'timeStamping'], None)})
    old_cert, old_key = _wstep_issued(app, ca_id, 'template-advertised.example.test')
    csr = _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.TIME_STAMPING)
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key, csr)
    assert err is None, err
    assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


def test_template_without_ekus_keeps_the_renewal_within_the_old_ones(app, templated_ca):
    ca_id = templated_ca('WSTEP renew bare template CA', {'Bare': ([], None)})
    old_cert, old_key = _wstep_issued(app, ca_id, 'template-bare.example.test')
    assert _template_oid(old_cert) is not None
    wider = _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.CODE_SIGNING)
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key, wider)
    assert cert is None and err.startswith("Renewal stays on template 'WSTEP renew bare template CA Bare'"), err
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _ekus(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


@pytest.mark.parametrize('twin', ['same', 'hex_serial', 'crlf_pem'])
def test_two_live_duplicates_are_claimed_together(client, app, wstep_renew_config, twin, no_serial_index):
    """A certificate held twice renews once, however the twin stores its serial or PEM."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], f"tls-renew-two-live-{twin.replace('_', '-')}.example.test")
    with app.app_context():
        original = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).one()
        columns = {c.name: getattr(original, c.name) for c in Certificate.__table__.columns
                   if c.name not in ('id', 'refid')}
        if twin == 'hex_serial':
            columns['serial_number'] = format(old_cert.serial_number, 'X')
        elif twin == 'crlf_pem':
            pem = old_cert.public_bytes(serialization.Encoding.PEM).replace(b'\n', b'\r\n')
            columns['crt'] = base64.b64encode(pem).decode()
        twin_row = Certificate(refid=f'{original.refid}-twin', **columns)
        db.session.add(twin_row)
        db.session.commit()
        ids = (original.id, twin_row.id)
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    assert _post(client, body, tls_cert=old_cert).status_code == 200
    r = _post(client, body, tls_cert=old_cert)
    assert r.status_code == 400
    assert b'superseded' in r.data, r.data
    with app.app_context():
        assert [db.session.get(Certificate, i).archived for i in ids] == [True, True]


def test_a_twin_claimed_by_another_renewal_loses_the_claim(app, wstep_renew_config, monkeypatch, no_serial_index):
    """One of two live rows archived between the read and the update: the claim fails."""
    from services.ca.ca_signing import _claim_superseded
    old_cert, _old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-twin-race.example.test')
    with app.app_context():
        original = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).one()
        columns = {c.name: getattr(original, c.name) for c in Certificate.__table__.columns
                   if c.name not in ('id', 'refid')}
        twin = Certificate(refid=f'{original.refid}-race', **columns)
        db.session.add(twin)
        db.session.commit()
        twin_id = twin.id
        execute = db.session.execute

        def concurrent_claim_first(statement, *args, **kwargs):
            if getattr(statement, 'is_update', False):
                execute(update(Certificate).where(Certificate.id == twin_id).values(archived=True)
                        .execution_options(synchronize_session=False))
            return execute(statement, *args, **kwargs)

        monkeypatch.setattr(db.session, 'execute', concurrent_claim_first)
        assert _claim_superseded(original) is False
        monkeypatch.undo()
        db.session.rollback()


@pytest.mark.parametrize('ekus', [['clientAuth', 'emailProtection', '1.3.6.1.4.1.311.10.3.4'],
                                  ['clientAuth'], ['clientAuth', 'smartcardLogon']])
def test_renewal_keeps_the_key_usage_of_its_template(app, templated_ca, ekus):
    """A renewal is signed under the profile of its template, as the issuance was."""
    ca_id = templated_ca(f'WSTEP renew user KU CA {len(ekus)}', {'User': (ekus, None)})
    with app.app_context():
        oids = [x509.ObjectIdentifier(o) for o in wstep_service._template_configured_ekus(
            CertificateTemplate.query.filter_by(name=f'WSTEP renew user KU CA {len(ekus)} User').one())]
    key = _key()
    csr = _eku_csr('jdoe', key, *oids)
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, ca_id),
                                       csr.public_bytes(serialization.Encoding.DER), 30, profile=None)
    assert err is None, err
    old_cert = x509.load_pem_x509_certificate(pem.encode())
    cert, err = _renew(app, ca_id, 'tls', old_cert, key, _eku_csr(old_cert, key, *oids))
    assert err is None, err
    assert (cert.extensions.get_extension_for_class(x509.KeyUsage).value
            == old_cert.extensions.get_extension_for_class(x509.KeyUsage).value)
