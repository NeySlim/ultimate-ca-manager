"""Every X.509 issuance path signs RSA-PSS for a CA set to PSS.

Each artefact carries the PSS AlgorithmIdentifier (salt = digest length) and
is checked by OpenSSL, not only by pyca. A path that forgot the scheme fails
loudly: the CA key refuses a PKCS#1 v1.5 signature.
"""
import base64
import json
import shutil
import subprocess
from unittest.mock import patch

import asn1crypto.crl
import asn1crypto.csr
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, SignatureAlgorithmOID

from models import CA, Certificate, db

OPENSSL = shutil.which('openssl')


def _salt(obj):
    der = obj.public_bytes(serialization.Encoding.DER)
    kind = {x509.Certificate: asn1crypto.x509.Certificate,
            x509.CertificateSigningRequest: asn1crypto.csr.CertificationRequest,
            x509.CertificateRevocationList: asn1crypto.crl.CertificateList}
    parsed = next(v for k, v in kind.items() if isinstance(obj, k)).load(der)
    return parsed['signature_algorithm']['parameters']['salt_length'].native


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM)


def _openssl(tmp_path, *args, **files):
    if not OPENSSL:
        return
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    out = subprocess.run(['openssl', *args], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr


def _assert_pss(obj):
    assert obj.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    assert _salt(obj) == obj.signature_hash_algorithm.digest_size


def _check_cert(cert, issuer, tmp_path, root=None):
    _assert_pss(cert)
    cert.verify_directly_issued_by(issuer)
    chain = {'leaf.pem': _pem(cert), 'ca.pem': _pem(root or issuer)}
    args = ['verify', '-CAfile', 'ca.pem']
    if root is not None:
        chain['inter.pem'] = _pem(issuer)
        args += ['-untrusted', 'inter.pem']
    _openssl(tmp_path, *args, 'leaf.pem', **chain)


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _csr(cn):
    key = rsa.generate_private_key(65537, 2048)
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])).sign(key, hashes.SHA256())


@pytest.fixture(scope='module')
def pss_ca(create_ca):
    return create_ca(cn='PSS paths root', signatureScheme='pss')


@pytest.fixture
def ca_cert(app, pss_ca):
    with app.app_context():
        return _row_cert(db.session.get(CA, pss_ca['id']))


