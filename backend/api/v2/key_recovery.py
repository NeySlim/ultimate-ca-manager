"""Key recovery (escrow) API — dual-control private-key recovery.

Recovering an archived private key is the most sensitive operation in UCM, so
it is a request -> approve -> recover workflow with four-eyes control and full
audit:
  - request  (write:key_recovery) — anyone who can manage certs asks, with a reason
  - approve / reject (admin:key_recovery) — an admin decides; by default the
    approver must differ from the requester (dual control)
  - recover  (write:key_recovery) — the requester (or an admin) downloads the
    key as PKCS#12, once, only after approval
"""
import base64
import logging
import os

from flask import Blueprint, request, g, Response
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from auth.unified import require_auth
from auth.permissions import has_permission
from utils.response import success_response, error_response, created_response
from utils.key_codec import load_pem_bytes
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
from models import db, Certificate, CA, KeyRecoveryRequest
from models.key_recovery import (
    STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_RECOVERED,
)
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

bp = Blueprint('key_recovery', __name__)


def _username():
    return getattr(getattr(g, 'current_user', None), 'username', 'system')


def _user_id():
    return getattr(getattr(g, 'current_user', None), 'id', None)


def _is_disabled_value(val):
    return str(val).strip().lower() in ('false', '0', 'no')


def _dual_control_env():
    """Env override for dual control, or None when unset.

    Accepted in both the canonical UPPER and lower case so the value an operator
    writes in /etc/ucm/ucm.env takes effect regardless of casing. When set it
    wins over the stored setting and the Settings toggle (operator escape hatch).
    """
    env = os.environ.get('KEY_RECOVERY_DUAL_CONTROL')
    if env is None:
        env = os.environ.get('key_recovery_dual_control')
    if env is None:
        return None
    return not _is_disabled_value(env)


def _dual_control_enabled():
    # Default ON (four-eyes). Only an explicit 'false'/'0'/'no' disables it.
    # Resolution order: env override (set in /etc/ucm/ucm.env) > DB > default ON.
    env = _dual_control_env()
    if env is not None:
        return env

    from models import SystemConfig
    row = SystemConfig.query.filter_by(key='key_recovery_dual_control').first()
    return not (row and _is_disabled_value(row.value))


def _audit(action, req, *, success=True, extra=None):
    # AuditService.log_action is exception-safe (logs + rolls back its own row).
    details = {'request_id': req.id, 'cert_id': req.cert_id, 'cert_cn': req.cert_cn}
    if extra:
        details.update(extra)
    AuditService.log_action(
        action=action, resource_type='key_recovery',
        resource_id=str(req.id), resource_name=req.cert_cn,
        details=details, user_id=_user_id(), success=success)


@bp.route('/api/v2/certificates/<int:cert_id>/key-recovery', methods=['POST'])
@require_auth(['write:key_recovery'])
def request_key_recovery(cert_id):
    """Open a recovery request for a certificate's archived private key."""
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    if not cert.prv:
        return error_response('Certificate has no archived private key to recover', 400)

    data = request.get_json(silent=True) or {}
    reason = (data.get('reason') or '').strip()
    if not reason:
        return error_response('A reason is required for key recovery', 400)
    if len(reason) > 2000:
        return error_response('Reason too long', 400)

    req = KeyRecoveryRequest(
        cert_id=cert.id,
        cert_refid=cert.refid,
        cert_cn=cert.subject_cn or cert.descr,
        reason=reason,
        status=STATUS_PENDING,
        requested_by=_username(),
        requested_at=utc_now(),
    )
    db.session.add(req)
    ok, err = safe_commit(logger, "Failed to create recovery request")
    if not ok:
        return err
    _audit('key_recovery.requested', req)
    return created_response(data=req.to_dict(), message='Key recovery request created')


@bp.route('/api/v2/key-recovery', methods=['GET'])
@require_auth(['read:key_recovery'])
def list_key_recovery():
    """List recovery requests, newest first; optional ?status= filter."""
    q = KeyRecoveryRequest.query
    status = request.args.get('status')
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(KeyRecoveryRequest.id.desc()).limit(500).all()
    return success_response(data={
        'requests': [r.to_dict() for r in rows],
        'dual_control': _dual_control_enabled(),
    })


