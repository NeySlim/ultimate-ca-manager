"""
SSH Certificates API

Issue, list, revoke, export, and verify SSH certificates.
"""

import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, g, Response

from auth.unified import require_auth
from fips_mode import FipsRestricted
from utils.response import success_response, error_response, created_response, no_content_response
from utils.pagination import parse_request_pagination
from services.ssh_cert_service import SSHCertificateService
from services.ssh_ca_service import normalize_key_type
from services.audit_service import AuditService
from sqlalchemy import or_, and_
from models.ssh import SSHCertificate, SSHCertificateAuthority
from utils.datetime_utils import utc_now
from utils.cert_status import (SSH_CERTIFICATE_STATUS_FILTERS,
                               normalize_status_filters,
                               unknown_status_message)
from models import db

logger = logging.getLogger(__name__)

bp = Blueprint('ssh_certificates_v2', __name__)

# Caps (defense in depth — services may also enforce)
_MAX_PUBKEY_LEN = 16 * 1024            # OpenSSH pubkeys are < 4KB
_MAX_PRINCIPALS = 64
_MAX_PRINCIPAL_LEN = 256
_MAX_KEY_ID_LEN = 256
_MAX_EXT_OR_OPTS = 32
_MAX_OPT_VALUE_LEN = 1024
_MAX_VALIDITY_SECONDS = 10 * 365 * 24 * 3600  # 10 years
_VALID_CERT_TYPES = ('user', 'host')
_VALID_KEY_TYPES = ('ed25519', 'rsa', 'ecdsa-p256', 'ecdsa-p384', 'ecdsa-p521')


def _validate_ssh_sign_payload(data, *, require_pubkey):
    """Return (kwargs_dict, None) on success or (None, error_response) on failure."""
    ca_id = data.get('ca_id')
    if not ca_id:
        return None, error_response('CA ID is required', 400)

    cert_type = (data.get('cert_type') or 'user').strip().lower()
    if cert_type not in _VALID_CERT_TYPES:
        return None, error_response('cert_type must be "user" or "host"', 400)

    public_key = ''
    if require_pubkey:
        public_key = (data.get('public_key') or '').strip()
        if not public_key:
            return None, error_response('Public key is required', 400)
        if len(public_key) > _MAX_PUBKEY_LEN:
            return None, error_response('Public key too large', 400)

    principals = data.get('principals', [])
    if isinstance(principals, str):
        principals = [p.strip() for p in principals.split(',') if p.strip()]
    if not isinstance(principals, list):
        return None, error_response('principals must be a list or comma-separated string', 400)
    if not principals:
        return None, error_response('At least one principal is required', 400)
    if len(principals) > _MAX_PRINCIPALS:
        return None, error_response(f'Too many principals (max {_MAX_PRINCIPALS})', 400)
    for p in principals:
        if not isinstance(p, str) or not p.strip():
            return None, error_response('Invalid principal', 400)
        if len(p) > _MAX_PRINCIPAL_LEN:
            return None, error_response('Principal name too long', 400)

    validity_seconds = data.get('validity_seconds')
    if validity_seconds is not None:
        try:
            validity_seconds = int(validity_seconds)
        except (TypeError, ValueError):
            return None, error_response('validity_seconds must be an integer', 400)
        if validity_seconds < 60 or validity_seconds > _MAX_VALIDITY_SECONDS:
            return None, error_response(
                f'validity_seconds must be between 60 and {_MAX_VALIDITY_SECONDS}', 400)

    key_id = data.get('key_id')
    if key_id is not None:
        if not isinstance(key_id, str):
            return None, error_response('key_id must be a string', 400)
        if len(key_id) > _MAX_KEY_ID_LEN:
            return None, error_response('key_id too long', 400)

    extensions = data.get('extensions')
    if extensions is not None:
        if isinstance(extensions, list):
            if len(extensions) > _MAX_EXT_OR_OPTS:
                return None, error_response('Too many extensions', 400)
            for e in extensions:
                if not isinstance(e, str) or len(e) > 128:
                    return None, error_response('Invalid extension', 400)
        elif isinstance(extensions, dict):
            if len(extensions) > _MAX_EXT_OR_OPTS:
                return None, error_response('Too many extensions', 400)
            for k, v in extensions.items():
                if not isinstance(k, str) or len(k) > 128:
                    return None, error_response('Invalid extension key', 400)
                if v is not None and (not isinstance(v, str) or len(v) > _MAX_OPT_VALUE_LEN):
                    return None, error_response('Invalid extension value', 400)
        else:
            return None, error_response('extensions must be a list or object', 400)

    critical_options = data.get('critical_options')
    if critical_options is not None:
        if not isinstance(critical_options, dict):
            return None, error_response('critical_options must be an object', 400)
        if len(critical_options) > _MAX_EXT_OR_OPTS:
            return None, error_response('Too many critical options', 400)
        for k, v in critical_options.items():
            if not isinstance(k, str) or len(k) > 128:
                return None, error_response('Invalid critical option key', 400)
            if v is not None and (not isinstance(v, str) or len(v) > _MAX_OPT_VALUE_LEN):
                return None, error_response('Invalid critical option value', 400)

    return {
        'ca_id': ca_id,
        'public_key': public_key,
        'cert_type': cert_type,
        'principals': principals,
        'validity_seconds': validity_seconds,
        'key_id': key_id,
        'extensions': extensions,
        'critical_options': critical_options,
    }, None


