"""
HSM-backed Private Key Wrappers.

Provides RSA/EC/ML-DSA private-key wrapper objects that are accepted by the
``cryptography`` library's CertificateBuilder/CertificateRevocationListBuilder
``.sign(private_key, ...)`` API but that delegate the actual signing operation
to a remote HSM via :class:`services.hsm.HsmService`.

Implementation notes
--------------------
``cryptography`` (>= 35) checks ``isinstance(private_key, (RSAPrivateKey,
EllipticCurvePrivateKey, ...))``.  Because those classes are abstract base
classes (``abc.ABCMeta``), we *register* our wrapper classes as virtual
subclasses so the isinstance check passes without us inheriting from a
concrete implementation.

The wrappers expose the minimal API surface ``cryptography`` uses internally
when signing X.509 / CRL structures:

  * ``public_key()``
  * ``key_size`` (RSA) / ``curve`` (EC)
  * ``sign(data, padding, algorithm)``     (RSA — PKCS1v15 with SHA-256/384/512)
  * ``sign(data, signature_algorithm)``    (EC  — ECDSA with SHA-256/384/512)
  * ``sign(data, context=None)``           (ML-DSA — pure, no digest)

For the underlying HSM call we pass the raw ``data`` (the to-be-signed
bytes that ``cryptography`` already prepared) along with the *key
algorithm* string (e.g. ``"RSA-2048"``).  All in-tree providers
(OpenBao, PKCS#11, Azure Key Vault, GCP KMS) interpret the data as
"raw, please hash with the algorithm matching this key" — see
``openbao_provider.SIGN_HASH_ALGORITHM`` / ``pkcs11_provider.SIGN_MECHANISMS``.
"""

from __future__ import annotations

import logging
from typing import Optional

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from models import db
from utils import key_algorithms

logger = logging.getLogger(__name__)


# Map cryptography hash class -> HSM hash hint string used by openbao etc.
_HASH_NAME = {
    'sha256': 'sha256',
    'sha384': 'sha384',
    'sha512': 'sha512',
}
_HASH_CLASS = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384, 'sha512': hashes.SHA512}


def _bound_signing_hash(hsm_key_id: int, key_algorithm: str, requested):
    """The digest the provider signs with for this key when *requested* is
    asked for: the request itself for providers that hash with any digest,
    the key-bound one for those that do not (self-review of #347)."""
    from services.hsm import HsmService
    name = HsmService.signing_hash(hsm_key_id, key_algorithm, getattr(requested, 'name', 'sha256'))
    return _HASH_CLASS.get(name, hashes.SHA256)()


def _hash_name(algorithm) -> Optional[str]:
    if algorithm is None:
        return None
    name = getattr(algorithm, 'name', None)
    return _HASH_NAME.get(name)


def _required_hash_name(algorithm) -> str:
    """The provider hash for *algorithm*: any other digest would be named but not used."""
    name = _hash_name(algorithm)
    if name is None:
        raise UnsupportedAlgorithm(
            f"HSM signing does not support digest {getattr(algorithm, 'name', algorithm)}")
    return name


