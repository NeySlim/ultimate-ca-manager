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
from sqlalchemy import update
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from utils.export_options import BOOL, PASSWORD, read_export_options
from utils.pkcs12_export import pkcs12_encryption
from utils.algorithm_refusal import refuse_unexportable_key
import fips_mode
from fips_mode import FipsRestricted

from auth.unified import require_auth, has_permission
# `auth.permissions` exports a function of the same name whose arguments
# are in the opposite order, by role rather than by permission list.
# This route imported that one and called it the way this one expects,
# so the administrator half of the rule below answered no to everyone.
from utils.response import success_response, error_response, created_response
from utils.export_password import validate_export_password
from utils.key_codec import load_pem_bytes
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
from utils.sanitize import content_disposition
from models import db, Certificate, CA, KeyRecoveryRequest
from models.key_recovery import (
    STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_RECOVERED, STATUS_CANCELLED,
)
from utils.pagination import parse_request_pagination, parse_request_sort, rank_of
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

bp = Blueprint('key_recovery', __name__)


def _username():
    return getattr(getattr(g, 'current_user', None), 'username', 'system')


def _user_id():
    return getattr(getattr(g, 'current_user', None), 'id', None)


def _is_requester(req):
    """The account that opened *req*, by id: a request written before the id was kept has none."""
    return req.requested_by_id is not None and req.requested_by_id == _user_id()


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


def _requested_certificate(req):
    """The certificate a request names, or None once its number belongs to another one."""
    cert = db.session.get(Certificate, req.cert_id)
    if cert is None or cert.refid != req.cert_refid:
        return None
    return cert


@bp.route('/api/v2/certificates/<int:cert_id>/key-recovery', methods=['POST'])
@require_auth(['write:key_recovery'])
def request_key_recovery(cert_id):
    """Open a recovery request for a certificate's archived private key."""
    cert = db.session.get(Certificate, cert_id)
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
        requested_by_id=_user_id(),
        requested_at=utc_now(),
    )
    db.session.add(req)
    ok, err = safe_commit(logger, "Failed to create recovery request")
    if not ok:
        return err
    _audit('key_recovery.requested', req)
    return created_response(data=req.to_dict(), message='Key recovery request created')


# Waiting on someone first, then what can still happen, then the closed outcomes
_STATES = (STATUS_PENDING, STATUS_APPROVED, STATUS_RECOVERED, STATUS_REJECTED, STATUS_CANCELLED)

_SORT = {
    'id': KeyRecoveryRequest.id,
    'requested_at': KeyRecoveryRequest.requested_at,
    'status': rank_of(KeyRecoveryRequest.status, _STATES),
    'cert_cn': KeyRecoveryRequest.cert_cn,
    'requested_by': KeyRecoveryRequest.requested_by,
}


@bp.route('/api/v2/key-recovery', methods=['GET'])
@require_auth(['read:key_recovery'])
def list_key_recovery():
    """Recovery requests, newest first, a page at a time (500 by default, the former
    ceiling) with their total in meta; optional ?status= filter."""
    page, per_page = parse_request_pagination(default_per_page=500, max_per_page=500)
    sort = parse_request_sort(_SORT, ('id', 'desc'), tiebreak=KeyRecoveryRequest.id)
    q = KeyRecoveryRequest.query
    status = request.args.get('status')
    if status:
        q = q.filter_by(status=status)
    total = q.count()
    rows = q.order_by(*sort.clauses).offset((page - 1) * per_page).limit(per_page).all()
    return success_response(data={
        'requests': [r.to_dict() for r in rows],
        'dual_control': _dual_control_enabled(),
    }, meta={'total': total, 'page': page, 'per_page': per_page})


@bp.route('/api/v2/key-recovery/<int:rid>', methods=['GET'])
@require_auth(['read:key_recovery'])
def get_key_recovery(rid):
    """One recovery request, whatever its age (the list is paged)."""
    req = db.session.get(KeyRecoveryRequest, rid)
    if not req:
        return error_response('Recovery request not found', 404)
    return success_response(data=req.to_dict())


@bp.route('/api/v2/key-recovery/<int:rid>/approve', methods=['POST'])
@require_auth(['admin:key_recovery'])
def approve_key_recovery(rid):
    req = db.session.get(KeyRecoveryRequest, rid)
    if not req:
        return error_response('Recovery request not found', 404)
    if req.status != STATUS_PENDING:
        return error_response(f'Request is not pending (status: {req.status})', 409)
    if _dual_control_enabled() and (_is_requester(req) or req.requested_by == _username()):
        _audit('key_recovery.approve_denied', req, success=False,
                extra={'reason': 'dual_control'})
        return error_response('Dual control: the approver must be different from the requester', 403)

    if _requested_certificate(req) is None:
        return error_response('The certificate this request was opened on no longer exists', 410)

    data = request.get_json(silent=True) or {}
    req.status = STATUS_APPROVED
    req.decided_by = _username()
    req.decided_by_id = _user_id()
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
    req = db.session.get(KeyRecoveryRequest, rid)
    if not req:
        return error_response('Recovery request not found', 404)
    if req.status != STATUS_PENDING:
        return error_response(f'Request is not pending (status: {req.status})', 409)
    data = request.get_json(silent=True) or {}
    req.status = STATUS_REJECTED
    req.decided_by = _username()
    req.decided_by_id = _user_id()
    req.decided_at = utc_now()
    req.decision_note = (data.get('note') or '').strip()[:2000] or None
    ok, err = safe_commit(logger, "Failed to reject recovery request")
    if not ok:
        return err
    _audit('key_recovery.rejected', req)
    return success_response(data=req.to_dict(), message='Recovery request rejected')