@bp.route('/api/v2/ssh/certificates', methods=['GET'])
@require_auth(['read:ssh'])
def list_ssh_certificates():
    """List SSH certificates with filtering and pagination."""
    page, per_page = parse_request_pagination(default_per_page=20)
    search = request.args.get('search', '').strip()
    statuses, unknown_status = normalize_status_filters(
        request.args.getlist('status'), SSH_CERTIFICATE_STATUS_FILTERS)
    if unknown_status:
        return error_response(
            unknown_status_message(
                unknown_status, SSH_CERTIFICATE_STATUS_FILTERS), 400)
    cert_types = request.args.getlist('type')
    ca_ids = request.args.getlist('ca_id', type=int)

    query = SSHCertificate.query

    if ca_ids:
        query = query.filter(SSHCertificate.ssh_ca_id.in_(ca_ids))

    if cert_types:
        valid = [t for t in cert_types if t in SSHCertificate.VALID_CERT_TYPES]
        if valid:
            query = query.filter(SSHCertificate.cert_type.in_(valid))

    # Status filtering (supports multiple statuses with OR)
    now = utc_now()
    if statuses:
        conditions = []
        for s in statuses:
            if s == 'valid':
                conditions.append(and_(SSHCertificate.revoked == False, SSHCertificate.valid_to > now))
            elif s == 'revoked':
                conditions.append(SSHCertificate.revoked == True)
            elif s == 'expired':
                conditions.append(and_(SSHCertificate.revoked == False, SSHCertificate.valid_to <= now))
            elif s == 'expiring':
                threshold = now + timedelta(days=7)
                conditions.append(and_(SSHCertificate.revoked == False, SSHCertificate.valid_to <= threshold, SSHCertificate.valid_to > now))
        if conditions:
            query = query.filter(or_(*conditions))

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
    cert = db.session.get(SSHCertificate, cert_id)
    if not cert:
        return error_response('SSH certificate not found', 404)

    return success_response(data=cert.to_dict())


