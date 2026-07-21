"""
SCEP Crypto Helpers - PKCS#7 construction, signing, and client encryption.
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding


def create_degenerate_pkcs7(certs: list) -> bytes:
    """
    Build a degenerate (certs-only) PKCS#7 SignedData structure.

    Args:
        certs: List of cryptography.x509.Certificate objects

    Returns:
        DER-encoded ContentInfo wrapping the degenerate SignedData
    """
    cert_ders = [
        asn1crypto.x509.Certificate.load(
            cert.public_bytes(serialization.Encoding.DER)
        )
        for cert in certs
    ]

    signed_data = asn1crypto.cms.SignedData({
        'version': 1,
        'digest_algorithms': [],
        'encap_content_info': {'content_type': 'data'},
        'certificates': cert_ders,
        'signer_infos': [],
    })

    content_info = asn1crypto.cms.ContentInfo({
        'content_type': 'signed_data',
        'content': signed_data,
    })

    return content_info.dump()


def create_signed_pkcs7(
    data: Optional[bytes],
    signer_key,
    signer_cert: x509.Certificate,
    signed_attributes: Optional[list] = None,
) -> bytes:
    """Build a CMS SignedData message signed by *signer_key*.

    The encapsulated bytes are bound through the CMS messageDigest signed
    attribute. The signer certificate is included so recipients can identify
    and validate the signature.
    """
    digest = hashes.Hash(hashes.SHA256())
    digest.update(data or b'')

    attributes = asn1crypto.cms.CMSAttributes([
        *(signed_attributes or []),
        {'type': 'content_type', 'values': ['data']},
        {
            'type': 'message_digest',
            'values': [asn1crypto.core.OctetString(digest.finalize())],
        },
        {
            'type': 'signing_time',
            'values': [asn1crypto.core.UTCTime(datetime.now(timezone.utc))],
        },
    ])

    attributes_der = attributes.dump()
    if attributes_der and attributes_der[0] == 0xA0:
        attributes_for_signing = b'\x31' + attributes_der[1:]
    else:
        attributes_for_signing = attributes_der

    signature = signer_key.sign(
        attributes_for_signing,
        asym_padding.PKCS1v15(),
        hashes.SHA256(),
    )
    signer_cert_asn1 = asn1crypto.x509.Certificate.load(
        signer_cert.public_bytes(serialization.Encoding.DER)
    )

    signer_info = asn1crypto.cms.SignerInfo({
        'version': 'v1',
        'sid': {
            'issuer_and_serial_number': {
                'issuer': signer_cert_asn1.issuer,
                'serial_number': signer_cert_asn1.serial_number,
            }
        },
        'digest_algorithm': {'algorithm': 'sha256'},
        'signed_attrs': attributes,
        'signature_algorithm': {'algorithm': 'rsassa_pkcs1v15'},
        'signature': asn1crypto.core.OctetString(signature),
    })

    encap_content_info = {'content_type': 'data'}
    if data is not None:
        encap_content_info['content'] = asn1crypto.core.OctetString(data)

    signed_data = asn1crypto.cms.SignedData({
        'version': 'v1',
        'digest_algorithms': [{'algorithm': 'sha256'}],
        'encap_content_info': encap_content_info,
        'certificates': [signer_cert_asn1],
        'signer_infos': [signer_info],
    })
    return asn1crypto.cms.ContentInfo({
        'content_type': 'signed_data',
        'content': signed_data,
    }).dump()


def encrypt_for_client(
    data: bytes,
    recipient_cert: x509.Certificate,
) -> bytes:
    """
    Encrypt *data* for the SCEP client using AES-256-CBC EnvelopedData (RFC 8894).

    The recipient is identified by *recipient_cert*'s issuer + serial, NOT by
    the CA's serial: per RFC 5652 §6.2.1 the RecipientInfo.rid identifies the
    *recipient's* certificate (the one whose public key wraps the CEK), so
    the issuer/serial pair must come from the client's signer cert (the
    self-signed bootstrap cert in PKCSReq, or the previously-issued cert in
    RenewalReq), not from the CA cert.

    Args:
        data: Plaintext to encrypt (typically the degenerate PKCS#7 with certs)
        recipient_cert: Client's cert from the SCEP message SignedData

    Returns:
        DER-encoded ContentInfo wrapping EnvelopedData
    """
    client_public_key = recipient_cert.public_key()

    content_key = secrets.token_bytes(32)   # AES-256
    iv = secrets.token_bytes(16)            # AES block size

    block_size = 16
    padding_len = block_size - (len(data) % block_size)
    padded_data = data + bytes([padding_len] * padding_len)
    encryptor = Cipher(algorithms.AES(content_key), modes.CBC(iv)).encryptor()
    encrypted_content = encryptor.update(padded_data) + encryptor.finalize()

    encrypted_key = client_public_key.encrypt(content_key, asym_padding.PKCS1v15())

    recipient_issuer = asn1crypto.x509.Name.load(
        recipient_cert.issuer.public_bytes(serialization.Encoding.DER)
    )
    recipient_serial = recipient_cert.serial_number

    recipient_info = asn1crypto.cms.RecipientInfo({
        'ktri': {
            'version': 'v0',
            'rid': {
                'issuer_and_serial_number': {
                    'issuer': recipient_issuer,
                    'serial_number': recipient_serial,
                }
            },
            'key_encryption_algorithm': {'algorithm': 'rsaes_pkcs1v15'},
            'encrypted_key': asn1crypto.core.OctetString(encrypted_key),
        }
    })

    encrypted_content_info = {
        'content_type': 'data',
        'content_encryption_algorithm': {
            'algorithm': '2.16.840.1.101.3.4.1.42',   # AES-256-CBC
            'parameters': asn1crypto.core.OctetString(iv),
        },
        'encrypted_content': asn1crypto.core.OctetString(encrypted_content),
    }

    enveloped_data = asn1crypto.cms.EnvelopedData({
        'version': 'v0',
        'recipient_infos': [recipient_info],
        'encrypted_content_info': encrypted_content_info,
    })

    content_info = asn1crypto.cms.ContentInfo({
        'content_type': 'enveloped_data',
        'content': enveloped_data,
    })

    return content_info.dump()
