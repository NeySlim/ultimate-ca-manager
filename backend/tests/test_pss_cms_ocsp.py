"""OCSP responses, timestamps and SCEP replies of a PSS CA are signed RSA-PSS.

These structures are assembled by hand (pyca's OCSP builder cannot sign PSS),
so each one is checked by OpenSSL, with the PSS AlgorithmIdentifier pyca
writes in certificates.
"""
import base64
import hashlib
import json
import shutil
import subprocess

import asn1crypto.cms
import pytest
from asn1crypto import ocsp as asn1_ocsp, tsp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import ocsp

from models import CA, Certificate, SystemConfig, db
from utils.signing_hash import pss_algorithm_identifier

OPENSSL = shutil.which('openssl')
PSS_SHA256 = pss_algorithm_identifier(hashes.SHA256()).dump()


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM)


def _openssl(tmp_path, *args, **files):
    if not OPENSSL:
        return ''
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    out = subprocess.run(['openssl', *args], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout + out.stderr


@pytest.fixture(scope='module')
def pss_ca(create_ca):
    return create_ca(cn='PSS CMS root', signatureScheme='pss')


@pytest.fixture
def ca_row(app, pss_ca):
    with app.app_context():
        yield db.session.get(CA, pss_ca['id'])


def _cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _ocsp_request(leaf, ca_cert):
    return ocsp.OCSPRequestBuilder().add_certificate(leaf, ca_cert, hashes.SHA1()).build() \
        .public_bytes(serialization.Encoding.DER)


def _assert_pss_ocsp(der, signer_cert):
    response = asn1_ocsp.OCSPResponse.load(der)
    basic = response['response_bytes']['response'].parsed
    assert basic['signature_algorithm'].dump() == PSS_SHA256
    signer_cert.public_key().verify(
        basic['signature'].native, basic['tbs_response_data'].dump(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())


def _ocsp_verify(tmp_path, der, request, ca_cert, leaf):
    out = _openssl(tmp_path, 'ocsp', '-respin', 'r.der', '-reqin', 'q.der', '-issuer', 'ca.pem',
                   '-CAfile', 'ca.pem', '-cert', 'leaf.pem', '-no_nonce',
                   **{'r.der': der, 'q.der': request, 'ca.pem': _pem(ca_cert), 'leaf.pem': _pem(leaf)})
    if OPENSSL:
        assert 'Response verify OK' in out and ': good' in out, out


def _leaf(create_cert, pss_ca, cn):
    leaf = create_cert(cn=cn, ca_id=pss_ca['id'])
    return _cert(db.session.get(Certificate, leaf['id']))


def test_single_ocsp_response(app, create_cert, pss_ca, ca_row, tmp_path):
    from services.ocsp_service import OCSPService
    leaf = _leaf(create_cert, pss_ca, 'pss-ocsp.example.test')
    ca_cert = _cert(ca_row)
    der, status = OCSPService().generate_response(ca_row, leaf.serial_number, hash_algorithm=hashes.SHA1())
    assert status == 'good'
    _assert_pss_ocsp(der, ca_cert)
    _ocsp_verify(tmp_path, der, _ocsp_request(leaf, ca_cert), ca_cert, leaf)


def test_multi_certid_ocsp_response(app, create_cert, pss_ca, ca_row, tmp_path):
    from services.ocsp_service import OCSPService
    leaf = _leaf(create_cert, pss_ca, 'pss-ocsp-multi.example.test')
    ca_cert = _cert(ca_row)
    request = _ocsp_request(leaf, ca_cert)
    parsed = OCSPService().parse_request_details(request)
    der, statuses = OCSPService().generate_multi_response(ca=ca_row, request_items=parsed.requests)
    assert statuses == ('good',)
    _assert_pss_ocsp(der, ca_cert)
    _ocsp_verify(tmp_path, der, request, ca_cert, leaf)


def test_delegated_responder_follows_the_ca(app, auth_client, create_cert, pss_ca, ca_row, tmp_path):
    from services.ocsp_service import OCSPService
    r = auth_client.post('/api/v2/certificates', content_type='application/json', data=json.dumps({
        'cn': 'pss-responder.example.test', 'ca_id': pss_ca['id'], 'validity_days': 60,
        'key_type': 'RSA 2048', 'cert_type': 'server', 'extra_ekus': ['1.3.6.1.5.5.7.3.9']}))
    assert r.status_code == 201, r.get_json()
    responder_id = r.get_json()['data']['id']
    r = auth_client.post(f"/api/v2/cas/{pss_ca['id']}/ocsp-responder", content_type='application/json',
                         data=json.dumps({'certificate_id': responder_id}))
    assert r.status_code == 200, r.get_json()
    try:
        leaf = _leaf(create_cert, pss_ca, 'pss-ocsp-delegated.example.test')
        ca_cert = _cert(ca_row)
        responder = _cert(db.session.get(Certificate, responder_id))
        der, status = OCSPService().generate_response(ca_row, leaf.serial_number, hash_algorithm=hashes.SHA1())
        assert status == 'good'
        _assert_pss_ocsp(der, responder)
        # The responder certificate travels in the response
        basic = asn1_ocsp.OCSPResponse.load(der)['response_bytes']['response'].parsed
        assert len(basic['certs']) == 1
        _ocsp_verify(tmp_path, der, _ocsp_request(leaf, ca_cert), ca_cert, leaf)
    finally:
        SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{pss_ca['id']}").delete()
        db.session.commit()


def test_timestamp_from_a_dedicated_signer(app, pss_ca, ca_row, tmp_path):
    from services import tsa_signer_cert
    from services.tsa_service import TSAService, _load_signer_certificate
    issued = tsa_signer_cert.issue_tsa_signer_certificate(ca=ca_row, cn='pss-tsa-signer.example.test')
    _, cert, key, chain = _load_signer_certificate(issued.refid)
    data = b'timestamp me'
    request = tsp.TimeStampReq({
        'version': 1, 'cert_req': True,
        'message_imprint': {'hash_algorithm': {'algorithm': 'sha256'},
                            'hashed_message': hashlib.sha256(data).digest()},
    }).dump()
    der, http = TSAService(cert, key, chain_certs=chain).process_request(request)
    signed = tsp.TimeStampResp.load(der)['time_stamp_token']['content']
    assert signed['signer_infos'][0]['signature_algorithm'].dump() == PSS_SHA256
    # The token is checked as CMS: `openssl ts -verify` goes through OpenSSL's
    # PKCS7 code, which verifies every RSA SignerInfo as PKCS#1 v1.5
    token = tsp.TimeStampResp.load(der)['time_stamp_token'].dump()
    _openssl(tmp_path, 'cms', '-verify', '-inform', 'DER', '-in', 'token.der', '-CAfile', 'ca.pem',
             '-certfile', 'signer.pem', '-purpose', 'any', '-out', '/dev/null',
             **{'token.der': token, 'ca.pem': _pem(_cert(ca_row)), 'signer.pem': _pem(cert)})


def test_scep_reply(app, pss_ca, ca_row, tmp_path):
    from services.scep.scep_service import SCEPService
    from tests.test_scep_rfc8894_operations import (
        _build_request, _client_identity, _decrypt_response, _response_attributes)
    from tests.test_csr_windows_basic_constraints import PKI_STATUS_OID, _windows_shaped_csr
    challenge = 'pss-scep-challenge'
    db.session.add(SystemConfig(key=f"scep_challenge_{pss_ca['id']}", value=challenge))
    db.session.commit()
    try:
        ca_cert = _cert(ca_row)
        signer_cert, key = _client_identity('pss scep device')
        csr = _windows_shaped_csr(key, 'pss-scep.example.test', challenge)
        request = _build_request(ca_cert, signer_cert, key, 19,
                                 csr.public_bytes(serialization.Encoding.DER), b'pss-nonce-16byte')
        response, status = SCEPService(ca_row.refid, challenge_password=challenge,
                                       auto_approve=True).process_pkcs_req(request, '127.0.0.1')
        assert status == 200 and _response_attributes(response)[PKI_STATUS_OID] == '0'
        signer_info = asn1crypto.cms.ContentInfo.load(response)['content']['signer_infos'][0]
        assert signer_info['signature_algorithm'].dump() == PSS_SHA256
        degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response, key, signer_cert))
        issued = x509.load_der_x509_certificate(degenerate['content']['certificates'][0].chosen.dump())
        assert issued.signature_algorithm_oid == x509.oid.SignatureAlgorithmOID.RSASSA_PSS
        _openssl(tmp_path, 'cms', '-verify', '-inform', 'DER', '-in', 'r.der', '-CAfile', 'ca.pem',
                 '-purpose', 'any', '-out', '/dev/null',
                 **{'r.der': response, 'ca.pem': _pem(ca_cert)})
    finally:
        SystemConfig.query.filter_by(key=f"scep_challenge_{pss_ca['id']}").delete()
        db.session.commit()
