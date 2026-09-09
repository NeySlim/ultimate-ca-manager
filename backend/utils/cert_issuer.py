"""Cryptographic issuer check for X.509 certificates.

A certificate names its issuer by DN, and two CAs can carry the same DN (a
decoy root imported under a parent's name, a re-keyed root), so anything
that resolves "the CA that issued this certificate" must check the
signature with the candidate's key, not the name (#343 review).
"""
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding, rsa


def certificate_signed_by(cert: x509.Certificate, issuer: x509.Certificate) -> bool:
    """Whether *cert*'s signature verifies with *issuer*'s public key."""
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
        elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            public_key.verify(cert.signature, cert.tbs_certificate_bytes)
        else:
            return False
    except Exception:
        return False
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
