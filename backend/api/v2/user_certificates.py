"""
User Certificates API - Manage user/client certificates (mTLS)
Provides list, detail, export, revoke, delete for certificates linked to users via auth_certificates.
"""

import base64
import logging
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from flask import Blueprint, Response, g, request

from auth.unified import require_auth
from models import CA, AuthCertificate, Certificate, User, db
from services.audit_service import AuditService
from services.cert_service import CertificateService
from utils.response import error_response, no_content_response, success_response

logger = logging.getLogger(__name__)

bp = Blueprint('user_certificates', __name__, url_prefix='/api/v2/user-certificates')


def _is_admin_or_operator(user):
    """Check if user has admin or operator role."""
    return getattr(user, 'role', '') in ('admin', 'operator')


def _is_auditor(user):
    """Check if user has auditor role."""
    return getattr(user, 'role', '') == 'auditor'


def _can_access_cert(user, auth_cert):
    """Check if user can access a specific certificate."""
    if _is_admin_or_operator(user) or _is_auditor(user):
        return True
    return auth_cert.user_id == user.id


def _get_certificate_for_auth_cert(auth_cert):
    """Find the Certificate record linked to an AuthCertificate."""
    return Certificate.query.filter(
        Certificate.serial_number == auth_cert.cert_serial
    ).first()


def _build_cert_response(auth_cert, certificate, owner_user=None):
    """Build a combined response dict from auth_cert + certificate."""
    result = auth_cert.to_dict()
    if certificate:
        result['cert_id'] = certificate.id
        result['refid'] = certificate.refid
        result['description'] = certificate.descr
        result['subject'] = certificate.subject
        result['issuer'] = certificate.issuer
        result['serial_number'] = certificate.serial_number
        result['valid_from'] = certificate.valid_from.isoformat() if certificate.valid_from else None
        result['valid_to'] = certificate.valid_to.isoformat() if certificate.valid_to else None
        result['cert_type'] = certificate.cert_type
        result['revoked'] = certificate.revoked or False
        result['has_private_key'] = bool(certificate.prv)
        result['caref'] = certificate.caref
        # Compute status
        now = datetime.utcnow()
        if certificate.revoked:
            result['status'] = 'revoked'
        elif certificate.valid_to and certificate.valid_to <= now:
            result['status'] = 'expired'
        elif certificate.valid_to and certificate.valid_to <= now + timedelta(days=30):
            result['status'] = 'expiring'
        else:
            result['status'] = 'valid'
    else:
        result['status'] = 'orphan'
        result['has_private_key'] = False

    if owner_user:
        result['owner'] = owner_user.username
        result['owner_id'] = owner_user.id
    return result


@bp.route('', methods=['GET'])
@require_auth(['read:user_certificates'])
def list_user_certificates():
    """List user certificates with ownership-aware access control."""
    user = g.current_user

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    per_page = min(per_page, 100)

    # Filters
    status_filter = request.args.get('status')
    user_filter = request.args.get('user_id', type=int)
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')

    # Base query
    query = AuthCertificate.query

    # Access control: viewers see only own certs
    if not _is_admin_or_operator(user) and not _is_auditor(user):
        query = query.filter(AuthCertificate.user_id == user.id)
    elif user_filter:
        query = query.filter(AuthCertificate.user_id == user_filter)

    # Search
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                AuthCertificate.name.ilike(search_pattern),
                AuthCertificate.cert_subject.ilike(search_pattern),
                AuthCertificate.cert_serial.ilike(search_pattern),
            )
        )

    # Sorting
    sort_col_map = {
        'created_at': AuthCertificate.created_at,
        'name': AuthCertificate.name,
        'valid_until': AuthCertificate.valid_until,
        'last_used_at': AuthCertificate.last_used_at,
    }
    sort_col = sort_col_map.get(sort_by, AuthCertificate.created_at)
    if sort_order == 'asc':
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Execute with pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    auth_certs = pagination.items

    # Build response with joined data
    results = []
    user_cache = {}
    for ac in auth_certs:
        cert = _get_certificate_for_auth_cert(ac)

        # Status filter (post-query since status is computed)
        if status_filter and cert:
            now = datetime.utcnow()
            if status_filter == 'revoked' and not cert.revoked:
                continue
            if status_filter == 'expired' and not (cert.valid_to and cert.valid_to <= now and not cert.revoked):
                continue
            if status_filter == 'valid' and not (cert.valid_to and cert.valid_to > now and not cert.revoked):
                continue
            if status_filter == 'expiring':
                threshold = now + timedelta(days=30)
                if not (cert.valid_to and now < cert.valid_to <= threshold and not cert.revoked):
                    continue

        # Cache user lookup
        if ac.user_id not in user_cache:
            user_cache[ac.user_id] = User.query.get(ac.user_id)
        owner = user_cache[ac.user_id]

        results.append(_build_cert_response(ac, cert, owner))

    return success_response(data={
        'items': results,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages,
    })


