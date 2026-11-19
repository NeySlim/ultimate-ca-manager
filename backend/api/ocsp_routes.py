"""
OCSP Responder Routes (RFC 6960)
Handles OCSP requests via GET and POST methods.
"""
import base64
import hashlib
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import unquote

from flask import Blueprint, request, Response
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.hazmat.primitives import hashes, serialization

from models import CA
from services.ocsp_service import OCSPService, _subject_public_key_bits

logger = logging.getLogger(__name__)

ocsp_bp = Blueprint('ocsp', __name__)
ocsp_service = OCSPService()

OCSP_CONTENT_TYPE = 'application/ocsp-response'
OCSP_REQUEST_TYPE = 'application/ocsp-request'

# Requests answered and answered from the cache, since this process started (UCM
# runs one worker, which also serves the HTTP protocol port)
_STATS_LOCK = threading.Lock()
_STATS = {'requests': 0, 'cache_hits': 0}


def _count(name):
    with _STATS_LOCK:
        _STATS[name] += 1


def request_stats():
    with _STATS_LOCK:
        return dict(_STATS)


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
    _count('requests')
    try:
        # Extract DER-encoded request
        if request.method == 'POST':
            # RFC 6960 A.1 Content-Type; RFC 9110 §8.3.1: type and subtype ignore case
            if (request.mimetype or '').lower() != OCSP_REQUEST_TYPE:
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
    _count('requests')
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
        _add_cache_headers(resp, request_nonce, response_der)
        return resp

    item = parsed_request.requests[0]
    cert_serial_hex = format(item.serial_number, 'x')
    # RFC 6960 §4.4.1: when client sends a nonce, the response MUST include
    # the same nonce. A cached response holds the nonce of an earlier
    # request, so we cannot reuse it here — regenerate fresh.
    cached = None if request_nonce is not None else ocsp_service.get_cached_response(
        ca.id, cert_serial_hex, item.hash_algorithm)
    if cached:
        _count('cache_hits')
        resp = Response(cached, status=200, content_type=OCSP_CONTENT_TYPE)
        _add_cache_headers(resp, request_nonce, cached)
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
    _add_cache_headers(resp, request_nonce, response_der)
    return resp


def _http_date(moment) -> str:
    return moment.astimezone(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')


def _add_cache_headers(resp: Response, request_nonce, response_der: bytes):
    """RFC 5019 §6.2: cacheable until nextUpdate, never no-cache or no-store."""
    if request_nonce is not None:
        # A nonce makes the answer unique to its request: nothing to reuse
        resp.headers['Cache-Control'] = 'max-age=0, must-revalidate'
        return
    try:
        singles = list(ocsp.load_der_ocsp_response(response_der).responses)
        this_update = max(single.this_update_utc for single in singles)
        next_update = min(single.next_update_utc for single in singles)
    except Exception:  # unsuccessful, or a response without nextUpdate
        return
    # Never past nextUpdate; at most an hour, so a revocation reaches proxy caches quickly
    remaining = int((next_update - datetime.now(timezone.utc)).total_seconds())
    resp.headers['Cache-Control'] = f'max-age={max(0, min(3600, remaining))}, public, no-transform, must-revalidate'
    resp.headers['Expires'] = _http_date(next_update)
    resp.headers['Last-Modified'] = _http_date(this_update)
    # The profile RECOMMENDS the hex SHA-1 of the OCSPResponse: an identifier, not a signature
    resp.headers['ETag'] = f'"{hashlib.sha1(response_der, usedforsecurity=False).hexdigest()}"'


def _find_ca_by_issuer_hash(issuer_name_hash, issuer_key_hash, hash_algorithm):
    """
    Find the CA that matches the OCSP request's issuer hashes (RFC 6960 §4.1.1).
    Compares both issuer name hash AND key hash to disambiguate re-keyed CAs
    that share the same Subject DN.
    """
    try:
        from utils.cert_issuer import self_signed_first
        cas = self_signed_first(CA.query.filter(CA.crt.isnot(None), CA.crt != '').order_by(CA.id).all())
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

                # RFC 6960 §4.1.1: hash of the subjectPublicKey BIT STRING as the certificate carries it
                spki_value = _subject_public_key_bits(ca_cert)
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