@bp.route('/api/v2/key-recovery/<int:rid>/approve', methods=['POST'])
@require_auth(['admin:key_recovery'])
def approve_key_recovery(rid):
    req = KeyRecoveryRequest.query.get(rid)
    if not req:
        return error_response('Recovery request not found', 404)
    if req.status != STATUS_PENDING:
        return error_response(f'Request is not pending (status: {req.status})', 409)
    if _dual_control_enabled() and req.requested_by == _username():
        _audit('key_recovery.approve_denied', req, success=False,
                extra={'reason': 'dual_control'})
        return error_response('Dual control: the approver must be different from the requester', 403)

    data = request.get_json(silent=True) or {}
    req.status = STATUS_APPROVED
    req.decided_by = _username()
    req.decided_at = utc_now()
    req.decision_note = (data.get('note') or '').strip()[:2000] or None
    ok, err = safe_commit(logger, "Failed to approve recovery request")
    if not ok:
        return err
    _audit('key_recovery.approved', req)
    return success_response(data=req.to_dict(), message='Recovery request approved')


@bp.route('/api/v2/key-recovery/<int:rid>/reject', methods=['POST'])
@require_auth(['admin:key_recovery'])
def reject_key_recovery(rid):
    req = KeyRecoveryRequest.query.get(rid)
    if not req:
        return error_response('Recovery request not found', 404)
    if req.status != STATUS_PENDING:
        return error_response(f'Request is not pending (status: {req.status})', 409)
    data = request.get_json(silent=True) or {}
    req.status = STATUS_REJECTED
    req.decided_by = _username()
    req.decided_at = utc_now()
    req.decision_note = (data.get('note') or '').strip()[:2000] or None
    ok, err = safe_commit(logger, "Failed to reject recovery request")
    if not ok:
        return err
    _audit('key_recovery.rejected', req)
    return success_response(data=req.to_dict(), message='Recovery request rejected')


@bp.route('/api/v2/key-recovery/<int:rid>/recover', methods=['POST'])
@require_auth(['write:key_recovery'])
def recover_key(rid):
    """Download the recovered key as PKCS#12 (once, after approval)."""
    req = KeyRecoveryRequest.query.get(rid)
    if not req:
        return error_response('Recovery request not found', 404)
    if req.status != STATUS_APPROVED:
        return error_response(f'Request is not approved (status: {req.status})', 409)
    # Only the original requester or an admin may collect the key.
    if req.requested_by != _username() and not has_permission('admin:key_recovery', getattr(g, 'permissions', [])):
        return error_response('Only the requester or an admin may recover this key', 403)

    data = request.get_json(silent=True) or {}
    password = data.get('password') or ''
    if len(password) < 8:
        return error_response('A PKCS#12 password of at least 8 characters is required', 400)

    cert = Certificate.query.get(req.cert_id)
    if not cert or not cert.prv:
        return error_response('The certificate or its archived key no longer exists', 410)

    try:
        cert_obj = x509.load_pem_x509_certificate(base64.b64decode(cert.crt), default_backend())
        key_pem = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
        private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
        chain = []
        ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
        while ca and ca.crt:
            chain.append(x509.load_pem_x509_certificate(base64.b64decode(ca.crt), default_backend()))
            ca = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None
        p12 = pkcs12.serialize_key_and_certificates(
            name=(cert.subject_cn or cert.refid or 'recovered').encode(),
            key=private_key, cert=cert_obj, cas=chain or None,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
        )
    except Exception as e:
        logger.error(f"Key recovery {rid} failed to build PKCS12: {e}")
        _audit('key_recovery.recover_failed', req, success=False)
        return error_response('Failed to assemble the recovered key', 500)

    req.status = STATUS_RECOVERED
    req.recovered_by = _username()
    req.recovered_at = utc_now()
    ok, err = safe_commit(logger, "Failed to finalize recovery")
    if not ok:
        return err
    _audit('key_recovery.recovered', req)

    filename = f"{(cert.descr or cert.refid or 'recovered')}.p12"
    return Response(p12, mimetype='application/x-pkcs12',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})