def _claim(rid, current, new, **values):
    """Move request *rid* from *current* to *new* in one conditional UPDATE, committed: True for
    the one caller that moved it, False for every concurrent one."""
    try:
        moved = db.session.execute(
            update(KeyRecoveryRequest)
            .where(KeyRecoveryRequest.id == rid, KeyRecoveryRequest.status == current)
            .values(status=new, **values)
            .execution_options(synchronize_session=False)).rowcount
        if moved != 1:
            db.session.rollback()
            return False
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise


def _give_back(rid):
    """The claim of a download that did not hand the key out: the approval stands again."""
    try:
        db.session.rollback()
        _claim(rid, STATUS_RECOVERED, STATUS_APPROVED, recovered_by=None, recovered_at=None)
    except Exception as e:
        logger.error(f"Key recovery {rid}: the claim could not be given back: {e}")


RECOVER_OPTIONS = {'password': PASSWORD, 'legacy': BOOL}


@bp.route('/api/v2/key-recovery/<int:rid>/recover', methods=['POST'])
@require_auth(['write:key_recovery'])
def recover_key(rid):
    """Download the recovered key as PKCS#12 (once, after approval)."""
    req = db.session.get(KeyRecoveryRequest, rid)
    if not req:
        return error_response('Recovery request not found', 404)
    if req.status != STATUS_APPROVED:
        return error_response(f'Request is not approved (status: {req.status})', 409)
    # Only the original requester or an admin may collect the key.
    if not _is_requester(req) and not has_permission('admin:key_recovery', getattr(g, 'permissions', [])):
        return error_response('Only the requester or an admin may recover this key', 403)

    opts, refused = read_export_options(RECOVER_OPTIONS, log_name='key recovery')
    if refused:
        return refused
    password = opts.get('password') or ''
    pw_err = validate_export_password(password)
    if pw_err:
        return error_response(pw_err, 400)
    legacy = opts.get('legacy', False)  # 3DES/SHA-1 profile (#331)

    cert = _requested_certificate(req)
    if not cert or not cert.prv:
        return error_response('The certificate or its archived key no longer exists', 410)

    # One download per approval: the request is claimed and committed before the key is read
    if not _claim(rid, STATUS_APPROVED, STATUS_RECOVERED,
                  recovered_by=_username(), recovered_at=utc_now()):
        return error_response('Request is no longer approved: it was recovered or closed', 409)

    # Every way out but the returned bundle gives the claim back: a claim stands only for a key handed out
    settled = False
    try:
        try:
            cert_obj = x509.load_pem_x509_certificate(base64.b64decode(cert.crt), default_backend())
            key_pem = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            refuse_unexportable_key(private_key, 'pkcs12', hint=(
                'an administrator allowed to read private keys can export it as PEM (PKCS#8) '
                'from the certificate'))
            from utils.ca_chain import issuer_chain
            start = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
            chain = [x509.load_pem_x509_certificate(link.pem, default_backend()) for link in issuer_chain(start)]
            p12 = pkcs12.serialize_key_and_certificates(
                name=(cert.subject_cn or cert.refid or 'recovered').encode(),
                key=private_key, cert=cert_obj, cas=chain or None,
                encryption_algorithm=pkcs12_encryption(password, legacy, caref=cert.caref),
            )
        except FipsRestricted:
            _give_back(rid)
            settled = True
            _audit('key_recovery.recover_failed', req, success=False)
            raise  # the app handler answers 400 with the FIPS problem type
        except Exception as e:
            logger.error(f"Key recovery {rid} failed to build PKCS12: {e}")
            _give_back(rid)
            settled = True
            _audit('key_recovery.recover_failed', req, success=False)
            return error_response('Failed to assemble the recovered key', 500)

        response = Response(p12, mimetype='application/x-pkcs12',
                            headers={'Content-Disposition': content_disposition(
                                cert.descr or cert.refid, '.p12', fallback=cert.refid or 'recovered')})
        _audit('key_recovery.recovered', req)
        settled = True
        return response
    finally:
        if not settled:
            _give_back(rid)
            _audit('key_recovery.recover_failed', req, success=False)
