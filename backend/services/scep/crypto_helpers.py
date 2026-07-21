"""
SCEP Crypto Helpers - PKCS#7 construction, signing, and client encryption.
"""
import secrets
from datetime import datetime, timezone
from typing import Optional

import asn1crypto.algos
import asn1crypto.cms
import asn1crypto.core
import asn1crypto.crl
import asn1crypto.x509
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, rsa
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


AES128_CBC = "aes128_cbc"
AES256_CBC = "aes256_cbc"
_CONTENT_ENCRYPTION = {
    AES128_CBC: (16, "2.16.840.1.101.3.4.1.2"),
    AES256_CBC: (32, "2.16.840.1.101.3.4.1.42"),
}
_PWRI_KEK_OID = "1.2.840.113549.1.9.16.3.9"
_PWRI_PBKDF2_ITERATIONS = 100_000


def create_degenerate_pkcs7(certs: list, crls: Optional[list] = None) -> bytes:
    """Build a degenerate PKCS#7 SignedData carrying certificates or CRLs."""
    cert_ders = [
        asn1crypto.x509.Certificate.load(
            cert.public_bytes(serialization.Encoding.DER)
        )
        for cert in certs
    ]
    crl_ders = [
        asn1crypto.crl.CertificateList.load(
            crl.public_bytes(serialization.Encoding.DER)
        )
        for crl in (crls or [])
    ]

    signed_data_fields = {
        'version': 1,
        'digest_algorithms': [],
        'encap_content_info': {'content_type': 'data'},
        'signer_infos': [],
    }
    if cert_ders:
        signed_data_fields['certificates'] = cert_ders
    if crl_ders:
        signed_data_fields['crls'] = crl_ders

    signed_data = asn1crypto.cms.SignedData(signed_data_fields)

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
    if isinstance(signer_key, ed25519.Ed25519PrivateKey):
        digest_name = 'sha512'
        digest_algorithm = hashes.SHA512()
        signature_algorithm = 'ed25519'
    else:
        digest_name = 'sha256'
        digest_algorithm = hashes.SHA256()
        if isinstance(signer_key, rsa.RSAPrivateKey):
            signature_algorithm = 'rsassa_pkcs1v15'
        elif isinstance(signer_key, ec.EllipticCurvePrivateKey):
            signature_algorithm = 'sha256_ecdsa'
        elif isinstance(signer_key, dsa.DSAPrivateKey):
            signature_algorithm = 'sha256_dsa'
        else:
            raise ValueError("Unsupported CMS signer key type")

    digest = hashes.Hash(digest_algorithm)
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

    if isinstance(signer_key, rsa.RSAPrivateKey):
        signature = signer_key.sign(
            attributes_for_signing,
            asym_padding.PKCS1v15(),
            digest_algorithm,
        )
    elif isinstance(signer_key, ec.EllipticCurvePrivateKey):
        signature = signer_key.sign(
            attributes_for_signing,
            ec.ECDSA(digest_algorithm),
        )
    elif isinstance(signer_key, dsa.DSAPrivateKey):
        signature = signer_key.sign(attributes_for_signing, digest_algorithm)
    else:
        signature = signer_key.sign(attributes_for_signing)
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
        'digest_algorithm': {'algorithm': digest_name},
        'signed_attrs': attributes,
        'signature_algorithm': {'algorithm': signature_algorithm},
        'signature': asn1crypto.core.OctetString(signature),
    })

    encap_content_info = {'content_type': 'data'}
    if data is not None:
        encap_content_info['content'] = asn1crypto.core.OctetString(data)

    signed_data = asn1crypto.cms.SignedData({
        'version': 'v1',
        'digest_algorithms': [{'algorithm': digest_name}],
        'encap_content_info': encap_content_info,
        'certificates': [signer_cert_asn1],
        'signer_infos': [signer_info],
    })
    return asn1crypto.cms.ContentInfo({
        'content_type': 'signed_data',
        'content': signed_data,
    }).dump()


