"""
SCEP Management Routes v2.0
/api/scep/* - SCEP configuration and requests
"""

from utils.signing_ca import signing_ca_problem
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


def _issuing_service(scep_req):
    """The service that issues for a stored request: with the template of
    the profile the request came through (its validity and key usages
    govern, as on auto-approval), the CA defaults for the global endpoint.
    A profile disabled meanwhile still governs the requests it received:
    the operator approving is the authority here. Raises LookupError when
    that profile or its template no longer exists."""
    from services.scep.scep_service import SCEPService
    template = None
    if scep_req.profile_id:
        from models.scep import ScepProfile
        profile = db.session.get(ScepProfile, scep_req.profile_id)
        if profile is None:
            raise LookupError('The SCEP profile this request came through no longer exists')
        if profile.template_id:
            from models import CertificateTemplate
            template = db.session.get(CertificateTemplate, profile.template_id)
            if template is None:
                raise LookupError('The template bound to the SCEP profile no longer exists')
    return SCEPService(ca_refid=scep_req.ca_refid, template=template, profile_id=scep_req.profile_id)


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
    # Approving means issuing: the client polls for the certificate, and a
    # request flipped to "approved" without one stayed PENDING for it forever
    try:
        cert_refid = _issuing_service(scep_req).approve_request(
            scep_req.transaction_id, username,
        )
    except LookupError as e:
        # The profile or template the request was made under is gone
        db.session.rollback()
        logger.warning(f"SCEP approve: request {request_id} cannot be issued: {e}")
        return error_response(str(e), 409)
    except ValueError as e:
        # The CA refused (offline, revoked, outside its signing window, name
        # constraints...): the approver needs the reason
        db.session.rollback()
        logger.warning(f"SCEP approve: issuance refused for request {request_id}: {e}")
        return error_response(str(e), 409)
    except Exception as e:
        logger.error(f"SCEP approve: issuance failed for request {request_id}: {e}", exc_info=True)
        db.session.rollback()
        return error_response('Failed to issue the certificate for this request', 500)
    if not cert_refid:
        db.session.rollback()
        return error_response('Failed to issue the certificate for this request', 500)
    db.session.refresh(scep_req)
    try:
        from models import Certificate as _Certificate
        from services.webhook_service import emit_cert_issued
        issued = _Certificate.query.filter_by(refid=cert_refid).first()
        if issued is not None:
            emit_cert_issued(issued.to_dict(), ca_refid=issued.caref)
    except Exception as e:
        logger.error(f"Webhook emit (SCEP approval) failed: {e}")
    
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
            ca = CA.query.filter_by(refid=str(data['ca_refid'])).first()
        elif data.get('ca_id'):
            ca = db.session.get(CA, data['ca_id'])
        if not ca:
            return False, 'CA not found'
        saved = db.session.get(ScepProfile, profile_id) if profile_id else None
        if not (saved is not None and saved.ca_refid == ca.refid) and signing_ca_problem(ca):
            return False, f'Selected CA cannot sign: {signing_ca_problem(ca)}'
        if not ca.has_private_key:
            return False, 'Selected CA has no private key'
        if ca.uses_hsm:
            return False, ('Selected CA is HSM-backed: SCEP requires RSA '
                           'envelope decryption, unavailable for HSM keys')
        data['ca_refid'] = ca.refid

    template_ref = data.get('template_id') if 'template_id' in data else None
    if 'template_id' not in data and partial and profile_id and 'intune_enabled' in data:
        # Turning Intune validation off re-validates the bound template
        # (Smartcard Logon is only tolerated with it)
        saved_profile = db.session.get(ScepProfile, profile_id)
        template_ref = saved_profile.template_id if saved_profile else None
    if template_ref:
        tpl = db.session.get(CertificateTemplate, template_ref)
        if not tpl:
            return False, 'Template not found'
        if tpl.template_type == 'ca':
            return False, 'CA templates cannot be used for SCEP profiles'
        # Same rule as ACME profiles: a template must not hand a SCEP
        # enrollee (a challenge password, at most an Intune check) an EKU
        # that grants authority over the PKI or an identity of its choosing
        from services.template_service import template_extensions
        from utils.eku_validation import PROTOCOL_UNBINDABLE_EKU_OIDS, normalize_extra_ekus
        ekus = template_extensions(tpl).get('extended_key_usage')
        if isinstance(ekus, list) and ekus:
            oids, err = normalize_extra_ekus(ekus)
            if err:
                return False, f'Template has invalid EKUs: {err}'
            # Smartcard Logon is tolerated when Intune validates the
            # requester (resulting state of the profile)
            saved = db.session.get(ScepProfile, profile_id) if (partial and profile_id) else None
            intune_on = (bool(data.get('intune_enabled')) if 'intune_enabled' in data
                         else bool(saved and saved.intune_enabled))
            tolerated = {'1.3.6.1.4.1.311.20.2.2'} if intune_on else set()
            refused = sorted((set(oids) & PROTOCOL_UNBINDABLE_EKU_OIDS) - tolerated)
            if refused:
                return False, (
                    f"Template EKU {', '.join(refused)} cannot be issued over SCEP"
                    + ('' if intune_on else ' (Smartcard Logon requires Intune validation)')
                )

    # Intune SCEP challenge validation (issue #228 part 2): validate against
    # the RESULTING state, not just what this payload touches — a partial
    # PATCH that only flips intune_enabled=True must still be checked against
    # whatever auto_approve/tenant/client already exist on the row.
    if 'intune_enabled' in data or 'auto_approve' in data or not partial:
        existing = db.session.get(ScepProfile, profile_id) if (partial and profile_id) else None
        resulting_intune_enabled = (
            bool(data['intune_enabled']) if 'intune_enabled' in data
            else bool(existing.intune_enabled) if existing else False
        )
        resulting_auto_approve = (
            bool(data['auto_approve']) if 'auto_approve' in data
            else bool(existing.auto_approve) if existing else bool(data.get('auto_approve', False))
        )
        if resulting_intune_enabled and not resulting_auto_approve:
            return False, ('Intune SCEP challenge validation requires auto-approve '
                            '. Intune expects a synchronous validate-then-issue '
                            'response, not a manual approval queue')
        if resulting_intune_enabled:
            try:
                app, err = _intune_app_for(data, existing, dry_run=True)
            except IntuneAppConflict as conflict:
                return False, (str(conflict), 409)
            if err:
                return False, err

    return True, None


