"""Compliance preflight: what a compliance profile would refuse or advise against on this instance.

Same contract as the FIPS preflight (read only, findings by severity). The rules
are read from ``compliance_profiles.PROFILES``: a rule in ``rules`` that the
instance breaks is a blocker, one in ``rules['advisories']`` a warning or a notice.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import compliance_profiles
from models import (CA, Certificate, CertificatePolicy, CertificateTemplate, SystemConfig)
from services import compliance_signer
from services.acme import profiles as acme_profiles
from services.fips_preflight import (_EDDSA_OIDS, _active_certificate_filter, _configured_certificate,
                                     _named, load_stored_certificate)
from services.ocsp_responder_renewal import RESPONDER_KEY_PREFIX
from services.policy_service import key_label_for_public_key, normalize_digest, parse_rule_date
from services.preflight_core import (BLOCKER, INFO, WARNING, Detector, run_detectors)
from services.template_service import _normalize_key_type_label
from services.tsa_service import tsa_is_enabled
from utils import key_algorithms
from utils.datetime_utils import utc_now

DETECTORS: List[Detector] = []

REFUSE, ADVISE = 'refuse', 'advise'


# --- context ----------------------------------------------------------------

def _label_set(values) -> set:
    """Policy labels of *values*; a spelling the registry does not know is kept as written."""
    if not isinstance(values, (list, tuple)):
        return set()
    return {_normalize_key_type_label(v) or str(v).strip().upper() for v in values if str(v).strip()}


def _horizons(value) -> Dict[str, date]:
    found = {}
    for label, text in (value.items() if isinstance(value, dict) else ()):
        try:
            found[_normalize_key_type_label(label) or str(label).upper()] = date.fromisoformat(str(text))
        except ValueError:
            continue
    return found


@dataclass
class Context:
    name: str
    profile: dict
    rules: dict
    advisories: dict
    ca: Optional[CA] = None
    today: date = field(default_factory=lambda: utc_now().date())
    cache: Dict[Callable, list] = field(default_factory=dict)

    def keys(self, rules: dict) -> set:
        """Key labels *rules* allow; empty when the rule is absent (no restriction)."""
        allowed = _label_set(rules.get('allowed_key_types'))
        for label, last in _horizons(rules.get('key_type_issue_until')).items():
            if self.today > last:
                allowed.discard(label)
        return allowed

    def key_grade(self, label: Optional[str]) -> Optional[str]:
        if not label:
            return None
        allowed, advised = self.keys(self.rules), self.keys(self.advisories)
        if allowed and label not in allowed:
            return REFUSE
        return ADVISE if advised and label not in advised else None

    def set_grade(self, rule: str, value: str, normalize=str) -> Optional[str]:
        """REFUSE / ADVISE of *value* against a list rule such as ``allowed_signature_schemes``."""
        allowed = {normalize(v) for v in self.rules.get(rule) or []}
        advised = {normalize(v) for v in self.advisories.get(rule) or []}
        if allowed and value not in allowed:
            return REFUSE
        return ADVISE if advised and value not in advised else None

    def digest_grade(self, digest) -> Optional[str]:
        name = normalize_digest(digest) or str(digest or '').strip().lower()
        if not name:
            return None
        return self.set_grade('allowed_digests', name, lambda d: normalize_digest(d) or str(d).lower())

    def horizon_grade(self, label: Optional[str], not_after) -> Optional[str]:
        if not label or not_after is None:
            return None
        end = not_after.date() if hasattr(not_after, 'date') else not_after
        if label in (limit := _horizons(self.rules.get('key_type_horizons'))) and end > limit[label]:
            return REFUSE
        if label in (soft := _horizons(self.advisories.get('key_type_horizons'))) and end > soft[label]:
            return ADVISE
        return None

    def flag_grade(self, rule: str) -> Optional[str]:
        if self.rules.get(rule) is True:
            return REFUSE
        return ADVISE if self.advisories.get(rule) is True else None


def graded(id: str, title: str, remedy: str, advisory_title: str, *, advisory_severity: str = WARNING):
    """Register a refusal detector and its advisory twin from one ``find(ctx)`` of (grade, name)."""
    def register(find):
        def pick(grade):
            def _find(ctx):
                if find not in ctx.cache:
                    ctx.cache[find] = find(ctx)
                return [name for g, name in ctx.cache[find] if g == grade]
            return _find
        DETECTORS.append(Detector(id, BLOCKER, title, remedy, pick(REFUSE)))
        DETECTORS.append(Detector(f'{id}.advisory', advisory_severity, advisory_title, remedy, pick(ADVISE)))
        return find
    return register


# --- key helpers ------------------------------------------------------------

def certificate_label(cert) -> Optional[str]:
    """Policy label of a certificate's key; EdDSA is told by its OID, unloaded."""
    oid = cert.public_key_algorithm_oid.dotted_string
    if oid in _EDDSA_OIDS:
        return key_algorithms.normalize_label(_EDDSA_OIDS[oid]) or _EDDSA_OIDS[oid].upper()
    try:
        return key_label_for_public_key(cert.public_key())
    except Exception:
        return None


