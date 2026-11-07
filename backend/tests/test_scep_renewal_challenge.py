"""RFC 8894 §2.4: a RenewalReq signed by a certificate this CA issued is
authenticated by that signature, so the challengePassword is not compared:
a client SHOULD omit it and MAY send the originally distributed secret."""
import uuid

import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AttributeOID, NameOID

from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
from services.scep.scep_service import SCEPService

from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, MESSAGE_TYPE_OID, PKI_STATUS_OID, SENDER_NONCE_OID,
    TRANSACTION_ID_OID, _client_identity, _decrypt_password_response,
    _decrypt_response, _load_ca_material, _response_attributes,
)

ORIGINAL = 'original shared secret'
ROTATED = 'rotated shared secret'


def _csr(key, cn, challenge=None):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    if challenge is not None:
        builder = builder.add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge.encode())
    return builder.sign(key, hashes.SHA256())


def _message(ca_cert, signer_cert, signer_key, message_type, csr):
    attrs = [
        {'type': TRANSACTION_ID_OID,
         'values': [asn1crypto.core.PrintableString(uuid.uuid4().hex)]},
        {'type': MESSAGE_TYPE_OID,
         'values': [asn1crypto.core.PrintableString(str(message_type))]},
        {'type': SENDER_NONCE_OID,
         'values': [asn1crypto.core.OctetString(b'renewal-nonce-16')]},
    ]
    return create_signed_pkcs7(
        encrypt_for_client(csr.public_bytes(serialization.Encoding.DER), ca_cert),
        signer_key, signer_cert, signed_attributes=attrs,
    )


def _enroll(ca, ca_cert, key, cn):
    """Initial PKCSReq with the original secret; returns the issued certificate."""
    self_signed, _ = _client_identity(cn, key=key)
    request = _message(ca_cert, self_signed, key, 19, _csr(key, cn, ORIGINAL))
    response, _ = SCEPService(ca.refid, challenge_password=ORIGINAL,
                              auto_approve=True).process_pkcs_req(request, '127.0.0.1')
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    if isinstance(key, rsa.RSAPrivateKey):
        plaintext = _decrypt_response(response, key, self_signed)
    else:
        plaintext, _, _ = _decrypt_password_response(response, ORIGINAL)
    return pkcs7.load_der_pkcs7_certificates(plaintext)[0]


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn=f'SCEP Renewal Challenge CA {uuid.uuid4().hex[:8]}')
    with app.app_context():
        yield _load_ca_material(ca_data['id'])[:2]


@pytest.mark.parametrize('sent', [None, ORIGINAL, 'wrong secret'],
                         ids=['no-challenge', 'original-after-rotation', 'wrong'])
def test_renewal_signed_by_issued_cert_ignores_challenge(app, scep_ca, sent):
    ca, ca_cert = scep_ca
    old_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issued = _enroll(ca, ca_cert, old_key, 'renew-rsa.example.test')
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    request = _message(ca_cert, issued, old_key, 17,
                       _csr(new_key, 'renew-rsa.example.test', sent))

    response, status = SCEPService(ca.refid, challenge_password=ROTATED,
                                   auto_approve=True).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert status == 200
    assert attrs[PKI_STATUS_OID] == '0', attrs.get(FAIL_INFO_OID)
    renewed = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, old_key, issued))[0]
    assert renewed.public_key().public_numbers() == new_key.public_key().public_numbers()


def test_renewal_signed_by_self_signed_cert_still_needs_challenge(app, scep_ca):
    """The exemption rests on the issued certificate, not on the messageType."""
    ca, ca_cert = scep_ca
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    self_signed, _ = _client_identity('forged-renewal.example.test', key=key)
    request = _message(ca_cert, self_signed, key, 17,
                       _csr(key, 'forged-renewal.example.test'))

    response, _ = SCEPService(ca.refid, challenge_password=ROTATED,
                              auto_approve=True).process_pkcs_req(request, '127.0.0.1')

    assert _response_attributes(response)[PKI_STATUS_OID] == '2'


def test_ec_renewal_answers_with_the_password_it_sent(app, scep_ca):
    """An EC client receives its reply through PWRI, keyed by the password it sent."""
    ca, ca_cert = scep_ca
    old_key = ec.generate_private_key(ec.SECP256R1())
    issued = _enroll(ca, ca_cert, old_key, 'renew-ec.example.test')
    new_key = ec.generate_private_key(ec.SECP256R1())
    request = _message(ca_cert, issued, old_key, 17,
                       _csr(new_key, 'renew-ec.example.test', ORIGINAL))

    response, _ = SCEPService(ca.refid, challenge_password=ROTATED,
                              auto_approve=True).process_pkcs_req(request, '127.0.0.1')

    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    plaintext, recipient_info, _ = _decrypt_password_response(response, ORIGINAL)
    assert recipient_info.name == 'pwri'
    assert pkcs7.load_der_pkcs7_certificates(plaintext)[0].subject == issued.subject


def test_ec_renewal_without_any_password_is_refused(app, scep_ca):
    """No password means no PWRI key for the reply: still a failure for EC."""
    ca, ca_cert = scep_ca
    old_key = ec.generate_private_key(ec.SECP256R1())
    issued = _enroll(ca, ca_cert, old_key, 'renew-ec-nopw.example.test')
    request = _message(ca_cert, issued, old_key, 17,
                       _csr(ec.generate_private_key(ec.SECP256R1()), 'renew-ec-nopw.example.test'))

    response, _ = SCEPService(ca.refid, challenge_password=ROTATED,
                              auto_approve=True).process_pkcs_req(request, '127.0.0.1')

    assert _response_attributes(response)[PKI_STATUS_OID] == '2'
