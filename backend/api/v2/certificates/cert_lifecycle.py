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

    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    cert_name = cert.descr or f'Certificate #{cert_id}'
    cert_snapshot = cert.to_dict()
    cert_caref = cert.caref

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

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'
        from services.webhook_service import emit_cert_deleted
        emit_cert_deleted(cert_snapshot, ca_refid=cert_caref, actor=username)

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
    invalidity_raw = None
    if data:
        invalidity_raw = data.get('invalidity_date') or data.get('invalidity_at')

    invalidity_at = None
    if invalidity_raw:
        from datetime import datetime
        from utils.datetime_utils import to_naive_utc
        try:
            raw = str(invalidity_raw).strip().replace('Z', '+00:00')
            invalidity_at = to_naive_utc(datetime.fromisoformat(raw))
        except (ValueError, TypeError, OverflowError) as e:
            return error_response(f'Invalid invalidity_date: {e}', 400)

    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if cert.revoked:
        return error_response('Certificate already revoked', 400)

    try:
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        # Revoke using service — the service emits a single lifecycle event
        # that the bus fans out to webhook + email + WebSocket subscribers.
        cert = CertificateService.revoke_certificate(
            cert_id=cert_id,
            reason=reason,
            username=username,
            invalidity_at=invalidity_at,
        )

        # A cert issued through a Microsoft CA connection: try to propagate the
        # revocation to the Windows CA via the WinRM admin channel if one is
        # configured. Web Enrollment (/certsrv) itself has no revocation
        # endpoint, so without the admin channel the revocation stays local.
        if cert.source == 'msca':
            return _revoke_msca_on_ca(cert, reason)

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


def _find_msca_for_cert(cert):
    """The MicrosoftCA connection that issued this cert, or None."""
    from models.msca import MicrosoftCA, MSCARequest
    req = (MSCARequest.query
           .filter((MSCARequest.cert_id == cert.id) | (MSCARequest.csr_id == cert.id))
           .order_by(MSCARequest.id.desc())
           .first())
    if req:
        msca = db.session.get(MicrosoftCA, req.msca_id)
        if msca:
            return msca
    if cert.imported_from and cert.imported_from.startswith('msca:'):
        return MicrosoftCA.query.filter_by(name=cert.imported_from[len('msca:'):]).first()
    return None


def _revoke_msca_on_ca(cert, reason):
    """After a local msca revocation, propagate to the Windows CA if possible."""
    from services.msca_service import MicrosoftCAService, MSCAAdminChannelError

    msca = _find_msca_for_cert(cert)
    cert_dict = cert.to_dict()

    if not msca or not MicrosoftCAService.admin_channel_available(msca):
        return success_response(
            data=cert_dict,
            message=(
                'Certificate revoked in UCM only — no Microsoft CA admin channel '
                'is configured, so the Windows CA was not notified. Enable the '
                'WinRM admin channel on the connection, or revoke it on the CA.'
            ),
            meta={'msca_local_only': True}
        )

    try:
        MicrosoftCAService.revoke_on_ca(msca, cert.serial_number, reason=reason)
    except MSCAAdminChannelError as e:
        logger.error(f"MS CA admin-channel revoke failed for cert {cert.id}: {e}")
        return success_response(
            data=cert_dict,
            message=(
                'Certificate revoked in UCM, but propagating the revocation to '
                f'the Windows CA failed: {e}. Revoke it on the CA manually.'
            ),
            meta={'msca_local_only': True, 'msca_ca_error': str(e)[:300]}
        )

    from services.audit_service import AuditService
    AuditService.log_action(
        action='msca.revoke_on_ca',
        resource_type='certificate',
        resource_id=str(cert.id),
        resource_name=cert.subject or cert.refid,
        details=f"Revocation propagated to Microsoft CA '{msca.name}' (reason={reason})",
        success=True,
    )
    return success_response(
        data=cert_dict,
        message='Certificate revoked in UCM and on the Microsoft CA',
        meta={'msca_ca_revoked': True}
    )


