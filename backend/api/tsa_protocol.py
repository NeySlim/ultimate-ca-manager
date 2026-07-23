"""
RFC 3161 Time-Stamp Protocol (TSP) API Endpoint

Provides /tsa endpoint for timestamp requests.
"""
from flask import Blueprint, request, make_response
import logging

from models import CA
from services.audit_service import AuditService
from utils.trusted_proxy import client_ip

logger = logging.getLogger(__name__)

bp = Blueprint('tsa', __name__)

# RFC 3161 TimeStampReq is a small DER struct (~ a few hundred bytes for a
# SHA-512 digest + nonce + policy). 64 KB is generous and prevents DoS via
# multi-megabyte garbage being ASN.1-parsed.
MAX_TSA_BODY_BYTES = 64 * 1024


@bp.route('/tsa', methods=['POST'])
def timestamp_request():
    """RFC 3161 Timestamp Request endpoint
    
    Accepts: application/timestamp-query (DER-encoded TimeStampReq)
    Returns: application/timestamp-reply (DER-encoded TimeStampResp)
    """
    # Validate content type
    content_type = request.content_type or ''
    if 'timestamp-query' not in content_type and 'application/octet-stream' not in content_type:
        response = make_response('Invalid content type', 400)
        return response

    # Cap body size up-front
    cl = request.content_length
    if cl is not None and cl > MAX_TSA_BODY_BYTES:
        response = make_response('Request body too large', 413)
        return response

    tsp_request = request.get_data(cache=False)
    if len(tsp_request) > MAX_TSA_BODY_BYTES:
        response = make_response('Request body too large', 413)
        return response
    if not tsp_request:
        response = make_response('Empty request', 400)
        return response
    
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from services.tsa_service import TSAConfigurationError, TSAService
        from models import SystemConfig

        # tsa_enabled did not exist before 2.200: an install that configured a
        # TSA CA but never saved the TSA page again has no row — treat that as
        # enabled (grandfathered) instead of breaking timestamping on upgrade.
        enabled_config = SystemConfig.query.filter_by(key='tsa_enabled').first()
        if enabled_config is not None and str(enabled_config.value).lower() != 'true':
            logger.warning("TSA request refused: TSA is disabled")
            response = make_response('TSA temporarily unavailable', 503)
            response.headers['Content-Type'] = 'text/plain'
            return response

        # Get configured TSA CA. Timestamping is an explicit opt-in service:
        # without an admin-designated CA we do NOT silently fall back to an
        # arbitrary CA key (that would turn any deployment into an anonymous
        # signing service using the CA's private key).
        tsa_ca_config = SystemConfig.query.filter_by(key='tsa_ca_refid').first()
        tsa_ca_refid = tsa_ca_config.value if tsa_ca_config else ''
        if not tsa_ca_refid:
            logger.warning("TSA request refused: no CA configured for TSA")
            response = make_response('TSA not configured', 503)
            response.headers['Content-Type'] = 'text/plain'
            return response
        ca = CA.query.filter_by(refid=tsa_ca_refid).first()

        if not ca or not ca.crt or not ca.prv:
            logger.warning(
                "TSA request refused: configured CA %r not found or missing cert/key",
                tsa_ca_refid,
            )
            response = make_response('TSA not configured', 503)
            response.headers['Content-Type'] = 'text/plain'
            return response

        # Offline CAs must not sign (consistent with CSR/CRL signing paths)
        if ca.offline:
            logger.warning(f"TSA request refused: CA '{ca.descr}' is offline")
            response = make_response('TSA temporarily unavailable', 503)
            response.headers['Content-Type'] = 'text/plain'
            return response
        
        # Load CA cert and key
        import base64
        ca_cert = x509.load_pem_x509_certificate(
            base64.b64decode(ca.crt), default_backend()
        )
        
        # Decrypt private key (may be stored encrypted)
        try:
            from security.encryption import decrypt_private_key
            prv_decrypted = decrypt_private_key(ca.prv)
        except ImportError:
            prv_decrypted = ca.prv
        
        ca_key = load_pem_private_key(
            base64.b64decode(prv_decrypted), password=None, backend=default_backend()
        )
        
        # Process timestamp request
        tsa_policy_config = SystemConfig.query.filter_by(key='tsa_policy_oid').first()
        tsa_policy = tsa_policy_config.value if tsa_policy_config else '1.2.3.4.1'
        try:
            service = TSAService(ca_cert, ca_key, tsa_policy)
        except TSAConfigurationError as exc:
            logger.error(f'Invalid TSA configuration: {exc}')
            response = make_response('TSA configuration invalid', 503)
            response.headers['Content-Type'] = 'text/plain'
            return response

        response_der, status_code = service.process_request(tsp_request)
        metadata = service.issued_token_metadata(response_der)
        if metadata is not None:
            ip_address = client_ip()
            AuditService.log_action(
                action='tsa.timestamp_issued',
                resource_type='tsa',
                resource_id=str(metadata['serial']),
                resource_name=metadata['policy_oid'],
                details=(
                    f"TSA timestamp issued: serial={metadata['serial']}; "
                    f"policy={metadata['policy_oid']}; ip={ip_address}"
                ),
                success=True,
            )

        response = make_response(response_der, status_code)
        response.headers['Content-Type'] = 'application/timestamp-reply'
        return response

    except ImportError as e:
        logger.error(f"TSA dependency missing: {e}")
        response = make_response('TSA not available', 503)
        response.headers['Content-Type'] = 'text/plain'
        return response
    except Exception as e:
        logger.error(f"TSA error: {e}", exc_info=True)
        response = make_response('Internal server error', 500)
        response.headers['Content-Type'] = 'text/plain'
        return response
