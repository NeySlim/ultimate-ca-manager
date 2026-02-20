"""
mTLS API
Manage client certificates and mTLS configuration
"""

import logging
from flask import Blueprint, request, g, Response
from auth.unified import require_auth
from models import User, Certificate, CA, SystemConfig, db
from services.audit_service import AuditService
from utils.response import success_response, error_response
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

bp = Blueprint('mtls', __name__, url_prefix='/api/v2/mtls')


# ---------------------------------------------------------------------------
# mTLS Settings (admin only)
# ---------------------------------------------------------------------------

def _get_mtls_config(key, default=None):
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def _set_mtls_config(key, value):
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


@bp.route('/settings', methods=['GET'])
@require_auth(['read:settings'])
def get_mtls_settings():
    """Get mTLS configuration"""
    enabled = _get_mtls_config('mtls_enabled', 'false') == 'true'
    required = _get_mtls_config('mtls_required', 'false') == 'true'
    ca_id = _get_mtls_config('mtls_trusted_ca_id')

    ca_info = None
    if ca_id:
        ca = CA.query.filter_by(refid=ca_id).first()
        if ca:
            ca_info = {
                'refid': ca.refid,
                'name': ca.descr,
                'valid_to': ca.valid_to.isoformat() if ca.valid_to else None,
                'has_private_key': ca.has_private_key,
            }

    return success_response(data={
        'enabled': enabled,
        'required': required,
        'trusted_ca_id': ca_id,
        'trusted_ca': ca_info,
    })


@bp.route('/settings', methods=['PUT'])
@require_auth(['admin:system'])
def update_mtls_settings():
    """Update mTLS configuration. Requires UCM restart to take effect."""
    data = request.get_json()
    if not data:
        return error_response('No data provided', 400)

    enabled = data.get('enabled')
    required = data.get('required')
    ca_id = data.get('trusted_ca_id')

    # Validate CA if enabling mTLS
    if enabled and ca_id:
        ca = CA.query.filter_by(refid=ca_id).first()
        if not ca:
            return error_response('Trusted CA not found', 404)

    # Safety: if requiring mTLS, check at least one admin has an enrolled cert
    if required and enabled:
        from models.auth_certificate import AuthCertificate
        admin_users = User.query.filter_by(role='admin', active=True).all()
        admin_ids = [u.id for u in admin_users]
        admin_certs = AuthCertificate.query.filter(
            AuthCertificate.user_id.in_(admin_ids),
            AuthCertificate.enabled == True
        ).count() if admin_ids else 0
        if admin_certs == 0:
            return error_response(
                'Cannot require mTLS: no admin user has an enrolled certificate. '
                'Enroll at least one admin certificate first.',
                400
            )

    changes = []
    if enabled is not None:
        _set_mtls_config('mtls_enabled', 'true' if enabled else 'false')
        changes.append(f"enabled={'true' if enabled else 'false'}")
    if required is not None:
        _set_mtls_config('mtls_required', 'true' if required else 'false')
        changes.append(f"required={'true' if required else 'false'}")
    if ca_id is not None:
        _set_mtls_config('mtls_trusted_ca_id', ca_id)
        changes.append(f"trusted_ca_id={ca_id}")

    db.session.commit()

    AuditService.log_action(
        action='mtls_settings_update',
        resource_type='settings',
        resource_name='mTLS',
        details=f'Updated mTLS settings: {", ".join(changes)}',
        success=True
    )

    # Trigger restart if mTLS config changed (SSL context needs reload)
    needs_restart = enabled is not None or required is not None or ca_id is not None
    restart_message = None
    if needs_restart:
        from config.settings import is_docker, restart_ucm_service
        if is_docker():
            restart_message = 'Restart the container to apply mTLS changes.'
        else:
            success, msg = restart_ucm_service()
            restart_message = msg if not success else 'Service restart initiated to apply mTLS changes.'

    return success_response(
        data={
            'enabled': _get_mtls_config('mtls_enabled', 'false') == 'true',
            'required': _get_mtls_config('mtls_required', 'false') == 'true',
            'trusted_ca_id': _get_mtls_config('mtls_trusted_ca_id'),
            'needs_restart': needs_restart,
            'restart_message': restart_message,
        },
        message='mTLS settings updated'
    )


@bp.route('/certificates', methods=['GET'])
@require_auth()
def list_mtls_certificates():
    """List user's mTLS certificates (certificates with clientAuth EKU)"""
    user = g.current_user
    
    # Get certificates issued for this user (CN contains username@mtls)
    mtls_certs = Certificate.query.filter(
        Certificate.subject.like(f'%CN={user.username}@mtls%')
    ).order_by(Certificate.created_at.desc()).all()
    
    result = []
    for cert in mtls_certs:
        result.append({
            'id': cert.id,
            'name': f'mTLS Certificate #{cert.id}',
            'serial': cert.serial_number,
            'subject': cert.subject,
            'created_at': cert.created_at.isoformat() if cert.created_at else None,
            'expires_at': cert.not_after.isoformat() if cert.not_after else None,
            'status': cert.status,
            'ca_id': cert.ca_id
        })
    
    return success_response(data=result)


