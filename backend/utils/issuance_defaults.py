"""Algorithms of the issuance paths where nobody picks one (#397).

The template bound to the path decides first; without one, the issuing CA's
key; the issuance policies then bound the result. One rule for EST, SCEP,
WSTEP, Sign CSR, renewals and the keys UCM generates for a requester.
"""
from __future__ import annotations

from utils import key_algorithms

# NIST curves: the EC leaf keys UCM generates, the ones browsers present
_BROWSER_CURVES = ('P256', 'P384', 'P521')


def _public(key):
    try:
        return key.public_key()
    except (AttributeError, TypeError):
        return key


def digest_for_key(key) -> str | None:
    """Digest matching *key* (public or private), from the registry: the curve's for EC
    (P-384 SHA-384, P-521 SHA-512), SHA-256 for RSA, None when its scheme takes none."""
    return key_algorithms.default_digest_for_key(_public(key))


def stronger_digest(*digests) -> str | None:
    """Strongest SHA-2 among *digests*, skipping None; an intermediate's default never falls
    below its parent key's hash nor its own key's."""
    from services.policy_service import POLICY_DIGESTS
    known = [d for d in digests if d in POLICY_DIGESTS]
    return max(known, key=POLICY_DIGESTS.index) if known else next((d for d in digests if d), None)


def digest_for_label(label) -> str | None:
    """``digest_for_key`` for a key type label ('EC-P384'); SHA-256 when unknown."""
    alg = key_algorithms.get(label)
    if alg is None:
        return 'sha256'
    return alg.default_digest if alg.needs_digest else None


def template_digest(template, ca_key) -> str | None:
    """The bound template's digest, a preference that yields to the policies; None when it is
    weaker than the CA key's, whose own then applies (a seeded SHA-256 must not lower P-384)."""
    from services.policy_service import POLICY_DIGESTS, normalize_digest
    chosen = normalize_digest(getattr(template, 'digest', None)) if template is not None else None
    floor = digest_for_key(ca_key) if chosen else None
    if floor is None or floor not in POLICY_DIGESTS:
        return chosen
    return chosen if POLICY_DIGESTS.index(chosen) >= POLICY_DIGESTS.index(floor) else None


def digest_replaced_notice(policies, requested, sign_hash) -> str | None:
    """The notice naming the policy that moved the signature off *requested*, or None."""
    from services.policy_service import normalize_digest
    from utils import notices
    requested = normalize_digest(requested)
    granted = getattr(sign_hash, 'name', None)
    if not requested or not granted or granted == requested:
        return None
    for policy in policies:
        allowed = {normalize_digest(d) for d in (policy.get_rules() or {}).get('allowed_digests') or []}
        if allowed and requested not in allowed:
            return notices.digest_replaced(requested, granted, policy.name)
    return None


def _strength(alg) -> int:
    return alg.security_level or alg.key_size or 0


def _security_bits(public_key) -> int:
    """Classical security of a key (NIST SP 800-57 Part 1, table 2)."""
    if key_algorithms.family_for_public_key(public_key) == 'RSA':
        size = public_key.key_size
        return 192 if size >= 7680 else 128 if size >= 3072 else 112
    alg = key_algorithms.get(key_algorithms.label_for_public_key(public_key))
    if alg is not None and alg.security_level:
        return 128 if alg.security_level <= 2 else 192 if alg.security_level <= 4 else 256
    return ((alg.key_size if alg is not None else None) or getattr(public_key, 'key_size', None) or 256) // 2


def _of_strength(family, bits):
    if family == 'RSA':
        return key_algorithms.get('RSA-2048' if bits <= 112 else 'RSA-3072')
    return key_algorithms.get('EC-P256' if bits <= 128 else 'EC-P384')


# What a leaf key is when nothing (request, template, issuer) names one; the policies bound it
BASELINE_ISSUE_KEY = 'RSA-2048'
# Key type of a new ACME account when the request names none (not an issuance key)
DEFAULT_ACME_ACCOUNT_KEY_TYPE = 'RSA-2048'
_ISSUE_KEY_FALLBACKS = ('RSA-3072', 'EC-P256', 'EC-P384')


def default_issue_key_type(ca_id=None, profile=None, template_id=None) -> str:
    """Registry label of the key issued when nothing names one.

    Candidates in order: RSA-2048, RSA-3072, EC-P256, EC-P384; the first that the policies
    in scope allow wins. In scope: FIPS mode, the compliance profile of *ca_id* (or *profile*
    for a CA not created yet) and the active policies of *ca_id* and *template_id* (not the
    CN or SANs, unknown here). PolicyViolation (HTTP 400 at issuance) when no candidate passes.
    """
    import compliance_profiles
    from services.policy_service import PolicyEvaluationService, PolicyViolation
    policies = PolicyEvaluationService.applicable_policies(ca_id, template_id, None)
    if profile:
        policies = [*policies, compliance_profiles.profile_policy(profile)]
    refused = []
    for label in (BASELINE_ISSUE_KEY, *_ISSUE_KEY_FALLBACKS):
        violations, _, _ = PolicyEvaluationService.enforce_rules(
            policies, key_type=label, ca_id=ca_id, notify=False)
        if not violations:
            return label
        refused.append(violations[0])
    raise PolicyViolation('Policy violation: no default key type is allowed (' + '; '.join(refused) + ')')