@bp.route('/stats', methods=['GET'])
@require_auth(['read:user_certificates'])
def get_user_certificate_stats():
    """Get user certificate statistics."""
    user = g.current_user
    now = datetime.utcnow()
    expiry_threshold = now + timedelta(days=30)

    # Base query with access control
    query = AuthCertificate.query
    if not _is_admin_or_operator(user) and not _is_auditor(user):
        query = query.filter(AuthCertificate.user_id == user.id)

    auth_certs = query.all()
    stats = {'total': len(auth_certs), 'valid': 0, 'expiring': 0, 'expired': 0, 'revoked': 0}

    for ac in auth_certs:
        cert = _get_certificate_for_auth_cert(ac)
        if not cert:
            continue
        if cert.revoked:
            stats['revoked'] += 1
        elif cert.valid_to and cert.valid_to <= now:
            stats['expired'] += 1
        elif cert.valid_to and cert.valid_to <= expiry_threshold:
            stats['expiring'] += 1
        else:
            stats['valid'] += 1

    # User count (admins/operators only)
    if _is_admin_or_operator(user) or _is_auditor(user):
        stats['users'] = db.session.query(
            db.func.count(db.distinct(AuthCertificate.user_id))
        ).scalar() or 0

    return success_response(data=stats)


@bp.route('/<int:cert_id>', methods=['GET'])
@require_auth(['read:user_certificates'])
def get_user_certificate(cert_id):
    """Get a single user certificate by auth_certificate ID."""
    user = g.current_user

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    if not _can_access_cert(user, auth_cert):
        return error_response('Certificate not found', 404)

    cert = _get_certificate_for_auth_cert(auth_cert)
    owner = User.query.get(auth_cert.user_id)

    return success_response(data=_build_cert_response(auth_cert, cert, owner))


