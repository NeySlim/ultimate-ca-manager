"""A Windows-shaped request (CA:FALSE with a path length) goes through the CSR routes.

The raw cryptography accessor refuses that BasicConstraints: the upload answered
500 and signing called the request invalid.
"""
import base64

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from models import Certificate, db
from tests.test_csr_sign_extra_names import _upload
from tests.test_csr_windows_basic_constraints import _windows_shaped_csr


def _csr(cn):
    return _windows_shaped_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048), cn)


def test_upload_detail_and_sign(app, auth_client, create_ca):
    ca = create_ca(cn='Windows CSR routes CA')
    csr_id = _upload(auth_client, _csr('win-route.example.test'))
    r = auth_client.get(f'/api/v2/csrs/{csr_id}')
    assert r.status_code == 200, r.get_json()
    assert 'win-route.example.test' in str(r.get_json()['data'])
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca['id'], 'validity_days': 30})
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        cert = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(Certificate, csr_id).crt))
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert names.get_values_for_type(x509.DNSName) == ['win-route.example.test']


def test_signing_through_an_approval(app, auth_client, create_ca, create_user):
    from tests.test_approval_on_sign_and_renew import _drop_policy, _operator, _policy
    ca = create_ca(cn='Windows CSR approval CA')
    pid = _policy(app, ca['id'], 'windows-csr-approval')
    operator = _operator(app, create_user)
    try:
        csr_id = _upload(operator, _csr('win-approval.example.test'))
        r = operator.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
        # Another file's policy may outrank this one: the response names the request
        approval_id = r.get_json()['data']['approval_id']
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200 and r.get_json()['data'].get('certificate_issued'), r.get_json()
        with app.app_context():
            assert db.session.get(Certificate, csr_id).crt
    finally:
        _drop_policy(app, pid)