@bp.route('/api/v2/ssh/certificates/import', methods=['POST'])
@require_auth(['write:ssh'])
def import_ssh_certificate():
    """Import an existing SSH certificate."""
    try:
        data = request.json or {}

        certificate_data = (data.get('certificate') or '').strip()
        if not certificate_data:
            return error_response('Certificate data is required', 400)
        if len(certificate_data) > 32768:
            return error_response('Certificate data too large', 400)

        descr = (data.get('descr') or '').strip()[:255] or None
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        cert = SSHCertificateService.import_certificate(
            certificate_data=certificate_data,
            descr=descr,
            ssh_ca_id=data.get('ssh_ca_id'),
            username=username,
        )

        AuditService.log_action(
            action='ssh_cert_imported',
            resource_type='ssh_certificate',
            resource_id=str(cert.id),
            resource_name=cert.key_id,
            details=f'SSH {cert.cert_type} certificate imported (serial: {cert.serial})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_issued
            on_ssh_certificate_issued(cert.id, cert.key_id, cert.ssh_ca_id, cert.cert_type)
        except Exception:
            pass

        return created_response(
            data=cert.to_dict(),
            message='SSH certificate imported successfully'
        )

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
    except ValueError as e:
        AuditService.log_action(
            action='ssh_cert_import_failed',
            resource_type='ssh_certificate',
            details=str(e)[:200],
            success=False,
            username=g.current_user.username if hasattr(g, 'current_user') else 'system',
        )
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to import SSH certificate: {e}")
        AuditService.log_action(
            action='ssh_cert_import_failed',
            resource_type='ssh_certificate',
            details='Internal error during SSH certificate import',
            success=False,
            username=g.current_user.username if hasattr(g, 'current_user') else 'system',
        )
        return error_response('Failed to import SSH certificate', 500)


@bp.route('/api/v2/ssh/certificates', methods=['POST'])
@require_auth(['write:ssh'])
def sign_ssh_certificate():
    """Issue a new SSH certificate by signing a public key."""
    try:
        data = request.json or {}

        validated, err = _validate_ssh_sign_payload(data, require_pubkey=True)
        if err:
            return err

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        cert = SSHCertificateService.sign_certificate(
            ca_id=validated['ca_id'],
            public_key_data=validated['public_key'],
            cert_type=validated['cert_type'],
            principals=validated['principals'],
            validity_seconds=validated['validity_seconds'],
            key_id=validated['key_id'],
            extensions=validated['extensions'],
            critical_options=validated['critical_options'],
            descr=data.get('descr'),
            source='web',
            username=username,
        )

        AuditService.log_action(
            action='ssh_cert_issued',
            resource_type='ssh_certificate',
            resource_id=str(cert.id),
            resource_name=cert.key_id,
            details=f'SSH {validated["cert_type"]} certificate issued for {", ".join(validated["principals"])} (serial: {cert.serial})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_issued
            on_ssh_certificate_issued(cert.id, cert.key_id, cert.ssh_ca_id, validated['cert_type'])
        except Exception:
            pass

        return created_response(
            data=cert.to_dict(),
            message='SSH certificate issued successfully'
        )

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
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

        validated, err = _validate_ssh_sign_payload(data, require_pubkey=False)
        if err:
            return err

        key_type = normalize_key_type(data.get('key_type'))
        if key_type not in _VALID_KEY_TYPES:
            return error_response(
                f'key_type must be one of: {", ".join(_VALID_KEY_TYPES)}', 400)

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        result = SSHCertificateService.generate_and_sign(
            ca_id=validated['ca_id'],
            cert_type=validated['cert_type'],
            principals=validated['principals'],
            key_type=key_type,
            validity_seconds=validated['validity_seconds'],
            key_id=validated['key_id'],
            extensions=validated['extensions'],
            critical_options=validated['critical_options'],
            descr=data.get('descr'),
            source='web',
            username=username,
        )

        cert = result['certificate']

        AuditService.log_action(
            action='ssh_cert_generated',
            resource_type='ssh_certificate',
            resource_id=str(cert.id),
            resource_name=cert.key_id,
            details=f'SSH {validated["cert_type"]} certificate generated with new {key_type} key',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_certificate_issued
            on_ssh_certificate_issued(cert.id, cert.key_id, cert.ssh_ca_id, validated['cert_type'])
        except Exception:
            pass

        return created_response(
            data={
                **cert.to_dict(),
                'private_key': result['private_key'],
            },
            message='SSH certificate and key pair generated'
        )

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
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
    cert = db.session.get(SSHCertificate, cert_id)
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
        # Guard refusal: 409; certificate gone in the meantime: 404
        msg = str(e)
        return error_response(msg, 404 if 'not found' in msg else 409)
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

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
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
