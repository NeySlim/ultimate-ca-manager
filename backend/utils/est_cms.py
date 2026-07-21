"""CMS encoding helpers for RFC 7030 server-side key generation."""
import os

from asn1crypto import algos, cms, x509 as asn1_x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


def _signed_private_key(private_key, issued_cert, pkcs8_der):
    """Return a CMS SignedData value containing and authenticating PKCS#8."""
    cert_der = issued_cert.public_bytes(serialization.Encoding.DER)
    signer_cert = asn1_x509.Certificate.load(cert_der)
    signature = private_key.sign(
        pkcs8_der,
        asym_padding.PKCS1v15(),
        hashes.SHA256(),
    )
    signer_info = cms.SignerInfo({
        'version': 'v1',
        'sid': {
            'issuer_and_serial_number': {
                'issuer': signer_cert.issuer,
                'serial_number': signer_cert.serial_number,
            }
        },
        'digest_algorithm': {'algorithm': 'sha256'},
        'signature_algorithm': {'algorithm': 'sha256_rsa'},
        'signature': signature,
    })
    return cms.SignedData({
        'version': 'v1',
        'digest_algorithms': [{'algorithm': 'sha256'}],
        'encap_content_info': {
            'content_type': 'data',
            'content': pkcs8_der,
        },
        'certificates': [signer_cert],
        'signer_infos': [signer_info],
    })


def _rsa_oaep_algorithm():
    parameters = algos.RSAESOAEPParams({
        'hash_algorithm': {'algorithm': 'sha256'},
        'mask_gen_algorithm': {
            'algorithm': 'mgf1',
            'parameters': {'algorithm': 'sha256'},
        },
        'p_source_algorithm': {
            'algorithm': 'p_specified',
            'parameters': b'',
        },
    })
    return {'algorithm': 'rsaes_oaep', 'parameters': parameters}


def build_server_generated_key_cms(private_key, issued_cert, recipient_cert):
    """Wrap a generated PKCS#8 key in SignedData and RSA KeyTrans EnvelopedData.

    The content is encrypted with AES-256-CBC. The content-encryption key is
    transported with RSA-OAEP/SHA-256 under the authenticated EST client's
    certificate, as required for the asymmetric RFC 7030 §4.4.2 response.
    """
    recipient_public_key = recipient_cert.public_key()
    if not isinstance(recipient_public_key, rsa.RSAPublicKey):
        raise ValueError(
            'EST server-generated key transport requires an RSA client certificate'
        )

    pkcs8_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    signed_data = _signed_private_key(private_key, issued_cert, pkcs8_der)
    signed_der = signed_data.dump()

    content_key = os.urandom(32)
    iv = os.urandom(16)
    padder = PKCS7(128).padder()
    padded = padder.update(signed_der) + padder.finalize()
    encryptor = Cipher(algorithms.AES(content_key), modes.CBC(iv)).encryptor()
    encrypted_content = encryptor.update(padded) + encryptor.finalize()
    encrypted_key = recipient_public_key.encrypt(
        content_key,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    recipient_der = recipient_cert.public_bytes(serialization.Encoding.DER)
    recipient_asn1 = asn1_x509.Certificate.load(recipient_der)
    recipient_info = cms.KeyTransRecipientInfo({
        'version': 'v0',
        'rid': {
            'issuer_and_serial_number': {
                'issuer': recipient_asn1.issuer,
                'serial_number': recipient_asn1.serial_number,
            }
        },
        'key_encryption_algorithm': _rsa_oaep_algorithm(),
        'encrypted_key': encrypted_key,
    })
    enveloped_data = cms.EnvelopedData({
        'version': 'v0',
        'recipient_infos': [
            cms.RecipientInfo(name='ktri', value=recipient_info)
        ],
        'encrypted_content_info': {
            'content_type': 'signed_data',
            'content_encryption_algorithm': {
                'algorithm': 'aes256_cbc',
                'parameters': iv,
            },
            'encrypted_content': encrypted_content,
        },
    })
    return cms.ContentInfo({
        'content_type': 'enveloped_data',
        'content': enveloped_data,
    }).dump()
