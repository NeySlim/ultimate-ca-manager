"""failInfo values and texts of SCEP failures (RFC 8894 §3.2.1.4, §3.3.2.2),
and a POST without `operation` taken as PKIOperation (§4.3)."""
import os
import uuid

import asn1crypto.algos
import asn1crypto.cms
import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import AttributeOID, NameOID

from models import SystemConfig, db
from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
from services.scep.scep_service import SCEPService

from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, MESSAGE_TYPE_OID, PKI_STATUS_OID, SENDER_NONCE_OID,
    TRANSACTION_ID_OID, _client_identity, _load_ca_material, _response_attributes,
)

FAIL_INFO_TEXT_OID = '1.3.6.1.5.5.7.24.1'


def _request(ca_cert, message_type=19, challenge='sekret', transaction_id=None, cipher=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer, _ = _client_identity('fail-info.example.test', key=key)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fail-info.example.test')]))
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge.encode())
           .sign(key, hashes.SHA256()))
    envelope = encrypt_for_client(csr.public_bytes(serialization.Encoding.DER), ca_cert)
    if cipher is not None:
        info = asn1crypto.cms.ContentInfo.load(envelope)
        info['content']['encrypted_content_info']['content_encryption_algorithm'] = \
            asn1crypto.algos.EncryptionAlgorithm({'algorithm': cipher,
                                                  'parameters': asn1crypto.core.OctetString(os.urandom(8))})
        envelope = info.dump(force=True)
    attrs = [
        {'type': TRANSACTION_ID_OID,
         'values': [asn1crypto.core.PrintableString(transaction_id or uuid.uuid4().hex)]},
        {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.PrintableString(str(message_type))]},
        {'type': SENDER_NONCE_OID, 'values': [asn1crypto.core.OctetString(b'fail-info-nonce!')]},
    ]
    return create_signed_pkcs7(envelope, key, signer, signed_attributes=attrs)


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn=f'SCEP failInfo CA {uuid.uuid4().hex[:8]}')
    with app.app_context():
        yield _load_ca_material(ca_data['id'])[:2]


def test_single_des_is_bad_alg(app, scep_ca):
    ca, ca_cert = scep_ca
    response, _ = SCEPService(ca.refid, challenge_password='sekret', auto_approve=True) \
        .process_pkcs_req(_request(ca_cert, cipher='des'), '127.0.0.1')
    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_OID] == '0'          # badAlg


def test_failure_carries_its_reason_as_fail_info_text(app, scep_ca):
    ca, ca_cert = scep_ca
    response, _ = SCEPService(ca.refid, challenge_password='sekret', auto_approve=True) \
        .process_pkcs_req(_request(ca_cert, challenge='wrong'), '127.0.0.1')
    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_TEXT_OID] == 'Invalid challenge password'


def test_rejection_reason_reaches_the_client(app, scep_ca):
    ca, ca_cert = scep_ca
    txn = uuid.uuid4().hex
    service = SCEPService(ca.refid, challenge_password='sekret', auto_approve=False)
    pending, _ = service.process_pkcs_req(_request(ca_cert, transaction_id=txn), '127.0.0.1')
    assert _response_attributes(pending)[PKI_STATUS_OID] == '3'
    assert service.reject_request(txn, 'Device not in inventory')

    response, _ = service.process_pkcs_req(_request(ca_cert, message_type=20, transaction_id=txn),
                                           '127.0.0.1')
    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2'
    assert attrs[FAIL_INFO_TEXT_OID] == 'Device not in inventory'


def test_success_and_pending_carry_no_fail_info_text(app, scep_ca):
    ca, ca_cert = scep_ca
    response, _ = SCEPService(ca.refid, challenge_password='sekret', auto_approve=False) \
        .process_pkcs_req(_request(ca_cert), '127.0.0.1')
    assert FAIL_INFO_TEXT_OID not in _response_attributes(response)


def test_post_without_operation_is_a_pki_operation(app, client, create_ca):
    ca = create_ca(cn=f'SCEP POST no operation CA {uuid.uuid4().hex[:8]}')
    with app.app_context():
        db.session.add(SystemConfig(key='scep_ca_id', value=str(ca['id'])))
        db.session.commit()
        _ca, ca_cert = _load_ca_material(ca['id'])[:2]
        body = _request(ca_cert)
    try:
        r = client.post('/scep/pkiclient.exe', data=body,
                        content_type='application/x-pki-message')
        assert r.status_code == 200
        assert r.content_type == 'application/x-pki-message'
        assert _response_attributes(r.data)[PKI_STATUS_OID] == '3'   # queued, no challenge set
        # A GET without operation keeps answering GetCACaps
        assert b'SCEPStandard' in client.get('/scep/pkiclient.exe').data
    finally:
        with app.app_context():
            db.session.delete(SystemConfig.query.filter_by(key='scep_ca_id').first())
            db.session.commit()
