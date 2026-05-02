"""ACME External Account Binding (EAB) routes (RFC 8555 §7.3.4)

Pre-shared HMAC credentials issued by UCM admins so external ACME
clients (cert-manager, certbot, lego...) can register an account on
the local ACME server. Single-use by design — once an account binds
to a credential it transitions to ``used``.
"""
import base64

from flask import request, g
from models import db, AcmeEabCredential, SystemConfig
from services.audit_service import AuditService
from auth.unified import require_auth
from utils.response import success_response, error_response

from . import bp, logger


def _eab_required_value():
    cfg = SystemConfig.query.filter_by(key='acme_eab_required').first()
    return (cfg.value if cfg else 'false').lower() == 'true'


@bp.route('/api/v2/acme/eab-required', methods=['GET'])
@require_auth(['read:acme'])
def get_eab_required():
    return success_response(data={'eab_required': _eab_required_value()})


@bp.route('/api/v2/acme/eab-required', methods=['PUT', 'PATCH'])
@require_auth(['write:acme'])
def set_eab_required():
    data = request.get_json() or {}
    value = bool(data.get('eab_required', False))
    cfg = SystemConfig.query.filter_by(key='acme_eab_required').first()
    if cfg:
        cfg.value = 'true' if value else 'false'
    else:
        db.session.add(SystemConfig(
            key='acme_eab_required',
            value='true' if value else 'false',
            description='Require External Account Binding for new ACME account registration'
        ))
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set acme_eab_required: {e}")
        return error_response('Failed to update setting', 500)

    AuditService.log_action(
        action='acme.eab_required.update',
        resource_type='system_config',
        resource_id='acme_eab_required',
        details=f'EAB required set to {value}'
    )
    return success_response(data={'eab_required': value})


@bp.route('/api/v2/acme/eab-credentials', methods=['GET'])
@require_auth(['read:acme'])
def list_eab_credentials():
    """List EAB credentials.

    HMAC keys are NEVER returned here — only on the create endpoint, once.
    """
    status_filter = request.args.get('status')
    q = AcmeEabCredential.query
    if status_filter:
        q = q.filter_by(status=status_filter)
    creds = q.order_by(AcmeEabCredential.created_at.desc()).limit(200).all()
    return success_response(data=[c.to_dict() for c in creds])


@bp.route('/api/v2/acme/eab-credentials', methods=['POST'])
@require_auth(['write:acme'])
def create_eab_credential():
    """Generate a new EAB credential.

    The HMAC key is returned in plain text **only in this response** —
    after this, only its base64 form is stored server-side. Show it once
    in the UI and let the user copy it to their ACME client config.
    """
    import secrets as _secrets
    from datetime import datetime, timedelta

    data = request.get_json() or {}
    label = (data.get('label') or '').strip()[:255] or None
    expires_in_days = data.get('expires_in_days')

    expires_at = None
    if expires_in_days is not None:
        try:
            days = int(expires_in_days)
            if days > 0:
                expires_at = datetime.utcnow() + timedelta(days=days)
        except (TypeError, ValueError):
            return error_response('expires_in_days must be a positive integer', 400)

    # 16-byte kid (URL-safe), 32-byte HMAC secret (256-bit), URL-safe base64 encoded
    # without padding — RFC 8555 §7.3.4 only specifies HMAC, doesn't mandate length.
    kid = _secrets.token_urlsafe(16)
    hmac_raw = _secrets.token_bytes(32)
    hmac_b64 = base64.urlsafe_b64encode(hmac_raw).rstrip(b'=').decode('ascii')

    user_id = getattr(g, 'user_id', None) or (getattr(g, 'current_user', None).id if getattr(g, 'current_user', None) else None)

    cred = AcmeEabCredential(
        kid=kid,
        hmac_key_b64=hmac_b64,
        label=label,
        created_by_user_id=user_id,
        expires_at=expires_at,
        status='active'
    )
    db.session.add(cred)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create EAB credential: {e}")
        return error_response('Failed to create EAB credential', 500)

    AuditService.log_action(
        action='acme.eab_credential.create',
        resource_type='acme_eab_credential',
        resource_id=str(cred.id),
        details=f'Created EAB credential kid={kid} label={label or "(none)"}'
    )

    payload = cred.to_dict(include_secret=True)
    payload['hmac_key'] = hmac_b64
    return success_response(data=payload, message='EAB credential created', status=201)


@bp.route('/api/v2/acme/eab-credentials/<int:cred_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_eab_credential(cred_id):
    cred = AcmeEabCredential.query.get(cred_id)
    if not cred:
        return error_response('EAB credential not found', 404)
    return success_response(data=cred.to_dict())


@bp.route('/api/v2/acme/eab-credentials/<int:cred_id>', methods=['DELETE'])
@require_auth(['delete:acme'])
def revoke_eab_credential(cred_id):
    """Revoke an EAB credential.

    We mark it ``revoked`` rather than hard-delete so audit / UI history
    keeps the binding visible. The credential becomes unusable
    immediately for future registrations.
    """
    from utils.datetime_utils import utc_now as _utc_now
    cred = AcmeEabCredential.query.get(cred_id)
    if not cred:
        return error_response('EAB credential not found', 404)
    if cred.status == 'revoked':
        return success_response(data=cred.to_dict(), message='Already revoked')

    user_id = getattr(g, 'user_id', None) or (getattr(g, 'current_user', None).id if getattr(g, 'current_user', None) else None)

    cred.status = 'revoked'
    cred.revoked_at = _utc_now()
    cred.revoked_by_user_id = user_id
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to revoke EAB credential {cred_id}: {e}")
        return error_response('Failed to revoke EAB credential', 500)

    AuditService.log_action(
        action='acme.eab_credential.revoke',
        resource_type='acme_eab_credential',
        resource_id=str(cred_id),
        details=f'Revoked EAB credential kid={cred.kid}'
    )
    return success_response(data=cred.to_dict(), message='EAB credential revoked')
