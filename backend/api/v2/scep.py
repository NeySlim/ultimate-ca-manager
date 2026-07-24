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



# ============ SCEP Profiles (issue #228) ============

import re as _re

_SLUG_REGEX = _re.compile(r'^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$')


def _slugify(name):
    slug = _re.sub(r'[^a-z0-9-]+', '-', (name or '').lower()).strip('-')
    return slug[:64].rstrip('-')


def _validate_profile_payload(data, *, partial=False, profile_id=None):
    """Validate/normalize a profile payload. Returns (ok, err)."""
    from models import ScepProfile, CertificateTemplate

    if not partial or 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return False, 'Profile name is required'
        if len(name) > 100:
            return False, 'Profile name too long (max 100)'
        clash = ScepProfile.query.filter_by(name=name).first()
        if clash and clash.id != profile_id:
            return False, 'Profile name already exists'
        data['name'] = name

    if 'url_slug' in data or not partial:
        slug = (data.get('url_slug') or '').strip().lower()
        if not slug:
            slug = _slugify(data.get('name', ''))
        if not slug or not _SLUG_REGEX.match(slug):
            return False, ('url_slug must be 1-64 lowercase letters, digits '
                           'or hyphens (no leading/trailing hyphen)')
        clash = ScepProfile.query.filter_by(url_slug=slug).first()
        if clash and clash.id != profile_id:
            return False, 'url_slug already in use'
        data['url_slug'] = slug

    if not partial or 'ca_id' in data or 'ca_refid' in data:
        ca = None
        if data.get('ca_refid'):
            ca = CA.query.filter_by(refid=data['ca_refid']).first()
        elif data.get('ca_id'):
            ca = db.session.get(CA, data['ca_id'])
        if not ca:
            return False, 'CA not found'
        if not ca.has_private_key:
            return False, 'Selected CA has no private key'
        if ca.uses_hsm:
            return False, ('Selected CA is HSM-backed: SCEP requires RSA '
                           'envelope decryption, unavailable for HSM keys')
        data['ca_refid'] = ca.refid

    if 'template_id' in data and data['template_id']:
        tpl = db.session.get(CertificateTemplate, data['template_id'])
        if not tpl:
            return False, 'Template not found'
        if tpl.template_type == 'ca':
            return False, 'CA templates cannot be used for SCEP profiles'

    return True, None


def _apply_challenge(profile, raw_challenge):
    """Encrypt and store a challenge; blank clears it."""
    from utils.datetime_utils import utc_now
    if raw_challenge:
        try:
            from security.encryption import encrypt_text
            profile.challenge_password = encrypt_text(raw_challenge)
        except Exception:
            profile.challenge_password = raw_challenge
        profile.challenge_generated_at = utc_now()
    else:
        profile.challenge_password = None
        profile.challenge_generated_at = None


@bp.route('/api/v2/scep/profiles', methods=['GET'])
@require_auth(['read:scep'])
def list_scep_profiles():
    """List SCEP profiles (challenge secrets are never returned)."""
    from models import ScepProfile, CertificateTemplate
    profiles = ScepProfile.query.order_by(ScepProfile.name).all()
    ca_names = {c.refid: (c.descr or c.common_name) for c in CA.query.all()}
    tpl_names = {t.id: t.name for t in CertificateTemplate.query.all()}
    data = []
    for p in profiles:
        d = p.to_dict()
        d['ca_name'] = ca_names.get(p.ca_refid)
        d['template_name'] = tpl_names.get(p.template_id)
        data.append(d)
    return success_response(data=data)


