"""The CA option enforce_unique_subject refuses a taken subject before anything leaves the
server: no pre-certificate reaches the Certificate Transparency logs (RFC 6962 §3.1), Intune
hears of no success, and of the failure. The check under the CA row lock stays (the race)."""
import base64
import uuid

import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from tests.test_unique_subject import _csr, _data, _issue, _key, _scoped_client, _sign, unique_ca

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture
def ct_logs(monkeypatch):
    """What would have been submitted to the CT logs, once armed."""
    from utils import ct_client
    seen, armed = [], []

    def submit(certificate, issuer, key):
        if armed:
            seen.append(certificate.subject.rfc4514_string())
        return certificate, []
    monkeypatch.setattr(ct_client, 'apply_ct_policy', submit)
    return seen, armed


def _trunk(app, ca, cn):
    from services.ca_service import CAService
    with app.app_context():
        CAService.sign_csr_from_crypto(db.session.get(CA, ca['id']), _csr(cn, _key()),
                                       validity_days=30, source='test')


def _mtls(app, ca, cn, holder):
    from services.cert_service import CertificateService
    with app.app_context():
        CertificateService.create_certificate(descr='mtls', caref=ca['refid'], dn={'CN': cn},
                                              validity_days=30, subject_holder=holder)


def _approved_manual(app, auth_client, ca, cn):
    from models.policy import ApprovalRequest
    from tests.protocol_approval_support import approval_policy
    operator = _scoped_client(app, ['read:certificates', 'write:certificates'])
    with approval_policy(app, ca['id'], f'unique-ct-{uuid.uuid4().hex[:6]}') as pid:
        r = app.test_client().post('/api/v2/certificates', headers=operator, json={
            'cn': cn, 'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200 and r.get_json()['data']['approval_required'], r.get_json()
        with app.app_context():
            approval_id = ApprovalRequest.query.filter_by(policy_id=pid).one().id
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        return r.get_json()['data'].get('certificate_issued') is True


@pytest.mark.parametrize('path', ['manual', 'csr', 'trunk', 'mtls', 'approval'])
def test_a_taken_subject_never_reaches_the_ct_logs(app, auth_client, create_ca, ct_logs, path):
    from services.cert.unique_subject import SubjectTaken
    seen, armed = ct_logs
    ca = unique_ca(app, create_ca, f'Unique CT {path} CA')
    cn = f'ct-{path}.unique.test'
    if path == 'mtls':
        _mtls(app, ca, cn, 'user:1')
    else:
        _data(_issue(auth_client, ca, cn), 201)
    armed.append(True)
    if path == 'manual':
        assert _issue(auth_client, ca, cn).status_code == 409
    elif path == 'csr':
        assert _sign(auth_client, app, ca, _csr(cn, _key())).status_code == 409
    elif path == 'trunk':
        with pytest.raises(SubjectTaken):
            _trunk(app, ca, cn)
    elif path == 'mtls':
        with pytest.raises(SubjectTaken):
            _mtls(app, ca, cn, 'user:2')
    else:
        assert _approved_manual(app, auth_client, ca, cn) is False
    assert seen == []
    # The same entity still reaches them
    if path == 'manual':
        _data(_issue(auth_client, ca, cn, override_unique_subject=True), 201)
        assert seen == [f'CN={cn}']


def test_a_refused_renewal_never_reaches_the_ct_logs(app, auth_client, create_ca, ct_logs):
    seen, armed = ct_logs
    ca = unique_ca(app, create_ca, 'Unique CT renewal CA', on=False)
    held = _data(_issue(auth_client, ca, 'ct-renew.unique.test'), 201)
    _data(_issue(auth_client, ca, 'ct-renew.unique.test'), 201)
    with app.app_context():
        db.session.get(CA, ca['id']).enforce_unique_subject = True
        db.session.commit()
    armed.append(True)
    assert auth_client.post(f"/api/v2/certificates/{held['id']}/renew", json={}).status_code == 409
    assert seen == []


# --- SCEP: the CT logs and Intune ----------------------------------------------------------------

class _Intune:
    def __init__(self):
        self.success, self.failure = [], []

    def validate_request(self, transaction_id, der_csr):
        pass

    def send_success_notification(self, transaction_id, der_csr, cert):
        self.success.append(transaction_id)

    def send_failure_notification(self, transaction_id, der_csr, hresult, description):
        self.failure.append((transaction_id, description))


def _rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pkcs_req(app, ca_id, cn, transaction_id):
    from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
    from tests.test_scep_rfc8894_operations import (
        MESSAGE_TYPE_OID, SENDER_NONCE_OID, TRANSACTION_ID_OID, _client_identity, _load_ca_material)
    key = _rsa()
    signer, _ = _client_identity(cn, key=key)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])).sign(key, hashes.SHA256())
    with app.app_context():
        _ca, ca_cert, _ = _load_ca_material(ca_id)
    attrs = [{'type': TRANSACTION_ID_OID, 'values': [asn1crypto.core.PrintableString(transaction_id)]},
             {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.PrintableString('19')]},
             {'type': SENDER_NONCE_OID, 'values': [asn1crypto.core.OctetString(uuid.uuid4().bytes)]}]
    return create_signed_pkcs7(encrypt_for_client(csr.public_bytes(serialization.Encoding.DER), ca_cert),
                               key, signer, signed_attributes=attrs)


