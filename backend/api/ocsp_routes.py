"""
OCSP Public Endpoint (RFC 6960)
Provides public OCSP responder - NO AUTHENTICATION REQUIRED
"""
import logging
from flask import Blueprint, request, Response
from cryptography.x509 import ocsp
from models import CA
from services.ocsp_service import OCSPService

logger = logging.getLogger(__name__)

ocsp_bp = Blueprint('ocsp', __name__)
ocsp_service = OCSPService()


@ocsp_bp.route('/ocsp', methods=['GET', 'POST'])
def ocsp_responder():
    """
    OCSP Responder endpoint
    Supports both GET and POST methods as per RFC 6960
    
    GET: /ocsp/<base64-encoded-request>
    POST: /ocsp with application/ocsp-request body
    
    Returns: application/ocsp-response
    """
    try:
        # Get request data
        if request.method == 'POST':
            # POST method - request is in body
            request_der = request.get_data()
            if not request_der:
                logger.warning("Empty OCSP request body")
                return Response(
                    _build_error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST),
                    mimetype='application/ocsp-response',
                    status=400
                )
        else:
            # GET method - request is in URL path
            # Format: /ocsp/<base64-url-encoded-request>
            import base64
            encoded_request = request.path.split('/ocsp/')[-1]
            if not encoded_request:
                logger.warning("Missing OCSP request in URL")
                return Response(
                    _build_error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST),
                    mimetype='application/ocsp-response',
                    status=400
                )
            
            try:
                # Decode base64-url encoding
                request_der = base64.urlsafe_b64decode(encoded_request + '==')
            except Exception as e:
                logger.error(f"Failed to decode OCSP request from URL: {e}")
                return Response(
                    _build_error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST),
                    mimetype='application/ocsp-response',
                    status=400
                )
        
        # Parse OCSP request
        ocsp_request = ocsp_service.parse_request(request_der)
        if not ocsp_request:
            logger.warning("Invalid OCSP request")
            return Response(
                _build_error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST),
                mimetype='application/ocsp-response',
                status=400
            )
        
        # Extract certificate serial from request
        # OCSP request contains one or more SingleRequest objects
        if len(ocsp_request) == 0:
            logger.warning("OCSP request contains no certificate requests")
            return Response(
                _build_error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST),
                mimetype='application/ocsp-response',
                status=400
            )
        
        # Get first request (most OCSP requests contain only one)
        single_request = ocsp_request[0]
        cert_serial = single_request.serial_number
        issuer_name_hash = single_request.issuer_name_hash
        issuer_key_hash = single_request.issuer_key_hash
        
        logger.info(f"OCSP request for serial: {cert_serial:x}")
        
        # Find CA by issuer hashes
        ca = _find_ca_by_hashes(issuer_name_hash, issuer_key_hash)
        if not ca:
            logger.warning(f"CA not found for OCSP request (serial: {cert_serial:x})")
            return Response(
                _build_error_response(ocsp.OCSPResponseStatus.UNAUTHORIZED),
                mimetype='application/ocsp-response',
                status=401
            )
        
        # Check if OCSP is enabled for this CA
        if not ca.ocsp_enabled:
            logger.warning(f"OCSP not enabled for CA {ca.id} ({ca.descr})")
            return Response(
                _build_error_response(ocsp.OCSPResponseStatus.UNAUTHORIZED),
                mimetype='application/ocsp-response',
                status=401
            )
        
        # Extract nonce if present (for replay protection)
        request_nonce = None
        try:
            for ext in ocsp_request.extensions:
                if isinstance(ext.value, ocsp.OCSPNonce):
                    request_nonce = ext.value.nonce
                    break
        except:
            pass  # Nonce is optional
        
        # Check cache first
        cert_serial_hex = format(cert_serial, 'x')
        cached_response = ocsp_service.get_cached_response(ca.id, cert_serial_hex)
        
        if cached_response and not request_nonce:
            # Use cached response (but only if no nonce, as nonce must be unique)
            logger.debug(f"Returning cached OCSP response for serial {cert_serial_hex}")
            return Response(
                cached_response,
                mimetype='application/ocsp-response',
                status=200
            )
        
        # Generate new response
        response_der, status = ocsp_service.generate_response(
            ca=ca,
            cert_serial=cert_serial,
            request_nonce=request_nonce
        )
        
        logger.info(f"OCSP response generated: serial={cert_serial_hex}, status={status}")
        
        return Response(
            response_der,
            mimetype='application/ocsp-response',
            status=200
        )
        
    except Exception as e:
        logger.error(f"OCSP responder error: {e}", exc_info=True)
        return Response(
            _build_error_response(ocsp.OCSPResponseStatus.INTERNAL_ERROR),
            mimetype='application/ocsp-response',
            status=500
        )


def _build_error_response(status: ocsp.OCSPResponseStatus) -> bytes:
    """Build error OCSP response"""
    from cryptography.hazmat.primitives import serialization
    response = ocsp.OCSPResponseBuilder.build_unsuccessful(status)
    return response.public_bytes(serialization.Encoding.DER)


def _find_ca_by_hashes(issuer_name_hash: bytes, issuer_key_hash: bytes) -> CA:
    """
    Find CA by issuer name hash and key hash
    
    Args:
        issuer_name_hash: SHA1 hash of issuer name
        issuer_key_hash: SHA1 hash of issuer public key
        
    Returns:
        CA object or None
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        
        # Get all CAs
        cas = CA.query.all()
        
        for ca in cas:
            try:
                # Load CA certificate
                ca_cert = x509.load_pem_x509_certificate(
                    ca.crt.encode(),
                    default_backend()
                )
                
                # Calculate hashes
                from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
                
                # Name hash
                name_hash = hashes.Hash(hashes.SHA1(), backend=default_backend())
                name_hash.update(ca_cert.subject.public_bytes(default_backend()))
                calculated_name_hash = name_hash.finalize()
                
                # Key hash
                key_hash = hashes.Hash(hashes.SHA1(), backend=default_backend())
                public_key_der = ca_cert.public_key().public_bytes(
                    Encoding.DER,
                    PublicFormat.SubjectPublicKeyInfo
                )
                # Extract the BIT STRING from the SubjectPublicKeyInfo
                # Skip the SEQUENCE and AlgorithmIdentifier to get to the BIT STRING
                key_hash.update(public_key_der)
                calculated_key_hash = key_hash.finalize()
                
                # Compare hashes
                if calculated_name_hash == issuer_name_hash or calculated_key_hash == issuer_key_hash:
                    return ca
                    
            except Exception as e:
                logger.debug(f"Error checking CA {ca.id}: {e}")
                continue
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding CA by hashes: {e}")
        return None