class IntuneAppConflict(Exception):
    """The pre-092 trio names credentials that clash with a registration on
    file: answered 409, never a silent overwrite nor a duplicate."""


def _intune_app_for(data, existing, dry_run=False):
    """The app registration a profile payload names: `intune_app_id`, or the
    pre-092 trio (tenant, client, secret) which finds or creates an app named
    after the profile. Returns (app, error); `dry_run` only validates. Raises
    IntuneAppConflict when the trio contradicts a registration on file."""
    from models import IntuneApp
    if 'intune_app_id' in data:
        app_id = data.get('intune_app_id')
        if not app_id:
            return None, 'Intune SCEP challenge validation requires an app registration'
        app = db.session.get(IntuneApp, app_id)
        if app is None:
            return None, 'Intune app registration not found'
        return app, None
    tenant = (data.get('intune_tenant_id') or '').strip()
    client = (data.get('intune_client_id') or '').strip()
    secret = (data.get('intune_client_secret') or '').strip()
    bound = existing.intune_app if existing is not None else None
    if not any((tenant, client, secret)):
        if bound is not None:
            return bound, None
        return None, 'Intune SCEP challenge validation requires an app registration'
    if bound is not None:
        # The pre-092 PATCH edited the profile's own credentials: it now edits
        # the app the profile is bound to, fields left out keep their value
        tenant, client = tenant or bound.tenant_id, client or bound.client_id
        if dry_run:
            return bound, None
        from utils.encryption import encrypt_value
        bound.tenant_id, bound.client_id = tenant, client
        if secret:
            bound.client_secret = encrypt_value(secret)
        return bound, None
    if not tenant or not client:
        return None, 'Intune SCEP challenge validation requires a tenant ID and client ID'
    candidates = IntuneApp.query.filter_by(tenant_id=tenant, client_id=client).all()
    if secret:
        app = next((c for c in candidates if c.decrypted_secret() == secret), None)
        if app is None and candidates:
            raise IntuneAppConflict(
                f"An app registration for this tenant and client ID already exists "
                f"({candidates[0].name}) with a different secret: pick it with "
                f"intune_app_id, or update its secret under SCEP > Intune app registrations")
    elif len(candidates) > 1:
        raise IntuneAppConflict(
            "Several app registrations exist for this tenant and client ID: pick one "
            "with intune_app_id")
    else:
        app = candidates[0] if candidates else None
    if app is None and not secret:
        return None, 'Intune SCEP challenge validation requires a client secret'
    if dry_run:
        return app, None
    if app is None:
        from utils.encryption import encrypt_value
        wanted = (data.get('name') or (existing.name if existing else None) or 'Intune')[:100]
        name, n = wanted, 2
        while IntuneApp.query.filter_by(name=name).first() is not None:
            suffix = f' ({n})'
            name, n = wanted[:100 - len(suffix)] + suffix, n + 1
        app = IntuneApp(name=name, tenant_id=tenant, client_id=client,
                        client_secret=encrypt_value(secret),
                        created_by=getattr(g.current_user, 'username', None))
        db.session.add(app)
        db.session.flush()
    elif secret:
        from utils.encryption import encrypt_value
        app.client_secret = encrypt_value(secret)
    return app, None


