"""CMS encoding helpers for RFC 7030 server-side key generation."""
import hashlib

from asn1crypto import algos, cms, core, keys, x509 as asn1_x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding as asym_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.x963kdf import X963KDF
from cryptography.hazmat.primitives.keywrap import aes_key_wrap
from cryptography.hazmat.primitives.padding import PKCS7

from utils import key_algorithms
from utils.est_key_encryption import KEY_WRAPS, KeyAgreement, choose_key_encryption
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


class _EccCmsSharedInfo(core.Sequence):
    """RFC 5753 §7.2 ECC-CMS-SharedInfo, the X9.63 KDF input."""
    _fields = [
        ('key_info', cms.KeyEncryptionAlgorithm),
        ('entity_u_info', core.OctetString, {'explicit': 0, 'optional': True}),
        ('supp_pub_info', core.OctetString, {'explicit': 2}),
    ]


_HASHES = {'sha1': hashes.SHA1, 'sha224': hashes.SHA224, 'sha256': hashes.SHA256,
           'sha384': hashes.SHA384, 'sha512': hashes.SHA512}


def _issuer_and_serial(cert):
    asn1 = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    return {'issuer': asn1.issuer, 'serial_number': asn1.serial_number}


def _oaep_identifier(transport):
    """RFC 4055 §4.1 RSAES-OAEP-params; DER drops the SHA-1 defaults."""
    return {'algorithm': 'rsaes_oaep', 'parameters': algos.RSAESOAEPParams({
        'hash_algorithm': {'algorithm': transport.oaep_hash},
        'mask_gen_algorithm': {'algorithm': 'mgf1',
                               'parameters': {'algorithm': transport.mgf_hash}},
    })}


def _key_trans_recipient(content_key, recipient_cert, transport):
    public_key = recipient_cert.public_key()
    if transport.oaep_hash is None:
        encrypted_key = public_key.encrypt(content_key, asym_padding.PKCS1v15())
        algorithm = {'algorithm': 'rsaes_pkcs1v15', 'parameters': core.Null()}  # RFC 3370 §4.2.1
    else:
        algorithm = _oaep_identifier(transport)
        encrypted_key = public_key.encrypt(content_key, asym_padding.OAEP(
            mgf=asym_padding.MGF1(_HASHES[transport.mgf_hash]()),
            algorithm=_HASHES[transport.oaep_hash](), label=None))
    return cms.RecipientInfo(name='ktri', value=cms.KeyTransRecipientInfo({
        'version': 'v0',
        'rid': {'issuer_and_serial_number': _issuer_and_serial(recipient_cert)},
        'key_encryption_algorithm': algorithm,
        'encrypted_key': encrypted_key,
    }))


def _key_agree_recipient(content_key, recipient_cert, agreement):
    """RFC 5753 §3.1 ephemeral-static ECDH: X9.63 KDF over ECC-CMS-SharedInfo, then AES key wrap."""
    public_key = recipient_cert.public_key()
    ephemeral = ec.generate_private_key(public_key.curve)
    wrap_name, kek_size = KEY_WRAPS[agreement.wrap]
    ukm = csp_bytes(32)  # RFC 5753 §3.1.1: originators SHOULD include the ukm
    shared_info = _EccCmsSharedInfo({
        'key_info': {'algorithm': wrap_name},
        'entity_u_info': ukm,
        'supp_pub_info': (kek_size * 8).to_bytes(4, 'big'),
    }).dump()
    kek = X963KDF(algorithm=_HASHES[agreement.kdf_hash](), length=kek_size,
                  sharedinfo=shared_info).derive(ephemeral.exchange(ec.ECDH(), public_key))
    originator = keys.PublicKeyInfo.load(ephemeral.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    return cms.RecipientInfo(name='kari', value=cms.KeyAgreeRecipientInfo({
        'version': 'v3',
        'originator': cms.OriginatorIdentifierOrKey(name='originator_key', value=originator),
        'ukm': ukm,
        # RFC 5753 §3.1.1: the key agreement OID, its parameters the KeyWrapAlgorithm
        'key_encryption_algorithm': {
            'algorithm': agreement.scheme,
            'parameters': cms.KeyEncryptionAlgorithm({'algorithm': wrap_name}),
        },
        'recipient_encrypted_keys': [{
            'rid': {'issuer_and_serial_number': _issuer_and_serial(recipient_cert)},
            'encrypted_key': aes_key_wrap(kek, content_key),
        }],
    }))


def build_server_generated_key_cms(private_key, signer_key, signer_cert, recipient_cert, chain=(),
                                   key_encryption=None):
    """The signed key package in EnvelopedData for *recipient_cert* (RFC 7030 §4.4.2).

    *key_encryption* (utils.est_key_encryption) picks the content cipher and the ktri (RSA) or
    kari (EC) recipient; None gives the defaults for the recipient's key.
    """
    recipient_public_key = recipient_cert.public_key()
    if key_encryption is None:
        key_encryption = choose_key_encryption(recipient_public_key, None)
    agreement = isinstance(key_encryption.recipient, KeyAgreement)
    if not isinstance(recipient_public_key,
                      ec.EllipticCurvePublicKey if agreement else rsa.RSAPublicKey):
        raise ValueError('EST server-generated key encryption does not match the client key')

    signed_der = signed_key_package(private_key, signer_key, signer_cert, chain).dump()
    content_key = csp_bytes(key_encryption.content_key_size)
    iv = csp_bytes(16)
    padder = PKCS7(128).padder()
    padded = padder.update(signed_der) + padder.finalize()
    encryptor = Cipher(algorithms.AES(content_key), modes.CBC(iv)).encryptor()
    encrypted_content = encryptor.update(padded) + encryptor.finalize()

    if agreement:
        recipient_info = _key_agree_recipient(content_key, recipient_cert, key_encryption.recipient)
    else:
        recipient_info = _key_trans_recipient(content_key, recipient_cert, key_encryption.recipient)
    enveloped_data = cms.EnvelopedData({
        # RFC 5652 §6.1: 0 when every RecipientInfo is version 0, else 2 (kari is version 3)
        'version': 'v2' if agreement else 'v0',
        'recipient_infos': [recipient_info],
        'encrypted_content_info': {
            'content_type': 'signed_data',
            'content_encryption_algorithm': {
                'algorithm': key_encryption.content_name,
                'parameters': iv,
            },
            'encrypted_content': encrypted_content,
        },
    })
    return cms.ContentInfo({
        'content_type': 'enveloped_data',
        'content': enveloped_data,
    }).dump()
