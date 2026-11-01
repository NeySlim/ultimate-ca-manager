"""WSTEP renewal as Windows sends it: no WS-Security, the TLS client certificate
authenticates, and the CMC request carries a SignerInfo per key (the renewed
certificate's, and the new key's own when the key changes)."""
import base64
import datetime

import pytest
from asn1crypto import cms, core
from asn1crypto import csr as asn1_csr
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, Certificate, db
from services.ca_service import CAService
from services.cert_service import CertificateService
from services.wstep.rst_parser import _PKIData, _TaggedRequest
from tests.test_wstep_renew import RENEW_URL, _build_signed_rst, wstep_renew_config  # noqa: F401

PKIDATA_OID = '1.3.6.1.5.5.7.12.2'
PKCS7_VALUE_TYPE = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#PKCS7'


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _issue(app, ca_id, cn):
    key = _key()
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .sign(key, hashes.SHA256()))
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        cert_pem, _serial = CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='test')
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


def _issued_count(app):
    with app.app_context():
        return Certificate.query.count()


def test_windows_renewal_with_a_new_key_is_issued(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-new-key.example.test')
    new_key = _key()
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, new_key), [(new_key, None), (old_key, old_cert)]))

    r = _post(client, body, tls_cert=old_cert)

    assert r.status_code == 200, r.data
    issued = x509.load_der_x509_certificate(base64.b64decode(
        r.data.split(b'#X509v3"')[-1].split(b'>', 1)[1].split(b'<', 1)[0]))
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


def test_new_key_without_its_own_signature_is_refused(client, app, wstep_renew_config):
    """The old certificate vouches for the request, not for a key it never signed with."""
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'tls-renew-pop.example.test')
    foreign_key = _key()
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, foreign_key), [(old_key, old_cert)]))
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
    assert b'TLS client certificate' not in r.data
