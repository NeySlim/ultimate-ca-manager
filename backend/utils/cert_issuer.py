"""Cryptographic issuer check for X.509 certificates.

A certificate names its issuer by DN, and two CAs can carry the same DN (a
decoy root imported under a parent's name, a re-keyed root), so anything
that resolves "the CA that issued this certificate" must check the
signature with the candidate's key, not the name (#343 review).
"""
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, padding, rsa


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
