"""
SCEP Protocol Routes
Implements RFC 8894 SCEP endpoints at /scep/pkiclient.exe
"""

from flask import Blueprint, request, make_response, current_app
from models import db, CA, SystemConfig
import base64

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
    except:
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
    
    if operation == 'GetCACaps':
        return handle_get_ca_caps()
    elif operation == 'GetCACert':
        return handle_get_ca_cert()
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
    ]
    
    response = make_response("\n".join(capabilities))
    response.headers['Content-Type'] = 'text/plain'
    return response


def handle_get_ca_cert():
    """Handle GetCACert operation - return CA certificate"""
    service, error = get_scep_service()
    
    if error:
        return make_error_response(error, 500)
    
    try:
        # Get CA certificate in DER format
        ca_cert_der = service.get_ca_cert()
        
        response = make_response(ca_cert_der)
        response.headers['Content-Type'] = 'application/x-x509-ca-cert'
        return response
        
    except Exception as e:
        current_app.logger.error(f"SCEP GetCACert error: {e}")
        return make_error_response(str(e), 500)


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
        current_app.logger.error(f"SCEP PKIOperation error: {e}")
        import traceback
        traceback.print_exc()
        return make_error_response(str(e), 500)


def make_error_response(message, status_code):
    """Create error response"""
    response = make_response(message)
    response.status_code = status_code
    response.headers['Content-Type'] = 'text/plain'
    return response


# Also support alternate URL patterns used by some clients
@bp.route('/scep', methods=['GET', 'POST'])
@bp.route('/scep/', methods=['GET', 'POST'])
@bp.route('/cgi-bin/pkiclient.exe', methods=['GET', 'POST'])
def scep_alternate():
    """Alternate SCEP URLs for compatibility"""
    return scep_endpoint()
