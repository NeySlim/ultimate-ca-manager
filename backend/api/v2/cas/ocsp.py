"""
CAs OCSP Responder Operations
"""

from . import bp
from flask import request, g
import base64
import logging
from datetime import datetime

from auth.unified import require_auth
from utils.response import success_response, error_response, no_content_response
from utils.datetime_utils import utc_isoformat
from services.audit_service import AuditService
from models import CA, Certificate, SystemConfig, db
from cryptography import x509
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


@bp.route('/api/v2/cas/<int:ca_id>/ocsp-responder', methods=['GET'])
@require_auth(['read:cas'])
def get_ocsp_responder(ca_id):
    """Get the delegated OCSP responder certificate for a CA."""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
    if not config or not config.value:
        return success_response(data={'responder': None})

    cert = Certificate.query.get(int(config.value))
    if not cert:
        return success_response(data={'responder': None})

    return success_response(data={'responder': {
        'id': cert.id,
        'common_name': cert.common_name,
        'serial_number': cert.serial_number,
        'valid_to': utc_isoformat(cert.valid_to),
        'issuer_name': cert.issuer_name,
        'revoked': cert.revoked
    }})


@bp.route('/api/v2/cas/<int:ca_id>/ocsp-responder', methods=['POST'])
@require_auth(['write:cas'])
def set_ocsp_responder(ca_id):
    """Set the delegated OCSP responder certificate for a CA."""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    data = request.get_json()
    cert_id = data.get('certificate_id')
    if not cert_id:
        return error_response('certificate_id is required', 400)

    cert = Certificate.query.get(int(cert_id))
    if not cert:
        return error_response('Certificate not found', 404)

    if cert.caref != ca.refid:
        return error_response('Certificate must be issued by this CA', 400)

    if not cert.prv:
        return error_response('Certificate must have a private key', 400)

    if cert.crt:
        try:
            crt_pem = base64.b64decode(cert.crt).decode('utf-8')
            x509_cert = x509.load_pem_x509_certificate(crt_pem.encode(), default_backend())
            try:
                eku = x509_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
                if x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING not in eku.value:
                    return error_response('Certificate must have OCSPSigning EKU', 400)
            except x509.ExtensionNotFound:
                return error_response('Certificate must have OCSPSigning EKU', 400)
        except Exception as e:
            logger.error(f"Failed to validate OCSP responder cert: {e}")
            return error_response('Failed to validate certificate', 500)

    try:
        config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
        if config:
            config.value = str(cert_id)
        else:
            config = SystemConfig(key=f'ocsp_responder_cert_{ca_id}', value=str(cert_id))
            db.session.add(config)
        db.session.commit()

        AuditService.log_action(
            'ocsp_responder_assigned',
            resource_type='ca',
            resource_id=ca_id,
            details=f'Delegated OCSP responder set to cert #{cert_id} for CA {ca.descr}'
        )

        return success_response(data={'certificate_id': cert_id}, message='OCSP responder configured')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set OCSP responder: {e}")
        return error_response('Failed to configure OCSP responder', 500)


@bp.route('/api/v2/cas/<int:ca_id>/ocsp-responder', methods=['DELETE'])
@require_auth(['delete:cas'])
def delete_ocsp_responder(ca_id):
    """Remove the delegated OCSP responder for a CA."""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    try:
        config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca_id}').first()
        if config:
            db.session.delete(config)
            db.session.commit()

            AuditService.log_action(
                'ocsp_responder_removed',
                resource_type='ca',
                resource_id=ca_id,
                details=f'Delegated OCSP responder removed for CA {ca.descr}'
            )

        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove OCSP responder: {e}")
        return error_response('Failed to remove OCSP responder', 500)


@bp.route('/api/v2/cas/<int:ca_id>/eligible-ocsp-responders', methods=['GET'])
@require_auth(['read:cas'])
def list_eligible_ocsp_responders(ca_id):
    """List certificates eligible as OCSP delegated responder for a CA.
    Eligible = issued by this CA, has OCSPSigning EKU, has private key, not revoked/expired.
    """
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    now = datetime.utcnow()
    certs = Certificate.query.filter(
        Certificate.caref == ca.refid,
        Certificate.crt.isnot(None),
        Certificate.prv.isnot(None),
        Certificate.revoked == False
    ).all()

    eligible = []
    for cert in certs:
        if cert.valid_to and cert.valid_to < now:
            continue
        try:
            crt_pem = base64.b64decode(cert.crt).decode('utf-8')
            x509_cert = x509.load_pem_x509_certificate(crt_pem.encode(), default_backend())
            eku = x509_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
            if x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING in eku.value:
                eligible.append({
                    'id': cert.id,
                    'common_name': cert.common_name,
                    'serial_number': cert.serial_number,
                    'valid_to': utc_isoformat(cert.valid_to)
                })
        except (x509.ExtensionNotFound, Exception):
            continue

    return success_response(data=eligible)
