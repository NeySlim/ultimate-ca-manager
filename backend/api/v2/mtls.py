"""
mTLS API
Manage client certificates and mTLS configuration
"""
import base64
import logging
import re
from datetime import datetime, timezone

from flask import Blueprint, request, g, Response
from cryptography import x509 as cx509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from auth.unified import require_auth
from config.settings import is_docker, restart_ucm_service
from models import User, Certificate, CA, SystemConfig, db
from models.auth_certificate import AuthCertificate
from services.audit_service import AuditService
from services.cert_service import CertificateService
from services.certificate_parser import CertificateParser
from utils.file_naming import cert_key_path
from utils.response import success_response, error_response, created_response

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
        admin_users = User.query.filter_by(role='admin', active=True).all()
        admin_ids = [u.id for u in admin_users]
        admin_certs = AuthCertificate.query.filter(
            AuthCertificate.user_id.in_(admin_ids),
            AuthCertificate.enabled == True  # noqa: E712 — SQLAlchemy requires ==
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
    """List user's mTLS certificates (enrolled in auth_certificates)"""
    user = g.current_user

    certs = AuthCertificate.query.filter_by(user_id=user.id).order_by(
        AuthCertificate.created_at.desc()
    ).all()

    return success_response(data=[c.to_dict() for c in certs])


@bp.route('/certificates', methods=['POST'])
@require_auth()
def create_mtls_certificate():
    """Issue a new mTLS client certificate and auto-enroll it"""

    user = g.current_user
    data = request.get_json() or {}

    # Resolve CA — prefer request ca_id, fall back to trusted CA, then first available
    ca_id = data.get('ca_id')
    ca = None
    if ca_id:
        ca = CA.query.get(ca_id) or CA.query.filter_by(refid=str(ca_id)).first()
    if not ca:
        trusted_refid = _get_mtls_config('mtls_trusted_ca_id')
        if trusted_refid:
            ca = CA.query.filter_by(refid=trusted_refid).first()
    if not ca:
        ca = CA.query.first()
    if not ca:
        return error_response('No CA available', 400)

    validity_days = min(max(int(data.get('validity_days', 365)), 1), 3650)
    cert_name = data.get('name', f'{user.username} mTLS')

    # Sanitize organization field
    org = data.get('organization', 'UCM Users')
    if not re.match(r'^[a-zA-Z0-9\s\-\.]{1,64}$', org):
        return error_response('Invalid organization name', 400)

    try:
        cert_obj = CertificateService.create_certificate(
            descr=cert_name,
            caref=ca.refid,
            dn={
                'CN': f'{user.username}@mtls',
                'O': org,
                'OU': 'mTLS Clients',
            },
            cert_type='usr_cert',
            key_type='2048',
            validity_days=validity_days,
            username=user.username,
        )

        # Read back the PEM cert and key for the response
        cert_pem = base64.b64decode(cert_obj.crt).decode('utf-8') if cert_obj.crt else ''
        key_pem = ''
        key_file = cert_key_path(cert_obj)
        if key_file.exists():
            key_pem = key_file.read_text()

        # Enroll in auth_certificates for auto-login
        auth_cert = AuthCertificate(
            user_id=user.id,
            cert_serial=cert_obj.serial_number or '',
            cert_subject=cert_obj.subject or '',
            cert_issuer=cert_obj.issuer or '',
            cert_fingerprint='',
            name=cert_name,
            valid_from=cert_obj.valid_from,
            valid_until=cert_obj.valid_to,
            enabled=True,
        )
        db.session.add(auth_cert)
        db.session.commit()

        AuditService.log_action(
            action='mtls_cert_create',
            resource_type='certificate',
            resource_id=str(cert_obj.id),
            resource_name=cert_name,
            details=f'Created mTLS certificate for user: {user.username}',
            success=True,
        )

        return created_response(data={
            'id': cert_obj.id,
            'serial': cert_obj.serial_number or '',
            'certificate': cert_pem,
            'private_key': key_pem,
            'created_at': cert_obj.valid_from.isoformat() if cert_obj.valid_from else '',
            'expires_at': cert_obj.valid_to.isoformat() if cert_obj.valid_to else '',
            'status': 'valid',
        }, message='mTLS certificate created')

    except Exception as e:
        logger.error(f'mTLS cert creation error: {e}', exc_info=True)
        return error_response('Failed to create certificate', 500)


@bp.route('/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth()
def delete_mtls_certificate(cert_id):
    """Delete an enrolled mTLS certificate"""
    user = g.current_user

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    if auth_cert.user_id != user.id and getattr(user, 'role', '') != 'admin':
        return error_response('Not authorized', 403)

    serial = auth_cert.cert_serial
    db.session.delete(auth_cert)
    db.session.commit()

    AuditService.log_action(
        action='mtls_cert_delete',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=auth_cert.name or serial,
        details=f'Deleted mTLS certificate for user: {user.username}',
        success=True,
    )

    return success_response(message='Certificate deleted')


@bp.route('/certificates/<int:cert_id>/download', methods=['GET'])
@require_auth()
def download_mtls_certificate(cert_id):
    """Download mTLS certificate as PEM or PKCS12"""

    user = g.current_user
    fmt = request.args.get('format', 'pem')
    password = request.args.get('password', '')

    # Authorize via auth_certificates ownership (not string match on subject)
    auth_cert = AuthCertificate.query.filter_by(id=cert_id, user_id=user.id).first()
    if not auth_cert and getattr(user, 'role', '') != 'admin':
        return error_response('Certificate not found or not authorized', 404)
    if not auth_cert:
        auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    # Find the actual Certificate row by serial
    cert = Certificate.query.filter(
        Certificate.serial_number == auth_cert.cert_serial
    ).first()
    if not cert or not cert.crt:
        return error_response('Certificate data not available', 404)

    cert_pem = base64.b64decode(cert.crt)

    if fmt in ('p12', 'pkcs12'):
        if not password or len(password) < 8:
            return error_response('PKCS12 export requires a password of at least 8 characters', 400)
        if not cert.prv:
            return error_response('Private key not available for PKCS12 export', 400)

        key_pem = base64.b64decode(cert.prv)
        private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
        x509_cert = cx509.load_pem_x509_certificate(cert_pem, default_backend())

        # Build CA chain with cycle detection
        ca_certs = []
        if cert.caref:
            seen_cas = set()
            ca = CA.query.filter_by(refid=cert.caref).first()
            while ca and len(ca_certs) < 10:
                if ca.refid in seen_cas:
                    logger.warning(f"Circular CA reference detected: {ca.refid}")
                    break
                seen_cas.add(ca.refid)
                if ca.crt:
                    try:
                        ca_certs.append(cx509.load_pem_x509_certificate(
                            base64.b64decode(ca.crt), default_backend()
                        ))
                    except Exception as e:
                        logger.error(f"Failed to load CA cert {ca.refid}: {e}")
                        break
                ca = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None

        p12_bytes = pkcs12.serialize_key_and_certificates(
            name=f'{user.username}-mtls'.encode(),
            key=private_key,
            cert=x509_cert,
            cas=ca_certs if ca_certs else None,
            encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
        )

        AuditService.log_action(
            action='mtls_cert_download',
            resource_type='certificate',
            resource_id=str(cert_id),
            resource_name=auth_cert.name or str(cert_id),
            details=f'Downloaded certificate as PKCS12 by user: {user.username}',
            success=True,
        )

        return Response(
            p12_bytes,
            mimetype='application/x-pkcs12',
            headers={'Content-Disposition': f'attachment; filename="{user.username}-mtls.p12"'},
        )

    # Default: PEM
    AuditService.log_action(
        action='mtls_cert_download',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=auth_cert.name or str(cert_id),
        details=f'Downloaded certificate as PEM by user: {user.username}',
        success=True,
    )

    return Response(
        cert_pem,
        mimetype='application/x-pem-file',
        headers={'Content-Disposition': f'attachment; filename="{user.username}-mtls.pem"'},
    )


@bp.route('/enroll', methods=['POST'])
@require_auth()
def enroll_presented_certificate():
    """Enroll a client certificate already presented via mTLS.
    Used when user has a valid cert signed by the trusted CA but not yet enrolled."""

    user = g.current_user
    cert_info = None

    # Try to get the cert from the current TLS connection
    try:
        peercert = request.environ.get('peercert')
        if peercert:
            cert_info = CertificateParser.extract_from_flask_native(peercert)
    except Exception as e:
        logger.error(f"Error extracting peer cert for enrollment: {e}")

    # Also try proxy headers
    if not cert_info:
        headers = dict(request.headers)
        if 'X-SSL-Client-Verify' in headers:
            cert_info = CertificateParser.extract_from_nginx_headers(headers)
        elif 'X-SSL-Client-S-DN' in headers:
            cert_info = CertificateParser.extract_from_apache_headers(headers)

    if not cert_info:
        return error_response('No client certificate detected in this request', 400)

    # Validate certificate is not expired and not not-yet-valid
    valid_until = cert_info.get('valid_until')
    if valid_until:
        if isinstance(valid_until, str):
            valid_until = datetime.fromisoformat(valid_until.replace('Z', '+00:00'))
        if hasattr(valid_until, 'timestamp') and valid_until < datetime.now(timezone.utc):
            return error_response('Cannot enroll expired certificate', 400)

    valid_from = cert_info.get('valid_from')
    if valid_from:
        if isinstance(valid_from, str):
            valid_from = datetime.fromisoformat(valid_from.replace('Z', '+00:00'))
        if hasattr(valid_from, 'timestamp') and valid_from > datetime.now(timezone.utc):
            return error_response('Cannot enroll certificate that is not yet valid', 400)

    # Check if already enrolled
    existing = AuthCertificate.query.filter_by(cert_serial=cert_info['serial']).first()
    if existing:
        return error_response('This certificate is already enrolled', 409)

    data = request.get_json() or {}
    auth_cert = AuthCertificate(
        user_id=user.id,
        cert_serial=cert_info['serial'],
        cert_subject=cert_info.get('subject_dn', ''),
        cert_issuer=cert_info.get('issuer_dn', ''),
        cert_fingerprint=cert_info.get('fingerprint', ''),
        name=data.get('name') or cert_info.get('common_name') or f"Certificate {cert_info['serial'][:8]}",
        valid_from=cert_info.get('valid_from'),
        valid_until=cert_info.get('valid_until'),
        enabled=True,
    )
    db.session.add(auth_cert)
    db.session.commit()

    AuditService.log_action(
        action='mtls_cert_enroll',
        resource_type='certificate',
        resource_name=auth_cert.name,
        details=f'Enrolled presented certificate for user: {user.username}',
        success=True,
    )

    return success_response(data=auth_cert.to_dict(), message='Certificate enrolled')
