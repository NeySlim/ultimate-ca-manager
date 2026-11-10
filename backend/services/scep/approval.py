"""SCEP requests held by a policy requiring approval.

The ``ApprovalRequest`` decides; the ``SCEPRequest`` follows it and answers
the client (RFC 8894 §3.3.2.2: PENDING, then SUCCESS or FAILURE). Approving
from the approvals queue issues through the SCEP service; the SCEP queue
records its votes on the same approval request.
"""
import logging

from models import Certificate, SCEPRequest, db
from services import protocol_approval
from services.protocol_approval import ProtocolRequestGone

logger = logging.getLogger(__name__)

_GONE = 'The SCEP request is no longer pending'


def _scep_request(data):
    ref = data.get('scep_request_id')
    if ref is None or not str(ref).isdecimal():
        return None
    return db.session.get(SCEPRequest, int(ref))


def _approver(approval):
    for vote in reversed(approval.get_approvals()):
        if vote.get('action') == 'approve':
            return vote.get('username') or 'system'
    return 'system'


def _issue(approval, data):
    from api.v2.scep import _issuing_service
    scep_req = _scep_request(data)
    if scep_req is None or scep_req.status != 'pending':
        raise ProtocolRequestGone(_GONE)
    try:
        service = _issuing_service(scep_req)
    except LookupError as e:
        raise ProtocolRequestGone(str(e)) from e
    from services.policy_service import PolicyViolation
    from services.scep.scep_service import SCEPRequestRefused
    from utils.request_names import RequestRejected
    try:
        cert_refid = service.approve_request(scep_req.transaction_id, _approver(approval))
    except (PolicyViolation, RequestRejected, SCEPRequestRefused) as e:
        # A refusal for good closes the request, as on ACME; transient ones keep it pending
        raise ProtocolRequestGone(f'The SCEP request was refused: {e}',
                                  refusal={'reason': str(e)}) from e
    if not cert_refid:
        raise ValueError('The SCEP request could not be issued')
    cert = Certificate.query.filter_by(refid=cert_refid).first()
    try:
        from services.webhook_service import emit_cert_issued
        emit_cert_issued(cert.to_dict(), ca_refid=cert.caref)
    except Exception as e:
        logger.error(f"Webhook emit (SCEP approval) failed: {e}")
    return {'id': cert.id, 'cn': data.get('cn'), 'protocol': 'scep',
            'serial_number': cert.serial_number, 'scep_request_id': scep_req.id}


def _closed(approval, data):
    scep_req = _scep_request(data)
    if scep_req is None or scep_req.status != 'pending':
        return
    scep_req.status = 'rejected'
    reason = (data.get('refusal') or {}).get('reason') or protocol_approval.decision_reason(approval)
    scep_req.rejection_reason = reason[:255]
    db.session.commit()


def _gone(approval, data):
    scep_req = _scep_request(data)
    return None if scep_req is not None and scep_req.status == 'pending' else _GONE


protocol_approval.register('scep_request', _issue, closed=_closed, gone=_gone)


def linked_approval(scep_req):
    """The pending approval request holding *scep_req*, None when none does."""
    ref = protocol_approval.make_ref('scep', scep_req.transaction_id, scep_req.ca_refid)
    approval = protocol_approval.find_protocol_request('scep', ref)
    if approval is None or approval.status != 'pending':
        return None
    return approval


def follow_approval(scep_req):
    """Bring a pending SCEP request in line with the approval holding it
    (closed by a rejection or an expiry the sweep has not echoed yet)."""
    if scep_req.status != 'pending':
        return
    ref = protocol_approval.make_ref('scep', scep_req.transaction_id, scep_req.ca_refid)
    approval = protocol_approval.find_protocol_request('scep', ref)
    if approval is not None and approval.status == 'rejected':
        _closed(approval, protocol_approval.request_data(approval))
        return
    if approval is None:
        from models.policy import ApprovalRequest
        closed = ApprovalRequest.query.filter(
            ApprovalRequest.request_type == 'scep_request',
            ApprovalRequest.status.in_(('rejected', 'expired')),
            ApprovalRequest.request_data.like(f'%"{ref}"%'),
        ).order_by(ApprovalRequest.id.desc()).first()
        if closed is not None and protocol_approval.request_data(closed).get('protocol_ref') == ref:
            _closed(closed, protocol_approval.request_data(closed))
