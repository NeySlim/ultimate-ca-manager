"""
ACME Proxy API Endpoints (RFC 8555)
Mirrors the standard ACME API but proxies requests to upstream providers.

Supports:
  - Legacy default proxy: /acme/proxy/directory
  - Per-CA proxy paths:   /acme/proxy/<slug>/directory
"""
from flask import Blueprint, request, jsonify, make_response
import base64
import json
import logging
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from services.acme.acme_proxy_service import AcmeProxyService
from services.acme.acme_proxy_account import resolve_proxy_by_slug
from services.acme import AcmeService
from utils.acme_public_url import get_acme_public_origin

logger = logging.getLogger(__name__)

acme_proxy_bp = Blueprint('acme_proxy', __name__, url_prefix='/acme/proxy')


# ==================== Helpers ====================

def _proxy_base_url(slug=None):
    root = f"{get_acme_public_origin(request)}/acme/proxy"
    return f"{root}/{slug}" if slug else root


def get_proxy_service(slug=None):
    base_url = _proxy_base_url(slug)
    if slug:
        account = resolve_proxy_by_slug(slug)
        return AcmeProxyService(base_url, account_id=account.id)
    return AcmeProxyService(base_url)


def _get_nonce():
    """Generate a fresh replay nonce."""
    return AcmeService().generate_nonce()


def proxy_response(data, status=200, headers=None):
    """Build a JSON ACME response with nonce and cache headers."""
    if headers is None:
        headers = {}
    headers['Replay-Nonce'] = _get_nonce()
    headers['Cache-Control'] = 'no-store'
    return make_response(jsonify(data), status, headers)


def proxy_error(error_type, detail, status_code=400):
    """Build an RFC 7807 problem+json error response (RFC 8555 §6.7)."""
    error_data = {
        "type": f"urn:ietf:params:acme:error:{error_type}",
        "detail": detail,
        "status": status_code
    }
    resp = make_response(jsonify(error_data), status_code)
    resp.headers['Content-Type'] = 'application/problem+json'
    resp.headers['Replay-Nonce'] = _get_nonce()
    return resp


def _proxy_expected_jws_urls():
    """URLs accepted for the RFC 8555 JWS ``url`` header on proxy endpoints."""
    path = request.path
    if request.query_string:
        path = f'{path}?{request.query_string.decode("utf-8")}'
    public_origin = get_acme_public_origin(request).rstrip('/')
    urls = [f'{public_origin}{path}']
    inbound = request.url.split('#', 1)[0]
    if inbound not in urls:
        urls.append(inbound)
    return urls


def verify_proxy_jws():
    """Verify incoming JWS against the client's own key.

    Returns:
        Tuple of (is_valid, payload_dict, jwk, error_message)
    """
    try:
        jws_data = request.get_json()
        if not jws_data:
            return False, None, None, "Request body is not valid JSON"

        from api.acme.acme_api import verify_jws
        last_error = "JWS verification failed"
        for expected_url in _proxy_expected_jws_urls():
            is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
            if is_valid:
                return is_valid, payload, jwk, error
            # A non-URL failure means the URL matched and something else is
            # wrong (nonce, signature, alg): retrying other URLs cannot
            # succeed and would only mask this error with a URL mismatch.
            if error and not error.startswith('URL mismatch'):
                return False, None, None, error
            last_error = error or last_error
        return False, None, None, last_error

    except Exception as e:
        logger.error(f"ACME proxy JWS verification error: {e}")
        return False, None, None, "JWS verification failed"


def _require_empty_payload(payload):
    """Validate POST-as-GET: payload MUST be empty (RFC 8555 §6.3)."""
    if payload:
        return proxy_error("malformed", "Payload must be empty for POST-as-GET requests")
    return None


def _dual_route(rule, methods, endpoint):
    """Register both default and slug-scoped proxy routes."""

    def decorator(view_func):
        acme_proxy_bp.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=lambda **kw: view_func(slug=None, **kw),
            methods=methods,
        )
        acme_proxy_bp.add_url_rule(
            f'/<slug>{rule}',
            endpoint=f'{endpoint}_slug',
            view_func=view_func,
            methods=methods,
        )
        return view_func

    return decorator


# ==================== Endpoints ====================

@_dual_route('/directory', methods=['GET'], endpoint='proxy_directory')
def directory(slug=None):
    """ACME directory (RFC 8555 §7.1.1)"""
    try:
        svc = get_proxy_service(slug)
        return proxy_response(svc.get_directory())
    except RuntimeError as e:
        logger.error(f"ACME proxy directory error: {e}")
        return proxy_error("serverInternal", str(e), 500)
    except Exception as e:
        logger.error(f"ACME proxy directory error: {e}")
        return proxy_error("serverInternal", "Failed to retrieve directory", 500)


