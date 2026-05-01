"""
Users mTLS Certificate Management Routes (Admin)
"""

from . import bp
from flask import request, g
import base64
import hashlib
import logging
import uuid

from cryptography import x509 as cx509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db, User, Certificate, CA
from services.audit_service import AuditService
from security.encryption import decrypt_private_key

logger = logging.getLogger(__name__)


@bp.route('/api/v2/users/<int:user_id>/mtls/certificates', methods=['GET'])
@require_auth(['admin:users'])
def list_user_mtls_certificates(user_id):
    """List mTLS certificates for a specific user (admin only)."""
    from models.auth_certificate import AuthCertificate

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response('User not found', 404)

    certs = AuthCertificate.query.filter_by(user_id=user_id).order_by(AuthCertificate.created_at.desc()).all()
    return success_response(data=[c.to_dict() for c in certs])


@bp.route('/api/v2/users/<int:user_id>/mtls/certificates', methods=['POST'])
@require_auth(['admin:users'])
def create_user_mtls_certificate(user_id):
    """Generate or import an mTLS certificate for a user (admin only)."""
    from models import Certificate, CA, SystemConfig
    from models.auth_certificate import AuthCertificate
    from services.cert_service import CertificateService

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response('User not found', 404)

    data = request.get_json() or {}
    mode = data.get('mode', 'generate')  # 'generate' or 'import'

    if mode == 'import':
        pem_text = data.get('pem', '').strip()
        name = data.get('name', '').strip()
        if not pem_text:
            return error_response('PEM certificate data is required', 400)

        try:
            if not pem_text.startswith('-----BEGIN'):
                try:
                    pem_text = base64.b64decode(pem_text).decode('utf-8')
                except Exception:
                    return error_response('Invalid certificate format', 400)
            pem_bytes = pem_text.encode('utf-8')
            cert_obj = cx509.load_pem_x509_certificate(pem_bytes, default_backend())
        except Exception as e:
            return error_response('Invalid PEM certificate data', 400)

        serial = str(cert_obj.serial_number)
        subject_dn = cert_obj.subject.rfc4514_string()
        issuer_dn = cert_obj.issuer.rfc4514_string()
        fingerprint = hashlib.sha256(cert_obj.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
        valid_from = cert_obj.not_valid_before_utc if hasattr(cert_obj, 'not_valid_before_utc') else cert_obj.not_valid_before
        valid_until = cert_obj.not_valid_after_utc if hasattr(cert_obj, 'not_valid_after_utc') else cert_obj.not_valid_after

        existing = AuthCertificate.query.filter_by(cert_serial=serial).first()
        if existing:
            return error_response('This certificate is already enrolled', 409)

        cn = ''
        for attr in cert_obj.subject:
            if attr.oid == cx509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break

        cert_name = name or cn or f"Imported {serial[:8]}"

        # Create Certificate record if not exists (#85: match by serial+issuer+fingerprint)
        from services.smart_import.validator import find_existing_cert_by_identity
        existing_cert = find_existing_cert_by_identity(
            Certificate, serial, issuer_dn, pem_text
        )
        if not existing_cert:
            issuer_ca = CA.query.filter(CA.subject == issuer_dn).first()
            existing_cert = Certificate(
                refid=str(uuid.uuid4()),
                descr=cert_name,
                caref=issuer_ca.refid if issuer_ca else None,
                crt=base64.b64encode(pem_bytes).decode('utf-8'),
                cert_type='usr_cert',
                subject=subject_dn,
                subject_cn=cn,
                issuer=issuer_dn,
                serial_number=serial,
                valid_from=valid_from,
                valid_to=valid_until,
                created_by=target_user.username,
            )
            db.session.add(existing_cert)
            db.session.flush()

        auth_cert = AuthCertificate(
            user_id=user_id,
            cert_serial=serial,
            cert_subject=subject_dn,
            cert_issuer=issuer_dn,
            cert_fingerprint=fingerprint,
            cert_pem=pem_bytes,
            name=cert_name,
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=True,
        )
        db.session.add(auth_cert)
        db.session.commit()

        AuditService.log_action(
            action='admin_mtls_import',
            resource_type='certificate',
            resource_name=auth_cert.name,
            details=f'Admin imported mTLS cert for user {target_user.username}',
            success=True,
        )
        return created_response(data=auth_cert.to_dict(), message='Certificate imported')

    else:
        # Generate mode
        name = data.get('name', '').strip() or f"{target_user.username}@mtls"
        ca_id = data.get('ca_id')
        validity_days = data.get('validity_days', 365)

        # Find CA
        ca = None
        if ca_id:
            ca = CA.query.filter((CA.refid == ca_id) | (CA.id == ca_id)).first()
        if not ca:
            config = SystemConfig.query.filter_by(key='mtls_trusted_ca').first()
            if config:
                ca = CA.query.filter_by(refid=config.value).first()
        if not ca:
            return error_response('No CA available for mTLS certificate generation', 400)

        try:
            result = CertificateService.create_user_certificate(
                ca_refid=ca.refid,
                common_name=name,
                validity_days=int(validity_days),
                key_type='RSA',
                key_size=2048,
                username=target_user.username,
            )

            cert_pem = base64.b64decode(result.crt) if result.crt else b''
            cert_obj = cx509.load_pem_x509_certificate(cert_pem, default_backend())
            serial = str(cert_obj.serial_number)
            subject_dn = cert_obj.subject.rfc4514_string()
            issuer_dn = cert_obj.issuer.rfc4514_string()
            fingerprint = hashlib.sha256(cert_obj.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
            valid_from = cert_obj.not_valid_before_utc if hasattr(cert_obj, 'not_valid_before_utc') else cert_obj.not_valid_before
            valid_until = cert_obj.not_valid_after_utc if hasattr(cert_obj, 'not_valid_after_utc') else cert_obj.not_valid_after

            auth_cert = AuthCertificate(
                user_id=user_id,
                cert_serial=serial,
                cert_subject=subject_dn,
                cert_issuer=issuer_dn,
                cert_fingerprint=fingerprint,
                cert_pem=cert_pem,
                name=name,
                valid_from=valid_from,
                valid_until=valid_until,
                enabled=True,
            )
            db.session.add(auth_cert)
            db.session.commit()

            key_pem = base64.b64decode(decrypt_private_key(result.prv)).decode('utf-8') if result.prv else ''

            AuditService.log_action(
                action='admin_mtls_generate',
                resource_type='certificate',
                resource_name=name,
                details=f'Admin generated mTLS cert for user {target_user.username}',
                success=True,
            )

            resp = auth_cert.to_dict()
            resp['certificate'] = cert_pem.decode('utf-8')
            resp['private_key'] = key_pem
            resp['cert_id'] = result.id
            return created_response(data=resp, message='Certificate generated')

        except Exception as e:
            logger.error(f"Failed to generate mTLS cert for user {user_id}: {e}")
            return error_response('Failed to generate certificate', 500)


@bp.route('/api/v2/users/<int:user_id>/mtls/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['admin:users'])
def delete_user_mtls_certificate(user_id, cert_id):
    """Delete an mTLS certificate for a user (admin only)."""
    from models.auth_certificate import AuthCertificate

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response('User not found', 404)

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert or auth_cert.user_id != user_id:
        return error_response('Certificate not found', 404)

    cert_name = auth_cert.name or f'Certificate #{cert_id}'
    db.session.delete(auth_cert)
    db.session.commit()

    AuditService.log_action(
        action='admin_mtls_delete',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=cert_name,
        details=f'Admin deleted mTLS cert {cert_name} for user {target_user.username}',
        success=True,
    )

    return no_content_response()
