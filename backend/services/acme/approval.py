"""ACME orders held for approval (RFC 8555 §7.1.6, §7.4).

The order stays ``processing`` while its request is pending; the approval
issues it as finalize would have (``valid`` with its certificate), and a
rejection or an expiry makes it ``invalid`` with an ``unauthorized`` error:
the server refuses to issue for this client's request (§6.7).
"""
import logging

from models import db
from models.acme_models import AcmeOrder
from services import protocol_approval
from services.protocol_approval import ProtocolRequestGone

logger = logging.getLogger(__name__)

# Seconds a client waits before reading an order held for approval again
APPROVAL_RETRY_AFTER = 300

_GONE = 'The ACME order is no longer awaiting issuance'


def _held_order(data):
    order = AcmeOrder.query.filter_by(order_id=str(data.get('order_id'))).first()
    if order is None or order.status != 'processing':
        return None
    return order


def _service(data):
    from services.acme.acme_service import AcmeService
    return AcmeService(base_url=data.get('base_url') or '')


def _issue(approval, data):
    """Finalize the held order with its stored CSR, as the client's finalize would have."""
    from api.acme.acme_api import _is_caa_failure
    order = _held_order(data)
    if order is None:
        raise ProtocolRequestGone(_GONE)
    order_id = order.order_id
    service = _service(data)
    service._finalizing_order_id = order_id
    try:
        success, error = service.finalize_order(order_id, data['csr'], ca_refid=data.get('ca_refid'),
                                                approval=approval)
    finally:
        service._finalizing_order_id = None
    if not success:
        error_type = 'caa' if _is_caa_failure(error) else (
            getattr(service, '_last_finalize_error_type', None) or 'badCSR')
        if error_type == 'serverInternal':
            # The order stays processing: the approver may try again once the CA is back
            raise ValueError(error)
        service.invalidate_processing_order(order_id, error_type, error)
        raise ProtocolRequestGone(f'The ACME order was refused: {error}')
    order = AcmeOrder.query.filter_by(order_id=order_id).first()
    return {'id': order.certificate_id, 'cn': data.get('cn'), 'order_id': order_id,
            'protocol': 'acme'}


def _closed(approval, data):
    order = _held_order(data)
    if order is None:
        return
    _service(data).invalidate_processing_order(
        order.order_id, 'unauthorized', protocol_approval.decision_reason(approval))


def _gone(approval, data):
    return None if _held_order(data) is not None else _GONE


protocol_approval.register('acme_order', _issue, closed=_closed, gone=_gone)


def held_by_approval(order) -> bool:
    """Bring a ``processing`` order in line with its approval request: True
    while it is held for a decision, False when it never was or the
    decision came (the order then reads ``invalid`` or ``valid``)."""
    if order.status != 'processing':
        return False
    approval = protocol_approval.find_protocol_request('acme', order.order_id)
    if approval is None:
        # Expired just now, or closed without its echo reaching the order
        db.session.refresh(order)
        if order.status == 'processing':
            closed = _last_closed(order.order_id)
            if closed is not None:
                _closed(closed, protocol_approval.request_data(closed))
                db.session.refresh(order)
        return False
    if approval.status == 'rejected':
        _closed(approval, protocol_approval.request_data(approval))
        db.session.refresh(order)
        return False
    return approval.status == 'pending'


def _last_closed(order_id):
    from models.policy import ApprovalRequest
    rows = ApprovalRequest.query.filter(
        ApprovalRequest.request_type == 'acme_order',
        ApprovalRequest.status.in_(('rejected', 'expired')),
        ApprovalRequest.request_data.like(f'%"{order_id}"%'),
    ).order_by(ApprovalRequest.id.desc()).all()
    for row in rows:
        if protocol_approval.request_data(row).get('protocol_ref') == order_id:
            return row
    return None