@_dual_route('/new-nonce', methods=['GET', 'HEAD'], endpoint='proxy_new_nonce')
def new_nonce(slug=None):
    """New nonce (RFC 8555 §7.2)"""
    svc = get_proxy_service(slug)
    nonce = svc.new_nonce()
    resp = make_response('', 200)
    resp.status_code = 204 if request.method == 'HEAD' else 200
    resp.headers['Replay-Nonce'] = nonce
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@_dual_route('/new-account', methods=['POST'], endpoint='proxy_new_account')
def new_account(slug=None):
    """New account (RFC 8555 §7.3)"""
    from models import SystemConfig

    is_valid, payload, jwk, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    if not jwk:
        return proxy_error("malformed", "Missing JWK in protected header")

    eab_data = payload.get('externalAccountBinding') if isinstance(payload, dict) else None
    eab_cfg = SystemConfig.query.filter_by(key='acme_eab_required').first()
    eab_required = (eab_cfg.value if eab_cfg else 'false').lower() == 'true'

    if eab_required and not eab_data:
        return proxy_error('externalAccountRequired',
                           'External account binding required', 400)

    if eab_data:
        acme_svc = AcmeService()
        eab_valid, eab_err = acme_svc.validate_eab(eab_data, jwk)
        if not eab_valid:
            return proxy_error('malformed',
                               f'Invalid external account binding: {eab_err}', 400)

    try:
        acme_svc = AcmeService()
        account, is_new = acme_svc.create_account(
            jwk=jwk,
            contact=payload.get("contact", []),
            terms_of_service_agreed=payload.get("termsOfServiceAgreed", False)
        )

        if eab_data and is_new:
            try:
                eab_protected = json.loads(
                    base64.urlsafe_b64decode(eab_data['protected'] + '==')
                )
                eab_kid = eab_protected.get('kid', '')
                if eab_kid:
                    acme_svc.mark_eab_used(eab_kid, account.account_id)
            except Exception as e:
                logger.warning(f"Could not mark EAB credential used: {e}")

        acct_url = f"{_proxy_base_url(slug)}/acct/{account.account_id}"

        resp_data = {
            "status": account.status,
            "contact": account.contact_list,
            "orders": f"{acct_url}/orders"
        }

        resp = proxy_response(resp_data, 201 if is_new else 200)
        resp.headers['Location'] = acct_url
        return resp
    except Exception as e:
        logger.error(f"ACME proxy new-account error: {e}")
        return proxy_error("serverInternal", "Failed to create account", 500)


@_dual_route('/new-order', methods=['POST'], endpoint='proxy_new_order')
def new_order(slug=None):
    """New order (RFC 8555 §7.4)"""
    is_valid, payload, jwk, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    try:
        identifiers = payload.get('identifiers')
        if not identifiers:
            return proxy_error("malformed", "Missing 'identifiers' in payload")

        not_before = payload.get('notBefore')
        if not_before:
            not_before = datetime.fromisoformat(not_before.replace('Z', '+00:00'))

        client_thumbprint = None
        if jwk:
            try:
                import hashlib
                jwk_canonical = json.dumps(jwk, separators=(',', ':'), sort_keys=True)
                client_thumbprint = base64.urlsafe_b64encode(
                    hashlib.sha256(jwk_canonical.encode()).digest()
                ).rstrip(b'=').decode()
            except Exception:
                pass

        svc = get_proxy_service(slug)
        order_data, order_id = svc.new_order(
            identifiers, not_before, client_thumbprint=client_thumbprint
        )

        order_url = f"{_proxy_base_url(slug)}/order/{order_id}"
        resp = proxy_response(order_data, 201)
        resp.headers['Location'] = order_url
        return resp

    except ValueError as e:
        return proxy_error("malformed", str(e))
    except RuntimeError as e:
        logger.warning(f"ACME proxy new-order: {e}")
        return proxy_error("serverInternal", str(e))
    except Exception as e:
        logger.error(f"ACME proxy new-order error: {e}")
        detail = str(e)
        if "No DNS provider" in detail:
            return proxy_error("serverInternal", detail)
        return proxy_error("serverInternal", "Internal server error", 500)


@_dual_route('/authz/<authz_id>', methods=['POST'], endpoint='proxy_authz')
def authz(authz_id, slug=None):
    """Get authorization (RFC 8555 §7.5) — POST-as-GET"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    err_resp = _require_empty_payload(payload)
    if err_resp:
        return err_resp

    try:
        svc = get_proxy_service(slug)
        result = svc.get_authz(authz_id)
        if not result:
            return proxy_error("malformed", "Authorization not found", 404)

        data, _ = result
        return proxy_response(data)
    except ValueError as e:
        return proxy_error("malformed", str(e), 400)
    except RuntimeError as e:
        logger.warning(f"ACME proxy authz: {e}")
        return proxy_error("unsupportedIdentifier", str(e))
    except Exception as e:
        logger.error(f"ACME proxy authz error: {e}")
        return proxy_error("serverInternal", "Internal server error", 500)


@_dual_route('/challenge/<chall_id>', methods=['POST'], endpoint='proxy_challenge')
def challenge(chall_id, slug=None):
    """Respond to challenge (RFC 8555 §7.5.1)"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    try:
        svc = get_proxy_service(slug)
        data, link_header = svc.respond_challenge(chall_id)
        resp = proxy_response(data)
        if link_header:
            resp.headers['Link'] = link_header
        return resp
    except ValueError as e:
        return proxy_error("malformed", str(e), 400)
    except RuntimeError as e:
        logger.warning(f"ACME proxy challenge: {e}")
        detail = str(e)
        error_type = "serverInternal"
        if "dns-01" in detail.lower() or "unsupported" in detail.lower():
            error_type = "unsupportedIdentifier"
        return proxy_error(error_type, detail)
    except Exception as e:
        logger.error(f"ACME proxy challenge error: {e}")
        return proxy_error("serverInternal", "Internal server error", 500)


