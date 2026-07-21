"""
SCEP Protocol Routes
Implements RFC 8894 SCEP endpoints at /scep/pkiclient.exe
"""

import base64
import logging

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from flask import Blueprint, make_response, request
from sqlalchemy import and_

from models import CA, SystemConfig, db
from services.scep.crypto_helpers import create_degenerate_pkcs7, create_signed_pkcs7
from services.scep.scep_service import SCEPService
from utils.trusted_proxy import client_ip

logger = logging.getLogger(__name__)

bp = Blueprint('scep_protocol', __name__)

# Cap PKIOperation POST bodies. A real CSR + CMS envelope is comfortably under
# 32 KB; 1 MiB is a generous ceiling that still prevents trivial DoS by feeding
# us multi-megabyte garbage to ASN.1-parse.
MAX_PKI_BODY_BYTES = 1 * 1024 * 1024


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def get_scep_service():
    """Get configured SCEP service instance"""
    # Get SCEP configuration
    enabled = get_config('scep_enabled', 'true') == 'true'
    if not enabled:
        return None, "SCEP is disabled"

    ca_id = get_config('scep_ca_id')
    if not ca_id:
        return None, "No CA configured for SCEP"

    # Find CA
    try:
        ca = db.session.get(CA, int(ca_id))
        if not ca:
            ca = CA.query.filter_by(refid=ca_id).first()
    except (ValueError, TypeError):
        ca = CA.query.filter_by(refid=ca_id).first()

    if not ca:
        return None, "Configured CA not found"

    if not ca.has_private_key:
        return None, "CA does not have a private key"

    if ca.offline:
        return None, "CA is offline; restore it before using it for SCEP"

    # SCEP enrollment decrypts the client's PKCS#7 envelope with the CA's
    # RSA private key (RFC 8894 §3.4). HSM-resident signing keys do not
    # expose decryption in the current providers, so SCEP is not supported
    # for HSM-backed CAs. Local CAs work normally.
    if ca.uses_hsm:
        return None, (
            "SCEP is not supported for HSM-backed CAs: the protocol "
            "requires RSA envelope decryption, which is not available "
            "for HSM-resident keys"
        )

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
        logger.error(f"SCEP service init failed: {e}")
        return None, "SCEP service initialization failed"


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
    """Handle GetCACaps operation - return implemented RFC 8894 capabilities."""
    # RFC 8894 §3.5.2 defines "AES" specifically as AES128-CBC. There is no
    # registered AES-256 capability keyword; support is inferred from requests.
    response = make_response("\n".join(SCEPService.CAPABILITIES))
    response.headers['Content-Type'] = 'text/plain'
    return response


def handle_get_ca_cert():
    """Handle GetCACert operation - return CA certificate (RFC 8894 §3.2)"""
    service, error = get_scep_service()

    if error:
        return make_error_response(error, 500)

    try:
        if service.ca.caref:
            ca_data = create_degenerate_pkcs7(service.get_ca_chain())
            content_type = 'application/x-x509-ca-ra-cert'
        else:
            ca_data = service.get_ca_cert()
            content_type = 'application/x-x509-ca-cert'

        response = make_response(ca_data)
        response.headers['Content-Type'] = content_type
        return response

    except Exception as e:
        logger.error(f"SCEP GetCACert error: {e}")
        return make_error_response("SCEP server error", 500)


def handle_get_next_ca_cert():
    """Handle GetNextCACert operation (RFC 8894 §4.7)

    Returns the next CA certificate for CA rollover scenarios.
    If the CA has a pending renewal certificate, return it in PKCS#7 format.
    Otherwise return 404 (no rollover in progress).
    """
    service, error = get_scep_service()

    if error:
        return make_error_response(error, 500)

    try:
        ca = service.ca

        # Look for a newer CA cert that is part of the same chain (same parent)
        # as the current CA, OR a self-renewed root with the same description.
        #
        # The previous code used a Python ternary inside a SQLAlchemy filter
        # expression — Python evaluates it once at request time using the
        # truthiness of CA.caref (a Column object, always truthy), so the
        # ``CA.id != ca.id`` branch was dead code and the resulting SQL
        # silently filtered on the wrong column. Use proper SQLAlchemy
        # disjunction instead.
        if ca.caref:
            same_chain = CA.caref == ca.caref
        else:
            # Root CA: just look for siblings with the same descriptor.
            same_chain = CA.descr == ca.descr

        next_ca = (
            CA.query
            .filter(and_(same_chain, CA.id != ca.id, CA.descr == ca.descr))
            .order_by(CA.id.desc())
            .first()
        )

        if not next_ca or not next_ca.crt:
            return make_error_response("No rollover CA certificate available", 404)

        # Parse the next CA cert to verify it's actually newer.
        try:
            next_cert = x509.load_pem_x509_certificate(
                base64.b64decode(next_ca.crt), default_backend()
            )
            if next_cert.not_valid_after_utc <= service.ca_cert.not_valid_after_utc:
                return make_error_response("No rollover CA certificate available", 404)
        except Exception as e:
            logger.warning(f"SCEP rollover certificate is invalid: {e}")
            return make_error_response("No rollover CA certificate available", 404)

        # RFC 8894 §4.7.1 requires an outer SignedData signed by the current
        # CA. Its content is a degenerate certificates-only SignedData carrying
        # the rollover certificate.
        rollover_certs = create_degenerate_pkcs7([next_cert])
        signed_response = create_signed_pkcs7(
            rollover_certs,
            service.ca_key,
            service.ca_cert,
        )

        response = make_response(signed_response)
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
            # Reject oversized bodies up-front to avoid spending cycles parsing
            # multi-megabyte garbage.
            content_length = request.content_length or 0
            if content_length > MAX_PKI_BODY_BYTES:
                return make_error_response(
                    f"PKIOperation body exceeds {MAX_PKI_BODY_BYTES} bytes", 413
                )
            pkcs7_data = request.get_data(cache=False)
            if len(pkcs7_data) > MAX_PKI_BODY_BYTES:
                return make_error_response(
                    f"PKIOperation body exceeds {MAX_PKI_BODY_BYTES} bytes", 413
                )
        else:
            # GET request - message is base64 encoded in 'message' parameter
            message_b64 = request.args.get('message', '')
            if not message_b64:
                return make_error_response("Missing 'message' parameter", 400)
            if len(message_b64) > MAX_PKI_BODY_BYTES:
                return make_error_response("PKIOperation body too large", 413)
            try:
                pkcs7_data = base64.b64decode(message_b64)
            except Exception:
                return make_error_response("Invalid base64 in 'message' parameter", 400)

        if not pkcs7_data:
            return make_error_response("Empty PKCS#7 message", 400)

        # Get client IP for logging (respects X-Forwarded-For only behind a trusted proxy)
        ip = client_ip() or 'unknown'

        # Process the SCEP request
        response_data, status = service.process_pkcs_req(pkcs7_data, ip)

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
