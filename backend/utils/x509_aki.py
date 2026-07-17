"""RFC 5280 Authority Key Identifier helpers.

§4.2.1.1 / §5.2.1 — when the issuer publishes a Subject Key Identifier, AKI
must identify that same key identifier (not a recomputed hash that can diverge
from a non-method-1 SKI, and never a value copied from a client CSR).
"""
from cryptography import x509
from cryptography.x509.oid import ExtensionOID


def authority_key_identifier_from_issuer(
    issuer_cert: x509.Certificate,
) -> x509.AuthorityKeyIdentifier:
    """Build AKI from the issuer certificate's SKI, with public-key fallback."""
    try:
        ski = issuer_cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        )
        return x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
            ski.value
        )
    except x509.ExtensionNotFound:
        return x509.AuthorityKeyIdentifier.from_issuer_public_key(
            issuer_cert.public_key()
        )
