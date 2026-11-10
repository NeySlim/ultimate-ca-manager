"""SCEP requests held by a policy requiring approval.

The ``ApprovalRequest`` decides; the ``SCEPRequest`` follows it and answers
the client (RFC 8894 §3.3.2.2: PENDING, then SUCCESS or FAILURE). Approving
from the approvals queue issues through the SCEP service; the SCEP queue
records its votes on the same approval request.
"""
import base64
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


def _intune_client(scep_req):
    """The Intune client of the profile *scep_req* came through, else None."""
    if scep_req.profile_id is None:
        return None
    from models.scep import ScepProfile
    from services.scep import intune_client
    return intune_client.client_for_profile(db.session.get(ScepProfile, scep_req.profile_id))


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
    # An Intune profile's request hears of its issuance as on auto-approval
    service.intune_client = _intune_client(scep_req)
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
    """Reject the SCEP request; True when it was rejected now (Intune is owed a notice)."""
    scep_req = _scep_request(data)
    if scep_req is None or scep_req.status != 'pending':
        return False
    scep_req.status = 'rejected'
    reason = (data.get('refusal') or {}).get('reason') or protocol_approval.decision_reason(approval)
    scep_req.rejection_reason = reason[:255]
    db.session.commit()
    return True


def _notice(approval, data):
    """Tell Intune, for an Intune profile's request, that it will not be issued."""
    scep_req = _scep_request(data)
    if scep_req is None or scep_req.status != 'rejected':
        return
    try:
        client = _intune_client(scep_req)
    except ValueError as e:
        logger.error("SCEP request %s: Intune not notified of its refusal: %s", scep_req.id, e)
        return
    from services.scep.scep_service import notify_intune_failure
    notify_intune_failure(client, scep_req.transaction_id, base64.b64decode(scep_req.csr),
                          scep_req.rejection_reason or protocol_approval.decision_reason(approval))


def _gone(approval, data):
    scep_req = _scep_request(data)
    return None if scep_req is not None and scep_req.status == 'pending' else _GONE


protocol_approval.register('scep_request', _issue, closed=_closed, gone=_gone, notice=_notice)


def linked_approval(scep_req):
    """The pending approval request holding *scep_req*, None when none does."""
    ref = protocol_approval.make_ref('scep', scep_req.transaction_id, scep_req.ca_refid)
    approval = protocol_approval.find_protocol_request('scep', ref)
    if approval is None or approval.status != 'pending':
        return None
    return approval


def approved_request(scep_req):
    """The approved request that held *scep_req*, delivered or not; None when none did."""
    from models.policy import ApprovalRequest
    ref = protocol_approval.make_ref('scep', scep_req.transaction_id, scep_req.ca_refid)
    for approval in ApprovalRequest.query.filter(
            ApprovalRequest.request_type == 'scep_request',
            ApprovalRequest.status == 'approved',
            ApprovalRequest.request_data.like(f'%"{ref}"%'),
    ).order_by(ApprovalRequest.id.desc()).all():
        if protocol_approval.request_data(approval).get('protocol_ref') == ref:
            return approval
    return None


def follow_approval(scep_req):
    """Bring a pending SCEP request in line with the approval holding it
    (closed by a rejection or an expiry the sweep has not echoed yet)."""
    if scep_req.status != 'pending':
        return
    ref = protocol_approval.make_ref('scep', scep_req.transaction_id, scep_req.ca_refid)
    approval = protocol_approval.find_protocol_request('scep', ref)
    if approval is not None and approval.status == 'rejected':
        protocol_approval.propagate_closed([approval])
        return
    if approval is None:
        from models.policy import ApprovalRequest
        closed = ApprovalRequest.query.filter(
            ApprovalRequest.request_type == 'scep_request',
            ApprovalRequest.status.in_(('rejected', 'expired')),
            ApprovalRequest.request_data.like(f'%"{ref}"%'),
        ).order_by(ApprovalRequest.id.desc()).first()
        if closed is not None and protocol_approval.request_data(closed).get('protocol_ref') == ref:
            protocol_approval.propagate_closed([closed])
