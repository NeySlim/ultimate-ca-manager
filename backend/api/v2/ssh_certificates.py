"""
SSH Certificates API

Issue, list, revoke, export, and verify SSH certificates.
"""

import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, g, Response

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from services.ssh_cert_service import SSHCertificateService
from services.audit_service import AuditService
from models.ssh import SSHCertificate, SSHCertificateAuthority
from utils.datetime_utils import utc_now
from sqlalchemy import or_

logger = logging.getLogger(__name__)

bp = Blueprint('ssh_certificates_v2', __name__)


@bp.route('/api/v2/ssh/certificates', methods=['GET'])
@require_auth(['read:ssh'])
def list_ssh_certificates():
    """List SSH certificates with filtering and pagination."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '').strip()
    cert_type = request.args.get('type', '').strip()
    ca_id = request.args.get('ca_id', type=int)

    query = SSHCertificate.query

    if ca_id:
        query = query.filter_by(ssh_ca_id=ca_id)

    if cert_type and cert_type in SSHCertificate.VALID_CERT_TYPES:
        query = query.filter_by(cert_type=cert_type)

    # Status filtering
    now = utc_now()
    if status == 'valid':
        query = query.filter_by(revoked=False)
        query = query.filter(SSHCertificate.valid_to > now)
    elif status == 'revoked':
        query = query.filter_by(revoked=True)
    elif status == 'expired':
        query = query.filter_by(revoked=False)
        query = query.filter(SSHCertificate.valid_to <= now)
    elif status == 'expiring':
        threshold = now + timedelta(days=7)
        query = query.filter_by(revoked=False)
        query = query.filter(SSHCertificate.valid_to <= threshold)
        query = query.filter(SSHCertificate.valid_to > now)

    if search:
        safe = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(
            or_(
                SSHCertificate.key_id.ilike(f'%{safe}%', escape='\\'),
                SSHCertificate.descr.ilike(f'%{safe}%', escape='\\'),
                SSHCertificate.principals.ilike(f'%{safe}%', escape='\\'),
            )
        )

    query = query.order_by(SSHCertificate.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success_response(
        data=[cert.to_dict() for cert in pagination.items],
        meta={
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'total_pages': (pagination.total + per_page - 1) // per_page
        }
    )


@bp.route('/api/v2/ssh/certificates/<int:cert_id>', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_certificate(cert_id):
    """Get SSH certificate details."""
    cert = SSHCertificate.query.get(cert_id)
    if not cert:
        return error_response('SSH certificate not found', 404)

    return success_response(data=cert.to_dict())


@bp.route('/api/v2/ssh/certificates', methods=['POST'])
@require_auth(['write:ssh'])
def sign_ssh_certificate():
    """Issue a new SSH certificate by signing a public key."""
    try:
        data = request.json or {}

        ca_id = data.get('ca_id')
        if not ca_id:
            return error_response('CA ID is required', 400)

        public_key = data.get('public_key', '').strip()
        if not public_key:
            return error_response('Public key is required', 400)

        cert_type = (data.get('cert_type') or 'user').strip().lower()
        principals = data.get('principals', [])
        if isinstance(principals, str):
            principals = [p.strip() for p in principals.split(',') if p.strip()]

        if not principals:
            return error_response('At least one principal is required', 400)

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        # Parse validity
        validity_seconds = data.get('validity_seconds')
        if validity_seconds:
            validity_seconds = int(validity_seconds)

        # Parse extensions
        extensions = data.get('extensions')
        critical_options = data.get('critical_options')

        cert = SSHCertificateService.sign_certificate(
            ca_id=ca_id,
            public_key_data=public_key,
            cert_type=cert_type,
            principals=principals,
            validity_seconds=validity_seconds,
            key_id=data.get('key_id'),
            extensions=extensions,
            critical_options=critical_options,
            descr=data.get('descr'),
            source='web',
            username=username,
            owner_group_id=data.get('owner_group_id'),
        )

        AuditService.log_action(
            action='ssh_cert_issued',
            resource_type='ssh_certificate',
            resource_id=str(cert.id),
            resource_name=cert.key_id,
            details=f'SSH {cert_type} certificate issued for {", ".join(principals)} (serial: {cert.serial})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_issued
            on_ssh_certificate_issued(cert.id, cert.key_id, cert.ssh_ca_id, cert_type)
        except Exception:
            pass

        return created_response(
            data=cert.to_dict(),
            message='SSH certificate issued successfully'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to issue SSH certificate: {e}")
        return error_response('Failed to issue SSH certificate', 500)


@bp.route('/api/v2/ssh/certificates/generate', methods=['POST'])
@require_auth(['write:ssh'])
def generate_ssh_certificate():
    """Generate a new key pair AND issue a certificate.

    Returns the certificate + private key (one-time download).
    """
    try:
        data = request.json or {}

        ca_id = data.get('ca_id')
        if not ca_id:
            return error_response('CA ID is required', 400)

        cert_type = (data.get('cert_type') or 'user').strip().lower()
        principals = data.get('principals', [])
        if isinstance(principals, str):
            principals = [p.strip() for p in principals.split(',') if p.strip()]

        if not principals:
            return error_response('At least one principal is required', 400)

        key_type = (data.get('key_type') or 'ed25519').strip().lower()
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        validity_seconds = data.get('validity_seconds')
        if validity_seconds:
            validity_seconds = int(validity_seconds)

        result = SSHCertificateService.generate_and_sign(
            ca_id=ca_id,
            cert_type=cert_type,
            principals=principals,
            key_type=key_type,
            validity_seconds=validity_seconds,
            key_id=data.get('key_id'),
            extensions=data.get('extensions'),
            critical_options=data.get('critical_options'),
            descr=data.get('descr'),
            source='web',
            username=username,
            owner_group_id=data.get('owner_group_id'),
        )

        cert = result['certificate']

        AuditService.log_action(
            action='ssh_cert_generated',
            resource_type='ssh_certificate',
            resource_id=str(cert.id),
            resource_name=cert.key_id,
            details=f'SSH {cert_type} certificate generated with new {key_type} key',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_issued
            on_ssh_certificate_issued(cert.id, cert.key_id, cert.ssh_ca_id, cert_type)
        except Exception:
            pass

        return created_response(
            data={
                **cert.to_dict(),
                'private_key': result['private_key'],
            },
            message='SSH certificate and key pair generated'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to generate SSH certificate: {e}")
        return error_response('Failed to generate SSH certificate', 500)


@bp.route('/api/v2/ssh/certificates/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:ssh'])
def revoke_ssh_certificate(cert_id):
    """Revoke an SSH certificate."""
    try:
        data = request.json or {}
        reason = data.get('reason', 'unspecified')
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        cert = SSHCertificateService.revoke_certificate(cert_id, reason, username)

        AuditService.log_action(
            action='ssh_cert_revoked',
            resource_type='ssh_certificate',
            resource_id=str(cert.id),
            resource_name=cert.key_id,
            details=f'SSH certificate revoked: {reason}',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_revoked
            on_ssh_certificate_revoked(cert.id, cert.key_id, reason, username)
        except Exception:
            pass

        return success_response(
            data=cert.to_dict(),
            message='SSH certificate revoked'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to revoke SSH certificate {cert_id}: {e}")
        return error_response('Failed to revoke certificate', 500)


@bp.route('/api/v2/ssh/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:ssh'])
def delete_ssh_certificate(cert_id):
    """Delete an SSH certificate record."""
    cert = SSHCertificate.query.get(cert_id)
    if not cert:
        return error_response('SSH certificate not found', 404)

    cert_name = cert.key_id
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'

    try:
        SSHCertificateService.delete_certificate(cert_id)

        AuditService.log_action(
            action='ssh_cert_deleted',
            resource_type='ssh_certificate',
            resource_id=str(cert_id),
            resource_name=cert_name,
            details=f'SSH certificate deleted',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_deleted
            on_ssh_certificate_deleted(cert_id, cert_name, username)
        except Exception:
            pass

        return no_content_response()

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to delete SSH certificate {cert_id}: {e}")
        return error_response('Failed to delete certificate', 500)


@bp.route('/api/v2/ssh/certificates/<int:cert_id>/export', methods=['GET'])
@require_auth(['read:ssh'])
def export_ssh_certificate(cert_id):
    """Export an SSH certificate in OpenSSH format."""
    try:
        result = SSHCertificateService.export_certificate(cert_id)

        return success_response(data=result)

    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to export SSH certificate: {e}")
        return error_response('Failed to export certificate', 500)


@bp.route('/api/v2/ssh/certificates/verify', methods=['POST'])
@require_auth(['read:ssh'])
def verify_ssh_certificate():
    """Decode and verify an SSH certificate."""
    try:
        data = request.json or {}
        cert_data = data.get('certificate', '').strip()
        if not cert_data:
            return error_response('Certificate data is required', 400)

        result = SSHCertificateService.decode_certificate(cert_data)

        return success_response(data=result)

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to verify SSH certificate: {e}")
        return error_response('Failed to verify certificate', 500)


@bp.route('/api/v2/ssh/stats', methods=['GET'])
@require_auth(['read:ssh'])
def ssh_stats():
    """Get SSH certificate statistics for dashboard."""
    now = utc_now()

    total_cas = SSHCertificateAuthority.query.count()
    user_cas = SSHCertificateAuthority.query.filter_by(ca_type='user').count()
    host_cas = SSHCertificateAuthority.query.filter_by(ca_type='host').count()

    total_certs = SSHCertificate.query.count()
    valid_certs = SSHCertificate.query.filter(
        SSHCertificate.revoked == False,
        SSHCertificate.valid_to > now
    ).count()
    revoked_certs = SSHCertificate.query.filter_by(revoked=True).count()
    expired_certs = SSHCertificate.query.filter(
        SSHCertificate.revoked == False,
        SSHCertificate.valid_to <= now
    ).count()

    return success_response(data={
        'cas': {
            'total': total_cas,
            'user': user_cas,
            'host': host_cas,
        },
        'certificates': {
            'total': total_certs,
            'valid': valid_certs,
            'revoked': revoked_certs,
            'expired': expired_certs,
        },
    })
