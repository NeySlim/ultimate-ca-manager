"""CMS SignedData (RFC 5652 §5) with one signer, as EST, SCEP and TSA sign it."""
import hashlib
from typing import Callable, NamedTuple

from asn1crypto import cms, core, crl as asn1_crl, x509 as asn1_x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, padding, rsa

from utils import key_algorithms
from utils.signing_hash import (
    HASH_BY_NAME, pss_algorithm_identifier, pss_padding, signing_hash_for, signs_pss,
)

# Digest identifiers with absent parameters (RFC 5754 §2, RFC 9882 §3.3); Ed448 takes
# id-shake256-len with 512 output bits (RFC 8419 §2.3)
DIGEST_DER = {
    'sha256': bytes.fromhex('300b0609608648016503040201'),
    'sha384': bytes.fromhex('300b0609608648016503040202'),
    'sha512': bytes.fromhex('300b0609608648016503040203'),
    'shake256_len': bytes.fromhex('300f060960864801650304021202020200'),
}

SIGNER_KINDS = ('rsa', 'ec', 'ed25519', 'ed448', 'ml-dsa')


class UnsupportedSigner(ValueError):
    """The signer key is of a kind the caller does not sign CMS with."""


class SignatureSuite(NamedTuple):
    digest: str                                # hashlib name, or shake256_len
    digest_algorithm: cms.DigestAlgorithm
    signature_algorithm: object                # SignedDigestAlgorithm or its dict
    sign: Callable[[bytes], bytes]

    def digest_of(self, content: bytes) -> bytes:
        if self.digest == 'shake256_len':
            return hashlib.shake_256(content).digest(64)
        return hashlib.new(self.digest, content).digest()


def signer_kind(signer_key):
    """One of SIGNER_KINDS or 'dsa' for *signer_key* (HSM wrappers included), else None."""
    if key_algorithms.family_for_public_key(signer_key.public_key()) == 'ML-DSA':
        return 'ml-dsa'
    for kind, cls in (('ed25519', ed25519.Ed25519PrivateKey), ('ed448', ed448.Ed448PrivateKey),
                      ('ec', ec.EllipticCurvePrivateKey), ('rsa', rsa.RSAPrivateKey),
                      ('dsa', dsa.DSAPrivateKey)):
        if isinstance(signer_key, cls):
            return kind
    return None


def signature_suite(signer_key, digest=None, *, pss=True, hsm_digest=True,
                    null_digest_params=False, rsa_encryption=False, accept=SIGNER_KINDS):
    """Digest and signature of *signer_key* for a SignerInfo. *digest* applies to RSA, EC and
    DSA (None: the key's own, *hsm_digest* letting an HSM provider bind it); EdDSA and ML-DSA fix
    theirs. *null_digest_params* and *rsa_encryption* keep the SCEP and TSA encodings."""
    kind = signer_kind(signer_key)
    if kind not in accept:
        label = key_algorithms.label_for_private_key(signer_key) or type(signer_key).__name__
        raise UnsupportedSigner(f'Unsupported CMS signer key type: {label}')
    if kind == 'ml-dsa':
        # RFC 9882 §3.3: SHA-512 digests the content, pure ML-DSA signs the attributes
        oid = key_algorithms.get(key_algorithms.label_for_public_key(signer_key.public_key())).oid
        return SignatureSuite('sha512', cms.DigestAlgorithm.load(DIGEST_DER['sha512']),
                              {'algorithm': oid}, signer_key.sign)
    if kind == 'ed448':
        return SignatureSuite('shake256_len', cms.DigestAlgorithm.load(DIGEST_DER['shake256_len']),
                              {'algorithm': 'ed448'}, signer_key.sign)

    def suite(name, signature_algorithm, sign):
        algorithm = (cms.DigestAlgorithm({'algorithm': name}) if null_digest_params
                     else cms.DigestAlgorithm.load(DIGEST_DER[name]))
        return SignatureSuite(name, algorithm, signature_algorithm, sign)

    if kind == 'ed25519':
        return suite('sha512', {'algorithm': 'ed25519'}, signer_key.sign)  # RFC 8419 §3.1
    if hsm_digest:
        algorithm = signing_hash_for(signer_key, digest and HASH_BY_NAME[digest]())
    else:
        algorithm = HASH_BY_NAME[digest or key_algorithms.default_digest_for_key(signer_key)]()
    name = algorithm.name
    if kind == 'ec':
        return suite(name, {'algorithm': f'{name}_ecdsa'},
                     lambda tbs: signer_key.sign(tbs, ec.ECDSA(algorithm)))
    if kind == 'dsa':
        return suite(name, {'algorithm': f'{name}_dsa'}, lambda tbs: signer_key.sign(tbs, algorithm))
    if pss and signs_pss(signer_key):
        return suite(name, pss_algorithm_identifier(algorithm),
                     lambda tbs: signer_key.sign(tbs, pss_padding(algorithm), algorithm))
    # RFC 3370 §3.2 allows rsaEncryption as the PKCS#1 v1.5 signature algorithm
    return suite(name, {'algorithm': 'rsassa_pkcs1v15' if rsa_encryption else f'{name}_rsa'},
                 lambda tbs: signer_key.sign(tbs, padding.PKCS1v15(), algorithm))