def _leaf(app, pss_ca, cn):
    from services.cert_service import CertificateService
    with app.app_context():
        row = CertificateService.create_certificate(
            descr=cn, caref=pss_ca['refid'], dn={'CN': cn}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin')
        db.session.commit()
        return row.id, _row_cert(row)


def test_lifecycle_service(app, pss_ca, ca_cert, tmp_path):
    _, cert = _leaf(app, pss_ca, 'pss-lifecycle.example.test')
    _check_cert(cert, ca_cert, tmp_path)


def test_sub_ca_and_its_own_default(app, auth_client, pss_ca, ca_cert, tmp_path):
    r = auth_client.post('/api/v2/cas', content_type='application/json', data=json.dumps({
        'type': 'intermediate', 'parentCAId': pss_ca['id'], 'commonName': 'PSS paths child',
        'keyAlgo': 'RSA', 'keySize': 2048, 'validityYears': 1, 'hashAlgorithm': 'sha384'}))
    assert r.status_code == 201, r.get_json()
    child = r.get_json()['data']
    with app.app_context():
        child_cert = _row_cert(db.session.get(CA, child['id']))
    _check_cert(child_cert, ca_cert, tmp_path)
    assert _salt(child_cert) == 48
    # The child keeps its own scheme: v1.5 unless asked
    assert child['signature_scheme'] == 'pkcs1v15'
    r = auth_client.post('/api/v2/certificates', content_type='application/json', data=json.dumps(
        {'cn': 'child-leaf.example.test', 'ca_id': child['id'], 'validity_days': 30}))
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        leaf = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
    assert leaf.signature_algorithm_oid == SignatureAlgorithmOID.RSA_WITH_SHA256
    _openssl(tmp_path, 'verify', '-CAfile', 'root.pem', '-untrusted', 'child.pem', 'leaf.pem',
             **{'root.pem': _pem(ca_cert), 'child.pem': _pem(child_cert), 'leaf.pem': _pem(leaf)})


def test_shared_csr_trunk(app, pss_ca, ca_cert, tmp_path):
    from services.ca_service import CAService
    with app.app_context():
        ca = db.session.get(CA, pss_ca['id'])
        cert_pem, _ = CAService.sign_csr_from_crypto(ca=ca, csr=_csr('pss-trunk.example.test'),
                                                       validity_days=30, source='est')
    _check_cert(x509.load_pem_x509_certificate(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem),
                ca_cert, tmp_path)


def test_approval_workflow(app, pss_ca, ca_cert, tmp_path):
    from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
    from models.policy import ApprovalRequest
    from api.v2.policies import _issue_approved_certificate
    with app.app_context():
        approval = db.session.get(ApprovalRequest, _mk_approval_id(
            app, _requester_id(app), {'cn': 'pss-approval.example.test', 'ca_id': pss_ca['id'],
                                      'cert_type': 'server', 'validity_days': 30}))
        result = _issue_approved_certificate(approval)
        cert = _row_cert(db.session.get(Certificate, result['id']))
    _check_cert(cert, ca_cert, tmp_path)


def test_in_place_renewal(app, pss_ca, ca_cert, tmp_path):
    from services.cert.renewal import renew_certificate_in_place
    row_id, _ = _leaf(app, pss_ca, 'pss-renew.example.test')
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        renew_certificate_in_place(row, username='admin')
        db.session.commit()
        cert = _row_cert(db.session.get(Certificate, row_id))
    _check_cert(cert, ca_cert, tmp_path)


def test_tsa_signer_certificate(app, pss_ca, ca_cert, tmp_path):
    from services import tsa_signer_cert
    with app.app_context():
        issued = tsa_signer_cert.issue_tsa_signer_certificate(
            ca=db.session.get(CA, pss_ca['id']), cn='pss-tsa.example.test')
        cert = _row_cert(issued)
    _check_cert(cert, ca_cert, tmp_path)


def test_ocsp_responder_renewal(app, pss_ca, ca_cert, tmp_path):
    from services import ocsp_responder_renewal
    row_id, _ = _leaf(app, pss_ca, 'pss-responder.example.test')
    with app.app_context():
        ocsp_responder_renewal._renew_responder_cert(db.session.get(CA, pss_ca['id']),
                                                     db.session.get(Certificate, row_id))
        db.session.commit()
        cert = _row_cert(db.session.get(Certificate, row_id))
    _check_cert(cert, ca_cert, tmp_path)


def test_full_and_delta_crls(app, pss_ca, ca_cert, tmp_path):
    from services.crl_service import CRLService
    with app.app_context():
        ca = db.session.get(CA, pss_ca['id'])
        ca.delta_crl_enabled = True
        db.session.commit()
        full = CRLService.generate_crl(pss_ca['id'])
        delta = CRLService.generate_delta_crl(pss_ca['id'])
        pems = [m.crl_pem for m in (full, delta)]
    for pem in pems:
        crl = x509.load_pem_x509_crl(pem.encode())
        _assert_pss(crl)
        assert crl.is_signature_valid(ca_cert.public_key())
        _openssl(tmp_path, 'crl', '-in', 'crl.pem', '-CAfile', 'ca.pem', '-noout',
                 **{'crl.pem': pem.encode(), 'ca.pem': _pem(ca_cert)})


def test_external_ca_csr_and_its_regeneration(app, auth_client, tmp_path):
    from services.ca.ca_creation import CACreationMixin
    r = auth_client.post('/api/v2/cas', content_type='application/json', data=json.dumps({
        'type': 'external', 'commonName': 'PSS paths external', 'keyAlgo': 'RSA', 'keySize': 2048,
        'signatureScheme': 'pss'}))
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        ca = db.session.get(CA, r.get_json()['data']['id'])
        first = x509.load_pem_x509_csr(base64.b64decode(ca.csr))
        CACreationMixin.regenerate_ca_csr(ca)
        db.session.commit()
        again = x509.load_pem_x509_csr(base64.b64decode(db.session.get(CA, ca.id).csr))
    for csr in (first, again):
        _assert_pss(csr)
        assert csr.is_signature_valid
        _openssl(tmp_path, 'req', '-in', 'csr.pem', '-verify', '-noout', **{'csr.pem': _pem(csr)})


def test_ct_precertificate_and_final_certificate(app, pss_ca, ca_cert):
    from services.hsm.ca_key_loader import get_ca_signing_key
    from utils import ct_client
    _, leaf = _leaf(app, pss_ca, 'pss-ct.example.test')
    seen = {}

    def _collect(chain, urls):
        seen['precert'] = x509.load_pem_x509_certificate(chain[0].encode())
        return [{}]

    with app.app_context():
        key = get_ca_signing_key(db.session.get(CA, pss_ca['id']))
        with patch.object(ct_client, 'collect_precert_scts', _collect), \
             patch.object(ct_client, '_encode_sct_list', return_value=(b'\x04\x02\x00\x00', [{}])):
            final, _ = ct_client.embed_scts_in_certificate(leaf, ca_cert, key)
    for cert in (seen['precert'], final):
        _assert_pss(cert)
        cert.verify_directly_issued_by(ca_cert)


def test_a_v15_ca_is_unchanged(app, create_ca):
    ca = create_ca(cn='PSS paths v1.5 control')
    _, cert = _leaf(app, ca, 'v15-control.example.test')
    assert cert.signature_algorithm_oid == SignatureAlgorithmOID.RSA_WITH_SHA256


def test_trust_store_crl_helper(app, pss_ca, ca_cert):
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.trust_store.trust_store_service import TrustStoreService
    with app.app_context():
        key = get_ca_signing_key(db.session.get(CA, pss_ca['id']))
        crl = x509.load_pem_x509_crl(TrustStoreService.generate_crl(ca_cert, key, []))
    _assert_pss(crl)
    assert crl.is_signature_valid(ca_cert.public_key())