def stored_label(key_algo, crt=None) -> Optional[str]:
    """Policy label of a stored key spelling ('RSA 2048', 'EC-P256'), else of the certificate."""
    label = key_algorithms.normalize_label(key_algo) if key_algo else None
    if label:
        return label
    match = re.fullmatch(r'\s*RSA[\s:_-]*(\d+)\s*', str(key_algo or ''), re.IGNORECASE)
    if match:
        return f'RSA-{int(match.group(1))}'
    cert = load_stored_certificate(crt)
    return certificate_label(cert) if cert is not None else None


def _is_edwards(label) -> bool:
    return label in ('ED25519', 'ED448')


def _signing_cas(ctx: Context) -> List[Tuple[CA, Any, str]]:
    """(CA, certificate, label) of the CAs in scope that hold a signing key."""
    cas = [ctx.ca] if ctx.ca is not None else CA.query.order_by(CA.id).all()
    found = []
    for ca in cas:
        cert = load_stored_certificate(ca.crt) if ca.has_private_key else None
        label = certificate_label(cert) if cert is not None else None
        if label:
            found.append((ca, cert, label))
    return found


def _ca_name(ca, detail=None):
    return _named(ca.descr, ca.id, detail)


# --- certificate authorities --------------------------------------------------

@graded('ca.key_type',
        'Certificate authorities whose key type the profile does not allow',
        'Create an authority with an allowed key type and move issuance to it; an authority '
        'key cannot be converted.',
        'Certificate authorities whose key type the profile does not recommend')
def _ca_key_type(ctx):
    return [(ctx.key_grade(label), _ca_name(ca, label))
            for ca, _cert, label in _signing_cas(ctx) if not _is_edwards(label)]


@graded('ca.eddsa_key',
        'Certificate authorities with an Ed25519 or Ed448 key, which the profile refuses',
        'Create an RSA or ECDSA authority and move issuance to it; an authority key cannot be converted.',
        'Certificate authorities with an Ed25519 or Ed448 key, which the profile does not recommend',
        advisory_severity=INFO)
def _ca_eddsa(ctx):
    return [(ctx.key_grade(label), _ca_name(ca, label))
            for ca, _cert, label in _signing_cas(ctx) if _is_edwards(label)]


@graded('ca.signature_scheme',
        'Certificate authorities whose signature scheme the profile does not allow',
        'Switch the authority to RSA-PSS in its settings, or create an authority with an allowed scheme.',
        'Certificate authorities whose signature scheme the profile does not recommend')
def _ca_scheme(ctx):
    found = []
    for ca, cert, label in _signing_cas(ctx):
        if _is_edwards(label):
            continue
        scheme = compliance_signer.scheme_for(cert.public_key(), ca.signature_scheme) or 'unknown'
        found.append((ctx.set_grade('allowed_signature_schemes', scheme), _ca_name(ca, scheme)))
    return found