@bp.route('/certificates', methods=['POST'])
@require_auth()
def create_mtls_certificate():
    """Issue a new mTLS certificate for the user"""
    user = g.current_user
    data = request.get_json() or {}
    
    # Get CA for issuing
    ca_id = data.get('ca_id')
    if not ca_id:
        # Use first available CA
        ca = CA.query.first()
        if not ca:
            return error_response('No CA available', 400)
        ca_id = ca.id
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Create client certificate
    from services.certificate_service import CertificateService
    cert_service = CertificateService()
    
    # Build subject
    subject = {
        'CN': f'{user.username}@mtls',
        'O': data.get('organization', 'UCM Users'),
        'OU': 'mTLS Clients'
    }
    
    validity_days = data.get('validity_days', 365)
    
    try:
        # Issue certificate
        cert_data = cert_service.issue_certificate(
            ca_id=ca_id,
            subject=subject,
            key_type='RSA',
            key_size=2048,
            validity_days=validity_days,
            key_usage=['digitalSignature', 'keyEncipherment'],
            extended_key_usage=['clientAuth']
        )
        
        AuditService.log_action(
            action='mtls_cert_create',
            resource_type='certificate',
            resource_id=str(cert_data['id']),
            resource_name=f'{user.username}@mtls',
            details=f'Created mTLS certificate for user: {user.username}',
            success=True
        )
        
        return success_response(data={
                'id': cert_data['id'],
                'serial': cert_data.get('serial', ''),
                'certificate': cert_data.get('pem', ''),
                'private_key': cert_data.get('private_key', ''),
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': cert_data.get('not_after', ''),
                'status': 'valid'
            }, message='mTLS certificate created'), 201
        
    except Exception as e:
        logger.error(f'mTLS error: {e}')
        return error_response('Internal error', 500)


@bp.route('/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth()
def revoke_mtls_certificate(cert_id):
    """Revoke a mTLS certificate"""
    user = g.current_user
    
    # Find certificate and verify ownership
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    # Verify ownership (CN should contain username@mtls)
    if f'{user.username}@mtls' not in (cert.subject or ''):
        return error_response('Not authorized to revoke this certificate', 403)
    
    # Revoke the certificate
    cert.status = 'revoked'
    cert.revoked_at = datetime.now(timezone.utc)
    cert.revocation_reason = 'User requested'
    db.session.commit()
    
    AuditService.log_action(
        action='mtls_cert_revoke',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=f'{user.username}@mtls',
        details=f'Revoked mTLS certificate {cert_id} for user: {user.username}',
        success=True
    )
    
    return success_response(message='Certificate revoked')


@bp.route('/certificates/<int:cert_id>/download', methods=['GET'])
@require_auth()
def download_mtls_certificate(cert_id):
    """Download mTLS certificate as PKCS12"""
    user = g.current_user
    
    # Find certificate
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    # Verify ownership
    if f'{user.username}@mtls' not in (cert.subject or ''):
        return error_response('Not authorized', 403)
    
    # Check if we have the certificate PEM
    if not cert.certificate_pem:
        return error_response('Certificate data not available', 404)
    
    # For now, just return PEM format
    # TODO: Implement PKCS12 conversion if private key is stored
    return Response(
        cert.certificate_pem,
        mimetype='application/x-pem-file',
        headers={
            'Content-Disposition': f'attachment; filename=mtls-{cert_id}.pem'
        }
    )


@bp.route('/authenticate', methods=['POST'])
def authenticate():
    """Authenticate via mTLS client certificate"""
    # Get client certificate from request
    # This requires NGINX/Apache to pass the client cert in a header
    client_cert = request.headers.get('X-Client-Cert')
    client_cert_verify = request.headers.get('X-Client-Cert-Verify')
    
    if not client_cert or client_cert_verify != 'SUCCESS':
        return error_response('No valid client certificate', 401)
    
    # Parse certificate to get username
    # The CN should be in format: username@mtls
    import re
    match = re.search(r'CN=([^@,]+)@mtls', client_cert)
    if not match:
        return error_response('Invalid certificate subject', 401)
    
    username = match.group(1)
    
    # Find user
    user = User.query.filter_by(username=username).first()
    if not user:
        return error_response('User not found', 401)
    
    if not user.active:
        return error_response('Account disabled', 401)
    
    # Create session
    from flask import session
    session['user_id'] = user.id
    session.permanent = True
    
    return success_response(data=user.to_dict(), message='mTLS authentication successful')
