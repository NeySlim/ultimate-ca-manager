"""A CSR signed with SHA-1 is refused with the reason EST and WSTEP give, on every other door too.

ACME keeps badCSR (RFC 8555 §7.4), SCEP answers badAlg (RFC 8894 §3.2.1.4.5); the text
comes from utils.csr_diagnostics, the one place that diagnoses a weak CSR hash.
"""
import base64
import json

import asn1crypto.csr
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import AttributeOID, NameOID

from services.scep.crypto_helpers import create_signed_pkcs7
from services.trust_store.trust_store_service import TrustStoreService
from tests.test_acme_pq import _b64u, _jws, _ready_order, rsa_account, rsa_ca, signing_ca  # noqa: F401
from tests.test_scep_fips import (  # noqa: F401
    CHALLENGE, _attrs, _envelope, _pkcs_req, _process, _resign, fips_off, fips_on, scep_ca,
)
from tests.test_scep_rfc8894_operations import FAIL_INFO_OID, PKI_STATUS_OID, _response_attributes
from utils.csr_diagnostics import weak_csr_hash_error
from utils.request_names import RequestRejected

SHA1_REASON = 'CSR signed with an unsupported hash algorithm (sha1); use SHA-256 or stronger'
FAIL_INFO_TEXT_OID = '1.3.6.1.5.5.7.24.1'


def _sha1(csr, key):
    """The same request re-signed with SHA-1: a valid signature pyca will not vouch for."""
    req = asn1crypto.csr.CertificationRequest.load(csr.public_bytes(serialization.Encoding.DER))
    info = req['certification_request_info']
    return x509.load_der_x509_csr(asn1crypto.csr.CertificationRequest({
        'certification_request_info': info,
        'signature_algorithm': {'algorithm': 'sha1_rsa'},
        'signature': key.sign(info.dump(), padding.PKCS1v15(), hashes.SHA1()),
    }).dump())


def _builder(cn):
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))


def test_the_shared_message_names_the_hash():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _builder('weak.example.com').sign(key, hashes.SHA256())
    assert weak_csr_hash_error(csr) is None
    assert weak_csr_hash_error(_sha1(csr, key)) == SHA1_REASON


# ── ACME ───────────────────────────────────────────────────────

def test_acme_finalize_names_the_sha1_hash_and_keeps_bad_csr(app, client, rsa_account,
                                                              signing_ca, rsa_ca):
    signing_ca(rsa_ca)
    domain = 'sha1.weak-hash.example.com'
    order_id = _ready_order(app, rsa_account, domain)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _sha1(_builder(domain).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False).sign(key, hashes.SHA256()), key)
    r = _jws(client, f'/acme/order/{order_id}/finalize',
             {'csr': _b64u(csr.public_bytes(serialization.Encoding.DER))},
             rsa_account['key'], kid=rsa_account['kid'])
    body = r.get_json()
    assert r.status_code == 400, body
    assert body['type'] == 'urn:ietf:params:acme:error:badCSR', body
    assert SHA1_REASON in body['detail'], body


def test_sign_csr_names_the_sha1_hash():
    from datetime import datetime, timedelta, timezone
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Weak hash CA')])
    ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
               .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _sha1(_builder('weak.example.com').sign(key, hashes.SHA256()), key)
    with pytest.raises(RequestRejected, match=r'unsupported hash algorithm \(sha1\)'):
        TrustStoreService.sign_csr(csr_pem=csr.public_bytes(serialization.Encoding.PEM),
                                   ca_cert=ca_cert, ca_private_key=ca_key, validity_days=30)


# ── SCEP ───────────────────────────────────────────────────────

def _sha1_csr_pkcs_req(ca_cert, identity):
    cert, key = identity
    csr = _sha1(x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
                .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
                .sign(key, hashes.SHA256()), key)
    payload = _envelope(csr.public_bytes(serialization.Encoding.DER), [(ca_cert, 'oaep-sha256')], 'aes128')
    return create_signed_pkcs7(payload, key, cert, signed_attributes=_attrs('fips-sha1-csr'))


def _failure(response, status):
    attrs = _response_attributes(response)
    assert status == 200 and attrs[PKI_STATUS_OID] == '2', attrs
    return attrs[FAIL_INFO_OID], attrs.get(FAIL_INFO_TEXT_OID)


@pytest.mark.parametrize('mode', ['fips_off', 'fips_on'])
def test_scep_sha1_csr_gets_bad_alg_and_the_reason(mode, request, app, scep_ca):
    request.getfixturevalue(mode)
    response, status, _ = _process(app, scep_ca, _sha1_csr_pkcs_req)
    assert _failure(response, status) == ('0', SHA1_REASON)  # badAlg


def test_scep_sha1_cms_signature_in_fips_mode_says_so(fips_on, app, scep_ca):
    response, status, _ = _process(
        app, scep_ca, lambda c, i: _resign(_pkcs_req(c, i), i[1], 'sha1', 'sha1_rsa'))
    assert _failure(response, status) == ('0', 'SHA-1 CMS signatures not available in FIPS mode')


# ── CSR upload, import, smart import, Microsoft CA ─────────────

def _sha1_pem(cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _sha1(_builder(cn).sign(key, hashes.SHA256()), key)
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def _rows(app):
    from models import Certificate
    with app.app_context():
        return Certificate.query.count()


def test_csr_upload_names_the_sha1_hash(app, auth_client):
    before = _rows(app)
    r = auth_client.post('/api/v2/csrs/upload', content_type='application/json',
                         data=json.dumps({'pem': _sha1_pem('upload.weak-hash.example.com'), 'name': 'w'}))
    assert r.status_code == 400, r.get_json()
    assert SHA1_REASON in r.get_json()['detail'], r.get_json()
    assert _rows(app) == before


def test_csr_import_names_the_sha1_hash(app, auth_client):
    before = _rows(app)
    r = auth_client.post('/api/v2/csrs/import',
                         data={'pem_content': _sha1_pem('import.weak-hash.example.com'), 'name': 'w'})
    assert r.status_code == 400, r.get_json()
    assert SHA1_REASON in r.get_json()['detail'], r.get_json()
    assert _rows(app) == before


def test_smart_import_names_the_sha1_hash(app, auth_client):
    r = auth_client.post('/api/v2/import/analyze', content_type='application/json',
                         data=json.dumps({'content': _sha1_pem('smart.weak-hash.example.com')}))
    assert r.status_code == 200, r.get_json()
    errors = r.get_json()['data']['validation']['errors']
    assert any(SHA1_REASON in e for e in errors), errors


def test_msca_sign_names_the_sha1_hash(app, auth_client):
    from models import Certificate, MicrosoftCA, db
    from tests.deploy_leftovers import delete_leftovers
    cleanup = delete_leftovers(app)
    next(cleanup)
    try:
        with app.app_context():
            msca = MicrosoftCA(name='weak-hash msca', server='adcs.test.local',
                               auth_method='basic', enabled=True)
            row = Certificate(refid='weak-hash-msca-csr', descr='weak hash',
                              csr=base64.b64encode(_sha1_pem('msca.weak-hash.example.com').encode()).decode())
            db.session.add_all([msca, row])
            db.session.commit()
            msca_id, csr_id = msca.id, row.id
        r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}',
                             content_type='application/json', data=json.dumps({'template': 'WebServer'}))
        assert r.status_code == 400, r.get_json()
        assert SHA1_REASON in r.get_json()['detail'], r.get_json()
    finally:
        next(cleanup, None)
