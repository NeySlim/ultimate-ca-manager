"""
OCSP Responder Routes (RFC 6960)
Handles OCSP requests via GET and POST methods.
"""
import base64
import logging
from datetime import timedelta
from urllib.parse import unquote

from flask import Blueprint, request, Response
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from models import CA
from services.ocsp_service import OCSPService
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

ocsp_bp = Blueprint('ocsp', __name__)
ocsp_service = OCSPService()

OCSP_CONTENT_TYPE = 'application/ocsp-response'
OCSP_REQUEST_TYPE = 'application/ocsp-request'

# RFC 6960 OCSP requests are very small (typically <1KB even with extensions).
# Cap to 16KB to prevent DoS via huge unauthenticated POSTs.
MAX_OCSP_REQUEST_BYTES = 16 * 1024


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
            # RFC 6960 §4.2.2: validate Content-Type
            content_type = request.content_type or ''
            if not content_type.startswith(OCSP_REQUEST_TYPE):
                return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
            # Cap body size — public unauthenticated endpoint
            cl = request.content_length
            if cl is not None and cl > MAX_OCSP_REQUEST_BYTES:
                return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
            request_der = request.get_data(cache=False)
            if len(request_der) > MAX_OCSP_REQUEST_BYTES:
                return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
        else:
            # GET: request is base64-encoded in the URL query string or path
            path_info = request.query_string.decode('utf-8') if request.query_string else ''
            if not path_info and request.path.startswith('/ocsp/'):
                path_info = request.path[6:]
            if not path_info:
                return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
            if len(path_info) > MAX_OCSP_REQUEST_BYTES * 2:  # base64 ~33% overhead
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
    if len(encoded_request) > MAX_OCSP_REQUEST_BYTES * 2:
        return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
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

    parsed_request = ocsp_service.parse_request_details(request_der)
    if not parsed_request:
        return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)
    if parsed_request.has_unsupported_critical_extension:
        return _error_response(ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    matched_cas = []
    for item in parsed_request.requests:
        ca = _find_ca_by_issuer_hash(
            item.issuer_name_hash,
            item.issuer_key_hash,
            item.hash_algorithm,
        )
        if not ca or not ca.ocsp_enabled:
            return _error_response(ocsp.OCSPResponseStatus.UNAUTHORIZED)
        matched_cas.append(ca)

    ca = matched_cas[0]
    if any(item_ca.id != ca.id for item_ca in matched_cas[1:]):
        # One BasicOCSPResponse signer must be authorized for every CertID.
        return _error_response(ocsp.OCSPResponseStatus.UNAUTHORIZED)

    request_nonce = parsed_request.nonce
    if len(parsed_request.requests) > 1:
        response_der, statuses = ocsp_service.generate_multi_response(
            ca=ca,
            request_items=parsed_request.requests,
            request_nonce=request_nonce,
        )
        logger.info(
            "OCSP multi-response for %d CertIDs: %s",
            len(parsed_request.requests),
            ','.join(statuses),
        )
        resp = Response(response_der, status=200, content_type=OCSP_CONTENT_TYPE)
        _add_cache_headers(resp, request_nonce)
        return resp

    item = parsed_request.requests[0]
    cert_serial_hex = format(item.serial_number, 'x')
    # RFC 6960 §4.4.1: when client sends a nonce, the response MUST include
    # the same nonce. A cached response holds the nonce of an earlier
    # request, so we cannot reuse it here — regenerate fresh.
    cached = None if request_nonce is not None else ocsp_service.get_cached_response(
        ca.id, cert_serial_hex, item.hash_algorithm)
    if cached:
        resp = Response(cached, status=200, content_type=OCSP_CONTENT_TYPE)
        _add_cache_headers(resp, request_nonce)
        return resp

    response_der, status_str = ocsp_service.generate_response(
        ca=ca,
        cert_serial=item.serial_number,
        request_nonce=request_nonce,
        # Echo the request CertID verbatim (RFC 6960 §4.2.1): strict clients
        # reject a SingleResponse whose CertID differs from the request.
        hash_algorithm=item.hash_algorithm,
        issuer_name_hash=item.issuer_name_hash,
        issuer_key_hash=item.issuer_key_hash,
    )

    logger.info(f"OCSP response for serial {cert_serial_hex}: {status_str}")
    resp = Response(response_der, status=200, content_type=OCSP_CONTENT_TYPE)
    _add_cache_headers(resp, request_nonce)
    return resp


def _add_cache_headers(resp: Response, request_nonce):
    """Add RFC 6960 recommended Cache-Control and Expires headers"""
    if request_nonce is not None:
        # Nonce present — response is unique, don't cache
        resp.headers['Cache-Control'] = 'no-cache, no-store'
    else:
        # No nonce — response can be cached (24h matches nextUpdate)
        resp.headers['Cache-Control'] = 'max-age=3600, public'
        expires = utc_now() + timedelta(hours=1)
        resp.headers['Expires'] = expires.strftime('%a, %d %b %Y %H:%M:%S GMT')


def _find_ca_by_issuer_hash(issuer_name_hash, issuer_key_hash, hash_algorithm):
    """
    Find the CA that matches the OCSP request's issuer hashes (RFC 6960 §4.1.1).
    Compares both issuer name hash AND key hash to disambiguate re-keyed CAs
    that share the same Subject DN.
    """
    try:
        cas = CA.query.filter(CA.crt.isnot(None)).all()
        for ca in cas:
            try:
                # ca.crt is base64-encoded PEM in DB
                ca_pem = base64.b64decode(ca.crt)
                ca_cert = x509.load_pem_x509_certificate(ca_pem)

                # Pick hash matching the request
                if isinstance(hash_algorithm, hashes.SHA224):
                    algo = hashes.SHA224()
                elif isinstance(hash_algorithm, hashes.SHA256):
                    algo = hashes.SHA256()
                elif isinstance(hash_algorithm, hashes.SHA384):
                    algo = hashes.SHA384()
                elif isinstance(hash_algorithm, hashes.SHA512):
                    algo = hashes.SHA512()
                elif isinstance(hash_algorithm, hashes.SHA1):
                    algo = hashes.SHA1()
                else:
                    logger.debug(
                        f"OCSP: unsupported issuer hash algorithm {hash_algorithm.name}"
                    )
                    return None

                # Issuer name hash (over DER-encoded subject)
                d = hashes.Hash(algo)
                d.update(ca_cert.subject.public_bytes(serialization.Encoding.DER))
                computed_name_hash = d.finalize()
                if computed_name_hash != issuer_name_hash:
                    continue

                # Issuer key hash — RFC 6960 §4.1.1: SHA hash of the
                # subjectPublicKey BIT STRING value (i.e. the contents of
                # the BIT STRING, *not* the full SubjectPublicKeyInfo).
                pubkey = ca_cert.public_key()
                if isinstance(pubkey, rsa.RSAPublicKey):
                    spki_value = pubkey.public_bytes(
                        encoding=serialization.Encoding.DER,
                        format=serialization.PublicFormat.PKCS1,
                    )
                elif isinstance(pubkey, ec.EllipticCurvePublicKey):
                    # X9.62 uncompressed point — the BIT STRING contents
                    # for an EC SubjectPublicKey.
                    spki_value = pubkey.public_bytes(
                        encoding=serialization.Encoding.X962,
                        format=serialization.PublicFormat.UncompressedPoint,
                    )
                else:
                    # Ed25519/Ed448: BIT STRING contents are the raw key
                    spki_value = pubkey.public_bytes(
                        encoding=serialization.Encoding.Raw,
                        format=serialization.PublicFormat.Raw,
                    )
                d2 = hashes.Hash(algo)
                d2.update(spki_value)
                computed_key_hash = d2.finalize()

                if issuer_key_hash != computed_key_hash:
                    # Both name AND key hash MUST match (CertID identity).
                    # Re-keyed CAs share the subject DN but differ in keys —
                    # accepting on name alone would mis-route the response.
                    continue
                return ca
            except Exception as e:
                logger.debug(f"OCSP: failed to parse CA cert {ca.refid}: {e}")
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