@bp.route('/<int:cert_id>/export', methods=['GET'])
@require_auth(['read:user_certificates'])
def export_user_certificate(cert_id):
    """Export user certificate (PEM or PKCS12). Auditors cannot export."""
    user = g.current_user

    if _is_auditor(user):
        return error_response('Auditors cannot export certificates', 403)

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    if not _can_access_cert(user, auth_cert):
        return error_response('Certificate not found', 404)

    cert = _get_certificate_for_auth_cert(auth_cert)
    if not cert:
        return error_response('Certificate data not found', 404)

    export_format = request.args.get('format', 'pem').lower()
    password = request.args.get('password', '')
    include_key = request.args.get('include_key', 'true').lower() == 'true'
    include_chain = request.args.get('include_chain', 'true').lower() == 'true'

    try:
        cert_pem = base64.b64decode(cert.crt)
        filename_base = auth_cert.name or cert.descr or cert.refid

        if export_format in ('pkcs12', 'p12', 'pfx'):
            if not password or len(password) < 8:
                return error_response('Password required (minimum 8 characters) for PKCS12 export', 400)
            if not cert.prv:
                return error_response('Certificate has no private key for PKCS12 export', 400)

            x509_cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = base64.b64decode(cert.prv)
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())

            # Build CA chain
            ca_certs = []
            if include_chain and cert.caref:
                ca = CA.query.filter_by(refid=cert.caref).first()
                seen = set()
                while ca and ca.refid not in seen and len(ca_certs) < 10:
                    seen.add(ca.refid)
                    if ca.crt:
                        try:
                            ca_cert = x509.load_pem_x509_certificate(
                                base64.b64decode(ca.crt), default_backend()
                            )
                            ca_certs.append(ca_cert)
                        except Exception:
                            logger.warning(f"Failed to load CA cert {ca.refid}")
                    ca = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=filename_base.encode(),
                key=private_key,
                cert=x509_cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )

            AuditService.log_action(
                action='user_certificate_exported',
                resource_type='user_certificate',
                resource_id=cert_id,
                resource_name=filename_base,
                details=f'Exported PKCS12 for user cert: {filename_base}',
                success=True
            )

            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{filename_base}.p12"'}
            )

        # PEM export (default)
        result = cert_pem
        filename = f"{filename_base}.crt"

        if include_key and cert.prv:
            key_pem = base64.b64decode(cert.prv)
            if not result.endswith(b'\n'):
                result += b'\n'
            result += key_pem
            filename = f"{filename_base}.pem"

        if include_chain and cert.caref:
            ca = CA.query.filter_by(refid=cert.caref).first()
            seen = set()
            while ca and ca.refid not in seen:
                seen.add(ca.refid)
                if ca.crt:
                    if not result.endswith(b'\n'):
                        result += b'\n'
                    result += base64.b64decode(ca.crt)
                ca = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None

        AuditService.log_action(
            action='user_certificate_exported',
            resource_type='user_certificate',
            resource_id=cert_id,
            resource_name=filename_base,
            details=f'Exported PEM for user cert: {filename_base}',
            success=True
        )

        return Response(
            result,
            mimetype='application/x-pem-file',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        logger.error(f"Failed to export user certificate {cert_id}: {e}")
        return error_response('Failed to export certificate', 500)


@bp.route('/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:user_certificates'])
def revoke_user_certificate(cert_id):
    """Revoke a user certificate. Operators and admins only."""
    user = g.current_user

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    cert = _get_certificate_for_auth_cert(auth_cert)
    if not cert:
        return error_response('Certificate data not found', 404)

    if cert.revoked:
        return error_response('Certificate already revoked', 400)

    data = request.json or {}
    reason = data.get('reason', 'unspecified')

    try:
        cert = CertificateService.revoke_certificate(
            cert_id=cert.id,
            reason=reason,
            username=user.username
        )

        # Disable auth certificate
        auth_cert.enabled = False
        db.session.commit()

        AuditService.log_action(
            action='user_certificate_revoked',
            resource_type='user_certificate',
            resource_id=cert_id,
            resource_name=auth_cert.name or cert.descr,
            details=f'Revoked user certificate: {auth_cert.name or cert.descr} (reason: {reason})',
            success=True
        )

        owner = User.query.get(auth_cert.user_id)
        return success_response(
            data=_build_cert_response(auth_cert, cert, owner),
            message='Certificate revoked successfully'
        )
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to revoke user certificate {cert_id}: {e}")
        return error_response('Failed to revoke certificate', 500)


@bp.route('/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:user_certificates'])
def delete_user_certificate(cert_id):
    """Delete a user certificate. Operators and admins only."""
    user = g.current_user

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert:
        return error_response('Certificate not found', 404)

    cert_name = auth_cert.name or f'User Certificate #{cert_id}'

    # Also delete the underlying certificate
    cert = _get_certificate_for_auth_cert(auth_cert)

    db.session.delete(auth_cert)
    if cert:
        db.session.delete(cert)
    db.session.commit()

    AuditService.log_action(
        action='user_certificate_deleted',
        resource_type='user_certificate',
        resource_id=cert_id,
        resource_name=cert_name,
        details=f'Deleted user certificate: {cert_name} (by: {user.username})',
        success=True
    )

    return no_content_response()
