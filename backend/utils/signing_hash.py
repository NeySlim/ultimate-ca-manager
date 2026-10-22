"""The digest a signing key is used with.

The AlgorithmIdentifier a signature carries must name the digest that was
actually computed. Software keys sign with whatever digest they are handed;
an HSM-resident key is signed by its provider, and some providers bind the
digest to the key (a curve-matched ECDSA, a KMS key version). The builders
ask here instead of assuming SHA-256 (self-review of #347).
"""
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed448, ed25519, padding, rsa

from utils import key_algorithms

HASH_BY_NAME = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384, 'sha512': hashes.SHA512}


def signing_hash_for(key, requested=None):
    """The digest to hand ``builder.sign()`` for *key*.

    None for Ed25519/Ed448 keys, which take none. For an HSM-resident key,
    the digest its provider will sign with when *requested* is asked for.
    Otherwise *requested*, else the registry digest of the key (SHA-256 for
    RSA and NIST curves, the curve's own for Brainpool).
    """
    if isinstance(key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)):
        return None
    requested = requested or HASH_BY_NAME[key_algorithms.default_digest_for_key(key)]()
    chooser = getattr(key, 'signing_hash', None)
    if callable(chooser):
        return chooser(requested)
    return requested


SIGNATURE_SCHEMES = ('pkcs1v15', 'pss')


def pss_padding(algorithm):
    """RSASSA-PSS with MGF1 over the same digest and a salt as long as it
    (CA/Browser Forum BR §7.1.3.2.1, Mozilla Root Store Policy)."""
    return padding.PSS(mgf=padding.MGF1(algorithm), salt_length=algorithm.digest_size)


def pss_algorithm_identifier(algorithm):
    """The RSASSA-PSS AlgorithmIdentifier of a hand-built structure (OCSP, CMS),
    in the encoding pyca writes in certificates and the Mozilla policy lists."""
    from asn1crypto import algos, core
    return algos.SignedDigestAlgorithm({'algorithm': 'rsassa_pss', 'parameters': algos.RSASSAPSSParams({
        'hash_algorithm': {'algorithm': algorithm.name, 'parameters': core.Null()},
        'mask_gen_algorithm': {'algorithm': 'mgf1',
                               'parameters': {'algorithm': algorithm.name, 'parameters': core.Null()}},
        'salt_length': algorithm.digest_size,
    })})


def signs_pss(key):
    """Whether *key* is bound to a CA that signs RSA-PSS."""
    return getattr(key, 'signature_scheme', None) == 'pss'


def rsa_padding_for(key, algorithm):
    """``rsa_padding`` for ``builder.sign()``: PSS when *key* is bound to it, else None (v1.5)."""
    if algorithm is not None and signs_pss(key):
        return pss_padding(algorithm)
    return None


class PssBoundRSAKey:
    """A software RSA key of a CA that signs RSA-PSS: a v1.5 signature from a
    path that forgot the scheme is refused instead of issued."""

    signature_scheme = 'pss'

    def __init__(self, key):
        self._key = key

    def sign(self, data, padding_alg, algorithm):
        if not isinstance(padding_alg, padding.PSS):
            raise ValueError('This CA signs with RSA-PSS: refusing a PKCS#1 v1.5 signature')
        return self._key.sign(data, padding_alg, algorithm)

    def public_key(self):
        return self._key.public_key()

    @property
    def key_size(self):
        return self._key.key_size

    def decrypt(self, ciphertext, padding_alg):
        return self._key.decrypt(ciphertext, padding_alg)

    def private_numbers(self):
        return self._key.private_numbers()

    def private_bytes(self, *args, **kwargs):
        return self._key.private_bytes(*args, **kwargs)

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


rsa.RSAPrivateKey.register(PssBoundRSAKey)
