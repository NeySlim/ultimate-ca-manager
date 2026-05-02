"""Certificate lifecycle routes (delete, revoke, unhold)"""
import logging
from flask import request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, no_content_response
from models import Certificate, CA, db
from models.ocsp import OCSPResponse
from services.cert_service import CertificateService
from services.audit_service import AuditService
from services.notification_service import NotificationService
from websocket.emitters import on_certificate_revoked, on_certificate_deleted
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['delete:certificates'])
def delete_certificate(cert_id):
    """Delete certificate"""

    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    cert_name = cert.descr or f'Certificate #{cert_id}'

    try:
        # Clean up dependent records
        from models import ApprovalRequest
        ApprovalRequest.query.filter_by(certificate_id=cert_id).delete()

        db.session.delete(cert)
        db.session.commit()

        # Audit log
        AuditService.log_action(
            action='certificate_deleted',
            resource_type='certificate',
            resource_id=cert_id,
            resource_name=cert_name,
            details=f'Deleted certificate: {cert_name}',
            success=True
        )

        try:
            username = g.current_user.username if hasattr(g, 'current_user') else 'system'
            on_certificate_deleted(cert_id, cert_name, username)
        except Exception:
            pass

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete certificate {cert_name}: {e}")
        return error_response('Failed to delete certificate', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/revoke', methods=['POST'])
@require_auth(['write:certificates'])
def revoke_certificate(cert_id):
    """Revoke certificate"""

    data = request.json
    reason = data.get('reason', 'unspecified') if data else 'unspecified'

    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if cert.revoked:
        return error_response('Certificate already revoked', 400)

    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        # Revoke using service
        cert = CertificateService.revoke_certificate(
            cert_id=cert_id,
            reason=reason,
            username=username
        )

        # Send notification
        try:
            NotificationService.on_certificate_revoked(cert, reason, username)
        except Exception:
            pass  # Non-blocking

        # WebSocket event
        try:
            on_certificate_revoked(
                cert_id=cert.id,
                cn=cert.descr or cert.refid,
                reason=reason,
                revoked_by=username
            )
        except Exception:
            pass  # Non-blocking

        return success_response(
            data=cert.to_dict(),
            message='Certificate revoked successfully'
        )
    except ValueError as e:
        logger.error(f"Certificate revocation validation error: {e}")
        return error_response('Validation failed', 400)
    except Exception as e:
        logger.error(f"Failed to revoke certificate: {e}")
        return error_response('Failed to revoke certificate', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/unhold', methods=['POST'])
@require_auth(['write:certificates'])
def unhold_certificate(cert_id):
    """Remove certificate hold (temporary revocation) and restore to valid status"""

    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if not cert.revoked:
        return error_response('Certificate is not revoked', 400)

    # Only certificateHold can be unheld
    hold_reasons = ('certificate_hold', 'certificateHold')
    if cert.revoke_reason not in hold_reasons:
        return error_response(
            'Only certificates with reason "certificateHold" can be unheld', 400
        )

    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        cert.revoked = False
        cert.revoked_at = None
        cert.revoke_reason = None
        db.session.commit()

        # Audit log
        AuditService.log(
            action='certificate.unheld',
            resource_type='certificate',
            resource_id=cert.id,
            resource_name=cert.descr or cert.refid,
            username=username,
            details=f'Certificate hold removed, restored to valid status'
        )

        # Regenerate CRL for the issuing CA
        try:
            if cert.ca_id:
                from services.crl_service import CRLService
                CRLService.generate_crl(cert.ca_id, username=username)
                logger.info(f"Regenerated CRL for CA {cert.ca_id} after unhold")
        except Exception as e:
            logger.warning(f"Failed to regenerate CRL after unhold: {e}")

        # Invalidate OCSP cache for this cert
        try:
            OCSPResponse.query.filter_by(cert_serial=cert.serial).delete()
            db.session.commit()
        except Exception:
            pass

        return success_response(
            data=cert.to_dict(),
            message='Certificate hold removed successfully'
        )
    except Exception as e:
        logger.error(f"Failed to unhold certificate: {e}")
        return error_response('Failed to remove certificate hold', 500)
