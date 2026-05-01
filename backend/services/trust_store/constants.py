"""
Constants for TrustStoreService
"""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

# Supported key types
KEY_TYPES = {
    '512': ('rsa', 512),
    '1024': ('rsa', 1024),
    '2048': ('rsa', 2048),
    '3072': ('rsa', 3072),
    '4096': ('rsa', 4096),
    '8192': ('rsa', 8192),
    'prime256v1': ('ec', ec.SECP256R1()),
    'secp384r1': ('ec', ec.SECP384R1()),
    'secp521r1': ('ec', ec.SECP521R1()),
}

# Supported hash algorithms
HASH_ALGORITHMS = {
    'sha224': hashes.SHA224(),
    'sha256': hashes.SHA256(),
    'sha384': hashes.SHA384(),
    'sha512': hashes.SHA512(),
}
