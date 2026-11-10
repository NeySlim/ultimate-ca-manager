"""The approval gate of the enrolment protocols (ACME, EST, SCEP, WSTEP).

A policy with ``requires_approval`` whose scope covers a protocol request
holds it in the approval queue: one ``ApprovalRequest`` per protocol request,
typed after the protocol and found again by its ``protocol_ref``. Each
protocol registers how an approved request is issued and how a closed one
reaches its own state (order, SCEP request), so the approval routes never
learn the protocols' internals.
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID

from models import db
from models.policy import ApprovalRequest
from utils.datetime_utils import utc_isoformat, utc_now

logger = logging.getLogger(__name__)

PROTOCOL_REQUEST_TYPES = {
    'acme': 'acme_order',
    'est': 'est_enroll',
    'scep': 'scep_request',
    'wstep': 'wstep_request',
}
REQUEST_TYPE_PROTOCOLS = {v: k for k, v in PROTOCOL_REQUEST_TYPES.items()}
_LABELS = {'acme': 'ACME', 'est': 'EST', 'scep': 'SCEP', 'wstep': 'WSTEP'}

# The statuses a protocol client is answered from; expired and cancelled
# requests are forgotten (the client's next request starts a new one)
_ANSWERING = ('pending', 'approved', 'rejected')


class ApprovalGateUnavailable(Exception):
    """The policies could not be evaluated: the caller must not issue."""


class ProtocolRequestGone(ValueError):
    """The protocol request an approval names can no longer be issued
    (order finalized or invalidated, SCEP request closed elsewhere).
    *refusal* is what the protocol tells its client once the request is closed."""

    def __init__(self, message, refusal: dict = None):
        super().__init__(message)
        self.refusal = refusal


@dataclass
class _Handler:
    issue: Callable  # (approval, data) -> dict with 'id' (certificate id, None when deferred)
    closed: Optional[Callable] = None  # (approval, data) after a rejection or an expiry
    gone: Optional[Callable] = None  # (approval, data) -> reason or None


_HANDLERS = {}


def register(request_type: str, issue: Callable, closed: Callable = None, gone: Callable = None):
    """Declare how a protocol issues its approved requests and follows closed ones."""
    _HANDLERS[request_type] = _Handler(issue=issue, closed=closed, gone=gone)


def _handler(request_type):
    if request_type not in REQUEST_TYPE_PROTOCOLS:
        return None
    if request_type not in _HANDLERS:
        # Each protocol registers on import; the approval route may run first
        _import_protocols()
    return _HANDLERS.get(request_type)


# The modules that register a protocol's handlers
_PROTOCOL_MODULES = ('services.acme.approval', 'services.est_approval', 'services.scep.approval',
                     'services.wstep.approval')


def _import_protocols():
    import importlib
    for name in _PROTOCOL_MODULES:
        importlib.import_module(name)


def is_protocol_request(approval) -> bool:
    return getattr(approval, 'request_type', None) in REQUEST_TYPE_PROTOCOLS


def make_ref(*parts) -> str:
    """A stable identifier of a protocol request from its parts."""
    return hashlib.sha256('\x1f'.join(str(p) for p in parts).encode()).hexdigest()


def csr_ref(csr) -> str:
    """SHA-256 of the request's DER, the part of a ref that names the CSR."""
    return hashlib.sha256(csr.public_bytes(serialization.Encoding.DER)).hexdigest()