def _encrypt_content(data: bytes, content_key: bytes, iv: bytes) -> bytes:
    block_size = 16
    padding_len = block_size - (len(data) % block_size)
    padded_data = data + bytes([padding_len] * padding_len)
    encryptor = Cipher(algorithms.AES(content_key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded_data) + encryptor.finalize()


def _key_transport_recipient_info(
    content_key: bytes,
    recipient_cert: x509.Certificate,
) -> asn1crypto.cms.RecipientInfo:
    encrypted_key = recipient_cert.public_key().encrypt(
        content_key, asym_padding.PKCS1v15()
    )
    recipient_asn1 = asn1crypto.x509.Certificate.load(
        recipient_cert.public_bytes(serialization.Encoding.DER)
    )
    return asn1crypto.cms.RecipientInfo({
        'ktri': {
            'version': 'v0',
            'rid': {
                'issuer_and_serial_number': {
                    'issuer': recipient_asn1.issuer,
                    'serial_number': recipient_asn1.serial_number,
                }
            },
            'key_encryption_algorithm': {'algorithm': 'rsaes_pkcs1v15'},
            'encrypted_key': encrypted_key,
        }
    })


def _rfc3211_wrap_key(content_key: bytes, kek: bytes, iv: bytes) -> bytes:
    """Wrap a CEK with the RFC 3211 double-CBC PWRI transform."""
    block_size = 16
    prefix = bytes([len(content_key)]) + bytes(
        (~byte) & 0xFF for byte in content_key[:3]
    )
    unpadded_length = len(prefix) + len(content_key)
    wrapped_length = max(
        block_size * 2,
        ((unpadded_length + block_size - 1) // block_size) * block_size,
    )
    formatted = (
        prefix
        + content_key
        + secrets.token_bytes(wrapped_length - unpadded_length)
    )

    first_encryptor = Cipher(algorithms.AES(kek), modes.CBC(iv)).encryptor()
    first_pass = first_encryptor.update(formatted) + first_encryptor.finalize()
    second_encryptor = Cipher(
        algorithms.AES(kek), modes.CBC(first_pass[-block_size:])
    ).encryptor()
    return second_encryptor.update(first_pass) + second_encryptor.finalize()


def _password_recipient_info(
    content_key: bytes,
    password: str | bytes,
) -> asn1crypto.cms.RecipientInfo:
    password_bytes = password.encode('utf-8') if isinstance(password, str) else password
    if not isinstance(password_bytes, bytes) or not password_bytes:
        raise ValueError("A non-empty challengePassword is required for PWRI")

    salt = secrets.token_bytes(16)
    kek_iv = secrets.token_bytes(16)
    kek_length = 16
    kek = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=kek_length,
        salt=salt,
        iterations=_PWRI_PBKDF2_ITERATIONS,
    ).derive(password_bytes)
    wrapped_key = _rfc3211_wrap_key(content_key, kek, kek_iv)
    kek_algorithm = asn1crypto.algos.EncryptionAlgorithm({
        'algorithm': AES128_CBC,
        'parameters': asn1crypto.core.OctetString(kek_iv),
    })

    return asn1crypto.cms.RecipientInfo({
        'pwri': {
            'version': 'v0',
            'key_derivation_algorithm': {
                'algorithm': 'pbkdf2',
                'parameters': {
                    'salt': {'specified': salt},
                    'iteration_count': _PWRI_PBKDF2_ITERATIONS,
                    'key_length': kek_length,
                    'prf': {'algorithm': 'sha256'},
                },
            },
            'key_encryption_algorithm': {
                'algorithm': _PWRI_KEK_OID,
                'parameters': kek_algorithm,
            },
            'encrypted_key': wrapped_key,
        }
    })


def select_response_content_encryption_algorithm(encrypted_bytes: bytes) -> str:
    """Use AES-256 only when the request envelope demonstrates support for it."""
    content_info = asn1crypto.cms.ContentInfo.load(encrypted_bytes)
    if content_info['content_type'].native != 'enveloped_data':
        return AES128_CBC
    algorithm = content_info['content']['encrypted_content_info'][
        'content_encryption_algorithm'
    ]['algorithm'].native
    return AES256_CBC if algorithm == AES256_CBC else AES128_CBC


def encrypt_for_client(
    data: bytes,
    recipient_cert: x509.Certificate,
    *,
    password: Optional[str | bytes] = None,
    content_encryption_algorithm: str = AES128_CBC,
) -> bytes:
    """Encrypt SCEP messageData with CMS EnvelopedData.

    AES-128-CBC is the RFC 8894 mandatory default. AES-256-CBC remains
    available when a request demonstrated support for it. RSA recipients use
    KeyTransRecipientInfo; signing-only recipients use PasswordRecipientInfo.
    """
    try:
        content_key_length, content_algorithm_oid = _CONTENT_ENCRYPTION[
            content_encryption_algorithm
        ]
    except KeyError as e:
        raise ValueError(
            f"Unsupported SCEP response encryption algorithm: "
            f"{content_encryption_algorithm}"
        ) from e

    content_key = secrets.token_bytes(content_key_length)
    content_iv = secrets.token_bytes(16)
    encrypted_content = _encrypt_content(data, content_key, content_iv)
    recipient_public_key = recipient_cert.public_key()

    if isinstance(recipient_public_key, rsa.RSAPublicKey):
        recipient_info = _key_transport_recipient_info(content_key, recipient_cert)
        enveloped_version = 'v0'
    else:
        recipient_info = _password_recipient_info(content_key, password)
        enveloped_version = 'v3'

    enveloped_data = asn1crypto.cms.EnvelopedData({
        'version': enveloped_version,
        'recipient_infos': [recipient_info],
        'encrypted_content_info': {
            'content_type': 'data',
            'content_encryption_algorithm': {
                'algorithm': content_algorithm_oid,
                'parameters': asn1crypto.core.OctetString(content_iv),
            },
            'encrypted_content': encrypted_content,
        },
    })
    return asn1crypto.cms.ContentInfo({
        'content_type': 'enveloped_data',
        'content': enveloped_data,
    }).dump()
