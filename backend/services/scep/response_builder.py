"""
SCEP Response Builder - signed CertRep PKCS#7 response construction.
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

from services.scep.crypto_helpers import create_degenerate_pkcs7, encrypt_for_client

logger = logging.getLogger(__name__)

# SCEP status codes (RFC 8894 §4.3)
STATUS_SUCCESS = 0
STATUS_FAILURE = 2
STATUS_PENDING = 3

# SCEP failure reason codes
FAIL_BAD_ALG = 0
FAIL_BAD_MESSAGE_CHECK = 1
FAIL_BAD_REQUEST = 2
FAIL_BAD_TIME = 3
FAIL_BAD_CERT_ID = 4


def build_cert_rep(
    status: int,
    data: bytes,
    transaction_id: str,
    recipient_nonce: Optional[bytes],
    ca_key,
    ca_cert: x509.Certificate,
    fail_info: Optional[int] = None,
) -> bytes:
    """
    Build a signed CertRep PKCS#7 response (RFC 8894 §4).

    Args:
        status: SCEP status (STATUS_SUCCESS / STATUS_PENDING / STATUS_FAILURE)
        data: Encapsulated content (EnvelopedData for SUCCESS, empty otherwise)
        transaction_id: SCEP transaction ID echoed from client
        recipient_nonce: senderNonce from the client request (becomes recipientNonce)
        ca_key: CA RSA private key for signing
        ca_cert: CA certificate embedded in SignedData
        fail_info: Failure reason code (required when status == STATUS_FAILURE)

    Returns:
        DER-encoded ContentInfo/SignedData CertRep
    """
    if recipient_nonce is None:
        recipient_nonce = secrets.token_bytes(16)

    scep_attrs = []

    if transaction_id:
        scep_attrs.append({
            'type': '2.16.840.1.113733.1.9.7',    # transactionID
            'values': [asn1crypto.core.PrintableString(transaction_id)],
        })

    scep_attrs.append({
        'type': '2.16.840.1.113733.1.9.2',         # messageType = CertRep (3)
        'values': [asn1crypto.core.PrintableString('3')],
    })

    scep_attrs.append({
        'type': '2.16.840.1.113733.1.9.3',         # pkiStatus
        'values': [asn1crypto.core.PrintableString(str(status))],
    })

    if status == STATUS_FAILURE and fail_info is not None:
        scep_attrs.append({
            'type': '2.16.840.1.113733.1.9.4',     # failInfo
            'values': [asn1crypto.core.PrintableString(str(fail_info))],
        })

    sender_nonce = secrets.token_bytes(16)
    scep_attrs.append({
        'type': '2.16.840.1.113733.1.9.5',         # senderNonce
        'values': [asn1crypto.core.OctetString(sender_nonce)],
    })

    if recipient_nonce:
        scep_attrs.append({
            'type': '2.16.840.1.113733.1.9.6',     # recipientNonce
            'values': [asn1crypto.core.OctetString(recipient_nonce)],
        })

    if data:
        encap_content = {
            'content_type': 'data',
            'content': asn1crypto.core.OctetString(data),
        }
    else:
        encap_content = {'content_type': 'data'}

    digest_obj = hashes.Hash(hashes.SHA256())
    if data:
        digest_obj.update(data)
    message_digest = digest_obj.finalize()

    signed_attrs = asn1crypto.cms.CMSAttributes(scep_attrs + [
        {'type': 'content_type', 'values': ['data']},
        {'type': 'message_digest', 'values': [asn1crypto.core.OctetString(message_digest)]},
        {'type': 'signing_time', 'values': [asn1crypto.core.UTCTime(datetime.now(timezone.utc))]},
    ])

    signed_attrs_der = signed_attrs.dump()
    # Replace outer tag: SET (0x31) → [0] IMPLICIT (context-specific constructed)
    signed_attrs_for_signing = b'\x31' + signed_attrs_der[1:]

    signature = ca_key.sign(signed_attrs_for_signing, asym_padding.PKCS1v15(), hashes.SHA256())

    ca_cert_der = ca_cert.public_bytes(serialization.Encoding.DER)
    ca_cert_asn1 = asn1crypto.x509.Certificate.load(ca_cert_der)

    signer_info = asn1crypto.cms.SignerInfo({
        'version': 'v1',
        'sid': asn1crypto.cms.SignerIdentifier({
            'issuer_and_serial_number': {
                'issuer': ca_cert_asn1.issuer,
                'serial_number': ca_cert_asn1.serial_number,
            }
        }),
        'digest_algorithm': {'algorithm': 'sha256'},
        'signed_attrs': signed_attrs,
        'signature_algorithm': {'algorithm': 'rsassa_pkcs1v15'},
        'signature': asn1crypto.core.OctetString(signature),
    })

    signed_data = asn1crypto.cms.SignedData({
        'version': 'v1',
        'digest_algorithms': [{'algorithm': 'sha256'}],
        'encap_content_info': encap_content,
        'certificates': [ca_cert_asn1],
        'signer_infos': [signer_info],
    })

    content_info = asn1crypto.cms.ContentInfo({
        'content_type': 'signed_data',
        'content': signed_data,
    })

    return content_info.dump()


def build_cert_rep_success(
    cert: x509.Certificate,
    transaction_id: str,
    sender_nonce: Optional[bytes],
    client_csr: x509.CertificateSigningRequest,
    ca_cert: x509.Certificate,
    ca_key,
) -> bytes:
    """Create a successful CertRep with the issued certificate encrypted for the client."""
    pkcs7_data = create_degenerate_pkcs7([cert, ca_cert])
    encrypted_data = encrypt_for_client(pkcs7_data, client_csr, ca_cert)
    return build_cert_rep(
        STATUS_SUCCESS, encrypted_data, transaction_id, sender_nonce, ca_key, ca_cert
    )


def build_cert_rep_pending(
    transaction_id: str,
    sender_nonce: Optional[bytes],
    ca_key,
    ca_cert: x509.Certificate,
) -> bytes:
    """Create a PENDING CertRep response."""
    return build_cert_rep(STATUS_PENDING, b'', transaction_id, sender_nonce, ca_key, ca_cert)


def build_error_response(
    fail_info: int,
    message: str,
    ca_key,
    ca_cert: x509.Certificate,
) -> bytes:
    """Create a FAILURE CertRep response with the given failInfo code."""
    logger.warning(f"SCEP error response: failInfo={fail_info}, message={message}")
    return build_cert_rep(
        STATUS_FAILURE, b'', '', None, ca_key, ca_cert, fail_info=fail_info
    )
