"""
OCSP Responder Routes (RFC 6960)
Handles OCSP requests via GET and POST methods.
"""
import base64
import logging
from urllib.parse import unquote

from flask import Blueprint, request, Response
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.hazmat.primitives import hashes, serialization

from models import db, CA
from services.ocsp_service import OCSPService

logger = logging.getLogger(__name__)

ocsp_bp = Blueprint('ocsp', __name__)
ocsp_service = OCSPService()

OCSP_CONTENT_TYPE = 'application/ocsp-response'
OCSP_REQUEST_TYPE = 'application/ocsp-request'


@ocsp_bp.route('/ocsp', methods=['GET', 'POST'])
def ocsp_responder():
    """
    OCSP responder endpoint (RFC 6960).
    
    GET:  /ocsp?{base64-encoded-request} (query string)
    POST: body = DER-encoded OCSP request
    """
    try:
        # Extract DER-encoded request
        if request.method == 'POST':
            request_der = request.get_data()
        else:
            # GET: request is base64-encoded in the URL query string or path
            path_info = request.query_string.decode('utf-8') if request.query_string else ''
            if not path_info and request.path.startswith('/ocsp/'):
                path_info = request.path[6:]
            if not path_info:
                return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
            try:
                request_der = base64.b64decode(unquote(path_info))
            except Exception:
                return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

        return _process_ocsp_request(request_der)

    except Exception as e:
        logger.error(f"OCSP responder error: {e}", exc_info=True)
        return _error_response(ocsp.OCSPResponseStatus.INTERNAL_ERROR)


@ocsp_bp.route('/ocsp/<path:encoded_request>', methods=['GET'])
def ocsp_responder_get(encoded_request):
    """Handle GET requests with base64-encoded OCSP request in URL path (RFC 6960 §A.1)"""
    try:
        request_der = base64.b64decode(unquote(encoded_request))
    except Exception:
        return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    try:
        return _process_ocsp_request(request_der)
    except Exception as e:
        logger.error(f"OCSP GET responder error: {e}", exc_info=True)
        return _error_response(ocsp.OCSPResponseStatus.INTERNAL_ERROR)


def _process_ocsp_request(request_der: bytes) -> Response:
    """
    Shared OCSP request processing for both GET and POST (RFC 6960).
    Returns OCSP response with proper Cache-Control headers.
    """
    if not request_der:
        return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    ocsp_req = ocsp_service.parse_request(request_der)
    if not ocsp_req:
        return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    cert_serial = ocsp_req.serial_number
    issuer_name_hash = ocsp_req.issuer_name_hash
    issuer_key_hash = ocsp_req.issuer_key_hash
    hash_algorithm = ocsp_req.hash_algorithm

    # Extract nonce for replay protection
    request_nonce = None
    try:
        nonce_ext = ocsp_req.extensions.get_extension_for_class(x509.OCSPNonce)
        request_nonce = nonce_ext.value.nonce
    except x509.ExtensionNotFound:
        pass

    ca = _find_ca_by_issuer_hash(issuer_name_hash, issuer_key_hash, hash_algorithm)
    if not ca:
        return _error_response(ocsp.OCSPResponseStatus.UNAUTHORIZED)

    if not ca.ocsp_enabled:
        return _error_response(ocsp.OCSPResponseStatus.UNAUTHORIZED)

    cert_serial_hex = format(cert_serial, 'x')
    cached = ocsp_service.get_cached_response(ca.id, cert_serial_hex)
    if cached:
        resp = Response(cached, status=200, content_type=OCSP_CONTENT_TYPE)
        _add_cache_headers(resp, request_nonce)
        return resp

    response_der, status_str = ocsp_service.generate_response(
        ca=ca, cert_serial=cert_serial, request_nonce=request_nonce
    )

    logger.info(f"OCSP response for serial {cert_serial_hex}: {status_str}")
    resp = Response(response_der, status=200, content_type=OCSP_CONTENT_TYPE)
    _add_cache_headers(resp, request_nonce)
    return resp


def _add_cache_headers(resp: Response, request_nonce):
    """Add RFC 6960 recommended Cache-Control and Expires headers"""
    if request_nonce:
        # Nonce present — response is unique, don't cache
        resp.headers['Cache-Control'] = 'no-cache, no-store'
    else:
        # No nonce — response can be cached (24h matches nextUpdate)
        resp.headers['Cache-Control'] = 'max-age=3600, public'
        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(hours=1)
        resp.headers['Expires'] = expires.strftime('%a, %d %b %Y %H:%M:%S GMT')


def _find_ca_by_issuer_hash(issuer_name_hash, issuer_key_hash, hash_algorithm):
    """
    Find the CA that matches the OCSP request's issuer hashes.
    Compares issuer name hash and key hash against all CAs.
    """
    try:
        cas = CA.query.filter(CA.crt.isnot(None)).all()
        for ca in cas:
            try:
                ca_cert = x509.load_pem_x509_certificate(ca.crt.encode())

                # Compute issuer name hash
                if isinstance(hash_algorithm, hashes.SHA1):
                    digest = hashes.Hash(hashes.SHA1())
                elif isinstance(hash_algorithm, hashes.SHA256):
                    digest = hashes.Hash(hashes.SHA256())
                else:
                    digest = hashes.Hash(hashes.SHA1())

                digest.update(ca_cert.subject.public_bytes(serialization.Encoding.DER))
                computed_name_hash = digest.finalize()

                if computed_name_hash == issuer_name_hash:
                    return ca

            except Exception:
                continue
        return None
    except Exception as e:
        logger.error(f"Error finding CA by issuer hash: {e}")
        return None


def _error_response(status):
    """Build an unsuccessful OCSP response"""
    response = ocsp.OCSPResponseBuilder.build_unsuccessful(status)
    return Response(
        response.public_bytes(serialization.Encoding.DER),
        status=200,  # OCSP always returns 200 HTTP, error is in the OCSP payload
        content_type=OCSP_CONTENT_TYPE
    )
