"""Certificates-only PKCS#7 bundles (P7B), built in-process for any key type."""
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7


def p7b_from_pems(pems, encoding=serialization.Encoding.DER) -> bytes:
    """Every certificate of the PEM blobs *pems*, in order, as ``openssl crl2pkcs7 -nocrl`` bundles them."""
    certs = []
    for pem in pems:
        if pem:
            certs.extend(x509.load_pem_x509_certificates(pem if isinstance(pem, bytes) else pem.encode()))
    return pkcs7.serialize_certificates(certs, encoding)
