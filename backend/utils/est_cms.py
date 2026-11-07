"""CMS encoding helpers for RFC 7030 server-side key generation."""
from asn1crypto import cms, core, keys, x509 as asn1_x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding as asym_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.x963kdf import X963KDF
from cryptography.hazmat.primitives.keywrap import aes_key_wrap
from cryptography.hazmat.primitives.padding import PKCS7

from utils import cms_signed
from utils.cms_envelope import OAEP_HASHES, oaep_algorithm
from utils.est_key_encryption import KEY_WRAPS, KeyAgreement, choose_key_encryption
from utils.randomness import csp_bytes


# RFC 5958 Appendix A: id-ct-KP-aKeyPackage
AKEY_PACKAGE_OID = '2.16.840.1.101.2.1.2.78.5'


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


def signed_key_package(private_key, signer_key, signer_cert, chain=()):
    """CMS SignedData over the RFC 5958 package of *private_key*, signed by *signer_key*.

    certificates carries *signer_cert* and *chain* (a SET OF, sorted in DER) for the path to the anchor.
    """
    try:
        suite = cms_signed.signature_suite(signer_key)
    except cms_signed.UnsupportedSigner:
        raise ValueError('EST key package signing does not support this CA key type') from None
    signed = cms_signed.signed_data(AKEY_PACKAGE_OID, asymmetric_key_package(private_key), signer_key,
                                    signer_cert, suite=suite, extra_certs=chain)
    return cms.ContentInfo.load(signed)['content'].untag()


class _EccCmsSharedInfo(core.Sequence):
    """RFC 5753 §7.2 ECC-CMS-SharedInfo, the X9.63 KDF input."""
    _fields = [
        ('key_info', cms.KeyEncryptionAlgorithm),
        ('entity_u_info', core.OctetString, {'explicit': 0, 'optional': True}),
        ('supp_pub_info', core.OctetString, {'explicit': 2}),
    ]


def _issuer_and_serial(cert):
    asn1 = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    return {'issuer': asn1.issuer, 'serial_number': asn1.serial_number}


def _key_trans_recipient(content_key, recipient_cert, transport):
    public_key = recipient_cert.public_key()
    if transport.oaep_hash is None:
        encrypted_key = public_key.encrypt(content_key, asym_padding.PKCS1v15())
        algorithm = {'algorithm': 'rsaes_pkcs1v15', 'parameters': core.Null()}  # RFC 3370 §4.2.1
    else:
        algorithm = oaep_algorithm(transport.oaep_hash, transport.mgf_hash)
        encrypted_key = public_key.encrypt(content_key, asym_padding.OAEP(
            mgf=asym_padding.MGF1(OAEP_HASHES[transport.mgf_hash]()),
            algorithm=OAEP_HASHES[transport.oaep_hash](), label=None))
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
    kek = X963KDF(algorithm=OAEP_HASHES[agreement.kdf_hash](), length=kek_size,
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
