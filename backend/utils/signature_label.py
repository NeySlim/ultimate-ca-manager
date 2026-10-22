"""Readable name of a certificate's or CSR's signature algorithm.

cryptography names RSASSA-PSS "rsassaPss", which hides the hash and the salt
length a compliance reader needs; every other algorithm keeps its OID name.
"""
import asn1crypto.csr
import asn1crypto.x509
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import SignatureAlgorithmOID

from utils.foreign_algorithms import signature_label


def signature_algorithm_label(obj) -> str:
    """'RSASSA-PSS SHA-256 (salt 32)' for PSS, the OID name (or dotted string) otherwise."""
    oid = obj.signature_algorithm_oid
    if oid != SignatureAlgorithmOID.RSASSA_PSS:
        return signature_label(oid)
    hash_name = obj.signature_hash_algorithm.name
    der = obj.public_bytes(serialization.Encoding.DER)
    parsed = (asn1crypto.x509.Certificate if isinstance(obj, x509.Certificate)
              else asn1crypto.csr.CertificationRequest).load(der)
    salt = parsed['signature_algorithm']['parameters']['salt_length'].native
    return f'RSASSA-PSS SHA-{hash_name[3:]} (salt {salt})'
