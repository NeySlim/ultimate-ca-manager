"""
SCEP Response Builder - signed CertRep PKCS#7 response construction.
"""
import logging
import secrets
from typing import Optional

import asn1crypto.core
from cryptography import x509

from services.scep.crypto_helpers import (
    create_degenerate_pkcs7,
    create_signed_pkcs7,
    encrypt_for_client,
)

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

    return create_signed_pkcs7(
        data if data else None,
        ca_key,
        ca_cert,
        signed_attributes=scep_attrs,
    )


def build_cert_rep_success(
    cert: x509.Certificate,
    transaction_id: str,
    sender_nonce: Optional[bytes],
    recipient_cert: x509.Certificate,
    ca_cert: x509.Certificate,
    ca_key,
) -> bytes:
    """Create a successful CertRep with the issued certificate encrypted for the client.

    *recipient_cert* is the client's signer cert from the original request
    (self-signed bootstrap cert for PKCSReq, previously-issued cert for
    RenewalReq); it provides both the encryption public key and the
    issuer/serial used in RecipientInfo.rid (RFC 5652 §6.2.1).
    """
    pkcs7_data = create_degenerate_pkcs7([cert, ca_cert])
    encrypted_data = encrypt_for_client(pkcs7_data, recipient_cert)
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
    transaction_id: str = '',
    recipient_nonce: Optional[bytes] = None,
) -> bytes:
    """Create a FAILURE CertRep response with the given failInfo code.

    Per RFC 8894 §3.3.2, error responses must echo the original transactionID
    and recipientNonce when available so the client can correlate them with
    its in-flight request. Callers that omit these (e.g. fast-path before
    parsing) fall back to empty values.
    """
    logger.warning(f"SCEP error response: failInfo={fail_info}, message={message}")
    return build_cert_rep(
        STATUS_FAILURE, b'', transaction_id, recipient_nonce, ca_key, ca_cert,
        fail_info=fail_info,
    )
