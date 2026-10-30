"""KeyUsage of ML-DSA certificates (RFC 9881): signature bits only, a CA keeps
keyCertSign, cRLSign and digitalSignature, and a bit removed from what a
template or CSR asked for is said in a notice."""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import mldsa, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, Certificate, db
from services import cert_linting_service
from services.trust_store import TrustStoreService
from utils import key_algorithms
from utils.leaf_key_usage import key_usage_for_key

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

KU_BITS = ('digital_signature', 'content_commitment', 'key_encipherment', 'data_encipherment',
           'key_agreement', 'key_cert_sign', 'crl_sign')
CA_BITS = {'digital_signature', 'key_cert_sign', 'crl_sign'}
KU_FINDINGS = ('key_usage', '_ku_')


def _bits(usage):
    if isinstance(usage, x509.Certificate):
        usage = usage.extensions.get_extension_for_class(x509.KeyUsage).value
    return {b for b in KU_BITS if getattr(usage, b)}


def _usage(*on):
    flags = dict.fromkeys(KU_BITS, False)
    flags.update(dict.fromkeys(on, True))
    return x509.KeyUsage(**flags, encipher_only=False, decipher_only=False)


def _post(client, url, body):
    return client.post(url, content_type='application/json', data=json.dumps(body))


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _ml_dsa_csr(cn, extensions=()):
    key = mldsa.MLDSA44PrivateKey.generate()
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    for ext in extensions:
        builder = builder.add_extension(ext, critical=True)
    return builder.sign(key, None).public_bytes(serialization.Encoding.PEM)


def _rsa_ca():
    key = rsa.generate_private_key(65537, 2048)
    pem, _ = TrustStoreService.create_ca_certificate(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'KU test root')]), key, validity_days=30)
    return x509.load_pem_x509_certificate(pem), key


# ---- leaves ---------------------------------------------------------------------

@pytest.mark.parametrize('level', [mldsa.MLDSA44PrivateKey, mldsa.MLDSA65PrivateKey, mldsa.MLDSA87PrivateKey])
def test_ml_dsa_leaf_keeps_only_signature_bits(level):
    public = level.generate().public_key()
    asked = _usage('digital_signature', 'content_commitment', 'key_encipherment',
                   'data_encipherment', 'key_agreement')
    got = key_usage_for_key(public, asked, [ExtendedKeyUsageOID.EMAIL_PROTECTION])
    assert _bits(got) == {'digital_signature', 'content_commitment'}


def test_sign_csr_drops_template_key_encipherment_with_a_notice():
    ca_cert, ca_key = _rsa_ca()
    notices = []
    pem = TrustStoreService.sign_csr(
        _ml_dsa_csr('tpl-ku.example.test'), ca_cert, ca_key, validity_days=30,
        template_ext={'key_usage': ['digitalSignature', 'keyEncipherment'],
                      'extended_key_usage': ['serverAuth']},
        notices=notices)
    assert _bits(x509.load_pem_x509_certificate(pem)) == {'digital_signature'}
    assert len(notices) == 1 and 'keyEncipherment' in notices[0] and 'ML-DSA-44' in notices[0], notices


def test_sign_csr_encryption_only_csr_gets_digital_signature():
    ca_cert, ca_key = _rsa_ca()
    notices = []
    pem = TrustStoreService.sign_csr(
        _ml_dsa_csr('enc-only.example.test', [_usage('key_encipherment')]), ca_cert, ca_key,
        validity_days=30, notices=notices)
    ku = x509.load_pem_x509_certificate(pem).extensions.get_extension_for_class(x509.KeyUsage)
    assert _bits(ku.value) == {'digital_signature'} and ku.critical
    assert len(notices) == 1 and 'only sign' in notices[0] and 'digitalSignature' in notices[0], notices


def test_key_usage_notice_wording_follows_the_family():
    from cryptography.hazmat.primitives.asymmetric import ec
    from utils.leaf_key_usage import key_usage_notice
    pub = ec.generate_private_key(ec.SECP256R1()).public_key()
    asked = _usage('digital_signature', 'key_encipherment')
    # S/MIME on EC: the encryption intent survives as keyAgreement, nothing to report
    smime = key_usage_for_key(pub, asked, [ExtendedKeyUsageOID.EMAIL_PROTECTION])
    assert smime.key_agreement and key_usage_notice(pub, asked, smime) is None
    tls = key_usage_notice(pub, asked, key_usage_for_key(pub, asked, [ExtendedKeyUsageOID.SERVER_AUTH]))
    assert tls == 'keyEncipherment removed from the key usage: EC-P256 keys encrypt only through keyAgreement.'
    pq = mldsa.MLDSA65PrivateKey.generate().public_key()
    assert 'ML-DSA-65 keys only sign' in key_usage_notice(pq, asked, key_usage_for_key(pq, asked))


def test_sign_csr_says_nothing_about_its_own_default():
    ca_cert, ca_key = _rsa_ca()
    notices = []
    pem = TrustStoreService.sign_csr(_ml_dsa_csr('default-ku.example.test'), ca_cert, ca_key,
                                     validity_days=30, notices=notices)
    assert _bits(x509.load_pem_x509_certificate(pem)) == {'digital_signature'}
    assert notices == []