@graded('ca.key_horizon',
        'Certificate authorities valid beyond the date the profile sets for their key type',
        'Create an authority with a stronger key or a shorter validity and move issuance to it.',
        'Certificate authorities valid beyond the date the profile recommends for their key type')
def _ca_horizon(ctx):
    found = []
    for ca, cert, label in _signing_cas(ctx):
        grade = ctx.horizon_grade(label, cert.not_valid_after_utc)
        found.append((grade, _ca_name(ca, f'{label} until {cert.not_valid_after_utc:%Y-%m-%d}')))
    return found


@graded('ca.key_protection',
        'Certificate authorities whose key is not in a hardware module, which the profile requires',
        'Create an authority whose key lives in an HSM (SoftHSM, OpenBao and software-protected cloud keys '
        'do not count) and move issuance to it; for an Azure or Google key, sync the provider keys first.',
        'Certificate authorities whose key is not in a hardware module, which the profile recommends')
def _ca_hsm(ctx):
    grade = ctx.flag_grade('require_hsm_ca_key')
    if grade is None:
        return []
    found = []
    for ca, _cert, _label in _signing_cas(ctx):
        storage = compliance_signer.storage_of_ca(ca)
        if storage != 'hsm':
            found.append((grade, _ca_name(ca, 'SoftHSM key' if storage == 'softhsm' else 'software key')))
    return found


def _ca_hsm_certification(ctx):
    accepted = ctx.rules.get('hsm_certifications')
    if not isinstance(accepted, dict) or not accepted:
        return []
    found, listed = [], ', '.join(sorted(accepted))
    for ca, _cert, _label in _signing_cas(ctx):
        if compliance_signer.storage_of_ca(ca) != 'hsm':
            continue  # ca.key_protection reports software and SoftHSM keys
        declared = compliance_signer.certification_of(ca)
        if declared is None:
            found.append(_ca_name(ca, f'no declared certification, accepted: {listed}'))
        elif declared not in accepted:
            found.append(_ca_name(ca, f'certification {declared} not accepted, accepted: {listed}'))
        elif (last := parse_rule_date(accepted[declared])) and ctx.today > last:
            found.append(_ca_name(ca, f'certification {declared} accepted until {last.isoformat()}'))
    return found


DETECTORS.append(Detector(
    'ca.hsm_certification', BLOCKER,
    'Certificate authorities whose HSM has no accepted certification declared, which the profile requires',
    'Declare an accepted certification of the HSM provider in its settings, '
    'or move the authority to a certified HSM.',
    _ca_hsm_certification))


# --- certificates -------------------------------------------------------------

@graded('certificates.key_horizon',
        'Active certificates valid beyond the date the profile sets for their key type',
        'Renew them with a shorter validity or a stronger key before the date.',
        'Active certificates valid beyond the date the profile recommends for their key type',
        advisory_severity=INFO)
def _certificate_horizon(ctx):
    if not (ctx.rules.get('key_type_horizons') or ctx.advisories.get('key_type_horizons')):
        return []
    query = Certificate.query.with_entities(
        Certificate.id, Certificate.descr, Certificate.subject_cn, Certificate.key_algo,
        Certificate.valid_to, Certificate.caref).filter(
            *_active_certificate_filter(Certificate), Certificate.caref.isnot(None))
    if ctx.ca is not None:
        query = query.filter(Certificate.caref == ctx.ca.refid)
    found = []
    for r in query.order_by(Certificate.id).all():
        crt = None
        label = stored_label(r.key_algo)
        if label is None:
            crt = Certificate.query.with_entities(Certificate.crt).filter_by(id=r.id).scalar()
            label = stored_label(None, crt)
        grade = ctx.horizon_grade(label, r.valid_to)
        if grade:
            found.append((grade, _named(r.subject_cn or r.descr, r.id, f'{label} until {r.valid_to:%Y-%m-%d}')))
    return found


