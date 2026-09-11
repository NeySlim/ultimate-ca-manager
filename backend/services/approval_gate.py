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

from models import db
from models.policy import ApprovalRequest, CertificatePolicy
from services.policy_service import APPROVAL_REQUEST_LIFETIME, PolicyEvaluationService

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


def request_deadline(approval):
    """When the request expires (naive UTC): its ``expires_at``, else the
    standard lifetime from its creation; None when neither is known."""
    from utils.datetime_utils import to_naive_utc
    if approval.expires_at:
        return to_naive_utc(approval.expires_at)
    if approval.created_at:
        return to_naive_utc(approval.created_at) + APPROVAL_REQUEST_LIFETIME
    return None


def approval_is_expired(approval) -> bool:
    """True when the request is past its deadline."""
    from utils.datetime_utils import utc_now
    deadline = request_deadline(approval)
    return deadline is not None and deadline < utc_now().replace(tzinfo=None)


def _pending_query(request_type: str, key: str, lock: bool = False):
    """The pending requests of ``request_type`` whose stored request carries
    ``key`` (SQL prefilter on the JSON text; the caller parses it). With
    ``lock`` the rows are taken FOR UPDATE SKIP LOCKED on PostgreSQL, so a
    request an approver is acting on at that moment is left to them (its
    votes are never overwritten); SQLite serialises writers and ignores the
    clause."""
    query = ApprovalRequest.query.filter_by(status='pending', request_type=request_type).filter(
        ApprovalRequest.request_data.like(f'%"{key}"%'))
    if lock:
        query = query.with_for_update(skip_locked=True)
    return query


def _named_target(approval, key):
    import json
    try:
        rd = json.loads(approval.request_data or '{}')
    except Exception:
        return None
    if not isinstance(rd, dict) or key not in rd:
        return None
    return str(rd.get(key))


def pending_requests_naming(request_type: str, key: str, target_id, *, lock: bool = False) -> list:
    """Pending approval requests of ``request_type`` whose stored request
    names ``target_id`` under ``key`` (``csr_id`` or ``certificate_id``);
    with ``lock`` they are taken for update (see ``_pending_query``)."""
    if target_id is None:
        return []
    return [approval for approval in _pending_query(request_type, key, lock=lock).all()
            if _named_target(approval, key) == str(target_id)]


def pending_target_ids(request_type: str, key: str) -> dict:
    """The targets (as strings) named by the pending requests of
    ``request_type`` still awaiting a decision, each with the deadline of
    its request (naive UTC, None when unknown), for callers that must
    leave them alone (the renewal scheduler does not override a renewal
    awaiting a human decision). A request past its deadline holds nothing
    back, whether or not it has been marked expired yet."""
    targets = {}
    for approval in _pending_query(request_type, key).all():
        if approval_is_expired(approval):
            continue
        target = _named_target(approval, key)
        if target is not None:
            targets[target] = request_deadline(approval)
    return targets


def expire_stale_requests(commit: bool = True) -> int:
    """Close the pending requests past their deadline as ``expired``. The
    approve and reject routes did so one request at a time when it was
    acted on; the pending list, the counters and the hourly task do it for
    all of them, so they neither accumulate nor pass for pending. Nothing
    is written when there is nothing to expire (the list is a read); a
    request an approver is acting on at that moment is left to them."""
    from sqlalchemy import and_, or_
    from utils.datetime_utils import utc_now
    now = utc_now().replace(tzinfo=None)
    stale_ids = [row[0] for row in db.session.query(ApprovalRequest.id).filter(
        ApprovalRequest.status == 'pending',
        or_(ApprovalRequest.expires_at < now,
            and_(ApprovalRequest.expires_at.is_(None),
                 ApprovalRequest.created_at < now - APPROVAL_REQUEST_LIFETIME)),
    ).with_for_update(skip_locked=True).all()]
    if not stale_ids:
        return 0
    count = db.session.query(ApprovalRequest).filter(
        ApprovalRequest.id.in_(stale_ids), ApprovalRequest.status == 'pending',
    ).update({ApprovalRequest.status: 'expired', ApprovalRequest.resolved_at: now},
             synchronize_session='fetch')
    if count and commit:
        from utils.db_transaction import safe_commit
        ok, _err = safe_commit(logger, "Failed to expire stale approval requests")
        if not ok:
            return 0
    if count:
        logger.info("Expired %s stale approval request(s)", count)
    return count


def scheduled_expiry():
    """Scheduler entry point."""
    return expire_stale_requests()


def resolve_moot_requests(request_type: str, key: str, target_id, *, outcome: str,
                          username: str, user_id=None, certificate_id=None,
                          reason: str, commit: bool = True) -> list:
    """Resolve the pending requests a direct action made moot.

    ``outcome`` ``'approved'``: the action itself was the approval (an
    administrator signed the request or renewed the certificate directly,
    or approved another request for the same target); the request is closed
    as approved, ``username`` recorded as its approver, and linked to the
    certificate when one is given. ``'rejected'``: the target is gone or
    revoked; the request is closed as rejected with the reason. A request
    past its expiry is closed as expired instead, without a vote. Returns
    the requests approved or rejected; the caller commits when ``commit``
    is False (the resolution then rides the caller's own transaction)."""
    from utils.datetime_utils import utc_now
    resolved = []
    touched = 0
    for approval in pending_requests_naming(request_type, key, target_id, lock=True):
        touched += 1
        if approval_is_expired(approval):
            # Past its expiry and not yet noticed: it expired, the action
            # neither approved nor rejected it
            approval.status = 'expired'
            approval.resolved_at = utc_now()
            logger.info("Approval request #%s expired before %s", approval.id, reason.lower())
            continue
        approval.add_approval(user_id=user_id, username=username,
                              action='approve' if outcome == 'approved' else 'reject',
                              comment=reason)
        approval.status = outcome
        approval.resolved_at = utc_now()
        if outcome == 'approved' and certificate_id is not None:
            approval.certificate_id = certificate_id
        resolved.append(approval)
        logger.info("Approval request #%s resolved as %s: %s", approval.id, outcome, reason)
    if touched and commit:
        from utils.db_transaction import safe_commit
        safe_commit(logger, "Failed to resolve superseded approval requests")
    return resolved