@bp.route('/api/v2/scep/profiles', methods=['POST'])
@require_auth(['write:scep'])
def create_scep_profile():
    """Create a SCEP profile served at /scep/<url_slug>/pkiclient.exe."""
    from models import ScepProfile
    data = request.json or {}
    ok, err = _validate_profile_payload(data)
    if not ok:
        return error_response(err, 400)

    profile = ScepProfile(
        name=data['name'],
        url_slug=data['url_slug'],
        description=(data.get('description') or '')[:255],
        enabled=bool(data.get('enabled', True)),
        ca_refid=data['ca_refid'],
        template_id=data.get('template_id') or None,
        auto_approve=bool(data.get('auto_approve', False)),
        created_by=getattr(g.current_user, 'username', None),
    )
    _apply_challenge(profile, (data.get('challenge_password') or '').strip())
    db.session.add(profile)
    ok, _err = safe_commit(logger, "Failed to create SCEP profile")
    if not ok:
        return _err

    AuditService.log_action(
        action='scep_profile_create',
        resource_type='scep',
        resource_id=str(profile.id),
        resource_name=profile.name,
        details=f'Created SCEP profile {profile.name} (/scep/{profile.url_slug}/)',
        success=True,
    )
    return success_response(data=profile.to_dict(),
                            message='SCEP profile created')


@bp.route('/api/v2/scep/profiles/<int:profile_id>', methods=['PUT', 'PATCH'])
@require_auth(['write:scep'])
def update_scep_profile(profile_id):
    from models import ScepProfile
    profile = db.session.get(ScepProfile, profile_id)
    if not profile:
        return error_response('Profile not found', 404)

    data = request.json or {}
    ok, err = _validate_profile_payload(data, partial=True, profile_id=profile_id)
    if not ok:
        return error_response(err, 400)

    if 'name' in data:
        profile.name = data['name']
    if 'url_slug' in data:
        profile.url_slug = data['url_slug']
    if 'description' in data:
        profile.description = (data.get('description') or '')[:255]
    if 'enabled' in data:
        profile.enabled = bool(data['enabled'])
    if 'ca_refid' in data:
        profile.ca_refid = data['ca_refid']
    if 'template_id' in data:
        profile.template_id = data.get('template_id') or None
    if 'auto_approve' in data:
        profile.auto_approve = bool(data['auto_approve'])
    if 'challenge_password' in data:
        _apply_challenge(profile, (data.get('challenge_password') or '').strip())
    profile.updated_by = getattr(g.current_user, 'username', None)

    ok, _err = safe_commit(logger, "Failed to update SCEP profile")
    if not ok:
        return _err

    AuditService.log_action(
        action='scep_profile_update',
        resource_type='scep',
        resource_id=str(profile.id),
        resource_name=profile.name,
        details=f'Updated SCEP profile {profile.name}',
        success=True,
    )
    return success_response(data=profile.to_dict(),
                            message='SCEP profile updated')


@bp.route('/api/v2/scep/profiles/<int:profile_id>', methods=['DELETE'])
@require_auth(['write:scep'])
def delete_scep_profile(profile_id):
    from models import ScepProfile
    profile = db.session.get(ScepProfile, profile_id)
    if not profile:
        return error_response('Profile not found', 404)

    name = profile.name
    try:
        db.session.delete(profile)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete SCEP profile: {e}')
        return error_response('Failed to delete SCEP profile', 500)

    AuditService.log_action(
        action='scep_profile_delete',
        resource_type='scep',
        resource_id=str(profile_id),
        resource_name=name,
        details=f'Deleted SCEP profile {name}',
        success=True,
    )
    return success_response(message='SCEP profile deleted')


@bp.route('/api/v2/scep/profiles/<int:profile_id>/challenge/regenerate', methods=['POST'])
@require_auth(['write:scep'])
def regenerate_scep_profile_challenge(profile_id):
    """Generate a fresh challenge for the profile; returned once."""
    from models import ScepProfile
    profile = db.session.get(ScepProfile, profile_id)
    if not profile:
        return error_response('Profile not found', 404)

    new_challenge = secrets.token_urlsafe(24)
    _apply_challenge(profile, new_challenge)
    profile.updated_by = getattr(g.current_user, 'username', None)
    ok, _err = safe_commit(logger, "Failed to regenerate profile challenge")
    if not ok:
        return _err

    AuditService.log_action(
        action='scep_profile_challenge_regenerate',
        resource_type='scep',
        resource_id=str(profile.id),
        resource_name=profile.name,
        details=f'Regenerated challenge for SCEP profile {profile.name}',
        success=True,
    )
    return success_response(data={'challenge': new_challenge},
                            message='Challenge password regenerated')
