"""Only RSA and EC take a default key size, on the routes that fill one in."""
import base64

import pytest
from cryptography import x509

from models import ApprovalRequest, Certificate, db
from services import tsa_signer_cert
from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
from utils import key_algorithms
from utils.key_type import issue_key_size

needs_mldsa = pytest.mark.skipif(not key_algorithms.mldsa_supported(), reason='this build has no ML-DSA')


@pytest.mark.parametrize('key_type,key_size,default,expected', [
    ('RSA', None, '2048', '2048'),
    ('RSA', '', '2048', '2048'),
    ('RSA', '4096', '2048', '4096'),
    ('EC', None, '2048', '2048'),
    ('RSA-3072', None, '2048', '2048'),
    ('Ed25519', None, '2048', None),
    ('ML-DSA-65', None, '2048', None),
])
def test_issue_key_size(key_type, key_size, default, expected):
    assert issue_key_size(key_type, key_size, default) == expected


@needs_mldsa
def test_an_approved_ml_dsa_request_issues_without_a_size(app, create_ca):
    from api.v2.policies import _issue_approved_certificate
    ca = create_ca(cn='Issue key size approval CA')
    approval_id = _mk_approval_id(app, _requester_id(app), {
        'cn': 'approved.mldsa.test', 'ca_id': ca['id'], 'key_type': 'ML-DSA-65', 'validity_days': 30})
    with app.app_context():
        issued = _issue_approved_certificate(db.session.get(ApprovalRequest, approval_id))
        row = db.session.get(Certificate, issued['id'])
        key = x509.load_pem_x509_certificate(base64.b64decode(row.crt)).public_key()
        assert 'MLDSA65' in type(key).__name__


@needs_mldsa
def test_the_tsa_signer_generates_ml_dsa_without_a_size(app):
    with app.app_context():
        key = tsa_signer_cert._generate_key('ML-DSA-65', None, None)
    key = key[0] if isinstance(key, tuple) else key
    assert 'MLDSA65' in type(key).__name__
