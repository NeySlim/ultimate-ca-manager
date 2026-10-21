"""
Policy Evaluation Service
Evaluates certificate requests against active policies to determine
if approval is required before issuance.
"""
import json
import logging
from typing import Optional, Tuple
from models import db
from models.policy import CertificatePolicy, ApprovalRequest
from datetime import timedelta
from utils.datetime_utils import utc_now
from utils import key_algorithms
import copy
import compliance_profiles
import fips_mode

logger = logging.getLogger(__name__)

# A renewal an operator performs re-issues the certificate: issuance
# policies have bound it since 2.228, renewal policies bind it too. The
# scheduler is held by renewal policies only.
RENEWAL_OPERATIONS = ('issuance', 'renewal')

# A request waits this long for a decision (a stored request without an
# expiry, from a restored backup, is given the same lifetime)
APPROVAL_REQUEST_LIFETIME = timedelta(days=7)


_REQUEST_LABELS = {'renewal': 'Renewal', 'revocation': 'Revocation',
                   'ca_revocation': 'CA revocation'}


class PolicyViolation(ValueError):
    """A request breaks a policy Rule (#335); the message names the rule."""


# Signature hashes a policy can allow, weakest first
POLICY_DIGESTS = ('sha256', 'sha384', 'sha512')


def normalize_digest(value):
    """'sha384', 'SHA-384' or a cryptography hash -> 'sha384'; None if not a policy digest."""
    name = getattr(value, 'name', value)
    name = str(name or '').strip().lower().replace('-', '')
    return name if name in POLICY_DIGESTS else None


def _rule_digests(rules):
    """The ``allowed_digests`` of one policy's rules, weakest first ([] when unset)."""
    allowed = rules.get('allowed_digests')
    if not isinstance(allowed, list):
        return []
    names = {normalize_digest(d) for d in allowed} - {None}
    return [d for d in POLICY_DIGESTS if d in names]


class SystemPolicy:
    """A policy that lives in code, not in the database: global, read only."""
    id = None
    ca_id = None
    template_id = None
    priority = 0
    requires_approval = False

    def __init__(self, name, rules, kind=None):
        self.name = name
        self._rules = rules
        self.kind = kind  # 'profile' for a compliance profile

    def get_rules(self):
        return copy.deepcopy(self._rules)


def fips_policy():
    """The policy FIPS mode puts ahead of all others, None outside FIPS mode."""
    if not fips_mode.enabled():
        return None
    return SystemPolicy('FIPS mode', {
        'allowed_key_types': list(key_algorithms.fips_approved_labels()),
        'allowed_digests': list(POLICY_DIGESTS),
    })


def with_system_policies(policies, ca_id=None):
    """*policies* headed by the system policies they do not already hold: FIPS
    mode, then the compliance profile of CA *ca_id* (one id or several)."""
    policies = list(policies or [])
    system = []
    if not any(isinstance(p, SystemPolicy) and p.kind != 'profile' for p in policies):
        system.append(fips_policy())
    if not any(isinstance(p, SystemPolicy) and p.kind == 'profile' for p in policies):
        ids = ca_id if isinstance(ca_id, (tuple, list)) else (ca_id,)
        for name in dict.fromkeys(compliance_profiles.profile_of_ca(i) for i in ids):
            if name:
                system.append(compliance_profiles.profile_policy(name))
    return [p for p in system if p is not None] + policies


def key_label_for_public_key(public_key):
    """Policy label of a public key (RSA-2048, EC-P256, ED25519), whatever issued it.

    An algorithm outside the vocabulary gets a label no policy lists, so a
    non-empty ``allowed_key_types`` refuses it rather than skipping the check.
    """
    label = key_algorithms.label_for_public_key(public_key)
    if label:
        return label
    family = key_algorithms.family_for_public_key(public_key)
    if family == 'RSA':
        return f'RSA-{public_key.key_size}'
    if family == 'EC':
        return f'EC-{public_key.curve.name}'
    return type(public_key).__name__


# Rule keys nothing ever enforced: dropped on save and by migration 102.
DEAD_RULE_KEYS = ('required_extensions', 'forbidden_extensions')
DEAD_SAN_RULE_KEYS = ('require_approval_for_external',)


