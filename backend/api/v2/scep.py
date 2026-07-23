"""
SCEP Management Routes v2.0
/api/scep/* - SCEP configuration and requests
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, SCEPRequest, SystemConfig, CA
from services.audit_service import AuditService
from datetime import datetime, timedelta, timezone
import secrets
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('scep_v2', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


@bp.route('/api/v2/scep/config', methods=['GET'])
@require_auth(['read:scep'])
def get_scep_config():
    """Get SCEP configuration from database"""
    return success_response(data={
        'enabled': get_config('scep_enabled', 'true') == 'true',
        'url': get_config('scep_url', '/scep/pkiclient.exe'),
        'ca_id': int(get_config('scep_ca_id', '0') or 0) or None,
        'ca_ident': get_config('scep_ca_ident', 'ucm-ca'),
        'auto_approve': get_config('scep_auto_approve', 'false') == 'true',
        'challenge_validity': int(get_config('scep_challenge_validity', '24')),
        'enforce_signing_time': get_config('scep_enforce_signing_time', 'false') == 'true',
        'time_skew_minutes': int(get_config('scep_time_skew_minutes', '10') or 10),
        'getcacert_chain': get_config('scep_getcacert_chain', 'false') == 'true',
    })


@bp.route('/api/v2/scep/config', methods=['PATCH'])
@require_auth(['write:scep'])
def update_scep_config():
    """Update SCEP configuration in database"""
    data = request.json or {}

    if 'enabled' in data:
        set_config('scep_enabled', 'true' if data['enabled'] else 'false')
    if 'url' in data:
        set_config('scep_url', data['url'])
    if 'ca_id' in data:
        # Validate CA exists if a non-empty ID was provided
        if data['ca_id']:
            try:
                ca_id_int = int(data['ca_id'])
            except (TypeError, ValueError):
                return error_response('Invalid ca_id', 400)
            if not db.session.get(CA, ca_id_int):
                return error_response('CA not found', 404)
            set_config('scep_ca_id', str(ca_id_int))
        else:
            set_config('scep_ca_id', '')
    if 'ca_ident' in data:
        set_config('scep_ca_ident', data['ca_ident'])
    if 'auto_approve' in data:
        set_config('scep_auto_approve', 'true' if data['auto_approve'] else 'false')
    if 'challenge_validity' in data:
        # Bound to a sane window: 1 hour .. 30 days. Anything beyond defeats
        # the point of a one-time enrollment secret.
        try:
            cv = int(data['challenge_validity'])
        except (TypeError, ValueError):
            return error_response('challenge_validity must be an integer (hours)', 400)
        if cv < 1 or cv > 720:
            return error_response('challenge_validity must be between 1 and 720 hours', 400)
        set_config('scep_challenge_validity', str(cv))
    if 'enforce_signing_time' in data:
        set_config('scep_enforce_signing_time',
                   'true' if data['enforce_signing_time'] else 'false')
    if 'time_skew_minutes' in data:
        try:
            skew = int(data['time_skew_minutes'])
        except (TypeError, ValueError):
            return error_response('time_skew_minutes must be an integer', 400)
        if skew < 1 or skew > 1440:
            return error_response('time_skew_minutes must be between 1 and 1440', 400)
        set_config('scep_time_skew_minutes', str(skew))
    if 'getcacert_chain' in data:
        set_config('scep_getcacert_chain',
                   'true' if data['getcacert_chain'] else 'false')
    
    ok, _err = safe_commit(logger, "Failed to update SCEP configuration")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='scep_config_update',
        resource_type='scep',
        resource_name='SCEP Configuration',
        details='Updated SCEP configuration',
        success=True
    )
    
    return success_response(message='SCEP configuration saved')


@bp.route('/api/v2/scep/requests', methods=['GET'])
@require_auth(['read:scep'])
def list_scep_requests():
    """List SCEP certificate requests"""
    status = request.args.get('status')
    query = SCEPRequest.query
    
    if status:
        query = query.filter_by(status=status)
        
    requests_list = query.order_by(SCEPRequest.created_at.desc()).limit(50).all()
    
    data = [req.to_dict() for req in requests_list]
    return success_response(data=data)


@bp.route('/api/v2/scep/<int:request_id>/approve', methods=['POST'])
@require_auth(['write:scep'])
def approve_scep_request(request_id):
    """Approve SCEP request"""
    scep_req = db.session.get(SCEPRequest, request_id)
    if not scep_req:
        return error_response('Request not found', 404)
        
    if scep_req.status != 'pending':
        return error_response(f'Request is already {scep_req.status}', 400)

    # Use the authenticated user's identity. Never default to 'admin' — that
    # silently impersonates the superuser in audit if the auth context is
    # somehow missing.
    if not (hasattr(g, 'current_user') and g.current_user):
        return error_response('Authentication context required', 401)
    username = g.current_user.username

    scep_req.status = 'approved'
    scep_req.approved_by = username
    scep_req.approved_at = datetime.now(timezone.utc)
    
    ok, _err = safe_commit(logger, "Failed to approve SCEP request")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='scep_approve',
        resource_type='scep_request',
        resource_id=str(request_id),
        resource_name=f'SCEP request {request_id}',
        details=f'Approved SCEP request {request_id}',
        success=True
    )
    
    return success_response(
        data=scep_req.to_dict(),
        message='SCEP request approved'
    )


@bp.route('/api/v2/scep/<int:request_id>/reject', methods=['POST'])
@require_auth(['write:scep'])
def reject_scep_request(request_id):
    """Reject SCEP request"""
    data = request.json
    reason = data.get('reason', 'Rejected by admin') if data else 'Rejected by admin'
    
    scep_req = db.session.get(SCEPRequest, request_id)
    if not scep_req:
        return error_response('Request not found', 404)
        
    if scep_req.status != 'pending':
        return error_response(f'Request is already {scep_req.status}', 400)

    if not (hasattr(g, 'current_user') and g.current_user):
        return error_response('Authentication context required', 401)
    username = g.current_user.username

    scep_req.status = 'rejected'
    scep_req.rejection_reason = reason
    scep_req.approved_by = username
    scep_req.approved_at = datetime.now(timezone.utc)
    
    ok, _err = safe_commit(logger, "Failed to reject SCEP request")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='scep_reject',
        resource_type='scep_request',
        resource_id=str(request_id),
        resource_name=f'SCEP request {request_id}',
        details=f'Rejected SCEP request {request_id}: {reason}',
        success=True
    )
    
    return success_response(
        data=scep_req.to_dict(),
        message='SCEP request rejected'
    )


@bp.route('/api/v2/scep/stats', methods=['GET'])
@require_auth(['read:scep'])
def get_scep_stats():
    """Get SCEP statistics"""
    total = SCEPRequest.query.count()
    pending = SCEPRequest.query.filter_by(status='pending').count()
    approved = SCEPRequest.query.filter_by(status='approved').count()
    rejected = SCEPRequest.query.filter_by(status='rejected').count()
    
    return success_response(data={
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected
    })


def challenge_age_state(ca_id):
    """Return ``(challenge, expired, expires_at)`` for a CA's SCEP challenge.

    ``scep_challenge_validity`` (hours) bounds how long a generated challenge
    stays usable. Challenges created before this was enforced carry no
    timestamp: they are stamped on first inspection rather than expired on the
    spot, so upgrading does not lock out an already-deployed fleet — they then
    expire normally one validity window later.
    """
    challenge = get_config(f'scep_challenge_{ca_id}')
    if not challenge:
        return None, False, None

    try:
        validity_hours = int(get_config('scep_challenge_validity', '24'))
    except (TypeError, ValueError):
        validity_hours = 24

    stamp_key = f'scep_challenge_{ca_id}_generated_at'
    raw = get_config(stamp_key)
    generated_at = None
    if raw:
        try:
            generated_at = datetime.fromisoformat(raw)
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            generated_at = None

    if generated_at is None:
        # Legacy challenge: adopt it now instead of failing every enrollment.
        generated_at = datetime.now(timezone.utc)
        set_config(stamp_key, generated_at.isoformat())
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    expires_at = generated_at + timedelta(hours=validity_hours)
    return challenge, datetime.now(timezone.utc) >= expires_at, expires_at


@bp.route('/api/v2/scep/challenge/<int:ca_id>', methods=['GET'])
@require_auth(['write:scep'])
def get_challenge_password(ca_id):
    """Get challenge password for a CA.

    The challenge password is a shared secret that grants the ability to
    enroll certificates against this CA via SCEP. Possessing it is
    operationally equivalent to write access — viewers MUST NOT be able to
    read it. Gated behind ``write:scep`` and audited as a sensitive read.
    """
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)

    challenge, expired, expires_at = challenge_age_state(ca_id)

    AuditService.log_action(
        action='scep_challenge_read',
        resource_type='scep',
        resource_id=str(ca_id),
        resource_name=ca.descr,
        details=f'Read SCEP challenge password for CA: {ca.descr}',
        success=True,
    )

    return success_response(data={
        'ca_id': ca_id,
        'challenge': challenge or 'Not configured',
        'expired': expired,
        'expires_at': expires_at.isoformat() if expires_at else None,
    })


@bp.route('/api/v2/scep/challenge/<int:ca_id>/regenerate', methods=['POST'])
@require_auth(['write:scep'])
def regenerate_challenge_password(ca_id):
    """Regenerate challenge password for a CA"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Generate a secure random challenge password
    new_challenge = secrets.token_urlsafe(24)
    set_config(f'scep_challenge_{ca_id}', new_challenge)
    # Stamp the generation time so `scep_challenge_validity` can expire it.
    set_config(f'scep_challenge_{ca_id}_generated_at',
               datetime.now(timezone.utc).isoformat())
    ok, _err = safe_commit(logger, "Failed to regenerate SCEP challenge")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='scep_challenge_regenerate',
        resource_type='scep',
        resource_id=str(ca_id),
        resource_name=ca.descr,
        details=f'Regenerated SCEP challenge password for CA: {ca.descr}',
        success=True
    )
    
    return success_response(
        data={'challenge': new_challenge},
        message='Challenge password regenerated'
    )

