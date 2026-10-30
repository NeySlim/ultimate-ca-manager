"""Single registry of the key algorithms UCM generates, issues and accepts.

Each row carries every name an algorithm goes by in UCM (policy and template
label, TrustStore ``KEY_TYPES`` id, legacy ``key_algo`` column, display text)
and how to recognise and generate its keys. New families are new rows:
lookups go through the table, never by splitting a label on '-'.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.backends.openssl.backend import backend as _openssl_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, mldsa, rsa

import fips_mode


class KeyGenerationError(RuntimeError):
    """``openssl genpkey`` could not produce the requested key."""


# FIPS 186-5 curves, by pyca name, as openssl genpkey spells them
_FIPS_CURVES = {'secp256r1': 'P-256', 'secp384r1': 'P-384', 'secp521r1': 'P-521'}
_GENPKEY_TIMEOUT = 110  # seconds; RSA-8192 is the slowest key UCM asks for


def _stderr_summary(stderr: bytes) -> str:
    text = (stderr or b'').decode('utf-8', 'replace')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '; '.join(lines[:3])[:300] or 'no error output'


def _genpkey(args: list[str]):
    """Private key from ``openssl genpkey``: inherits OPENSSL_CONF, so the FIPS
    provider generates it; the PEM is read from stdout, never from a file."""
    binary = shutil.which('openssl')
    if binary is None:
        raise KeyGenerationError('FIPS mode generates keys with the openssl command, which is not installed')
    try:
        proc = subprocess.run([binary, 'genpkey', '-quiet', *args], stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=_GENPKEY_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        raise KeyGenerationError(f'openssl genpkey timed out after {_GENPKEY_TIMEOUT} s') from None
    except OSError as exc:
        raise KeyGenerationError(f'openssl genpkey could not run: {exc.strerror or exc}') from None
    if proc.returncode != 0:
        raise KeyGenerationError(
            f'openssl genpkey failed (exit {proc.returncode}): {_stderr_summary(proc.stderr)}')
    try:
        return serialization.load_pem_private_key(proc.stdout, password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise KeyGenerationError('openssl genpkey printed no usable private key') from None


def generate_rsa(bits: int):
    """RSA key, public exponent 65537, of any size (off-registry ones included)."""
    if not fips_mode.enabled():
        return rsa.generate_private_key(public_exponent=65537, key_size=bits)
    bits = int(bits)
    if bits < 2048:
        fips_mode.refuse(f'RSA-{bits} keys')
    key = _genpkey(['-algorithm', 'RSA', '-pkeyopt', f'rsa_keygen_bits:{bits}'])
    if not (isinstance(key, rsa.RSAPrivateKey) and key.key_size == bits
            and key.private_numbers().public_numbers.e == 65537):
        raise KeyGenerationError(f'openssl genpkey returned a key that is not RSA-{bits}')
    return key


def generate_ec(curve: ec.EllipticCurve):
    """EC key on *curve* (an instance); FIPS mode allows P-256, P-384 and P-521 only."""
    if not fips_mode.enabled():
        return ec.generate_private_key(curve)
    openssl_name = _FIPS_CURVES.get(curve.name)
    if openssl_name is None:
        fips_mode.refuse(f'{curve.name} keys')
    key = _genpkey(['-algorithm', 'EC', '-pkeyopt', f'ec_paramgen_curve:{openssl_name}'])
    if not (isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == curve.name):
        raise KeyGenerationError(f'openssl genpkey returned a key that is not on {curve.name}')
    return key


def _non_fips_generator(name: str, private_class: type) -> Callable[[], object]:
    """Generator of a key the FIPS module does not approve: refused in FIPS mode."""
    def generate():
        fips_mode.refuse(f'{name} keys')
        return private_class.generate()
    return generate


@dataclass(frozen=True)
class KeyAlgorithm:
    label: str                      # canonical policy/template label: 'RSA-2048', 'EC-P256', 'ML-DSA-65'
    family: str                     # 'RSA', 'EC', 'ED25519', 'ED448', 'ML-DSA'
    param: str | None               # the label's parameter ('2048', 'P256'), None when it has none
    private_class: type
    public_class: type
    generator: Callable[[], object]
    needs_digest: bool              # False when the signature scheme fixes its own hash
    default_digest: str | None      # what UCM signs with when no digest is requested
    display: str
    legacy_key_algo: str            # spelling written to certificates.key_algo
    trust_store_id: str | None      # TrustStore KEY_TYPES id ('2048', 'prime256v1', 'ml-dsa-65'), None when it has none
    fips_approved: bool
    key_size: int | None = None     # RSA modulus or EC field size, in bits
    curve_names: tuple[str, ...] = ()   # pyca / OpenSSL curve names, EC only
    aliases: tuple[str, ...] = ()       # extra spellings accepted by normalize_label
    security_level: int | None = None   # NIST post-quantum security category, None for classical keys
    oid: str | None = None              # OID of a post-quantum key and of its signatures (one names both)

    def generate(self):
        return self.generator()

    def matches_key(self, key) -> bool:
        """True when *key* (public or private) is a key of exactly this algorithm."""
        if not isinstance(key, (self.public_class, self.private_class)):
            return False
        if self.curve_names:
            return key.curve.name.lower() in self.curve_names
        if self.family == 'RSA':
            return key.key_size == self.key_size
        return True


def _rsa(bits: int) -> KeyAlgorithm:
    return KeyAlgorithm(
        label=f'RSA-{bits}', family='RSA', param=str(bits),
        private_class=rsa.RSAPrivateKey, public_class=rsa.RSAPublicKey,
        generator=lambda: generate_rsa(bits),
        needs_digest=True, default_digest='sha256',
        display=f'RSA {bits}', legacy_key_algo=f'RSA {bits}', trust_store_id=str(bits),
        fips_approved=bits >= 2048, key_size=bits,
    )


def _ec(bits: int, curve: type, names: tuple[str, ...], trust_store_id: str) -> KeyAlgorithm:
    return KeyAlgorithm(
        label=f'EC-P{bits}', family='EC', param=f'P{bits}',
        private_class=ec.EllipticCurvePrivateKey, public_class=ec.EllipticCurvePublicKey,
        generator=lambda: generate_ec(curve()),
        needs_digest=True, default_digest='sha256',
        display=f'EC P-{bits}', legacy_key_algo=f'EC {curve.name}', trust_store_id=trust_store_id,
        fips_approved=True, key_size=bits, curve_names=names,
        aliases=(f'P-{bits}', f'NIST P-{bits}', f'ECDSA-P{bits}'),
    )


def _brainpool(bits: int, curve: type) -> KeyAlgorithm:
    """RFC 5639 curve; generated with pyca outside FIPS mode, refused inside it."""
    name = f'brainpoolP{bits}r1'
    return KeyAlgorithm(
        label=f'EC-BP{bits}', family='EC', param=f'BP{bits}',
        private_class=ec.EllipticCurvePrivateKey, public_class=ec.EllipticCurvePublicKey,
        generator=lambda: generate_ec(curve()),
        needs_digest=True, default_digest={256: 'sha256', 384: 'sha384', 512: 'sha512'}[bits],
        display=f'EC Brainpool P{bits}r1', legacy_key_algo=f'EC {name}', trust_store_id=name,
        fips_approved=False, key_size=bits, curve_names=(name.lower(),),
        aliases=(name, f'EC-{name}', f'BP-{bits}'),
    )


def _edwards(name: str, private_class: type, public_class: type, bits: int) -> KeyAlgorithm:
    return KeyAlgorithm(
        label=name.upper(), family=name.upper(), param=None,
        private_class=private_class, public_class=public_class,
        generator=_non_fips_generator(name, private_class),
        needs_digest=False, default_digest=None,
        display=name, legacy_key_algo=name, trust_store_id=None,
        fips_approved=False, key_size=bits,
    )


def _mldsa(param: str, level: int, oid_arc: int, private_class: type, public_class: type) -> KeyAlgorithm:
    """FIPS 204 key: signs without a separate digest, outside the FIPS module UCM ships."""
    label = f'ML-DSA-{param}'
    return KeyAlgorithm(
        label=label, family='ML-DSA', param=param,
        private_class=private_class, public_class=public_class,
        generator=_non_fips_generator(label, private_class),
        needs_digest=False, default_digest=None,
        display=label, legacy_key_algo=label, trust_store_id=label.lower(),
        fips_approved=False, key_size=None,
        security_level=level, oid=f'2.16.840.1.101.3.4.3.{oid_arc}',
    )


_CLASSICAL: tuple[KeyAlgorithm, ...] = (
    _rsa(2048),
    _rsa(3072),
    _rsa(4096),
    _ec(256, ec.SECP256R1, ('secp256r1', 'prime256v1'), 'prime256v1'),
    _ec(384, ec.SECP384R1, ('secp384r1',), 'secp384r1'),
    _ec(521, ec.SECP521R1, ('secp521r1',), 'secp521r1'),
    _brainpool(256, ec.BrainpoolP256R1),
    _brainpool(384, ec.BrainpoolP384R1),
    _brainpool(512, ec.BrainpoolP512R1),
    _edwards('Ed25519', ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey, 256),
    _edwards('Ed448', ed448.Ed448PrivateKey, ed448.Ed448PublicKey, 448),
)

_ML_DSA: tuple[KeyAlgorithm, ...] = (
    _mldsa('44', 2, 17, mldsa.MLDSA44PrivateKey, mldsa.MLDSA44PublicKey),
    _mldsa('65', 3, 18, mldsa.MLDSA65PrivateKey, mldsa.MLDSA65PublicKey),
    _mldsa('87', 5, 19, mldsa.MLDSA87PrivateKey, mldsa.MLDSA87PublicKey),
)


def mldsa_supported() -> bool:
    """Whether pyca was built against a libcrypto with ML-DSA (OpenSSL 3.5+, AWS-LC, BoringSSL);
    a FIPS provider loaded at run time may still lack it."""
    return bool(_openssl_backend.mldsa_supported())


def _collapse(value) -> str:
    """Case, whitespace, '-', '_' and ':' are not significant in a spelling."""
    return re.sub(r'[\s_:-]+', '', str(value).strip().lower())


class _Registry:
    """Lookup indexes over a tuple of algorithms; refuses ambiguous spellings."""

    def __init__(self, algorithms):
        self.algorithms = tuple(algorithms)
        self.by_label: dict[str, KeyAlgorithm] = {}
        self.by_spelling: dict[str, KeyAlgorithm] = {}
        self.by_curve: dict[str, KeyAlgorithm] = {}
        for alg in self.algorithms:
            if alg.label in self.by_label:
                raise ValueError(f'duplicate key algorithm label {alg.label!r}')
            self.by_label[alg.label] = alg
            spellings = (alg.label, alg.display, alg.legacy_key_algo, alg.trust_store_id,
                         *alg.curve_names, *alg.aliases)
            for spelling in spellings:
                if not spelling:
                    continue
                owner = self.by_spelling.setdefault(_collapse(spelling), alg)
                if owner is not alg:
                    raise ValueError(f'{spelling!r} names both {owner.label} and {alg.label}')
            for curve in alg.curve_names:
                self.by_curve[curve.lower()] = alg


def _load() -> None:
    """Build the tables: ML-DSA rows only when this build can use them; the others are
    kept apart so a request for one is told why, and its OID is still named."""
    global ALGORITHMS, _REGISTRY, _UNAVAILABLE, _KNOWN
    usable = _ML_DSA if mldsa_supported() else ()
    ALGORITHMS = _CLASSICAL + usable
    _REGISTRY = _Registry(ALGORITHMS)
    _UNAVAILABLE = _Registry(a for a in _ML_DSA if a not in usable)
    _KNOWN = _Registry(_CLASSICAL + _ML_DSA)


ALGORITHMS: tuple[KeyAlgorithm, ...]
_load()


def algorithms(family: str | None = None) -> tuple[KeyAlgorithm, ...]:
    """Registered algorithms in table order, optionally of one family."""
    return tuple(a for a in _REGISTRY.algorithms if family is None or a.family == family)


def labels(family: str | None = None) -> tuple[str, ...]:
    return tuple(a.label for a in algorithms(family))


def get(value) -> KeyAlgorithm | None:
    """The algorithm *value* names (any registered spelling), or None."""
    if value is None or isinstance(value, bool):
        return None
    key = _collapse(value)
    return _REGISTRY.by_spelling.get(key) if key else None


def normalize_label(value) -> str | None:
    """Canonical label for any registered spelling ('rsa:2048', 'EC P-256', 'prime256v1')."""
    alg = get(value)
    return alg.label if alg else None


def parse_label(value) -> tuple[str, str | None] | None:
    """``(family, param)`` of a registered algorithm, e.g. ``('EC', 'P384')``."""
    alg = get(value)
    return (alg.family, alg.param) if alg else None


def label_for_curve_name(name) -> str | None:
    """Label of the registered EC algorithm whose pyca/OpenSSL curve name is *name*."""
    alg = _REGISTRY.by_curve.get(str(name or '').strip().lower())
    return alg.label if alg else None


def family_for_public_key(public_key) -> str | None:
    """Family of *public_key* when it is a registered family, whatever its size or curve."""
    for alg in _REGISTRY.algorithms:
        if isinstance(public_key, alg.public_class):
            return alg.family
    return None


def label_for_public_key(public_key) -> str | None:
    """Label of a public key, None when its exact algorithm is not registered."""
    for alg in _REGISTRY.algorithms:
        if isinstance(public_key, alg.public_class) and alg.matches_key(public_key):
            return alg.label
    return None


def default_digest_for_key(key) -> str | None:
    """Digest name UCM signs with when none is requested, for a public or private key;
    None when its scheme takes no digest (Ed25519, Ed448, ML-DSA), sha256 if unregistered."""
    for alg in _REGISTRY.algorithms:
        if alg.matches_key(key):
            return alg.default_digest
    return 'sha256'


def needs_digest(key) -> bool:
    """Whether signing with *key* (public or private) takes a separate digest; True if unregistered."""
    for alg in _REGISTRY.algorithms:
        if alg.matches_key(key):
            return alg.needs_digest
    return True


def key_algo_for_public_key(public_key) -> str:
    """Spelling stored in ``certificates.key_algo``; sizes and curves outside
    the registry keep the "RSA <bits>" / "EC <curve>" form, DSA "DSA <bits>"."""
    for alg in _REGISTRY.algorithms:
        if isinstance(public_key, alg.public_class) and alg.matches_key(public_key):
            return alg.legacy_key_algo
    if isinstance(public_key, rsa.RSAPublicKey):
        return f'RSA {public_key.key_size}'
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return f'EC {public_key.curve.name}'
    if isinstance(public_key, dsa.DSAPublicKey):
        return f'DSA {public_key.key_size}'
    return 'Unknown'


def label_for_private_key(private_key) -> str | None:
    """Label of a private key (HSM wrappers included), None when not registered."""
    for alg in _REGISTRY.algorithms:
        if isinstance(private_key, alg.private_class) and alg.matches_key(private_key):
            return alg.label
    return None


def generate(label):
    """A new private key for *label*; ValueError when the label is unknown or this build lacks it."""
    alg = get(label)
    if alg is None:
        missing = _UNAVAILABLE.by_spelling.get(_collapse(label)) if label else None
        if missing is not None:
            raise ValueError(f'{missing.label} keys are not available on this build: '
                             'they need OpenSSL 3.5 or later')
        raise ValueError(f'Unsupported key algorithm: {label}')
    return alg.generate()


@dataclass(frozen=True)
class PostQuantumName:
    """A post-quantum algorithm as UCM names and rates it, usable here or not."""
    label: str
    family: str             # 'ML-DSA' or 'SLH-DSA'
    security_level: int     # NIST category
    oid: str                # names the key and its signatures alike


# FIPS 205 / RFC 9909: named and rated for display only, pyca cannot load these keys
_SLH_DSA = tuple(
    PostQuantumName(f'SLH-DSA-{h}-{n}{v}', 'SLH-DSA', {128: 1, 192: 3, 256: 5}[n],
                    f'2.16.840.1.101.3.4.3.{20 + i}')
    for i, (h, n, v) in enumerate((h, n, v) for h in ('SHA2', 'SHAKE')
                                  for n in (128, 192, 256) for v in ('s', 'f')))


def _post_quantum_index():
    names = [PostQuantumName(a.label, a.family, a.security_level, a.oid) for a in _ML_DSA]
    by_label = {n.label: n for n in names}
    index = {key: by_label[alg.label] for key, alg in _KNOWN.by_spelling.items() if alg.security_level}
    index.update({_collapse(n.label): n for n in _SLH_DSA})
    index.update({n.oid: n for n in (*names, *_SLH_DSA)})
    return index


_POST_QUANTUM = _post_quantum_index()


def post_quantum_info(value) -> PostQuantumName | None:
    """The post-quantum algorithm a label, spelling or OID (dotted or ``ObjectIdentifier``)
    names, whether or not this build can use it; None otherwise."""
    value = getattr(value, 'dotted_string', value)
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return _POST_QUANTUM.get(text) or _POST_QUANTUM.get(_collapse(text))


def slh_dsa_names() -> tuple[PostQuantumName, ...]:
    return _SLH_DSA


def is_post_quantum(label) -> bool:
    """Whether *label* names a post-quantum algorithm, whether or not this build can use it."""
    return post_quantum_info(label) is not None


def label_for_signature_oid(oid) -> str | None:
    """Label of the algorithm a signature OID names on its own (ML-DSA), dotted string or
    ``ObjectIdentifier``; None for hash-qualified OIDs (sha256WithRSA...) and unknown ones."""
    dotted = getattr(oid, 'dotted_string', oid)
    if not dotted or not isinstance(dotted, str):
        return None
    return next((a.label for a in _KNOWN.algorithms if a.oid == dotted), None)


EXPORT_FORMATS = ('pem', 'der', 'key', 'pkcs8', 'pkcs7', 'p7b', 'pkcs12', 'pfx', 'jks')
_KEY_CONTAINERS = ('pkcs12', 'pfx', 'jks')  # pyca writes no ML-DSA key into PKCS#12


def _family_of(key) -> str | None:
    if isinstance(key, str):
        alg = get(key)
        return alg.family if alg else None
    for alg in _REGISTRY.algorithms:
        if isinstance(key, (alg.public_class, alg.private_class)):
            return alg.family
    return None


def export_formats_for(key) -> tuple[str, ...]:
    """Export formats open to a key (public, private or label): ML-DSA has no PKCS#12 nor JKS."""
    if _family_of(key) == 'ML-DSA':
        return tuple(f for f in EXPORT_FORMATS if f not in _KEY_CONTAINERS)
    return EXPORT_FORMATS


def fips_approved(label) -> bool:
    """Whether *label* is allowed by the FIPS policy; False when unknown."""
    alg = get(label)
    return bool(alg and alg.fips_approved)


def fips_approved_labels() -> tuple[str, ...]:
    return tuple(a.label for a in _REGISTRY.algorithms if a.fips_approved)