def csr_names(csr):
    """``(cn, dns_names)`` a policy scopes a request by."""
    from utils.csr_extensions import csr_extensions
    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn = str(cn_attrs[0].value) if cn_attrs else None
    try:
        dns = list(csr_extensions(csr).get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
    except Exception:
        dns = []
    return cn, dns


def request_data(approval) -> dict:
    try:
        data = json.loads(approval.request_data or '{}')
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def find_protocol_request(protocol: str, protocol_ref: str) -> Optional[ApprovalRequest]:
    """The latest request of *protocol* for *protocol_ref* the client is
    still to hear about (pending, or decided and not yet delivered); one
    past its deadline is closed as expired on the way (and forgotten)."""
    request_type = PROTOCOL_REQUEST_TYPES[protocol]
    candidates = ApprovalRequest.query.filter(
        ApprovalRequest.request_type == request_type,
        ApprovalRequest.status.in_(_ANSWERING),
        ApprovalRequest.request_data.like(f'%"{protocol_ref}"%'),
    ).order_by(ApprovalRequest.id.desc()).all()
    for approval in candidates:
        data = request_data(approval)
        if data.get('protocol_ref') != protocol_ref or data.get('delivered_at'):
            continue
        if approval.status == 'pending' and expire_if_stale(approval):
            return None
        return approval
    return None


def expire_if_stale(approval) -> bool:
    """Close *approval* as expired when it is pending past its deadline,
    and let its protocol follow; True when it did."""
    from services.approval_gate import approval_is_expired
    if approval.status != 'pending' or not approval_is_expired(approval):
        return False
    approval.status = 'expired'
    approval.resolved_at = utc_now()
    db.session.commit()
    propagate_closed([approval])
    return True


def gate_protocol_issuance(protocol: str, *, ca, template_id=None, cn=None, san_list=(),
                           csr_pem: str, identity: str, protocol_ref: str,
                           renewal: bool = False, extra: dict = None) -> Optional[ApprovalRequest]:
    """``None`` when the request may be issued now, else the
    ``ApprovalRequest`` holding it: the one already open for *protocol_ref*
    (pending, or decided and not yet delivered), or a new one when a policy
    requires approval. Raises :class:`ApprovalGateUnavailable` when the
    policies cannot be evaluated."""
    from services.policy_service import RENEWAL_OPERATIONS, PolicyEvaluationService
    existing = find_protocol_request(protocol, protocol_ref)
    if existing is not None:
        return existing
    policy = None
    try:
        policy = PolicyEvaluationService.check_approval_required(
            ca_id=ca.id, template_id=template_id, cn=cn, san_list=list(san_list or []),
            operation=RENEWAL_OPERATIONS if renewal else 'issuance')
    except Exception as e:
        # Fail closed: a policy that cannot be read never lets a request through
        logger.error("%s: policy evaluation failed, refusing to issue: %s",
                     _LABELS[protocol], e, exc_info=True)
        raise ApprovalGateUnavailable('Policy evaluation failed') from e
    if policy is None:
        return None
    data = dict(extra or {})
    data.update(protocol=protocol, protocol_ref=protocol_ref, ca_id=ca.id, ca_refid=ca.refid,
                template_id=template_id, cn=cn, san=list(san_list or []), csr=csr_pem,
                identity=identity, requested_by=f'{protocol}:{identity}', renewal=renewal)
    try:
        return PolicyEvaluationService.create_approval_request(
            policy=policy, request_data=data, requester_id=None, request_type=PROTOCOL_REQUEST_TYPES[protocol],
            comment=f"{_LABELS[protocol]} {'renewal' if renewal else 'enrolment'} request: {cn or 'unknown'}")
    except Exception as e:
        raise ApprovalGateUnavailable('The request could not be queued for approval') from e


def mark_delivered(approval) -> None:
    """Record that the client heard the decision: its next request is a new one."""
    data = request_data(approval)
    data['delivered_at'] = utc_isoformat(utc_now())
    approval.request_data = json.dumps(data)
    db.session.commit()


def record_refusal(approval, error) -> None:
    """Keep the protocol's own refusal on *approval* for its closed handler."""
    refusal = getattr(error, 'refusal', None)
    if refusal:
        data = request_data(approval)
        data['refusal'] = refusal
        approval.request_data = json.dumps(data)


def decision_reason(approval) -> str:
    """What the client is told about a request that will not be issued."""
    if approval.status == 'expired':
        return 'The request was not approved in time'
    for vote in reversed(approval.get_approvals()):
        if vote.get('action') == 'reject':
            return f"The request was rejected: {vote.get('comment')}" if vote.get('comment') \
                else 'The request was rejected'
    return 'The request was rejected'


def issue_approved(approval, data: dict) -> dict:
    """Issue an approved protocol request through its protocol's own path."""
    handler = _handler(approval.request_type)
    if handler is None:
        raise ValueError(f'No issuer for {approval.request_type} requests')
    return handler.issue(approval, data)


def target_gone(approval) -> Optional[str]:
    """Why an approved protocol request can no longer be issued, else None."""
    handler = _handler(approval.request_type)
    if handler is None or handler.gone is None:
        return None
    return handler.gone(approval, request_data(approval))


def propagate_closed(approvals) -> None:
    """Carry rejections and expiries to the protocols' own state. Never
    raises: the decision is recorded whatever happens to its echo, and the
    protocol reads it again at the client's next request."""
    for approval in approvals:
        handler = _handler(approval.request_type)
        if handler is None or handler.closed is None:
            continue
        try:
            handler.closed(approval, request_data(approval))
        except Exception as e:
            db.session.rollback()
            logger.warning("Approval #%s: protocol state not updated: %s", approval.id, e)