def default_issue_key_id(ca_id=None, profile=None, template_id=None) -> str:
    """``default_issue_key_type`` as a TrustStore KEY_TYPES id ('2048', 'prime256v1')."""
    return key_algorithms.get(default_issue_key_type(ca_id, profile, template_id)).trust_store_id


def default_rsa_key_size(ca_id=None, template_id=None) -> str:
    """RSA modulus size of the default key; the first fallback's when the default is not RSA."""
    alg = key_algorithms.get(default_issue_key_type(ca_id, template_id=template_id))
    if alg.family != 'RSA':
        alg = key_algorithms.get(_ISSUE_KEY_FALLBACKS[0])
    return str(alg.key_size)


def _candidates(classical_only: bool):
    """Leaf keys UCM generates for a requester: no EdDSA (CA keys only), no Brainpool."""
    for alg in key_algorithms.algorithms():
        if alg.trust_store_id is None or (alg.family == 'EC' and alg.param not in _BROWSER_CURVES):
            continue
        if classical_only and alg.family not in ('RSA', 'EC'):
            continue
        yield alg


def _closest(wanted, pool, *, other_families):
    same = [a for a in pool if a.family == wanted.family]
    order = (sorted((a for a in same if _strength(a) >= _strength(wanted)), key=_strength)
             + sorted((a for a in same if _strength(a) < _strength(wanted)), key=_strength, reverse=True))
    if other_families:
        order += [a for a in pool if a.family != wanted.family]
    return (wanted if wanted in pool else order[0]) if order else None


def generated_key_algorithm(issuer_public_key, policies, *, ca_id=None, request_public_key=None,
                            classical_only=False):
    """Registry algorithm of a key UCM generates for a requester (EST serverkeygen, mTLS),
    at the issuer's strength: the family of *request_public_key* when RSA or EC (a hint only,
    RFC 7030 §4.4.1 ignores its values), else the issuer's; the closest the policies allow.
    *classical_only* (browsers) keeps RSA and NIST EC.
    PolicyViolation when the policies allow none UCM can generate."""
    from services.policy_service import PolicyEvaluationService, PolicyViolation

    def allowed(alg):
        violations, _, _ = PolicyEvaluationService.enforce_rules(
            policies, key_type=alg.label, ca_id=ca_id, notify=False)
        return not violations

    bits = _security_bits(issuer_public_key)
    pool = [a for a in _candidates(classical_only) if allowed(a)]
    hint = key_algorithms.family_for_public_key(request_public_key) if request_public_key is not None else None
    if hint in ('RSA', 'EC'):
        pick = _closest(_of_strength(hint, bits), pool, other_families=False)
        if pick is not None:
            return pick
    family = key_algorithms.family_for_public_key(issuer_public_key)
    issuer = key_algorithms.get(key_algorithms.label_for_public_key(issuer_public_key))
    if family == 'ML-DSA' and issuer is not None and not classical_only:
        wanted = issuer
    else:  # EC, EdDSA, and ML-DSA when classical only: a NIST curve of that strength
        wanted = _of_strength('RSA' if family == 'RSA' else 'EC', bits)
    pick = _closest(wanted, pool, other_families=True)
    if pick is None:
        raise PolicyViolation('The issuance policies allow no key type UCM can generate here '
                              f'(wanted {wanted.label})')
    return pick


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


def renewal_digest(certificate, ca_key) -> str | None:
    """The original's hash as a renewal's preference while it is at least the CA key's;
    None otherwise, so a SHA-256 renewal under P-384 is raised instead of kept forever."""
    from services.policy_service import POLICY_DIGESTS, normalize_digest
    kept = normalize_digest(original_digest(certificate))
    floor = digest_for_key(ca_key) if kept else None
    if floor is None or floor not in POLICY_DIGESTS:
        return kept
    return kept if POLICY_DIGESTS.index(kept) >= POLICY_DIGESTS.index(floor) else None


def log_renewal_digest(logger, certificate, sign_hash, subject) -> None:
    """One log line when a renewal does not keep the original's signature hash."""
    kept = original_digest(certificate)
    signs = getattr(sign_hash, 'name', None)
    if kept and kept != signs:
        logger.info("Renewal of %s signs with %s instead of the original %s (CA key or policies)",
                    subject, (signs or 'no separate digest').upper(), kept.upper())
