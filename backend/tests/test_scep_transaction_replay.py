"""A transactionID names one enrollment: replaying it with another key must
not return the certificate issued for the first key."""
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import AttributeOID

from models import Certificate, SystemConfig, db
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, PKI_STATUS_OID, _build_request, _client_identity,
    _load_ca_material, _response_attributes,
)

CHALLENGE = 'replay horse battery staple'


def _enroll_request(ca_cert, identity):
    key_cert, key = identity
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(key_cert.subject)
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
           .sign(key, hashes.SHA256()))
    # _build_request stamps every message 19 with the same transactionID
    return _build_request(ca_cert, key_cert, key, 19,
                          csr.public_bytes(serialization.Encoding.DER), b'replay-nonce-16b')


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn='SCEP Replay CA')
    with app.app_context():
        db.session.add(SystemConfig(key=f'scep_challenge_{ca_data["id"]}', value=CHALLENGE))
        db.session.commit()
    yield ca_data
    with app.app_context():
        row = SystemConfig.query.filter_by(key=f'scep_challenge_{ca_data["id"]}').first()
        if row:
            db.session.delete(row)
            db.session.commit()


def _process(ca, request):
    return SCEPService(ca.refid, challenge_password=CHALLENGE,
                       auto_approve=True).process_pkcs_req(request, '127.0.0.1')


def test_same_transaction_with_another_key_is_refused(app, scep_ca):
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
        first = _client_identity('replay device')
        response, _ = _process(ca, _enroll_request(ca_cert, first))
        assert _response_attributes(response)[PKI_STATUS_OID] == '0'
        issued = Certificate.query.count()

        other = _client_identity('replay device')          # same subject, new key
        response, status = _process(ca, _enroll_request(ca_cert, other))
        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == '2'                 # FAILURE
        assert attrs[FAIL_INFO_OID] == '2'                  # badRequest
        assert Certificate.query.count() == issued

        response, _ = _process(ca, _enroll_request(ca_cert, first))
        assert _response_attributes(response)[PKI_STATUS_OID] == '0'   # same key: replay ok
        assert Certificate.query.count() == issued


def test_pending_transaction_with_another_key_is_refused(app, scep_ca):
    """Manual approval: the first key's request waits, another key on the same
    transaction must not be told to wait for a certificate it can never use."""
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
        first = _client_identity('pending device')
        response, _ = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                  auto_approve=False).process_pkcs_req(
            _enroll_request(ca_cert, first), '127.0.0.1')
        assert _response_attributes(response)[PKI_STATUS_OID] == '3'   # PENDING

        other = _client_identity('pending device')
        response, _ = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                  auto_approve=False).process_pkcs_req(
            _enroll_request(ca_cert, other), '127.0.0.1')
        attrs = _response_attributes(response)
        assert attrs[PKI_STATUS_OID] == '2'
        assert attrs[FAIL_INFO_OID] == '2'

        response, _ = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                  auto_approve=False).process_pkcs_req(
            _enroll_request(ca_cert, first), '127.0.0.1')
        assert _response_attributes(response)[PKI_STATUS_OID] == '3'   # same key still waits