def _asn1_cert(cert):
    return asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))


def _content_info(signed):
    return cms.ContentInfo({'content_type': 'signed_data', 'content': signed}).dump()


def signed_data(content_type, content, signer_key, signer_cert, *, suite=None, signed_attrs=(),
                extra_certs=(), include_certs=True, detached=False):
    """ContentInfo DER of a SignedData over *content*: signedAttrs hold content-type,
    message-digest and *signed_attrs* (RFC 5652 §5.3), certificates hold *signer_cert* and
    *extra_certs* (a SET OF, DER-sorted), and the version is 1 for id-data, else 3 (§5.1)."""
    suite = suite or signature_suite(signer_key)
    attrs = cms.CMSAttributes([
        {'type': 'content_type', 'values': [content_type]},
        {'type': 'message_digest', 'values': [core.OctetString(suite.digest_of(content))]},
        *signed_attrs,
    ])
    signer = _asn1_cert(signer_cert)
    signer_info = cms.SignerInfo({
        'version': 'v1',
        'sid': {'issuer_and_serial_number': {
            'issuer': signer.issuer, 'serial_number': signer.serial_number}},
        'digest_algorithm': suite.digest_algorithm,
        'signed_attrs': attrs,
        'signature_algorithm': suite.signature_algorithm,
        # §5.4: the signature covers the DER of signedAttrs as a SET OF
        'signature': suite.sign(attrs.dump()),
    })
    is_data = cms.ContentType(content_type).native == 'data'
    encap = {'content_type': content_type}
    if not detached:
        encap['content'] = (core.OctetString if is_data else core.ParsableOctetString)(content)
    fields = {
        'version': 'v1' if is_data else 'v3',
        'digest_algorithms': [suite.digest_algorithm],
        'encap_content_info': encap,
        'signer_infos': [signer_info],
    }
    if include_certs:
        fields['certificates'] = [signer, *(_asn1_cert(c) for c in extra_certs)]
    return _content_info(cms.SignedData(fields))


def certs_only(certs=(), crls=()):
    """ContentInfo DER of a degenerate SignedData carrying *certs* and *crls* (RFC 5652 §5.2)."""
    fields = {
        'version': 1,
        'digest_algorithms': [],
        'encap_content_info': {'content_type': 'data'},
        'signer_infos': [],
    }
    if certs:
        fields['certificates'] = [_asn1_cert(c) for c in certs]
    if crls:
        fields['crls'] = [asn1_crl.CertificateList.load(c.public_bytes(serialization.Encoding.DER))
                          for c in crls]
    return _content_info(cms.SignedData(fields))
