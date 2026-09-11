"""Certificate renewal route"""
import logging
from flask import request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import Certificate, db
from services.audit_service import AuditService
from services.cert.renewal import RenewalError, renew_certificate_in_place
from . import bp

logger = logging.getLogger(__name__)


def _approval_for_renewal(user, cert, data):
    """Queue the renewal for approval when a policy requires it: ``(policy,
    approval)`` or ``(None, None)``. Raises on evaluation error."""
    from services.approval_gate import certificate_identity, queue_if_approval_required
    from services.cert.renewal import resolve_issuing_ca
    ca = resolve_issuing_ca(cert)
    cn, dns = certificate_identity(cert.crt)
    return queue_if_approval_required(
        user, ca_id=ca.id if ca else None, template_id=getattr(cert, 'template_id', None),
        cn=cn, san_list=dns, request_type='renewal',
        request_data={'certificate_id': cert.id, 'ca_id': ca.id if ca else None, 'cn': cn,
                      'cert_type': cert.cert_type},
        comment=(data or {}).get('approval_comment'),
    )


@bp.route('/api/v2/certificates/<int:cert_id>/renew', methods=['POST'])
@require_auth(['write:certificates'])
def renew_certificate(cert_id):
    """
    Renew certificate - In-place update with old serial revocation.

    The certificate row (id, refid, created_at) is preserved. The old serial
    is recorded in revoked_serials with reason 'superseded' and
    certificate_id pointing back to this row, so the CRL query can
    distinguish between the current serial (good) and previous serials
    (revoked/superseded). renewed_at is set to utc_now().
    """

    # Get original certificate
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    if not cert.crt:
        return error_response('Certificate data not available', 400)

    # Certificates issued by a Microsoft AD CS connection can't be re-signed
    # locally (the issuing CA's key lives on the Windows CA) — resubmit the
    # original CSR through the connector instead.
    if cert.source == 'msca':
        return _renew_msca_certificate(cert)
    # An issuance policy that requires approval binds a renewal as it binds
    # the issue form (administrators bypass). Fail closed on any error.
    try:
        policy, approval = _approval_for_renewal(g.current_user, cert, request.get_json(silent=True) or {})
    except Exception as e:
        logger.error(f"Policy evaluation failed for renewal of {cert_id}: {e}", exc_info=True)
        return error_response('Policy evaluation failed; the certificate was not renewed', 500)
    if approval is not None:
        from services.approval_gate import approval_payload
        return success_response(data=approval_payload(policy, approval),
                                message='Certificate renewal submitted for approval')

    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    actor_user_id = g.current_user.id if hasattr(g, 'current_user') else None

    try:
        # Manual renewal re-keys: UCM holds this certificate's private key and
        # serves the new one through the export endpoints.
        renew_certificate_in_place(
            cert,
            username=username,
            actor_user_id=actor_user_id,
            rekey=True,
            regenerate_crl=True,
            trigger='manual',
        )
    except RenewalError as e:
        db.session.rollback()
        logger.info(f"Renewal refused for certificate {cert_id}: {e.message}")
        return error_response(e.message, e.status)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to renew certificate {cert_id}: {e}", exc_info=True)
        return error_response('Failed to renew certificate', 500)

    return success_response(
        data=cert.to_dict(),
        message='Certificate renewed successfully'
    )


def _renew_msca_certificate(cert):
    """Renew a Microsoft-CA-issued certificate through its AD CS connection."""
    from api.v2.msca import renew_via_msca  # deferred: avoids circular import

    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    cert_id = cert.id

    try:
        result = renew_via_msca(cert, username=username)
    except PermissionError as e:
        return error_response(str(e), 403)
    except ValueError as e:
        logger.error(f"Cannot renew certificate {cert_id} via Microsoft CA: {e}")
        return error_response(str(e), 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to renew certificate {cert_id} via Microsoft CA: {e}", exc_info=True)
        return error_response('Failed to renew certificate via Microsoft CA', 500)

    if result.get('status') == 'pending':
        return success_response(
            data=cert.to_dict(),
            message='Renewal submitted to Microsoft CA — pending CA manager approval',
            meta={'msca_status': 'pending'}
        )

    # Issued: the certificate row was updated in place by the import
    try:
        AuditService.log_action(
            action='certificate_renewed',
            resource_type='certificate',
            resource_id=str(cert_id),
            resource_name=cert.subject,
            details=f"Renewed via Microsoft CA until {cert.valid_to.isoformat() if cert.valid_to else 'unknown'}",
            user_id=g.current_user.id if hasattr(g, 'current_user') else None
        )
    except Exception:
        pass

    cert_dict = cert.to_dict()
    cert_caref = cert.caref
    from services.webhook_service import emit_cert_renewed
    emit_cert_renewed(cert_dict, ca_refid=cert_caref, actor=username)

    return success_response(
        data=cert_dict,
        message='Certificate renewed by Microsoft CA',
        meta={'msca_status': 'issued'}
    )
