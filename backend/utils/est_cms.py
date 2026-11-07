"""CMS encoding helpers for RFC 7030 server-side key generation."""
import hashlib

from asn1crypto import algos, cms, core, x509 as asn1_x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding as asym_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from utils import key_algorithms
from utils.randomness import csp_bytes
from utils.signing_hash import pss_algorithm_identifier, pss_padding, signing_hash_for, signs_pss


# RFC 5958 Appendix A: id-ct-KP-aKeyPackage
AKEY_PACKAGE_OID = '2.16.840.1.101.2.1.2.78.5'

# Digest identifiers with absent parameters (RFC 5754 §2, RFC 9882 §3.3); Ed448 takes
# id-shake256-len with 512 output bits (RFC 8419 §2.3)
_DIGEST_DER = {
    'sha256': bytes.fromhex('300b0609608648016503040201'),
    'sha384': bytes.fromhex('300b0609608648016503040202'),
    'sha512': bytes.fromhex('300b0609608648016503040203'),
    'shake256_len': bytes.fromhex('300f060960864801650304021202020200'),
}


class _AsymmetricKeyPackage(core.SequenceOf):
    _child_spec = core.Any


def asymmetric_key_package(private_key):
    """RFC 5958 AsymmetricKeyPackage holding *private_key* as one OneAsymmetricKey (v1)."""
    pkcs8 = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return _AsymmetricKeyPackage([core.Any.load(pkcs8)]).dump()


def _signature_suite(signer_key):
    """(digest name, signature AlgorithmIdentifier, sign(tbs)) for *signer_key*, HSM included."""
    family = key_algorithms.family_for_public_key(signer_key.public_key())
    if family == 'ML-DSA':
        # RFC 9882 §3.3: SHA-512 digests the content, pure ML-DSA signs the attributes
        oid = key_algorithms.get(key_algorithms.label_for_public_key(signer_key.public_key())).oid
        return 'sha512', {'algorithm': oid}, signer_key.sign
    if isinstance(signer_key, ed25519.Ed25519PrivateKey):
        return 'sha512', {'algorithm': 'ed25519'}, signer_key.sign  # RFC 8419 §3.1
    if isinstance(signer_key, ed448.Ed448PrivateKey):
        return 'shake256_len', {'algorithm': 'ed448'}, signer_key.sign
    algorithm = signing_hash_for(signer_key)
    if isinstance(signer_key, ec.EllipticCurvePrivateKey):
        return (algorithm.name, {'algorithm': f'{algorithm.name}_ecdsa'},
                lambda tbs: signer_key.sign(tbs, ec.ECDSA(algorithm)))
    if isinstance(signer_key, rsa.RSAPrivateKey):
        if signs_pss(signer_key):
            return (algorithm.name, pss_algorithm_identifier(algorithm),
                    lambda tbs: signer_key.sign(tbs, pss_padding(algorithm), algorithm))
        return (algorithm.name, {'algorithm': f'{algorithm.name}_rsa'},
                lambda tbs: signer_key.sign(tbs, asym_padding.PKCS1v15(), algorithm))
    raise ValueError('EST key package signing does not support this CA key type')


def _content_digest(name, content):
    if name == 'shake256_len':
        return hashlib.shake_256(content).digest(64)
    return hashlib.new(name, content).digest()


def signed_key_package(private_key, signer_key, signer_cert, chain=()):
    """CMS SignedData over the RFC 5958 package of *private_key*, signed by *signer_key*.

    certificates carries *signer_cert* and *chain* (a SET OF, sorted in DER) for the path to the anchor.

    eContentType is id-ct-KP-aKeyPackage, so signedAttrs carry content-type and
    message-digest (RFC 5652 §5.3) and the version is 3 (§5.1).
    """
    package = asymmetric_key_package(private_key)
    digest_name, signature_algorithm, sign = _signature_suite(signer_key)
    digest_algorithm = cms.DigestAlgorithm.load(_DIGEST_DER[digest_name])
    signed_attrs = cms.CMSAttributes([
        cms.CMSAttribute({'type': 'content_type', 'values': [cms.ContentType(AKEY_PACKAGE_OID)]}),
        cms.CMSAttribute({'type': 'message_digest',
                          'values': [core.OctetString(_content_digest(digest_name, package))]}),
    ])
    signer = asn1_x509.Certificate.load(signer_cert.public_bytes(serialization.Encoding.DER))
    signer_info = cms.SignerInfo({
        'version': 'v1',
        'sid': {'issuer_and_serial_number': {
            'issuer': signer.issuer, 'serial_number': signer.serial_number}},
        'digest_algorithm': digest_algorithm,
        'signed_attrs': signed_attrs,
        'signature_algorithm': signature_algorithm,
        # RFC 5652 §5.4: the signature covers the DER of signedAttrs as a SET OF
        'signature': sign(signed_attrs.dump()),
    })
    return cms.SignedData({
        'version': 'v3',
        'digest_algorithms': [digest_algorithm],
        'encap_content_info': {
            'content_type': AKEY_PACKAGE_OID,
            'content': core.ParsableOctetString(package),
        },
        'certificates': [signer, *(
            asn1_x509.Certificate.load(c.public_bytes(serialization.Encoding.DER)) for c in chain)],
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


def build_server_generated_key_cms(private_key, signer_key, signer_cert, recipient_cert, chain=()):
    """Wrap the generated key in a signed key package and RSA KeyTrans EnvelopedData.

    The content is encrypted with AES-256-CBC. The content-encryption key is
    transported with RSA-OAEP/SHA-256 under the authenticated EST client's
    certificate, as required for the asymmetric RFC 7030 §4.4.2 response.
    """
    recipient_public_key = recipient_cert.public_key()
    if not isinstance(recipient_public_key, rsa.RSAPublicKey):
        raise ValueError(
            'EST server-generated key transport requires an RSA client certificate'
        )

    signed_data = signed_key_package(private_key, signer_key, signer_cert, chain)
    signed_der = signed_data.dump()

    content_key = csp_bytes(32)
    iv = csp_bytes(16)
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