def _scep_taken(app, auth_client, create_ca, name):
    ca = unique_ca(app, create_ca, name)
    first = _data(_issue(auth_client, ca, 'scep-ct.unique.test'), 201)
    return ca, first


def test_scep_refuses_before_ct_and_intune_hears_of_the_failure_only(
        app, auth_client, create_ca, ct_logs, monkeypatch):
    from services.scep.scep_service import SCEPService
    from tests.test_scep_rfc8894_operations import FAIL_INFO_OID, PKI_STATUS_OID, _response_attributes
    monkeypatch.setenv('UCM_SCEP_ALLOW_NO_CHALLENGE', '1')
    seen, armed = ct_logs
    ca, _first = _scep_taken(app, auth_client, create_ca, 'Unique SCEP CT CA')
    armed.append(True)
    intune, txn = _Intune(), uuid.uuid4().hex
    request = _pkcs_req(app, ca['id'], 'scep-ct.unique.test', txn)
    with app.app_context():
        response, status = SCEPService(ca['refid'], auto_approve=True,
                                       intune_client=intune).process_pkcs_req(request, '127.0.0.1')
        assert Certificate.query.filter_by(caref=ca['refid']).count() == 1
    attrs = _response_attributes(response)
    assert (status, attrs[PKI_STATUS_OID], attrs[FAIL_INFO_OID]) == (200, '2', '2')
    assert attrs['1.3.6.1.5.5.7.24.1'] == ('the subject CN=scep-ct.unique.test is already carried by a '
                                           'certificate of this CA issued to another entity')
    assert (seen, intune.success, [t for t, _ in intune.failure]) == ([], [], [txn])


def _pending_scep(app, ca, monkeypatch):
    from models import SCEPRequest
    from services.scep.scep_service import SCEPService
    monkeypatch.setenv('UCM_SCEP_ALLOW_NO_CHALLENGE', '1')
    txn = uuid.uuid4().hex
    with app.app_context():
        SCEPService(ca['refid'], auto_approve=False).process_pkcs_req(
            _pkcs_req(app, ca['id'], 'scep-ct.unique.test', txn), '127.0.0.1')
        row = SCEPRequest.query.filter_by(transaction_id=txn, ca_refid=ca['refid']).one()
        assert row.status == 'pending'
        return txn, row.id


def test_a_scep_approval_of_a_taken_subject_tells_intune_and_stays_pending(
        app, auth_client, create_ca, ct_logs, monkeypatch):
    from models import SCEPRequest
    from services.cert.unique_subject import SubjectTaken
    from services.scep.scep_service import SCEPService
    seen, armed = ct_logs
    ca = unique_ca(app, create_ca, 'Unique SCEP approval CA')
    txn, request_id = _pending_scep(app, ca, monkeypatch)
    _data(_issue(auth_client, ca, 'scep-ct.unique.test'), 201)  # taken meanwhile
    armed.append(True)
    intune = _Intune()
    with app.app_context():
        with pytest.raises(SubjectTaken):
            SCEPService(ca['refid'], auto_approve=False, intune_client=intune).approve_request(txn, 'admin')
        db.session.rollback()
        assert db.session.get(SCEPRequest, request_id).status == 'pending'
    assert (seen, intune.success, [t for t, _ in intune.failure]) == ([], [], [txn])


def test_the_scep_approval_route_answers_409_naming_the_serial(app, auth_client, create_ca, monkeypatch):
    from models import SCEPRequest
    ca = unique_ca(app, create_ca, 'Unique SCEP route CA')
    _txn, request_id = _pending_scep(app, ca, monkeypatch)
    first = _data(_issue(auth_client, ca, 'scep-ct.unique.test'), 201)
    r = auth_client.post(f'/api/v2/scep/{request_id}/approve', json={})
    assert r.status_code == 409, r.get_json()
    assert r.get_json()['message'] == (
        f"The subject CN=scep-ct.unique.test is already carried by certificate serial "
        f"{first['serial_number']}, issued by this CA to another entity")
    with app.app_context():
        assert db.session.get(SCEPRequest, request_id).status == 'pending'
        assert Certificate.query.filter_by(caref=ca['refid']).count() == 1