class HsmRSAPrivateKey:
    """Wraps an HSM-resident RSA private key.

    Quacks like :class:`cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey`
    well enough that ``CertificateBuilder.sign(self, hashes.SHA256())`` works.
    """

    # 'pss' once bound to a CA that signs RSA-PSS (ca_key_loader.bind_signature_scheme)
    signature_scheme = 'pkcs1v15'

    def __init__(self, hsm_key_id: int, public_key: rsa.RSAPublicKey,
                 key_algorithm: str = 'RSA-2048'):
        self._hsm_key_id = hsm_key_id
        self._public_key = public_key
        self._key_algorithm = key_algorithm

    # --- public API used by cryptography -------------------------------

    def public_key(self) -> rsa.RSAPublicKey:
        return self._public_key

    @property
    def key_size(self) -> int:
        return self._public_key.key_size

    def sign(self, data: bytes, padding_alg, algorithm) -> bytes:
        """Sign ``data`` via HSM.

        ``cryptography`` calls this with the (already prepared) TBS bytes,
        a padding instance and a hash algorithm. PKCS#1 v1.5, or PSS where the
        provider signs it: anything else is refused rather than signed v1.5.
        """
        from services.hsm import HsmService

        if self.signature_scheme == 'pss' and not isinstance(padding_alg, padding.PSS):
            raise ValueError('This CA signs with RSA-PSS: refusing a PKCS#1 v1.5 signature')
        if isinstance(padding_alg, padding.PSS):
            return self._sign_pss(data, padding_alg, algorithm)
        if not isinstance(padding_alg, padding.PKCS1v15):
            raise UnsupportedAlgorithm(
                f"HSM RSA signing supports PKCS#1 v1.5 and PSS only, not {type(padding_alg).__name__}")

        # The digest cryptography asked for is what the AlgorithmIdentifier
        # will name: the provider must hash with it, not with a digest of its
        # own choosing (self-review of #347)
        return HsmService.sign(self._hsm_key_id, data, self._key_algorithm,
                               hash_algorithm=_required_hash_name(algorithm))

    def _sign_pss(self, data: bytes, padding_alg, algorithm) -> bytes:
        """PSS through the provider, checked here: a provider that picked
        another salt or digest would yield a signature nobody can verify."""
        from services.hsm import HsmService

        salt = getattr(padding_alg, '_salt_length', None)
        if salt not in (padding.PSS.DIGEST_LENGTH, getattr(algorithm, 'digest_size', None)):
            raise UnsupportedAlgorithm('HSM RSA-PSS signs with a salt as long as the digest only')
        signature = HsmService.sign(self._hsm_key_id, data, self._key_algorithm,
                                    hash_algorithm=_required_hash_name(algorithm), padding='pss')
        try:
            self._public_key.verify(signature, data, padding.PSS(
                mgf=padding.MGF1(algorithm), salt_length=algorithm.digest_size), algorithm)
        except InvalidSignature:
            raise ValueError('The HSM returned an RSA-PSS signature that does not verify '
                             '(digest or salt length differs)') from None
        return signature

    def signing_hash(self, requested):
        """The digest the provider will sign with when *requested* is asked for."""
        return _bound_signing_hash(self._hsm_key_id, self._key_algorithm, requested)

    # --- minimal stubs so private_bytes() failures are explicit --------

    def private_numbers(self):
        raise NotImplementedError("HSM-resident RSA key cannot be exported")

    def private_bytes(self, *args, **kwargs):
        raise NotImplementedError("HSM-resident RSA key cannot be exported")

    def decrypt(self, *args, **kwargs):
        raise NotImplementedError("HSM RSA decrypt not implemented")

    def __repr__(self) -> str:
        return f"<HsmRSAPrivateKey hsm_key_id={self._hsm_key_id}>"


class HsmECPrivateKey:
    """Wraps an HSM-resident EC private key.

    Quacks like :class:`cryptography.hazmat.primitives.asymmetric.ec.EllipticCurvePrivateKey`.
    """

    def __init__(self, hsm_key_id: int, public_key: ec.EllipticCurvePublicKey,
                 key_algorithm: str = 'EC-P256'):
        self._hsm_key_id = hsm_key_id
        self._public_key = public_key
        self._key_algorithm = key_algorithm

    # --- public API used by cryptography -------------------------------

    def public_key(self) -> ec.EllipticCurvePublicKey:
        return self._public_key

    @property
    def curve(self) -> ec.EllipticCurve:
        return self._public_key.curve

    @property
    def key_size(self) -> int:
        return self._public_key.key_size

    def sign(self, data: bytes, signature_algorithm) -> bytes:
        """Sign ``data`` via HSM.

        ``cryptography`` calls this with TBS bytes and an ``ec.ECDSA(digest)``
        instance; the digest is what the signature's AlgorithmIdentifier will
        name, so the provider hashes with it (self-review of #347).
        """
        from services.hsm import HsmService

        if not isinstance(signature_algorithm, ec.ECDSA):
            raise UnsupportedAlgorithm(
                f"HSM EC signing supports ECDSA only, not {type(signature_algorithm).__name__}")
        return HsmService.sign(self._hsm_key_id, data, self._key_algorithm,
                               hash_algorithm=_required_hash_name(signature_algorithm.algorithm))

    def signing_hash(self, requested):
        """The digest the provider will sign with when *requested* is asked for."""
        return _bound_signing_hash(self._hsm_key_id, self._key_algorithm, requested)

    def exchange(self, *args, **kwargs):
        raise NotImplementedError("HSM EC exchange not implemented")

    def private_numbers(self):
        raise NotImplementedError("HSM-resident EC key cannot be exported")

    def private_bytes(self, *args, **kwargs):
        raise NotImplementedError("HSM-resident EC key cannot be exported")

    def __repr__(self) -> str:
        return f"<HsmECPrivateKey hsm_key_id={self._hsm_key_id}>"