@_dual_route('/order/<order_id>', methods=['POST'], endpoint='proxy_get_order')
def get_order(order_id, slug=None):
    """Get order status (RFC 8555 §7.4) — POST-as-GET"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    err_resp = _require_empty_payload(payload)
    if err_resp:
        return err_resp

    try:
        svc = get_proxy_service(slug)
        data = svc.get_order(order_id)
        order_url = f"{_proxy_base_url(slug)}/order/{order_id}"
        resp = proxy_response(data)
        resp.headers['Location'] = order_url
        return resp
    except ValueError as e:
        return proxy_error("malformed", str(e), 400)
    except Exception as e:
        logger.error(f"ACME proxy get-order error: {e}")
        return proxy_error("serverInternal", "Internal server error", 500)


@_dual_route('/order/<order_id>/finalize', methods=['POST'], endpoint='proxy_finalize')
def finalize(order_id, slug=None):
    """Finalize order with CSR (RFC 8555 §7.4)"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    requester_account_id = None
    try:
        jws_data = request.get_json(silent=True) or {}
        protected_b64 = jws_data.get('protected', '')
        if protected_b64:
            protected_b64 += '=' * (-len(protected_b64) % 4)
            protected = json.loads(base64.urlsafe_b64decode(protected_b64))
            kid = protected.get('kid', '')
            if kid:
                requester_account_id = kid.rstrip('/').rsplit('/', 1)[-1]
    except Exception:
        pass

    try:
        csr_b64 = payload.get('csr')
        if not csr_b64:
            return proxy_error("malformed", "Missing 'csr' in payload")

        csr_b64 += '=' * (4 - len(csr_b64) % 4)
        csr_der = base64.urlsafe_b64decode(csr_b64)
        csr_obj = x509.load_der_x509_csr(csr_der)
        csr_pem = csr_obj.public_bytes(serialization.Encoding.PEM).decode()

        svc = get_proxy_service(slug)
        data = svc.finalize_order(order_id, csr_pem,
                                  requester_account_id=requester_account_id)

        order_url = f"{_proxy_base_url(slug)}/order/{order_id}"
        resp = proxy_response(data)
        resp.headers['Location'] = order_url
        return resp
    except PermissionError as e:
        return proxy_error("unauthorized", str(e), 403)
    except ValueError as e:
        return proxy_error("malformed", str(e), 400)
    except Exception as e:
        logger.error(f"ACME proxy finalize error: {e}")
        return proxy_error("serverInternal", "Internal server error", 500)


@_dual_route('/cert/<cert_id>', methods=['POST'], endpoint='proxy_cert')
def cert(cert_id, slug=None):
    """Download certificate (RFC 8555 §7.4.2) — POST-as-GET"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    err_resp = _require_empty_payload(payload)
    if err_resp:
        return err_resp

    try:
        svc = get_proxy_service(slug)
        content, content_type, link_header = svc.get_certificate(cert_id)

        resp = make_response(content, 200)
        resp.headers['Content-Type'] = content_type
        resp.headers['Replay-Nonce'] = _get_nonce()
        resp.headers['Cache-Control'] = 'no-store'
        if link_header:
            resp.headers['Link'] = link_header
        return resp
    except ValueError as e:
        return proxy_error("malformed", str(e), 400)
    except Exception as e:
        logger.error(f"ACME proxy cert error: {e}")
        return proxy_error("serverInternal", "Internal server error", 500)


@_dual_route('/revoke-cert', methods=['POST'], endpoint='proxy_revoke_cert')
def revoke_cert(slug=None):
    """Revoke certificate (RFC 8555 §7.6)"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    if not payload or 'certificate' not in payload:
        return proxy_error("malformed", "Missing 'certificate' in payload")

    logger.warning("ACME proxy revoke-cert called but not implemented")
    return proxy_error("serverInternal", "Certificate revocation via proxy is not supported", 501)


@_dual_route('/key-change', methods=['POST'], endpoint='proxy_key_change')
def key_change(slug=None):
    """Key change (RFC 8555 §7.3.5)"""
    is_valid, payload, _, err = verify_proxy_jws()
    if not is_valid:
        return proxy_error("malformed", err)

    logger.warning("ACME proxy key-change called but not implemented")
    return proxy_error("serverInternal", "Key change via proxy is not supported", 501)
