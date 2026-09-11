"""The approval gate shared by every operator issuance path.

An issuance policy with ``requires_approval`` used to be consulted by the
issue form only: an operator signed a stored request, in bulk or one by one,
or renewed a certificate, without any approval. The gate below evaluates the
same policies (CA, template, name pattern scoping) for those paths and
queues an ``ApprovalRequest`` typed after the operation, which the approval
route then performs.
"""

import base64
import logging
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID, NameOID

from models.policy import ApprovalRequest, CertificatePolicy
from services.policy_service import PolicyEvaluationService

logger = logging.getLogger(__name__)


def certificate_identity(pem_b64: str) -> Tuple[Optional[str], list]:
    """``(cn, dns_names)`` of a stored certificate or request (base64 PEM)."""
    raw = base64.b64decode(pem_b64)
    try:
        obj = x509.load_pem_x509_certificate(raw, default_backend())
    except ValueError:
        obj = x509.load_pem_x509_csr(raw, default_backend())
    cn_attrs = obj.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = cn_attrs[0].value if cn_attrs else None
    try:
        dns = list(obj.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        dns = []
    return cn, dns


def queue_if_approval_required(user, *, ca_id, template_id, cn, san_list,
                               request_type: str, request_data: dict,
                               comment: Optional[str] = None
                               ) -> Tuple[Optional[CertificatePolicy], Optional[ApprovalRequest]]:
    """``(policy, approval)`` when a policy requires approval for this
    request (queued), else ``(None, None)``. Administrators bypass, as on
    the issue form. Any evaluation error propagates: the caller must fail
    closed (never issue on a policy it could not evaluate)."""
    if getattr(user, 'role', None) == 'admin':
        return None, None
    policy = PolicyEvaluationService.check_approval_required(
        ca_id=ca_id, template_id=template_id, cn=cn, san_list=list(san_list or []))
    if policy is None:
        return None, None
    approval = PolicyEvaluationService.create_approval_request(
        policy=policy, request_data=request_data, requester_id=user.id,
        comment=comment, request_type=request_type)
    return policy, approval


def approval_payload(policy: CertificatePolicy, approval: ApprovalRequest) -> dict:
    """The response body the issue form returns when a request is queued."""
    return {
        'approval_required': True,
        'approval_id': approval.id,
        'policy_name': policy.name,
        'status': 'pending_approval',
        'message': f'Certificate request requires approval per policy "{policy.name}"',
    }


def pending_requests_naming(request_type: str, key: str, target_id) -> list:
    """Pending approval requests of ``request_type`` whose stored request
    names ``target_id`` under ``key`` (``csr_id`` or ``certificate_id``)."""
    import json
    if target_id is None:
        return []
    found = []
    for approval in ApprovalRequest.query.filter_by(status='pending', request_type=request_type).all():
        try:
            rd = json.loads(approval.request_data or '{}')
        except Exception:
            continue
        if isinstance(rd, dict) and key in rd and str(rd.get(key)) == str(target_id):
            found.append(approval)
    return found


def resolve_moot_requests(request_type: str, key: str, target_id, *, outcome: str,
                          username: str, user_id=None, certificate_id=None,
                          reason: str, commit: bool = True) -> list:
    """Resolve the pending requests a direct action made moot.

    ``outcome`` ``'approved'``: the action itself was the approval (an
    administrator signed the request or renewed the certificate directly,
    or approved another request for the same target); the request is closed
    as approved, ``username`` recorded as its approver, and linked to the
    certificate when one is given. ``'rejected'``: the target is gone or
    revoked; the request is closed as rejected with the reason. Returns the
    requests resolved; the caller commits when ``commit`` is False (the
    resolution then rides the caller's own transaction)."""
    from utils.datetime_utils import utc_now
    resolved = []
    for approval in pending_requests_naming(request_type, key, target_id):
        approval.add_approval(user_id=user_id, username=username,
                              action='approve' if outcome == 'approved' else 'reject',
                              comment=reason)
        approval.status = outcome
        approval.resolved_at = utc_now()
        if outcome == 'approved' and certificate_id is not None:
            approval.certificate_id = certificate_id
        resolved.append(approval)
        logger.info("Approval request #%s resolved as %s: %s", approval.id, outcome, reason)
    if resolved and commit:
        from utils.db_transaction import safe_commit
        safe_commit(logger, "Failed to resolve superseded approval requests")
    return resolved