def test_sign_csr_route_reports_a_dropped_csr_bit(app, auth_client, create_ca):
    ca = create_ca(cn='KU sign route CA')
    csr_pem = _ml_dsa_csr('csr-ku.example.test', [_usage('digital_signature', 'key_encipherment')])
    r = _post(auth_client, '/api/v2/csrs/upload', {'pem': csr_pem.decode(), 'name': 'csr-ku'})
    assert r.status_code in (200, 201), r.get_json()
    csr_id = r.get_json()['data']['id']
    r = _post(auth_client, f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
    assert r.status_code == 200, r.get_json()
    notices = (r.get_json().get('meta') or {}).get('notices') or []
    assert any('keyEncipherment' in n for n in notices), notices
    with app.app_context():
        assert _bits(_row_cert(db.session.get(Certificate, csr_id))) == {'digital_signature'}


def test_issue_form_reports_a_dropped_template_bit(app, auth_client, create_ca):
    ca = create_ca(cn='KU template CA')
    r = _post(auth_client, '/api/v2/templates', {
        'name': 'pq-ku-template', 'template_type': 'custom', 'key_type': 'ML-DSA-65',
        'validity_days': 90, 'extensions_template': {
            'key_usage': ['digitalSignature', 'keyEncipherment'], 'extended_key_usage': ['serverAuth']}})
    assert r.status_code in (200, 201), r.get_json()
    tpl = r.get_json()['data']
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'tpl-mldsa.example.test', 'ca_id': ca['id'], 'template_id': tpl['id'], 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    notices = (r.get_json().get('meta') or {}).get('notices') or []
    assert any('keyEncipherment' in n and 'ML-DSA-65' in n for n in notices), notices
    with app.app_context():
        cert = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
    assert isinstance(cert.public_key(), mldsa.MLDSA65PublicKey)
    assert _bits(cert) == {'digital_signature'}


def _ku_template(auth_client, name):
    r = _post(auth_client, '/api/v2/templates', {
        'name': name, 'template_type': 'custom', 'key_type': 'ML-DSA-65', 'validity_days': 90,
        'extensions_template': {'key_usage': ['digitalSignature', 'keyEncipherment'],
                                'extended_key_usage': ['serverAuth']}})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['data']['id']


def test_approval_reports_a_dropped_template_bit(app, auth_client, create_ca):
    from api.v2.policies import _issue_approved_certificate
    from models import User
    from models.policy import ApprovalRequest, CertificatePolicy
    from services.policy_service import PolicyEvaluationService
    ca = create_ca(cn='KU approval CA')
    tpl_id = _ku_template(auth_client, 'pq-ku-approval-template')
    with app.app_context():
        # Inactive: an active policy would hold every later issuance of the session
        pol = CertificatePolicy(name='pq-ku-approval-policy', policy_type='issuance',
                                requires_approval=True, min_approvers=1, is_active=False)
        db.session.add(pol)
        db.session.commit()
        requester = User.query.filter_by(role='admin').first() or User.query.first()
        approval = PolicyEvaluationService.create_approval_request(
            policy=pol, requester_id=requester.id, request_data={
                'cn': 'approval-mldsa.example.test', 'ca_id': ca['id'], 'cert_type': 'server',
                'template_id': tpl_id})
        result = _issue_approved_certificate(db.session.get(ApprovalRequest, approval.id))
        cert = _row_cert(db.session.get(Certificate, result['id']))
    assert isinstance(cert.public_key(), mldsa.MLDSA65PublicKey)
    assert _bits(cert) == {'digital_signature'}
    assert any('keyEncipherment' in n and 'ML-DSA-65' in n for n in result['notices']), result['notices']


def test_approved_csr_reports_a_dropped_csr_bit(app, auth_client, create_ca):
    from api.v2.policies import _issue_approved_certificate
    from models import User
    from models.policy import ApprovalRequest, CertificatePolicy
    from services.policy_service import PolicyEvaluationService
    ca = create_ca(cn='KU approved CSR CA')
    csr_pem = _ml_dsa_csr('approved-csr-ku.example.test', [_usage('digital_signature', 'key_encipherment')])
    r = _post(auth_client, '/api/v2/csrs/upload', {'pem': csr_pem.decode(), 'name': 'approved-csr-ku'})
    assert r.status_code in (200, 201), r.get_json()
    csr_id = r.get_json()['data']['id']
    with app.app_context():
        pol = CertificatePolicy(name='pq-ku-approved-csr-policy', policy_type='issuance',
                                requires_approval=True, min_approvers=1, is_active=False)
        db.session.add(pol)
        db.session.commit()
        requester = User.query.filter_by(role='admin').first() or User.query.first()
        approval = PolicyEvaluationService.create_approval_request(
            policy=pol, requester_id=requester.id, request_type='csr', request_data={
                'cn': 'approved-csr-ku.example.test', 'csr_id': csr_id, 'ca_id': ca['id'],
                'validity_days': 30})
        # Approved first, as the approve route does: signing closes the still-pending ones
        approval = db.session.get(ApprovalRequest, approval.id)
        approval.status = 'approved'
        db.session.commit()
        result = _issue_approved_certificate(approval)
        assert _bits(_row_cert(db.session.get(Certificate, csr_id))) == {'digital_signature'}
    assert result['id'] == csr_id
    assert any('keyEncipherment' in n and 'ML-DSA-44' in n for n in result['notices']), result['notices']


def test_bulk_sign_reports_a_dropped_csr_bit(app, auth_client, create_ca):
    ca = create_ca(cn='KU bulk sign CA')
    csr_pem = _ml_dsa_csr('bulk-ku.example.test', [_usage('digital_signature', 'key_encipherment')])
    r = _post(auth_client, '/api/v2/csrs/upload', {'pem': csr_pem.decode(), 'name': 'bulk-ku'})
    assert r.status_code in (200, 201), r.get_json()
    csr_id = r.get_json()['data']['id']
    r = _post(auth_client, '/api/v2/csrs/bulk/sign', {'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['success'] == [csr_id], r.get_json()
    notices = (r.get_json().get('meta') or {}).get('notices') or []
    assert any(n.startswith(f'CSR {csr_id}:') and 'keyEncipherment' in n for n in notices), notices
    with app.app_context():
        assert _bits(_row_cert(db.session.get(Certificate, csr_id))) == {'digital_signature'}


# ---- CAs ------------------------------------------------------------------------

def test_sign_csr_sub_ca_drops_the_csr_encryption_bits():
    ca_cert, ca_key = _rsa_ca()
    asked = _usage('digital_signature', 'key_encipherment', 'data_encipherment', 'key_agreement',
                   'key_cert_sign', 'crl_sign')
    notices = []
    pem = TrustStoreService.sign_csr(
        _ml_dsa_csr('sub-ca-ku', [asked, x509.BasicConstraints(ca=True, path_length=0)]),
        ca_cert, ca_key, validity_days=30, cert_type='intermediate_ca', notices=notices)
    assert _bits(x509.load_pem_x509_certificate(pem)) == CA_BITS
    assert len(notices) == 1 and 'keyEncipherment' in notices[0], notices


def test_ml_dsa_ca_certificate_default_bits():
    key = mldsa.MLDSA65PrivateKey.generate()
    pem, _ = TrustStoreService.create_ca_certificate(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ML-DSA KU root')]), key, validity_days=30)
    assert _bits(x509.load_pem_x509_certificate(pem)) == CA_BITS


def _ca(auth_client, label, parent=None):
    body = {'type': 'intermediate' if parent else 'root', 'commonName': f'KU {label} {parent or "root"}',
            'organization': 'UCM Test', 'country': 'FR', 'keyAlgo': label, 'validityYears': 2}
    if parent:
        body['parentCAId'] = parent
    r = _post(auth_client, '/api/v2/cas', body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['data']['id']


def test_api_ml_dsa_root_and_intermediate_bits(app, auth_client):
    root = _ca(auth_client, 'ML-DSA-87')
    sub = _ca(auth_client, 'ML-DSA-65', parent=root)
    rsa_root = _ca(auth_client, 'RSA-2048')
    with app.app_context():
        assert _bits(_row_cert(db.session.get(CA, root))) == CA_BITS
        assert _bits(_row_cert(db.session.get(CA, sub))) == CA_BITS
        # Classical roots keep their profile
        assert _bits(_row_cert(db.session.get(CA, rsa_root))) == {'key_cert_sign', 'crl_sign'}


# ---- lint -----------------------------------------------------------------------

@pytest.fixture(scope='module')
def issued_pq_pair(app, auth_client):
    """An ML-DSA root and an ML-DSA leaf it issued with the default server profile."""
    root = _ca(auth_client, 'ML-DSA-65')
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'lint-mldsa.example.test', 'ca_id': root, 'key_type': 'ml-dsa', 'key_size': 44,
        'cert_type': 'server', 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        return {'ca': _row_cert(db.session.get(CA, root)),
                'leaf': _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))}


@pytest.mark.skipif(not cert_linting_service.is_available(), reason='no linter installed')
@pytest.mark.parametrize('kind', ['ca', 'leaf'])
def test_pkilint_finds_no_key_usage_error(issued_pq_pair, kind):
    pem = issued_pq_pair[kind].public_bytes(serialization.Encoding.PEM).decode()
    rfc = cert_linting_service.lint_certificate_pem(pem, 'rfc5280')
    assert rfc['summary']['fatal'] == rfc['summary']['error'] == 0, rfc['findings']
    # CA/B Forum refuses ML-DSA itself; what must not appear is a KeyUsage finding
    cabf = cert_linting_service.lint_certificate_pem(pem, 'cabf')
    ku_errors = [f for f in cabf['findings'] if f['severity'] in ('fatal', 'error')
                 and any(s in (f.get('code') or '') for s in KU_FINDINGS)]
    assert ku_errors == []
