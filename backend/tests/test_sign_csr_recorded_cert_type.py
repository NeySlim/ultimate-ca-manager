"""A certificate signed through CAService.sign_csr_from_crypto (EST, WSTEP) is
recorded under the type it was signed as, not as a server certificate: the
details panel and an approval request show what the certificate is."""

import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, Certificate, db
from tests import test_wstep_renew_tls as renew_tls
from tests.test_approval_on_sign_and_renew import _drop_policy, _policy
from tests.test_est_rfc7030 import _basic_auth, _post_csr, est_config  # noqa: F401
from tests.test_wstep_renew_tls import USER_AND_CODESIGN, _eku_csr, _key, _renew
from services.wstep import wstep_service

templated_ca = renew_tls.templated_ca
MAIL = {'Mail': (['emailProtection'], None)}


def _row(app, cert):
    with app.app_context():
        return Certificate.query.filter_by(serial_number=str(cert.serial_number)).one()


def _wstep(app, ca_id, cn, eku):
    key = _key()
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, ca_id), _eku_csr(cn, key, eku).public_bytes(
            serialization.Encoding.DER), 30)
    assert err is None, err
    return x509.load_pem_x509_certificate(pem.encode()), key


@pytest.mark.parametrize('templates,cn,eku,expected', [
    (MAIL, 'john.doe', ExtendedKeyUsageOID.EMAIL_PROTECTION, 'email_cert'),
    (USER_AND_CODESIGN, 'jdoe', ExtendedKeyUsageOID.CLIENT_AUTH, 'client_cert'),
])
def test_wstep_records_the_template_type(app, templated_ca, templates, cn, eku, expected):
    ca_id = templated_ca(f'Recorded type WSTEP CA {expected}', templates)
    cert, _key_ = _wstep(app, ca_id, cn, eku)
    assert _row(app, cert).cert_type == expected


def test_wstep_renewal_keeps_the_type(app, templated_ca):
    ca_id = templated_ca('Recorded type WSTEP renew CA', USER_AND_CODESIGN)
    old_cert, old_key = _wstep(app, ca_id, 'jdoe-renew', ExtendedKeyUsageOID.CLIENT_AUTH)
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _row(app, cert).cert_type == 'client_cert'


def test_est_records_the_device_type(app, client, est_config):  # noqa: F811
    cn = 'recorded-type-est.example.test'
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))
    r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
    assert r.status_code == 200, r.data
    with app.app_context():
        assert Certificate.query.filter_by(subject_cn=cn, source='est').one().cert_type == 'device_cert'


def test_sign_csr_records_the_explicit_type(app, auth_client, create_ca):
    """Unchanged: the Sign CSR route already records the type it was asked for."""
    from tests.test_cert_profile_names import _cn, _csr, _sign, _upload
    ca = create_ca(cn='Recorded type Sign CSR CA')
    csr_id = _upload(auth_client, _csr(_cn('Jane Roe')))
    r = _sign(auth_client, csr_id, ca['id'], cert_type='client')
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        assert db.session.get(Certificate, csr_id).cert_type == 'client_cert'


def test_a_renewal_approval_names_the_recorded_type(app, templated_ca):
    from models.policy import ApprovalRequest
    from services.approval_gate import queue_renewal
    ca_id = templated_ca('Recorded type approval CA', MAIL)
    cert, _key_ = _wstep(app, ca_id, 'jane.roe', ExtendedKeyUsageOID.EMAIL_PROTECTION)
    pid = _policy(app, ca_id, 'recorded-type-renewal')
    try:
        with app.app_context():
            row = Certificate.query.filter_by(serial_number=str(cert.serial_number)).one()
            _policy_row, approval = queue_renewal(None, row)
            assert approval is not None
            db.session.commit()
            data = json.loads(db.session.get(ApprovalRequest, approval.id).request_data)
        assert data['cert_type'] == 'email_cert'
    finally:
        _drop_policy(app, pid)


SA, CA_, EP, EFS, SC, CS = ('1.3.6.1.5.5.7.3.1', '1.3.6.1.5.5.7.3.2', '1.3.6.1.5.5.7.3.4',
                            '1.3.6.1.4.1.311.10.3.4', '1.3.6.1.4.1.311.20.2.2', '1.3.6.1.5.5.7.3.3')


@pytest.mark.parametrize('ekus,expected', [
    ([], 'server_cert'), ([SA], 'server_cert'), ([SA, CA_], 'server_cert'),
    ([EP, SA], 'server_cert'), ([EP], 'email_cert'), ([EFS], 'email_cert'),
    ([EFS, CA_], 'email_cert'), ([EP, CA_], 'email_cert'), ([CA_], 'client_cert'),
    ([SC], 'client_cert'), ([SC, CA_], 'client_cert'), ([CS], 'code_signing'),
    ([CS, CA_], 'client_cert'),
])
def test_scep_and_wstep_type_an_eku_set_alike(ekus, expected):
    """SCEP types its issued EKUs, WSTEP its template's: one rule for both."""
    from models.certificate_template import CertificateTemplate
    from utils.request_names import cert_type_for_ekus
    template = CertificateTemplate(extensions_template=json.dumps({'extended_key_usage': ekus}))
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'jdoe')]))
           .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))
    assert wstep_service._template_profile(template, csr)[0] == cert_type_for_ekus(ekus) == expected