class HsmMLDSAPrivateKey:
    """Wraps an HSM-resident ML-DSA key. One subclass per parameter set, each
    registered as the pyca class of that set: the builders read the signature
    OID from the class, so a wrapper of another level would mislabel it."""

    LABEL: Optional[str] = None

    def __init__(self, hsm_key_id: int, public_key, key_algorithm: Optional[str] = None):
        self._hsm_key_id = hsm_key_id
        self._public_key = public_key
        self._key_algorithm = key_algorithm or self.LABEL

    def public_key(self):
        return self._public_key

    def sign(self, data: bytes, context: Optional[bytes] = None) -> bytes:
        """Pure ML-DSA over ``data``, no digest; X.509 uses the empty context (RFC 9881)."""
        from services.hsm import HsmService

        if context:
            raise UnsupportedAlgorithm('HSM ML-DSA signing takes no context')
        signature = HsmService.sign(self._hsm_key_id, data, self._key_algorithm)
        try:
            self._public_key.verify(signature, data)
        except InvalidSignature:
            raise ValueError('The HSM returned an ML-DSA signature that does not verify '
                             '(another key, parameter set or pre-hash)') from None
        return signature

    def sign_mu(self, *args, **kwargs):
        raise NotImplementedError("HSM ML-DSA signing over mu not implemented")

    def private_bytes(self, *args, **kwargs):
        raise NotImplementedError("HSM-resident ML-DSA key cannot be exported")

    def private_bytes_raw(self):
        raise NotImplementedError("HSM-resident ML-DSA key cannot be exported")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} hsm_key_id={self._hsm_key_id}>"


class HsmMLDSA44PrivateKey(HsmMLDSAPrivateKey):
    LABEL = 'ML-DSA-44'


class HsmMLDSA65PrivateKey(HsmMLDSAPrivateKey):
    LABEL = 'ML-DSA-65'


class HsmMLDSA87PrivateKey(HsmMLDSAPrivateKey):
    LABEL = 'ML-DSA-87'


_ML_DSA_WRAPPERS = {cls.LABEL: cls for cls in (
    HsmMLDSA44PrivateKey, HsmMLDSA65PrivateKey, HsmMLDSA87PrivateKey)}

# Register as virtual subclasses so isinstance() in cryptography succeeds.
rsa.RSAPrivateKey.register(HsmRSAPrivateKey)
ec.EllipticCurvePrivateKey.register(HsmECPrivateKey)
# Each ML-DSA wrapper takes the pyca class the registry gives its level
for _alg in key_algorithms.algorithms('ML-DSA'):
    _alg.private_class.register(_ML_DSA_WRAPPERS[_alg.label])


def load_hsm_private_key(hsm_key_id: int):
    """Build the right wrapper for the given HSM key id.

    Picks the wrapper from the family of the cached/published public key:
    :class:`HsmRSAPrivateKey`, :class:`HsmECPrivateKey` or the
    :class:`HsmMLDSAPrivateKey` subclass of its parameter set.

    Raises :class:`ValueError` when the key id is invalid or the key
    type is not supported.
    """
    from models.hsm import HsmKey
    from services.hsm import HsmService

    hsm_key = db.session.get(HsmKey, hsm_key_id)
    if not hsm_key:
        raise ValueError(f"HSM key {hsm_key_id} not found")

    if hsm_key.key_type != 'asymmetric':
        raise ValueError(
            f"HSM key {hsm_key_id} ({hsm_key.label}) is not an asymmetric key"
        )
    if hsm_key.purpose not in ('signing', 'all'):
        raise ValueError(
            f"HSM key {hsm_key_id} ({hsm_key.label}) is not a signing key"
        )

    pem = HsmService.get_public_key(hsm_key_id)
    public_key = serialization.load_pem_public_key(
        pem.encode() if isinstance(pem, str) else pem,
        backend=default_backend(),
    )

    family = key_algorithms.family_for_public_key(public_key)
    if family == 'RSA':
        return HsmRSAPrivateKey(hsm_key_id, public_key, hsm_key.algorithm)
    if family == 'EC':
        return HsmECPrivateKey(hsm_key_id, public_key, hsm_key.algorithm)
    if family == 'ML-DSA':
        label = key_algorithms.label_for_public_key(public_key)
        return _ML_DSA_WRAPPERS[label](hsm_key_id, public_key, label)

    raise ValueError(
        f"Unsupported HSM public key type {type(public_key).__name__} "
        f"for key {hsm_key_id} ({hsm_key.label})"
    )


def is_hsm_private_key(obj) -> bool:
    """True if ``obj`` is one of our HSM wrapper instances."""
    return isinstance(obj, (HsmRSAPrivateKey, HsmECPrivateKey, HsmMLDSAPrivateKey))
