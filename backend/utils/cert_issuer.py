"""Cryptographic issuer check for X.509 certificates.

A certificate names its issuer by DN, and two CAs can carry the same DN (a
decoy root imported under a parent's name, a re-keyed root), so anything
that resolves "the CA that issued this certificate" must check the
signature with the candidate's key, not the name (#343 review).
"""
import logging

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, padding, rsa


logger = logging.getLogger(__name__)


class UnsupportedIssuerKey(Exception):
    """The candidate issuer's key type cannot be verified here."""


def certificate_signed_by(cert: x509.Certificate, issuer: x509.Certificate) -> bool:
    """Whether *cert*'s signature verifies with *issuer*'s public key.

    Raises UnsupportedIssuerKey when the key type is not one this can check,
    so a caller never reads "unverifiable" as "not the issuer"."""
    public_key = issuer.public_key()
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            params = getattr(cert, 'signature_algorithm_parameters', None)
            public_key.verify(
                cert.signature, cert.tbs_certificate_bytes,
                params if isinstance(params, padding.PSS) else padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(
                cert.signature, cert.tbs_certificate_bytes,
                ec.ECDSA(cert.signature_hash_algorithm),
            )
        elif isinstance(public_key, dsa.DSAPublicKey):
            public_key.verify(
                cert.signature, cert.tbs_certificate_bytes,
                cert.signature_hash_algorithm,
            )
        elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            public_key.verify(cert.signature, cert.tbs_certificate_bytes)
        else:
            # An unknown key type cannot be cleared: saying "not signed by this
            # issuer" would drop the CA out of its chain and out of its
            # revocation with it (#343 review)
            raise UnsupportedIssuerKey(f"unsupported issuer key type {type(public_key).__name__}")
    except UnsupportedIssuerKey:
        raise
    except Exception:
        return False
    return True


def is_self_signed(cert: x509.Certificate) -> bool:
    """Whether the certificate is signed by its own key.

    A subordinate CA can carry the same DN as its issuer (a self-issued
    cross-certificate), so comparing subject and issuer is not enough to
    call it a root and stop walking the chain there (#343 review)."""
    if cert.subject != cert.issuer:
        return False
    try:
        return certificate_signed_by(cert, cert)
    except UnsupportedIssuerKey:
        # Cannot tell: treat the DN match as authoritative, as before
        return True


def authority_key_identifier_hex(cert: x509.Certificate):
    """The AKI keyIdentifier as stored in CA.ski ("AA:BB:..."), or None."""
    try:
        aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
    except x509.ExtensionNotFound:
        return None
    if not aki.key_identifier:
        return None
    return aki.key_identifier.hex(':').upper()


def private_key_matches(private_key, cert: x509.Certificate) -> bool:
    """Whether *private_key* is the key of *cert*: same SubjectPublicKeyInfo.

    A key stored next to a certificate it does not belong to signs answers
    nobody can verify; the pair is checked wherever one arrives (#347 review).
    """
    from cryptography.hazmat.primitives import serialization
    try:
        spki = lambda pub: pub.public_bytes(  # noqa: E731
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return spki(private_key.public_key()) == spki(cert.public_key())
    except Exception:
        return False


def stored_private_key_matches(prv_column, cert: x509.Certificate, *, context: str = 'record'):
    """Whether the key stored in *prv_column* is *cert*'s key.

    True or False when the stored key can be read and compared. None when
    there is nothing to compare: the column holds no key, or the key cannot
    be read (corrupt, or encrypted with a key this instance no longer has).
    An unreadable key has not been shown to be another certificate's, so
    the caller refuses to decide rather than drop it (#347 review).
    """
    if not prv_column:
        return None
    try:
        from cryptography.hazmat.primitives import serialization
        from utils.key_codec import load_pem_bytes
        pem = load_pem_bytes(prv_column, context=context)
        key = serialization.load_pem_private_key(pem, password=None)
    except Exception:
        logger.warning(f"Stored private key of {context} could not be read; "
                       "it cannot be compared with the certificate")
        return None
    return private_key_matches(key, cert)


def hsm_key_binding_matches(hsm_key_id, cert: x509.Certificate):
    """Whether the HSM key bound to a record is *cert*'s key.

    True or False from the HSM key's public key; None when that public key
    cannot be obtained, in which case nothing can be asserted and the
    caller must not keep or drop the binding on a guess (#347 review).
    """
    if not hsm_key_id:
        return None
    try:
        from services.hsm import HsmService
        from cryptography.hazmat.primitives import serialization
        pem = HsmService.get_public_key(hsm_key_id)
        if not pem:
            return None
        public_key = serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
        spki = lambda pub: pub.public_bytes(  # noqa: E731
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        return spki(public_key) == spki(cert.public_key())
    except Exception:
        return None
