"""
SCEP Crypto Helpers - PKCS#7 construction, signing, and client encryption.
"""
from datetime import datetime, timezone
from typing import Optional

import asn1crypto.algos
import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

import fips_mode
from utils import cms_signed
from utils.cms_envelope import (  # noqa: F401 (oaep_padding re-exported)
    OAEP_HASHES, oaep_algorithm, oaep_parameters, oaep_padding,
)
from utils.randomness import csp_bytes


AES128_CBC = "aes128_cbc"
AES256_CBC = "aes256_cbc"

RSAES_PKCS1V15 = "rsaes_pkcs1v15"
RSAES_OAEP = "rsaes_oaep"
# (algorithm, OAEP hash): a reply wraps its content key the way the request did.
DEFAULT_KEY_TRANSPORT = (RSAES_PKCS1V15, None)

def select_response_key_transport(encrypted_bytes: bytes) -> tuple:
    """Key transport of the request's first RSA recipient, to reuse in the reply."""
    content_info = asn1crypto.cms.ContentInfo.load(encrypted_bytes)
    if content_info['content_type'].native != 'enveloped_data':
        return DEFAULT_KEY_TRANSPORT
    for recipient_info in content_info['content']['recipient_infos']:
        if recipient_info.name != 'ktri':
            continue
        algorithm = recipient_info.chosen['key_encryption_algorithm']
        if algorithm['algorithm'].native == RSAES_OAEP:
            hash_name, _mgf_hash, _label = oaep_parameters(algorithm['parameters'])
            if hash_name in OAEP_HASHES:
                return (RSAES_OAEP, hash_name)
        if fips_mode.enabled():
            continue  # a v1.5 recipient is not ours: FIPS mode refused it inbound
        return DEFAULT_KEY_TRANSPORT
    return DEFAULT_KEY_TRANSPORT
_CONTENT_ENCRYPTION = {
    AES128_CBC: (16, "2.16.840.1.101.3.4.1.2"),
    AES256_CBC: (32, "2.16.840.1.101.3.4.1.42"),
}
_PWRI_KEK_OID = "1.2.840.113549.1.9.16.3.9"
_PWRI_PBKDF2_ITERATIONS = 100_000


def create_degenerate_pkcs7(certs: list, crls: Optional[list] = None) -> bytes:
    """Build a degenerate PKCS#7 SignedData carrying certificates or CRLs."""
    return cms_signed.certs_only(certs, crls or ())


# CertRep keeps its PKCS#7-era encoding: SHA-256 whatever the key (Ed25519: SHA-512),
# NULL digest parameters, rsaEncryption for v1.5, DSA accepted, Ed448 and ML-DSA refused
_CERTREP_SUITE = {'hsm_digest': False, 'null_digest_params': True, 'rsa_encryption': True,
                  'accept': ('rsa', 'ec', 'dsa', 'ed25519')}


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
    suite = cms_signed.signature_suite(signer_key, 'sha256', **_CERTREP_SUITE)
    signing_time = {'type': 'signing_time',
                    'values': [asn1crypto.core.UTCTime(datetime.now(timezone.utc))]}
    return cms_signed.signed_data(
        'data', data or b'', signer_key, signer_cert, suite=suite,
        signed_attrs=[*(signed_attributes or []), signing_time], detached=data is None,
    )


def _encrypt_content(data: bytes, content_key: bytes, iv: bytes) -> bytes:
    block_size = 16
    padding_len = block_size - (len(data) % block_size)
    padded_data = data + bytes([padding_len] * padding_len)
    encryptor = Cipher(algorithms.AES(content_key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded_data) + encryptor.finalize()


def _key_transport_recipient_info(
    content_key: bytes,
    recipient_cert: x509.Certificate,
    key_transport: tuple = DEFAULT_KEY_TRANSPORT,
) -> asn1crypto.cms.RecipientInfo:
    algorithm, hash_name = key_transport
    if algorithm != RSAES_OAEP:
        fips_mode.refuse('RSA PKCS#1 v1.5 key transport')
    if algorithm == RSAES_OAEP:
        hash_cls = OAEP_HASHES[hash_name]
        encrypted_key = recipient_cert.public_key().encrypt(
            content_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(hash_cls()), algorithm=hash_cls(), label=None
            ),
        )
        key_algorithm = oaep_algorithm(hash_name)
    else:
        encrypted_key = recipient_cert.public_key().encrypt(
            content_key, asym_padding.PKCS1v15()
        )
        key_algorithm = {'algorithm': RSAES_PKCS1V15}
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
            'key_encryption_algorithm': key_algorithm,
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
        + csp_bytes(wrapped_length - unpadded_length)
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

    salt = csp_bytes(16)
    kek_iv = csp_bytes(16)
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
    key_transport: tuple = DEFAULT_KEY_TRANSPORT,
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

    content_key = csp_bytes(content_key_length)
    content_iv = csp_bytes(16)
    encrypted_content = _encrypt_content(data, content_key, content_iv)
    recipient_public_key = recipient_cert.public_key()

    if isinstance(recipient_public_key, rsa.RSAPublicKey):
        recipient_info = _key_transport_recipient_info(
            content_key, recipient_cert, key_transport
        )
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
