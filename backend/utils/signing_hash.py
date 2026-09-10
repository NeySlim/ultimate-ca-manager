"""The digest a signing key is used with.

The AlgorithmIdentifier a signature carries must name the digest that was
actually computed. Software keys sign with whatever digest they are handed;
an HSM-resident key is signed by its provider, and some providers bind the
digest to the key (a curve-matched ECDSA, a KMS key version). The builders
ask here instead of assuming SHA-256 (self-review of #347).
"""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed448, ed25519

HASH_BY_NAME = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384, 'sha512': hashes.SHA512}


def signing_hash_for(key, requested=None):
    """The digest to hand ``builder.sign()`` for *key*.

    None for Ed25519/Ed448 keys, which take none. For an HSM-resident key,
    the digest its provider will sign with when *requested* is asked for.
    Otherwise *requested*, SHA-256 by default.
    """
    if isinstance(key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)):
        return None
    requested = requested or hashes.SHA256()
    chooser = getattr(key, 'signing_hash', None)
    if callable(chooser):
        return chooser(requested)
    return requested