def strip_dead_rules(rules):
    """A copy of *rules* without the keys no evaluation reads."""
    rules = {k: v for k, v in rules.items() if k not in DEAD_RULE_KEYS}
    san = rules.get('san_restrictions')
    if isinstance(san, dict):
        rules['san_restrictions'] = {k: v for k, v in san.items() if k not in DEAD_SAN_RULE_KEYS}
    return rules


class PolicyEvaluationService:
    """Evaluates certificate requests against policies"""

    @staticmethod
    def _in_scope(operation, ca_id, template_id, cn, san_list, *, approval: bool) -> list:
        """Active policies governing *operation* (a name or a tuple of them)
        whose CA (*ca_id*, or any of a tuple), template and name pattern
        cover the request, by priority (lower number first)."""
        operations = (operation,) if isinstance(operation, str) else tuple(operation)
        ca_ids = tuple(ca_id) if isinstance(ca_id, (tuple, list)) else (ca_id,)
        query = CertificatePolicy.query.filter_by(is_active=True)
        if approval:
            query = query.filter_by(requires_approval=True)
        matching = []
        for policy in query.order_by(CertificatePolicy.priority.asc()).all():
            if not any(policy.applies_to(op) for op in operations):
                continue
            if policy.ca_id is not None and policy.ca_id not in ca_ids:
                continue
            if policy.template_id is not None and policy.template_id != template_id:
                continue
            if not PolicyEvaluationService._matches_rules(policy, cn, san_list):
                continue
            matching.append(policy)
        return matching

    @staticmethod
    def check_approval_required(ca_id: int, template_id: int = None,
                                cn: str = None, san_list: list = None,
                                operation='issuance') -> Optional[CertificatePolicy]:
        """The first active policy governing *operation* that requires
        approval for this CA / template / name (dns_pattern), None otherwise.
        For a revocation or renewal, *ca_id* is the issuing CA."""
        matching = PolicyEvaluationService._in_scope(
            operation, ca_id, template_id, cn, san_list, approval=True)
        return matching[0] if matching else None

    @staticmethod
    def applicable_policies(ca_id: int, template_id: int = None,
                            cn: str = None, san_list: list = None,
                            operation='issuance') -> list:
        """Active policies governing *operation* whose scope covers this request (#335).

        Same CA / template / dns_pattern scoping as ``check_approval_required``
        but regardless of ``requires_approval``: a policy's Rules bind every
        request in its scope, not only the ones routed through approval.
        Ordered by priority (lower number first), the system policies first.
        """
        return with_system_policies(PolicyEvaluationService._in_scope(
            operation, ca_id, template_id, cn, san_list, approval=False), ca_id)

    @staticmethod
    def enforce_rules(policies: list, *, key_type=None, dns_name_count=None,
                      validity_days=None, digest=None, context=None, notify=True,
                      ca_id=None):
        """Apply the Rules of *policies* to a request (#335).

        Returns ``(violations, validity_days, capped_by)``: the
        human-readable reasons the request must be refused
        (``allowed_key_types`` not matched, ``san_restrictions.max_dns_names``
        exceeded), the validity capped by the lowest ``max_validity_days``
        among the policies, and the name of the policy that set that cap, or
        ``None`` when nothing was shortened. Parameters left ``None`` are not
        checked. The system policies (FIPS mode, and the compliance profile of
        *ca_id* when given) apply whatever the list.
        Key types compare in the template label form (RSA-2048,
        EC-P256), whatever spelling the request used; *digest* is the hash the
        signature is computed with (None for Ed25519/Ed448 signers).

        The caller names the capping policy in a notice: a validity silently
        shortened is the one outcome the requester cannot see. A policy whose
        rules refuse the request notifies its recipients (*context*: operation,
        subject, ca, requester) unless *notify* is False.
        """
        from services.template_service import _normalize_key_type_label

        violations = []
        effective_validity = validity_days
        capped_by = None
        by_policy = {}
        checked = with_system_policies(policies, ca_id)
        for policy in checked:
            rules = policy.get_rules() or {}
            before = len(violations)

            allowed = rules.get('allowed_key_types')
            if key_type is not None and isinstance(allowed, list) and allowed:
                allowed_labels = {_normalize_key_type_label(a) for a in allowed} - {None}
                requested = _normalize_key_type_label(key_type)
                if allowed_labels and requested not in allowed_labels:
                    violations.append(
                        f'Key type {requested or key_type} is not allowed by policy '
                        f'"{policy.name}" (allowed: {", ".join(sorted(allowed_labels))})'
                    )

            allowed_digests = _rule_digests(rules)
            requested_digest = normalize_digest(digest)
            if (digest is not None and allowed_digests
                    and requested_digest not in allowed_digests):
                violations.append(
                    f'Signature hash {(requested_digest or str(digest)).upper()} is not '
                    f'allowed by policy "{policy.name}" '
                    f'(allowed: {", ".join(d.upper() for d in allowed_digests)})'
                )

            san_rules = rules.get('san_restrictions') or {}
            max_dns = san_rules.get('max_dns_names') if isinstance(san_rules, dict) else None
            if (dns_name_count is not None and isinstance(max_dns, int)
                    and not isinstance(max_dns, bool) and max_dns > 0
                    and dns_name_count > max_dns):
                violations.append(
                    f'{dns_name_count} DNS names exceed the {max_dns} allowed by policy '
                    f'"{policy.name}"'
                )

            max_validity = rules.get('max_validity_days')
            if (effective_validity is not None and isinstance(max_validity, int)
                    and not isinstance(max_validity, bool) and max_validity > 0
                    and effective_validity > max_validity):
                effective_validity = max_validity
                capped_by = policy.name
            if len(violations) > before:
                by_policy[id(policy)] = violations[before:]
        if by_policy and notify:
            try:
                from services import policy_notifications
                policy_notifications.violation(checked, by_policy, context)
            except Exception as e:  # never turns a refusal into a 500
                logger.warning("Policy violation notification failed: %s", e)
        return violations, effective_validity, capped_by

    @staticmethod
    def allowed_digests(policies: list):
        """Digests every policy with an ``allowed_digests`` rule accepts, weakest
        first; None when no policy restricts the digest."""
        allowed = None
        for policy in policies:
            names = _rule_digests(policy.get_rules() or {})
            if names:
                allowed = names if allowed is None else [d for d in allowed if d in names]
        return allowed

    @staticmethod
    def choose_digest(policies: list, default='sha256'):
        """The digest for a path whose hash nobody chose: *default* when the
        policies accept it, else the weakest one they all accept. An explicit
        choice (template, ACME profile, CA form) is checked, never replaced."""
        default = normalize_digest(default) or 'sha256'
        allowed = PolicyEvaluationService.allowed_digests(policies)
        if not allowed or default in allowed:
            return default
        return allowed[0]

    @staticmethod
    def checked_signing_hash(policies: list, ca_key, digest=None, *, explicit=True,
                             key_type=None, context=None):
        """``(hash for builder.sign(), violations)``. An implicit *digest* yields
        to the weakest one the policies allow; the hash the key really signs
        with (HSM-bound, None for Ed25519/Ed448) is then checked with *key_type*."""
        from cryptography.hazmat.primitives import hashes
        from services.trust_store.constants import hash_algorithm
        from utils.signing_hash import signing_hash_for
        name = str(digest or 'sha256').strip().lower()
        if not explicit:
            name = PolicyEvaluationService.choose_digest(policies, name)
        try:
            requested = hash_algorithm(name)
        except ValueError as e:
            return hashes.SHA256(), [str(e)]
        sign_hash = signing_hash_for(ca_key, requested)
        violations, _, _ = PolicyEvaluationService.enforce_rules(
            policies, key_type=key_type,
            digest=sign_hash.name if sign_hash is not None else None, context=context)
        return sign_hash, violations

    @staticmethod
    def algorithm_violations(ca_id, template_id=None, *, cn=None, san_list=None,
                             public_key=None, key_type=None, digest=None):
        """Key-type and digest rules alone, for the protocol and internal paths
        (ACME, SCEP, EST, WSTEP, CA creation, TSA, OCSP responder)."""
        if public_key is not None:
            key_type = key_label_for_public_key(public_key)
        policies = PolicyEvaluationService.applicable_policies(ca_id, template_id, cn, san_list)
        violations, _, _ = PolicyEvaluationService.enforce_rules(
            policies, key_type=key_type, digest=digest)
        return violations

    @staticmethod
    def effective_algorithms(ca_id, template_id=None):
        """``(allowed_key_types, allowed_digests)`` every name in this scope must
        meet, each None when unrestricted. Policies narrowed by a DNS pattern
        bind only some names: without a name they do not match, and are left to
        the issuance-time check."""
        from services.template_service import _normalize_key_type_label
        policies = PolicyEvaluationService.applicable_policies(ca_id, template_id)
        key_types = None
        for policy in policies:
            allowed = (policy.get_rules() or {}).get('allowed_key_types')
            if isinstance(allowed, list) and allowed:
                labels = {_normalize_key_type_label(a) for a in allowed} - {None}
                if not labels:
                    continue  # unknown labels only: enforce_rules skips it too
                key_types = labels if key_types is None else key_types & labels
        if key_types is not None:
            key_types = sorted(key_types)
        return key_types, PolicyEvaluationService.allowed_digests(policies)

    @staticmethod
    def _matches_rules(policy: CertificatePolicy, cn: str = None, san_list: list = None) -> bool:
        """
        Check if the request matches this policy's rules.
        If the policy has narrowing rules (e.g. dns_pattern), the request must match them.
        If the policy has no narrowing rules, it matches everything in its scope.
        """
        rules = policy.get_rules() if hasattr(policy, 'get_rules') else {}
        san_restrictions = rules.get('san_restrictions', {})
        dns_pattern = san_restrictions.get('dns_pattern', '')
        
        if not dns_pattern:
            return True
        
        # Collect all names to check
        names = []
        if cn:
            names.append(cn)
        if san_list:
            names.extend(san_list)
        
        if not names:
            return False
        
        # Check if any name matches the pattern
        for name in names:
            name = str(name)
            if dns_pattern == '*.':
                # Wildcard policy: matches if name starts with *.
                if name.startswith('*.'):
                    return True
            elif name.startswith(dns_pattern) or name.endswith(dns_pattern):
                return True
        
        return False

    @staticmethod
    def create_approval_request(
        policy: CertificatePolicy,
        request_data: dict,
        requester_id: Optional[int],
        comment: str = None,
        request_type: str = 'certificate',
    ) -> ApprovalRequest:
        """
        Create an approval request for deferred certificate issuance.
        
        Args:
            policy: The policy that requires approval
            request_data: The full certificate request data (stored as JSON)
            requester_id: ID of the requesting user
            comment: Optional requester comment
            
        Returns:
            The created ApprovalRequest
        """
        approval = ApprovalRequest(
            request_type=request_type,
            policy_id=policy.id,
            requester_id=requester_id,
            requester_comment=comment or (
                f"{_REQUEST_LABELS.get(request_type, 'Certificate')} request: "
                f"{request_data.get('cn', 'unknown')}"),
            request_data=json.dumps(request_data),
            required_approvals=policy.min_approvers or 1,
            expires_at=utc_now() + APPROVAL_REQUEST_LIFETIME,
        )
        db.session.add(approval)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Failed to queue approval request: {_commit_err}", exc_info=True)
            raise
        
        logger.info(
            f"Approval request #{approval.id} created for CN={request_data.get('cn')} "
            f"by user #{requester_id}, policy={policy.name}"
        )
        try:
            from services import policy_notifications
            policy_notifications.approval_queued(policy, approval, request_data)
        except Exception as e:  # the request is queued whatever happens to the e-mail
            logger.warning("Approval notification failed: %s", e)
        
        return approval

    @staticmethod
    def get_request_data(approval: ApprovalRequest) -> Optional[dict]:
        """Get the stored certificate request data from an approval"""
        if not approval.request_data:
            return None
        try:
            return json.loads(approval.request_data)
        except Exception:
            return None
