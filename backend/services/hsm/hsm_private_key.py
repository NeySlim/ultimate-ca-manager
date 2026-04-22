"""
HSM-backed Private Key Wrappers.

Provides RSA/EC private-key wrapper objects that are accepted by the
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
  * ``sign(data, padding, algorithm)``     (RSA — PKCS1v15/SHA-256)
  * ``sign(data, signature_algorithm)``    (EC  — ECDSA(SHA-256))

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

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

logger = logging.getLogger(__name__)


# Map cryptography hash class -> HSM hash hint string used by openbao etc.
_HASH_NAME = {
    'sha256': 'sha256',
    'sha384': 'sha384',
    'sha512': 'sha512',
}


def _hash_name(algorithm) -> Optional[str]:
    if algorithm is None:
        return None
    name = getattr(algorithm, 'name', None)
    return _HASH_NAME.get(name)


class HsmRSAPrivateKey:
    """Wraps an HSM-resident RSA private key.

    Quacks like :class:`cryptography.hazmat.primitives.asymmetric.rsa.RSAPrivateKey`
    well enough that ``CertificateBuilder.sign(self, hashes.SHA256())`` works.
    """

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
        a padding instance and a hash algorithm.  We only support
        PKCS1v15+SHA-256 in MVP; other combinations log a warning but are
        still forwarded — the HSM provider decides based on the key type.
        """
        from services.hsm import HsmService

        if not isinstance(padding_alg, padding.PKCS1v15):
            logger.warning(
                "HSM RSA sign requested with %s padding — only PKCS1v15 is "
                "fully tested; falling back to provider default.",
                type(padding_alg).__name__,
            )

        if algorithm is not None and not isinstance(algorithm, hashes.SHA256):
            logger.warning(
                "HSM RSA sign requested with %s; provider may select a "
                "different hash based on the key algorithm.",
                getattr(algorithm, 'name', type(algorithm).__name__),
            )

        return HsmService.sign(self._hsm_key_id, data, self._key_algorithm)

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

        ``cryptography`` calls this with TBS bytes and an
        ``ec.ECDSA(hashes.SHA256())`` instance.
        """
        from services.hsm import HsmService

        if not isinstance(signature_algorithm, ec.ECDSA):
            logger.warning(
                "HSM EC sign called with %s — expected ec.ECDSA",
                type(signature_algorithm).__name__,
            )
        else:
            inner = signature_algorithm.algorithm
            if not isinstance(inner, hashes.SHA256):
                logger.warning(
                    "HSM EC sign requested with hash %s; provider may select "
                    "a different hash based on the key algorithm.",
                    getattr(inner, 'name', type(inner).__name__),
                )

        return HsmService.sign(self._hsm_key_id, data, self._key_algorithm)

    def exchange(self, *args, **kwargs):
        raise NotImplementedError("HSM EC exchange not implemented")

    def private_numbers(self):
        raise NotImplementedError("HSM-resident EC key cannot be exported")

    def private_bytes(self, *args, **kwargs):
        raise NotImplementedError("HSM-resident EC key cannot be exported")

    def __repr__(self) -> str:
        return f"<HsmECPrivateKey hsm_key_id={self._hsm_key_id}>"


# Register as virtual subclasses so isinstance() in cryptography succeeds.
rsa.RSAPrivateKey.register(HsmRSAPrivateKey)
ec.EllipticCurvePrivateKey.register(HsmECPrivateKey)


def load_hsm_private_key(hsm_key_id: int):
    """Build the right wrapper for the given HSM key id.

    Detects RSA vs EC from the cached/published public key and returns
    either an :class:`HsmRSAPrivateKey` or :class:`HsmECPrivateKey`.

    Raises :class:`ValueError` when the key id is invalid or the key
    type is not supported.
    """
    from models.hsm import HsmKey
    from services.hsm import HsmService

    hsm_key = HsmKey.query.get(hsm_key_id)
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

    if isinstance(public_key, rsa.RSAPublicKey):
        return HsmRSAPrivateKey(hsm_key_id, public_key, hsm_key.algorithm)
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return HsmECPrivateKey(hsm_key_id, public_key, hsm_key.algorithm)

    raise ValueError(
        f"Unsupported HSM public key type {type(public_key).__name__} "
        f"for key {hsm_key_id} ({hsm_key.label})"
    )


def is_hsm_private_key(obj) -> bool:
    """True if ``obj`` is one of our HSM wrapper instances."""
    return isinstance(obj, (HsmRSAPrivateKey, HsmECPrivateKey))
