"""Algorithms of the issuance paths where nobody picks one (#397).

The template bound to the path decides first; without one, the issuing CA's
key; the issuance policies then bound the result. One rule for EST, SCEP,
WSTEP, Sign CSR, renewals and the keys UCM generates for a requester.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ec

from utils import key_algorithms
from utils.ca_profile import default_digest_for_key_type

# NIST curves: the EC keys browsers present as TLS client keys
_BROWSER_CURVES = ('P256', 'P384', 'P521')


def _public(key):
    try:
        return key.public_key()
    except (AttributeError, TypeError):
        return key


def _algorithm_digest(alg) -> str | None:
    if not alg.needs_digest:
        return None
    return default_digest_for_key_type(alg.curve_names[0]) if alg.curve_names else 'sha256'


def digest_for_key(key) -> str | None:
    """Digest matching *key* (public or private): the curve's for EC (P-384 SHA-384,
    P-521 SHA-512, CA/Browser Forum BR 7.1.3.2.2), SHA-256 for RSA, None when it takes none."""
    public = _public(key)
    if not key_algorithms.needs_digest(public):
        return None
    if isinstance(public, ec.EllipticCurvePublicKey):
        return default_digest_for_key_type(public.curve.name)
    return 'sha256'


def digest_for_label(label) -> str | None:
    """``digest_for_key`` for a key type label ('EC-P384'); SHA-256 when unknown."""
    alg = key_algorithms.get(label)
    return _algorithm_digest(alg) if alg else 'sha256'


def template_digest(template, ca_key) -> str | None:
    """The digest of the template bound to a protocol path, a choice the policies check;
    None when it is weaker than the CA key's (a seeded SHA-256 must not lower a P-384 CA)."""
    from services.policy_service import POLICY_DIGESTS, normalize_digest
    chosen = normalize_digest(getattr(template, 'digest', None)) if template is not None else None
    floor = digest_for_key(ca_key) if chosen else None
    if floor is None or floor not in POLICY_DIGESTS:
        return chosen
    return chosen if POLICY_DIGESTS.index(chosen) >= POLICY_DIGESTS.index(floor) else None


def _strength(alg) -> int:
    return alg.security_level or alg.key_size or 0


def _issuer_match(issuer_public_key, classical_only: bool):
    """The leaf algorithm of the issuer's family and strength."""
    issuer = key_algorithms.get(key_algorithms.label_for_public_key(issuer_public_key))
    family = key_algorithms.family_for_public_key(issuer_public_key)
    if family == 'RSA':
        return key_algorithms.get('RSA-3072' if issuer_public_key.key_size >= 3072 else 'RSA-2048')
    if family == 'ML-DSA' and issuer is not None and not classical_only:
        return issuer
    # EC (Brainpool and P-521 included), EdDSA, ML-DSA when classical only: a NIST curve of that strength
    if issuer is not None and issuer.security_level:
        stronger = issuer.security_level > 2
    else:
        stronger = (getattr(issuer, 'key_size', None) or 256) > 256
    return key_algorithms.get('EC-P384' if stronger else 'EC-P256')


def _candidates(wanted, classical_only: bool):
    """Leaf keys UCM generates; a Brainpool one only when the template asks for it."""
    for alg in key_algorithms.algorithms():
        if alg.trust_store_id is None:  # EdDSA: UCM generates CA keys only
            continue
        nist = alg.family != 'EC' or alg.param in _BROWSER_CURVES
        if classical_only and not (alg.family == 'RSA' or (alg.family == 'EC' and nist)):
            continue
        if not nist and alg is not wanted:
            continue
        yield alg


def generated_key_algorithm(issuer_public_key, policies, *, ca_id=None, template_key_type=None,
                            classical_only=False):
    """Registry algorithm of a key UCM generates for a requester (EST serverkeygen, mTLS):
    the template's type, else the issuer's family and strength, else the closest one the
    policies allow; *classical_only* (browsers, CMS key transport) keeps RSA and NIST EC.
    PolicyViolation when the policies allow none UCM can generate."""
    from services.policy_service import PolicyEvaluationService, PolicyViolation

    def allowed(alg):
        violations, _, _ = PolicyEvaluationService.enforce_rules(
            policies, key_type=alg.label, ca_id=ca_id, notify=False)
        return not violations

    wanted = key_algorithms.get(template_key_type) if template_key_type else None
    if wanted is None or wanted.trust_store_id is None:
        wanted = _issuer_match(issuer_public_key, classical_only)
    pool = [a for a in _candidates(wanted, classical_only) if allowed(a)]
    if wanted in pool:
        return wanted
    same = [a for a in pool if a.family == wanted.family]
    order = (sorted((a for a in same if _strength(a) >= _strength(wanted)), key=_strength)
             + sorted((a for a in same if _strength(a) < _strength(wanted)), key=_strength, reverse=True)
             + [a for a in pool if a.family != wanted.family])
    if not order:
        raise PolicyViolation('The issuance policies allow no key type UCM can generate here '
                              f'(wanted {wanted.label})')
    return order[0]


def browser_key_type(ca, cn=None) -> str:
    """KEY_TYPES id of a browser mTLS key issued by *ca* (``generated_key_algorithm``)."""
    from cryptography import x509
    from services.ca.helpers import get_ca_cert_pem
    from services.policy_service import PolicyEvaluationService
    if not ca.crt:
        raise ValueError('CA is awaiting its certificate - cannot sign certificates')
    issuer = x509.load_pem_x509_certificate(get_ca_cert_pem(ca)).public_key()
    policies = PolicyEvaluationService.applicable_policies(ca.id, None, cn)
    return generated_key_algorithm(issuer, policies, ca_id=ca.id, classical_only=True).trust_store_id


def original_digest(certificate) -> str | None:
    """The signature hash of a certificate being renewed, its preference; None when
    it has none or one cryptography cannot name (the CA key's then applies)."""
    try:
        return getattr(certificate.signature_hash_algorithm, 'name', None)
    except Exception:
        return None


def log_renewal_digest(logger, certificate, sign_hash, subject) -> None:
    """One log line when a renewal does not keep the original's signature hash."""
    kept = original_digest(certificate)
    signs = getattr(sign_hash, 'name', None)
    if kept and kept != signs:
        logger.info("Renewal of %s signs with %s instead of the original %s (CA key or policies)",
                    subject, (signs or 'no separate digest').upper(), kept.upper())
