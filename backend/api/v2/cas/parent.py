"""
Parent of a CA confirmed by hand, when this build cannot check the parent's signature
"""
import logging

from flask import g, request

from . import bp
from auth.unified import require_auth
from models import CA, db
from models.ca import clear_request_caches
from services.audit_service import AuditService
from services.ca import parent_confirmation
from utils.db_transaction import safe_commit
from utils.response import error_response, success_response

logger = logging.getLogger(__name__)


def _confirmed(data):
    return data.get('confirm') is True


@bp.route('/api/v2/cas/<int:ca_id>/parent-confirmation', methods=['POST'])
@require_auth(['write:cas'])
def confirm_ca_parent(ca_id):
    """Link a CA to the parent proposed for it, on an explicit confirmation.

    Body: ``{"parent_id": int, "confirm": true}``. Everything is checked again: the CA has
    no parent, the parent is the one proposed, and its key can still not check the
    signature (one that does not verify is refused, one that verifies needs no confirmation)."""
    data = request.get_json(silent=True) or {}
    if not _confirmed(data):
        return error_response('Linking a CA to a parent whose signature cannot be verified needs '
                              '"confirm": true', 400)
    parent_id = data.get('parent_id')
    if type(parent_id) is not int:
        return error_response('parent_id must be the id of a CA', 400)
    ca = db.session.get(CA, ca_id)
    if ca is None:
        return error_response('CA not found', 404)
    username = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
    try:
        found = parent_confirmation.confirm(ca, db.session.get(CA, parent_id), username)
    except parent_confirmation.ConfirmationRefused as e:
        db.session.rollback()
        return error_response(e.message, e.status)
    parent_name, ca_name = found.parent.descr, ca.descr
    ok, err = safe_commit(logger, "Failed to confirm the CA parent")
    if not ok:
        return err
    AuditService.log_action(
        action='ca_parent_confirmed', resource_type='ca', resource_id=ca_id, resource_name=ca_name,
        details=f'Parent "{parent_name}" (id {parent_id}) confirmed by hand: {found.reason}', success=True)
    clear_request_caches()  # the chain walks cached before the change are stale
    return success_response(data=db.session.get(CA, ca_id).to_dict(),
                            message=f'CA "{ca_name}" linked under "{parent_name}"')


@bp.route('/api/v2/cas/<int:ca_id>/parent-confirmation', methods=['DELETE'])
@require_auth(['write:cas'])
def withdraw_ca_parent(ca_id):
    """Withdraw a parent confirmed by hand; body ``{"confirm": true}``. The CA is left without a parent."""
    data = request.get_json(silent=True) or {}
    if not _confirmed(data):
        return error_response('Withdrawing a parent confirmed by hand needs "confirm": true', 400)
    ca = db.session.get(CA, ca_id)
    if ca is None:
        return error_response('CA not found', 404)
    try:
        former = parent_confirmation.withdraw(ca)
    except parent_confirmation.ConfirmationRefused as e:
        db.session.rollback()
        return error_response(e.message, e.status)
    parent = CA.query.filter_by(refid=former).first()
    parent_name = parent.descr if parent else former
    ca_name = ca.descr
    ok, err = safe_commit(logger, "Failed to withdraw the CA parent")
    if not ok:
        return err
    AuditService.log_action(
        action='ca_parent_unconfirmed', resource_type='ca', resource_id=ca_id, resource_name=ca_name,
        details=f'Parent "{parent_name}" confirmed by hand withdrawn', success=True)
    clear_request_caches()  # the chain walks cached before the change are stale
    return success_response(data=db.session.get(CA, ca_id).to_dict(),
                            message=f'CA "{ca_name}" no longer linked under "{parent_name}"')
