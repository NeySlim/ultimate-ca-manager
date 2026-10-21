"""
Constants for TrustStoreService
"""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# Supported key types; 8192 is not in the key registry but MSCA rekeys keep it.
KEY_TYPES = {
    '2048': ('rsa', 2048),
    '3072': ('rsa', 3072),
    '4096': ('rsa', 4096),
    '8192': ('rsa', 8192),
    'prime256v1': ('ec', ec.SECP256R1()),
    'secp256r1': ('ec', ec.SECP256R1()),
    'secp384r1': ('ec', ec.SECP384R1()),
    'secp521r1': ('ec', ec.SECP521R1()),
}

# Supported signature hashes, the policy digests (services.policy_service.POLICY_DIGESTS)
HASH_ALGORITHMS = {
    'sha256': hashes.SHA256(),
    'sha384': hashes.SHA384(),
    'sha512': hashes.SHA512(),
}


def hash_algorithm(digest):
    """The signature hash named *digest*, SHA-256 when none is named; an unknown
    name is refused rather than signed in SHA-256."""
    if not digest:
        return hashes.SHA256()
    algo = HASH_ALGORITHMS.get(str(digest).strip().lower())
    if algo is None:
        raise ValueError(f'Unsupported signature hash: {digest}')
    return algo
