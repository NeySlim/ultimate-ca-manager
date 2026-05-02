"""
SCEP Crypto Helpers - degenerate PKCS#7 construction and client encryption.
"""
import secrets

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
from Crypto.Cipher import AES
from cryptography import x509
from cryptography.hazmat.primitives import serialization
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


def encrypt_for_client(
    data: bytes,
    client_csr: x509.CertificateSigningRequest,
    ca_cert: x509.Certificate,
) -> bytes:
    """
    Encrypt *data* for the SCEP client using AES-256-CBC EnvelopedData (RFC 8894).

    Args:
        data: Plaintext to encrypt (typically the degenerate PKCS#7 with certs)
        client_csr: Client's CSR — provides the public key for CEK encryption
        ca_cert: CA certificate — serial number is embedded in RecipientInfo

    Returns:
        DER-encoded ContentInfo wrapping EnvelopedData
    """
    client_public_key = client_csr.public_key()

    content_key = secrets.token_bytes(32)   # AES-256
    iv = secrets.token_bytes(16)            # AES block size

    cipher = AES.new(content_key, AES.MODE_CBC, iv)
    block_size = 16
    padding_len = block_size - (len(data) % block_size)
    padded_data = data + bytes([padding_len] * padding_len)
    encrypted_content = cipher.encrypt(padded_data)

    encrypted_key = client_public_key.encrypt(content_key, asym_padding.PKCS1v15())

    csr_subject_der = client_csr.subject.public_bytes(serialization.Encoding.DER)
    recipient_name = asn1crypto.x509.Name.load(csr_subject_der)

    recipient_info = asn1crypto.cms.RecipientInfo({
        'ktri': {
            'version': 'v0',
            'rid': {
                'issuer_and_serial_number': {
                    'issuer': recipient_name,
                    'serial_number': ca_cert.serial_number,
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