# --- templates, policies, ACME profiles ------------------------------------------

def _active_templates():
    template = CertificateTemplate
    return (template.query.with_entities(template.id, template.name, template.key_type, template.digest)
            .filter(template.is_active.isnot(False)).order_by(template.id).all())


@graded('templates.key_type',
        'Active templates whose key type the profile does not allow: issuance from them is refused',
        'Change the key type of these templates to one the profile allows.',
        'Active templates whose key type the profile does not recommend')
def _templates_key(ctx):
    return [(ctx.key_grade(_normalize_key_type_label(r.key_type) or str(r.key_type).upper()),
             _named(r.name, r.id, r.key_type)) for r in _active_templates() if r.key_type]


@graded('templates.digest',
        'Active templates whose signature hash the profile does not allow: issuance from them is refused',
        'Change the hash of these templates to SHA-256, SHA-384 or SHA-512.',
        'Active templates whose signature hash the profile does not recommend')
def _templates_digest(ctx):
    return [(ctx.digest_grade(r.digest), _named(r.name, r.id, r.digest))
            for r in _active_templates() if r.digest]


def _scoped_policies(ctx):
    active = CertificatePolicy.is_active.isnot(False)
    for policy in CertificatePolicy.query.filter(active).order_by(CertificatePolicy.id).all():
        if ctx.ca is not None and policy.ca_id not in (None, ctx.ca.id):
            continue
        yield policy, policy.get_rules()


@graded('policies.key_type',
        'Active policies that allow key types the profile refuses',
        'Remove those key types from the policies: the profile applies on top of them anyway.',
        'Active policies that allow key types the profile does not recommend')
def _policies_key(ctx):
    found = []
    for policy, rules in _scoped_policies(ctx):
        entries = rules.get('allowed_key_types')
        for entry in entries if isinstance(entries, list) else []:
            label = _normalize_key_type_label(entry)
            if label and ctx.key_grade(label):
                found.append((ctx.key_grade(label), _named(policy.name, policy.id, label)))
    return found


@graded('policies.digest',
        'Active policies that allow signature hashes the profile refuses',
        'Remove those hashes from the policies: the profile applies on top of them anyway.',
        'Active policies that allow signature hashes the profile does not recommend')
def _policies_digest(ctx):
    found = []
    for policy, rules in _scoped_policies(ctx):
        entries = rules.get('allowed_digests')
        for entry in entries if isinstance(entries, list) else []:
            grade = ctx.digest_grade(entry)
            if grade:
                found.append((grade, _named(policy.name, policy.id, str(entry))))
    return found


def _unknown_key_types_only(ctx):
    found = []
    for policy, rules in _scoped_policies(ctx):
        allowed = rules.get('allowed_key_types')
        if isinstance(allowed, list) and allowed and all(_normalize_key_type_label(a) is None for a in allowed):
            found.append(_named(policy.name, policy.id, ', '.join(str(a) for a in allowed)))
    return found


DETECTORS.append(Detector(
    'policies.unknown_key_types_only', BLOCKER,
    'Active policies whose allowed key types are all unknown: issuance under them is refused',
    'Replace the entries with key types UCM knows (RSA-2048, EC-P256, ...), or remove the rule.',
    _unknown_key_types_only))


def _acme_profile_digests() -> List[Tuple[str, str]]:
    """(name, digest) of every ACME profile and of the server-wide default digest."""
    found = []
    row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
    try:
        configured = json.loads(row.value) if row and row.value else {}
    except ValueError:
        configured = {}
    default = acme_profiles.get_default_digest()
    for name, profile in sorted((configured if isinstance(configured, dict) else {}).items()):
        digest = profile.get('digest') if isinstance(profile, dict) else None
        found.append((f'profile {name}', digest or default))
    default_row = SystemConfig.query.filter_by(key=acme_profiles.DEFAULT_DIGEST_KEY).first()
    if default_row and default_row.value:
        found.append((acme_profiles.DEFAULT_DIGEST_KEY, default_row.value))
    return found


