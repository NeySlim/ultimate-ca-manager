"""
SCEP Protocol Routes
Implements RFC 8894 SCEP endpoints at /scep/pkiclient.exe
"""

from flask import Blueprint, request, make_response
from models import db, CA, SystemConfig
import base64
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('scep_protocol', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def get_scep_service():
    """Get configured SCEP service instance"""
    from services.scep_service import SCEPService
    
    # Get SCEP configuration
    enabled = get_config('scep_enabled', 'true') == 'true'
    if not enabled:
        return None, "SCEP is disabled"
    
    ca_id = get_config('scep_ca_id')
    if not ca_id:
        return None, "No CA configured for SCEP"
    
    # Find CA
    try:
        ca = CA.query.get(int(ca_id))
        if not ca:
            ca = CA.query.filter_by(refid=ca_id).first()
    except (ValueError, TypeError):
        ca = CA.query.filter_by(refid=ca_id).first()
    
    if not ca:
        return None, "Configured CA not found"
    
    if not ca.prv:
        return None, "CA does not have a private key"
    
    # Get challenge password and auto-approve setting
    challenge = get_config(f'scep_challenge_{ca.id}')
    auto_approve = get_config('scep_auto_approve', 'false') == 'true'
    
    try:
        service = SCEPService(
            ca_refid=ca.refid,
            challenge_password=challenge,
            auto_approve=auto_approve
        )
        return service, None
    except Exception as e:
        return None, str(e)


@bp.route('/scep/pkiclient.exe', methods=['GET', 'POST'])
def scep_endpoint():
    """
    Main SCEP endpoint - handles all SCEP operations
    
    Operations (via 'operation' query parameter):
    - GetCACaps: Get CA capabilities
    - GetCACert: Get CA certificate
    - PKIOperation: Certificate enrollment (GET=poll, POST=enroll)
    """
    operation = request.args.get('operation', '')
    
    if not operation:
        # Return capabilities by default (common client behavior)
        return handle_get_ca_caps()
    elif operation == 'GetCACaps':
        return handle_get_ca_caps()
    elif operation == 'GetCACert':
        return handle_get_ca_cert()
    elif operation == 'GetNextCACert':
        return handle_get_next_ca_cert()
    elif operation == 'PKIOperation':
        return handle_pki_operation()
    else:
        return make_error_response(f"Unknown operation: {operation}", 400)


def handle_get_ca_caps():
    """Handle GetCACaps operation - return CA capabilities"""
    # Return capabilities even if SCEP is disabled (for discovery)
    capabilities = [
        "POSTPKIOperation",
        "SHA-1",
        "SHA-256", 
        "SHA-512",
        "DES3",
        "AES",
        "SCEPStandard",
        "Renewal",
        "GetNextCACert",
    ]
    
    response = make_response("\n".join(capabilities))
    response.headers['Content-Type'] = 'text/plain'
    return response


def handle_get_ca_cert():
    """Handle GetCACert operation - return CA certificate (RFC 8894 §3.2)"""
    service, error = get_scep_service()
    
    if error:
        return make_error_response(error, 500)
    
    try:
        # Always return the single CA cert as DER with application/x-x509-ca-cert.
        # application/x-x509-ca-ra-cert is only correct when a separate RA cert
        # exists (distinct from the CA cert); UCM uses the CA itself as the RA,
        # so that content-type causes Apple clients to fail validation looking for
        # dedicated RA signing/encryption certs that aren't there (-67731).
        ca_cert_der = service.get_ca_cert()
        response = make_response(ca_cert_der)
        response.headers['Content-Type'] = 'application/x-x509-ca-cert'
        return response
        
    except Exception as e:
        logger.error(f"SCEP GetCACert error: {e}")
        return make_error_response("SCEP server error", 500)


def handle_get_next_ca_cert():
    """Handle GetNextCACert operation (RFC 8894 §3.5)
    
    Returns the next CA certificate for CA rollover scenarios.
    If the CA has a pending renewal certificate, return it in PKCS#7 format.
    Otherwise return 404 (no rollover in progress).
    """
    service, error = get_scep_service()
    
    if error:
        return make_error_response(error, 500)
    
    try:
        ca = service.ca
        
        # Look for a newer CA certificate issued to the same subject
        # that is not yet active (validity starts in the future)
        # or a recently renewed CA cert
        from utils.datetime_utils import utc_now
        
        next_ca = CA.query.filter(
            CA.caref == ca.caref if ca.caref else CA.id != ca.id,
            CA.id != ca.id,
            CA.descr == ca.descr,
        ).order_by(CA.id.desc()).first()
        
        if not next_ca or not next_ca.crt:
            return make_error_response("No rollover CA certificate available", 404)
        
        # Parse the next CA cert to verify it's actually newer
        from cryptography import x509 as x509_mod
        from cryptography.hazmat.backends import default_backend
        
        try:
            next_cert = x509_mod.load_pem_x509_certificate(
                next_ca.crt.encode() if isinstance(next_ca.crt, str) else next_ca.crt,
                default_backend()
            )
            current_cert = x509_mod.load_pem_x509_certificate(
                ca.crt.encode() if isinstance(ca.crt, str) else ca.crt,
                default_backend()
            )
            
            if next_cert.not_valid_after_utc <= current_cert.not_valid_after_utc:
                return make_error_response("No rollover CA certificate available", 404)
        except Exception:
            return make_error_response("No rollover CA certificate available", 404)
        
        # Return as degenerate PKCS#7 (same format as GetCACert for intermediates)
        chain_der = service._create_degenerate_pkcs7([next_cert])
        
        response = make_response(chain_der)
        response.headers['Content-Type'] = 'application/x-x509-next-ca-cert'
        return response
        
    except Exception as e:
        logger.error(f"SCEP GetNextCACert error: {e}")
        return make_error_response("SCEP server error", 500)


def handle_pki_operation():
    """Handle PKIOperation - certificate enrollment"""
    service, error = get_scep_service()
    
    if error:
        return make_error_response(error, 500)
    
    try:
        # Get PKCS#7 message from request
        if request.method == 'POST':
            pkcs7_data = request.data
        else:
            # GET request - message is base64 encoded in 'message' parameter
            message_b64 = request.args.get('message', '')
            if not message_b64:
                return make_error_response("Missing 'message' parameter", 400)
            try:
                pkcs7_data = base64.b64decode(message_b64)
            except Exception:
                return make_error_response("Invalid base64 in 'message' parameter", 400)
        
        if not pkcs7_data:
            return make_error_response("Empty PKCS#7 message", 400)
        
        # Get client IP for logging
        client_ip = request.remote_addr or 'unknown'
        
        # Process the SCEP request
        response_data, status = service.process_pkcs_req(pkcs7_data, client_ip)
        
        # Return PKCS#7 response
        response = make_response(response_data)
        response.headers['Content-Type'] = 'application/x-pki-message'
        return response
        
    except Exception as e:
        logger.error(f"SCEP PKIOperation error: {e}", exc_info=True)
        return make_error_response("SCEP processing error", 500)


def make_error_response(message, status_code):
    """Create error response"""
    response = make_response(message)
    response.status_code = status_code
    response.headers['Content-Type'] = 'text/plain'
    return response


# Alternate URL for compatibility (Cisco, etc.)
@bp.route('/cgi-bin/pkiclient.exe', methods=['GET', 'POST'])
def scep_alternate():
    """Alternate SCEP URLs for compatibility"""
    return scep_endpoint()