def _profile_error(err):
    """A validation error is a message, or (message, status) for a 409."""
    if isinstance(err, tuple):
        return error_response(err[0], err[1])
    return error_response(err, 400)


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
        return _profile_error(err)

    profile = ScepProfile(
        name=data['name'],
        url_slug=data['url_slug'],
        description=(data.get('description') or '')[:255],
        enabled=bool(data.get('enabled', True)),
        ca_refid=data['ca_refid'],
        template_id=data.get('template_id') or None,
        auto_approve=bool(data.get('auto_approve', False)),
        intune_enabled=bool(data.get('intune_enabled', False)),
        created_by=getattr(g.current_user, 'username', None),
    )
    _apply_challenge(profile, (data.get('challenge_password') or '').strip())
    if profile.intune_enabled or data.get('intune_app_id'):
        try:
            app, err = _intune_app_for(data, None)
        except IntuneAppConflict as conflict:
            return error_response(str(conflict), 409)
        if err:
            return error_response(err, 400)
        profile.intune_app = app
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
        return _profile_error(err)

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
    if 'intune_enabled' in data:
        profile.intune_enabled = bool(data['intune_enabled'])
    names_app = any(key in data for key in (
        'intune_app_id', 'intune_tenant_id', 'intune_client_id', 'intune_client_secret'))
    if names_app or (profile.intune_enabled and profile.intune_app is None):
        if 'intune_app_id' in data and not data.get('intune_app_id') and not profile.intune_enabled:
            profile.intune_app = None
        else:
            try:
                app, err = _intune_app_for(data, profile)
            except IntuneAppConflict as conflict:
                return error_response(str(conflict), 409)
            if err:
                return error_response(err, 400)
            profile.intune_app = app
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


# ---- Intune app registrations (issue #358): defined once, picked per profile