@graded('acme.digest',
        'ACME profiles or defaults that sign with a hash the profile does not allow',
        'Set SHA-256, SHA-384 or SHA-512 on the ACME profile or the ACME default digest.',
        'ACME profiles or defaults that sign with a hash the profile does not recommend')
def _acme_digest(ctx):
    return [(ctx.digest_grade(digest), f'{name}: {digest}') for name, digest in _acme_profile_digests()]


# --- signers --------------------------------------------------------------------

@graded('ocsp.responder_key',
        'Delegated OCSP responders whose key the profile does not allow',
        'Issue a new responder certificate with an allowed key and select it in the CA settings.',
        'Delegated OCSP responders whose key the profile does not recommend')
def _ocsp_responders(ctx):
    found = []
    for row, cert in _configured_certificate(RESPONDER_KEY_PREFIX, 'id'):
        if ctx.ca is not None and row.key != f'{RESPONDER_KEY_PREFIX}{ctx.ca.id}':
            continue
        label = stored_label(cert.key_algo, cert.crt)
        found.append((ctx.key_grade(label), _named(cert.descr or cert.subject_cn, cert.id, label)))
    return found


@graded('tsa.signer_key',
        'The timestamping signer has a key the profile does not allow',
        'Issue a new timestamping certificate with an EC key where the profile asks for one, '
        'and select it in the TSA settings.',
        'The timestamping signer has a key the profile does not recommend')
def _tsa_signer(ctx):
    if not tsa_is_enabled():
        return []
    found = []
    for _row, cert in _configured_certificate('tsa_signer_cert_refid', 'refid'):
        if ctx.ca is not None and cert.caref != ctx.ca.refid:
            continue
        label = stored_label(cert.key_algo, cert.crt)
        grades = [(ctx.key_grade(label), label)]
        for rules, grade in ((ctx.rules, REFUSE), (ctx.advisories, ADVISE)):
            wanted = _label_set(rules.get('tsa_signer_key_types'))
            if wanted and label not in wanted:
                grades.append((grade, f'{label}, the profile asks for {", ".join(sorted(wanted))}'))
        worst = REFUSE if any(g == REFUSE for g, _ in grades) else ADVISE
        detail = next((d for g, d in grades if g == worst and d != label), label)
        if any(g for g, _ in grades):
            found.append((worst, _named(cert.descr or cert.subject_cn, cert.id, detail)))
    return found


# --- run --------------------------------------------------------------------

def build_context(profile: str, ca_id: Optional[int] = None) -> Context:
    """ValueError for a profile that is not listed, LookupError for a CA that does not exist."""
    rules = compliance_profiles.profile_policy(profile).get_rules()
    ca = None
    if ca_id is not None:
        ca = CA.query.filter_by(id=ca_id).first()
        if ca is None:
            raise LookupError(f'CA {ca_id} not found')
    advisories = rules.pop('advisories', None)
    return Context(profile, compliance_profiles.PROFILES[profile], rules,
                   advisories if isinstance(advisories, dict) else {}, ca)


def run(profile: str, ca_id: Optional[int] = None, detectors: Optional[Iterable[Detector]] = None) -> dict:
    """Findings of *profile* on this instance (on CA *ca_id* alone when given), blockers first."""
    ctx = build_context(profile, ca_id)
    result = run_detectors(DETECTORS if detectors is None else detectors, ctx, label='Compliance preflight')
    return {'profile': {'name': profile, 'title': ctx.profile['title'], 'reference': ctx.profile['reference']},
            'ca_id': ca_id,
            'ready': not result['summary'][BLOCKER] and not result['errors'],
            'summary': result['summary'], 'findings': result['findings'],
            'errors': result['errors'], 'checked': result['checked']}