@bp.route('/api/v2/certificates/<int:cert_id>/unhold', methods=['POST'])
@require_auth(['write:certificates'])
def unhold_certificate(cert_id):
    """Remove certificate hold (temporary revocation) and restore to valid status"""

    cert = db.session.get(Certificate, cert_id)
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
        from utils.datetime_utils import utc_now

        ca = None
        if cert.caref:
            ca = CA.query.filter_by(refid=cert.caref).first()

        # RFC 5280 §5.3.1 — when delta CRLs are enabled, emit removeFromCRL on
        # a delta before clearing the hold so relying parties drop the entry.
        if ca and ca.delta_crl_enabled and ca.cdp_enabled:
            try:
                cert.revoke_reason = 'removeFromCRL'
                cert.revoked_at = utc_now()
                db.session.commit()
                from services.crl_service import CRLService
                CRLService.generate_delta_crl(ca.id, username=username)
            except Exception as e:
                logger.warning(f"Failed to emit removeFromCRL delta before unhold: {e}")
                db.session.rollback()
                cert = db.session.get(Certificate, cert_id)

        cert.revoked = False
        cert.revoked_at = None
        cert.revoke_reason = None
        cert.invalidity_at = None
        db.session.commit()

        # Audit log
        AuditService.log_action(
            action='certificate_unheld',
            resource_type='certificate',
            resource_id=str(cert.id),
            resource_name=cert.descr or cert.refid,
            details='Certificate hold removed, restored to valid status',
            success=True
        )

        # Regenerate CRL for the issuing CA
        try:
            if ca:
                from services.crl_service import CRLService
                CRLService.generate_crl(ca.id, username=username)
                logger.info(f"Regenerated CRL for CA {ca.id} after unhold")
        except Exception as e:
            logger.warning(f"Failed to regenerate CRL after unhold: {e}")

        # Invalidate OCSP cache for this cert (cache uses hex serial — RFC 6960 §2.2)
        try:
            if cert.serial_number:
                from utils.serial_format import serial_to_hex
                serial_hex = serial_to_hex(cert.serial_number)
                if serial_hex:
                    OCSPResponse.query.filter_by(cert_serial=serial_hex).delete()
                    db.session.commit()
        except Exception:
            db.session.rollback()

        # Propagate the unhold to the Windows CA if this cert came from an MS CA
        # with an admin channel (certutil unrevoke only lifts a certificateHold).
        if cert.source == 'msca':
            from services.msca_service import MicrosoftCAService, MSCAAdminChannelError
            msca = _find_msca_for_cert(cert)
            if msca and MicrosoftCAService.admin_channel_available(msca):
                try:
                    MicrosoftCAService.unrevoke_on_ca(msca, cert.serial_number)
                    AuditService.log_action(
                        action='msca.unrevoke_on_ca',
                        resource_type='certificate',
                        resource_id=str(cert.id),
                        resource_name=cert.subject or cert.refid,
                        details=f"Hold lifted on Microsoft CA '{msca.name}'",
                        success=True,
                    )
                    return success_response(
                        data=cert.to_dict(),
                        message='Certificate hold removed in UCM and on the Microsoft CA',
                        meta={'msca_ca_unrevoked': True}
                    )
                except MSCAAdminChannelError as e:
                    logger.error(f"MS CA admin-channel unrevoke failed for cert {cert.id}: {e}")
                    return success_response(
                        data=cert.to_dict(),
                        message=(
                            'Certificate hold removed in UCM, but lifting it on the '
                            f'Windows CA failed: {e}. Unrevoke it on the CA manually.'
                        ),
                        meta={'msca_local_only': True, 'msca_ca_error': str(e)[:300]}
                    )

        return success_response(
            data=cert.to_dict(),
            message='Certificate hold removed successfully'
        )
    except Exception as e:
        logger.error(f"Failed to unhold certificate: {e}")
        return error_response('Failed to remove certificate hold', 500)