def _test_intune_credentials(tenant_id, client_id, client_secret):
    """Token acquisition and service discovery only: no device, no CSR, no
    Intune challenge spent."""
    from services.scep.intune_client import IntuneScepClient
    try:
        IntuneScepClient(tenant_id=tenant_id, client_id=client_id,
                         client_secret=client_secret).test_connection()
        return {'success': True, 'message': 'Connected to Intune successfully'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


def _record_intune_test(app, result):
    from utils.datetime_utils import utc_now
    app.last_test_at = utc_now()
    app.last_test_result = 'success' if result['success'] else f"failed: {result['message']}"
    safe_commit(logger, 'Failed to record Intune connection test result')


def _audit_intune_app(action, app, details):
    AuditService.log_action(
        action=action, resource_type='scep', resource_id=str(app.id),
        resource_name=app.name, details=details, success=True)


@bp.route('/api/v2/scep/intune-apps', methods=['GET'])
@require_auth(['read:scep'])
def list_intune_apps():
    """Every app registration, secrets never returned."""
    from models import IntuneApp
    apps = IntuneApp.query.order_by(IntuneApp.name).all()
    return success_response(data=[a.to_dict() for a in apps])


def _intune_app_payload(data, existing=None):
    name = (data.get('name') or (existing.name if existing else '')).strip()
    tenant = (data.get('tenant_id') if 'tenant_id' in data
              else (existing.tenant_id if existing else '')) or ''
    client = (data.get('client_id') if 'client_id' in data
              else (existing.client_id if existing else '')) or ''
    tenant, client = tenant.strip(), client.strip()
    if not name:
        return None, 'Name is required'
    if not tenant or not client:
        return None, 'Tenant ID and client ID are required'
    return {'name': name[:100], 'tenant_id': tenant[:255], 'client_id': client[:255]}, None


@bp.route('/api/v2/scep/intune-apps', methods=['POST'])
@require_auth(['write:scep'])
def create_intune_app():
    from models import IntuneApp
    from utils.encryption import encrypt_value
    data = request.json or {}
    fields, err = _intune_app_payload(data)
    if err:
        return error_response(err, 400)
    secret = (data.get('client_secret') or '').strip()
    if not secret:
        return error_response('Client secret is required', 400)
    if IntuneApp.query.filter_by(name=fields['name']).first():
        return error_response('An app registration with this name already exists', 409)
    twin = IntuneApp.query.filter_by(tenant_id=fields['tenant_id'],
                                     client_id=fields['client_id']).first()
    if twin:
        return error_response(
            f'An app registration for this tenant and client ID already exists: {twin.name}', 409)
    app = IntuneApp(**fields, client_secret=encrypt_value(secret),
                    created_by=getattr(g.current_user, 'username', None))
    db.session.add(app)
    ok, _err = safe_commit(logger, 'Failed to create Intune app registration')
    if not ok:
        return _err
    _audit_intune_app('intune_app_create', app,
                      f'Created Intune app registration {app.name} (tenant {app.tenant_id})')
    return success_response(data=app.to_dict(), message='Intune app registration created')


@bp.route('/api/v2/scep/intune-apps/<int:app_id>', methods=['PUT', 'PATCH'])
@require_auth(['write:scep'])
def update_intune_app(app_id):
    from models import IntuneApp
    from utils.encryption import encrypt_value
    app = db.session.get(IntuneApp, app_id)
    if not app:
        return error_response('Intune app registration not found', 404)
    data = request.json or {}
    fields, err = _intune_app_payload(data, app)
    if err:
        return error_response(err, 400)
    clash = IntuneApp.query.filter(IntuneApp.name == fields['name'], IntuneApp.id != app.id).first()
    if clash:
        return error_response('An app registration with this name already exists', 409)
    twin = IntuneApp.query.filter(IntuneApp.tenant_id == fields['tenant_id'],
                                  IntuneApp.client_id == fields['client_id'],
                                  IntuneApp.id != app.id).first()
    if twin and (fields['tenant_id'], fields['client_id']) != (app.tenant_id, app.client_id):
        return error_response(
            f'An app registration for this tenant and client ID already exists: {twin.name}', 409)
    changed = [key for key, value in fields.items() if getattr(app, key) != value]
    for key, value in fields.items():
        setattr(app, key, value)
    # A blank secret leaves the stored one alone: the masked field never
    # round-trips the real value back to the form
    secret = (data.get('client_secret') or '').strip()
    if secret:
        app.client_secret = encrypt_value(secret)
        changed.append('client_secret')
    app.updated_by = getattr(g.current_user, 'username', None)
    ok, _err = safe_commit(logger, 'Failed to update Intune app registration')
    if not ok:
        return _err
    _audit_intune_app('intune_app_update', app,
                      f"Updated Intune app registration {app.name}; changed fields: "
                      f"{', '.join(changed) if changed else 'none'}")
    return success_response(data=app.to_dict(), message='Intune app registration updated')


@bp.route('/api/v2/scep/intune-apps/<int:app_id>', methods=['DELETE'])
@require_auth(['write:scep'])
def delete_intune_app(app_id):
    from models import IntuneApp
    from services.deletion_blockers import first_blocker, intune_app_deletion_blockers
    app = db.session.get(IntuneApp, app_id)
    if not app:
        return error_response('Intune app registration not found', 404)
    blocker = first_blocker(intune_app_deletion_blockers(app))
    if blocker:
        return error_response(blocker.message, blocker.status)
    name = app.name
    try:
        db.session.delete(app)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete Intune app registration: {e}')
        return error_response('Failed to delete Intune app registration', 500)
    AuditService.log_action(
        action='intune_app_delete', resource_type='scep', resource_id=str(app_id),
        resource_name=name, details=f'Deleted Intune app registration {name}', success=True)
    return success_response(message='Intune app registration deleted')


@bp.route('/api/v2/scep/intune-apps/test', methods=['POST'])
@require_auth(['write:scep'])
def test_intune_app():
    """Test an app registration: unsaved form values, or a saved app by
    `app_id` whose stored secret is used when the field was left blank."""
    from models import IntuneApp
    data = request.json or {}
    app = db.session.get(IntuneApp, data.get('app_id')) if data.get('app_id') else None
    if data.get('app_id') and app is None:
        return error_response('Intune app registration not found', 404)
    tenant = (data.get('tenant_id') or (app.tenant_id if app else '')).strip()
    client = (data.get('client_id') or (app.client_id if app else '')).strip()
    secret = (data.get('client_secret') or '').strip() or (app.decrypted_secret() if app else '')
    if not tenant or not client or not secret:
        return error_response('Tenant ID, client ID and client secret are all required', 400)
    result = _test_intune_credentials(tenant, client, secret)
    if app:
        _record_intune_test(app, result)
        _audit_intune_app('intune_app_test', app,
                          f"Tested Intune app registration {app.name}: {app.last_test_result}")
    if result['success']:
        return success_response(data=result, message=result['message'])
    return error_response(result['message'], 400)


@bp.route('/api/v2/scep/profiles/test-intune-connection', methods=['POST'])
@require_auth(['write:scep'])
def test_intune_connection():
    """Pre-092 shape, kept for one release: the profile's app, or the trio."""
    from models import IntuneApp, ScepProfile
    data = request.json or {}
    profile = db.session.get(ScepProfile, data.get('profile_id')) if data.get('profile_id') else None
    app = profile.intune_app if profile else None
    if data.get('intune_app_id'):
        app = db.session.get(IntuneApp, data['intune_app_id'])
    tenant = (data.get('intune_tenant_id') or (app.tenant_id if app else '')).strip()
    client = (data.get('intune_client_id') or (app.client_id if app else '')).strip()
    secret = (data.get('intune_client_secret') or '').strip() or (app.decrypted_secret() if app else '')
    if not tenant or not client or not secret:
        return error_response('Tenant ID, client ID and client secret are all required', 400)
    result = _test_intune_credentials(tenant, client, secret)
    if app and tenant == app.tenant_id and client == app.client_id:
        _record_intune_test(app, result)
    if result['success']:
        return success_response(data=result, message=result['message'])
    return error_response(result['message'], 400)


@bp.route('/api/v2/scep/profiles/<int:profile_id>', methods=['DELETE'])
@require_auth(['write:scep'])
def delete_scep_profile(profile_id):
    from models import ScepProfile
    profile = db.session.get(ScepProfile, profile_id)
    if not profile:
        return error_response('Profile not found', 404)

    # A pending request is approved with its profile's template: the
    # profile stays until those requests are decided
    pending = SCEPRequest.query.filter_by(profile_id=profile_id, status='pending').count()
    if pending:
        return error_response(
            f'Cannot delete: {pending} pending request(s) came through this profile; '
            f'approve or reject them first', 409)

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
