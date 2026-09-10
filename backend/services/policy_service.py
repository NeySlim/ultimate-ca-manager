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

logger = logging.getLogger(__name__)


class PolicyViolation(ValueError):
    """A request breaks a policy Rule (#335); the message names the rule."""


class PolicyEvaluationService:
    """Evaluates certificate requests against policies"""

    @staticmethod
    def check_approval_required(ca_id: int, template_id: int = None,
                                cn: str = None, san_list: list = None) -> Optional[CertificatePolicy]:
        """
        Check if any active policy requires approval for this CA/template/request.
        
        Also evaluates policy rules against the actual request:
        - san_restrictions.dns_pattern: only matches if CN or a SAN matches the pattern
        
        Returns the matching policy if approval is required, None otherwise.
        Policies are checked by priority (lower number = higher priority).
        """
        query = CertificatePolicy.query.filter_by(
            is_active=True,
            requires_approval=True,
            policy_type='issuance'
        ).order_by(CertificatePolicy.priority.asc())

        policies = query.all()
        
        for policy in policies:
            # Check CA scope
            if policy.ca_id is not None and policy.ca_id != ca_id:
                continue
            # Check template scope
            if policy.template_id is not None and policy.template_id != template_id:
                continue
            # Check rules-based filtering (e.g. wildcard pattern)
            if not PolicyEvaluationService._matches_rules(policy, cn, san_list):
                continue
            return policy
        
        return None

    @staticmethod
    def applicable_policies(ca_id: int, template_id: int = None,
                            cn: str = None, san_list: list = None) -> list:
        """Active issuance policies whose scope covers this request (#335).

        Same CA / template / dns_pattern scoping as ``check_approval_required``
        but regardless of ``requires_approval``: a policy's Rules bind every
        request in its scope, not only the ones routed through approval.
        Ordered by priority (lower number first).
        """
        query = CertificatePolicy.query.filter_by(
            is_active=True, policy_type='issuance'
        ).order_by(CertificatePolicy.priority.asc())
        matching = []
        for policy in query.all():
            if policy.ca_id is not None and policy.ca_id != ca_id:
                continue
            if policy.template_id is not None and policy.template_id != template_id:
                continue
            if not PolicyEvaluationService._matches_rules(policy, cn, san_list):
                continue
            matching.append(policy)
        return matching

    @staticmethod
    def enforce_rules(policies: list, *, key_type=None, dns_name_count=None,
                      validity_days=None):
        """Apply the Rules of *policies* to a request (#335).

        Returns ``(violations, validity_days)``: the human-readable reasons
        the request must be refused (``allowed_key_types`` not matched,
        ``san_restrictions.max_dns_names`` exceeded), and the validity capped
        by the lowest ``max_validity_days`` among the policies. Parameters
        left ``None`` are not checked. Key types compare in the template
        label form (RSA-2048, EC-P256), whatever spelling the request used.
        """
        from services.template_service import _normalize_key_type_label

        violations = []
        effective_validity = validity_days
        for policy in policies:
            rules = policy.get_rules() or {}

            allowed = rules.get('allowed_key_types')
            if key_type is not None and isinstance(allowed, list) and allowed:
                allowed_labels = {_normalize_key_type_label(a) for a in allowed} - {None}
                requested = _normalize_key_type_label(key_type)
                if allowed_labels and requested not in allowed_labels:
                    violations.append(
                        f'Key type {requested or key_type} is not allowed by policy '
                        f'"{policy.name}" (allowed: {", ".join(sorted(allowed_labels))})'
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
        return violations, effective_validity

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
        requester_id: int,
        comment: str = None
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
            request_type='certificate',
            policy_id=policy.id,
            requester_id=requester_id,
            requester_comment=comment or f"Certificate request: {request_data.get('cn', 'unknown')}",
            request_data=json.dumps(request_data),
            required_approvals=policy.min_approvers or 1,
            expires_at=utc_now() + timedelta(days=7),
        )
        db.session.add(approval)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/policy_service.py:118: {_commit_err}", exc_info=True)
            raise
        
        logger.info(
            f"Approval request #{approval.id} created for CN={request_data.get('cn')} "
            f"by user #{requester_id}, policy={policy.name}"
        )
        
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
