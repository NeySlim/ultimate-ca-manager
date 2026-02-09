
"""
ACME Proxy API Endpoints
Mirrors the standard ACME API but proxies requests to upstream
"""
from flask import Blueprint, request, jsonify, make_response
import json
import base64
from datetime import datetime

from services.acme.acme_proxy_service import AcmeProxyService
from services.acme import AcmeService  # For JWS verification helper

acme_proxy_bp = Blueprint('acme_proxy', __name__, url_prefix='/acme/proxy')

def get_proxy_service():
    base_url = f"{request.scheme}://{request.host}"
    return AcmeProxyService(base_url)

def proxy_response(data, status=200, headers=None):
    if headers is None:
        headers = {}
    
    # Add nonce
    svc = AcmeService() # Local service for local nonces
    headers['Replay-Nonce'] = svc.generate_nonce()
    headers['Cache-Control'] = 'no-store'
    
    return make_response(jsonify(data), status, headers)

def verify_proxy_jws(request):
    """Verify incoming JWS using Local AcmeService"""
    # We verify the client's signature against THEIR key
    # We don't care about upstream here
    svc = AcmeService(f"{request.scheme}://{request.host}")
    
    try:
        jws_data = request.get_json()
        if not jws_data:
            return False, None, None, "No JSON"
            
        # We need to construct expected URL
        # e.g. https://ucm.local/acme/proxy/new-order
        expected_url = request.url
        
        # Reuse existing verification logic
        # Import dynamically to avoid circular imports
        from api.acme.acme_api import verify_jws
        return verify_jws(jws_data, expected_url)
        
    except Exception as e:
        return False, None, None, str(e)

# --- Endpoints ---

@acme_proxy_bp.route('/directory', methods=['GET'])
def directory():
    svc = get_proxy_service()
    return proxy_response(svc.get_directory())

@acme_proxy_bp.route('/new-nonce', methods=['GET', 'HEAD'])
def new_nonce():
    svc = get_proxy_service()
    nonce = svc.new_nonce()
    resp = make_response('', 204)
    resp.headers['Replay-Nonce'] = nonce
    resp.headers['Cache-Control'] = 'no-store'
    return resp

@acme_proxy_bp.route('/new-account', methods=['POST'])
def new_account():
    # ACME Proxy doesn't really register the CLIENT account upstream
    # It uses a SHARED upstream account.
    # But we should register the client locally to track them?
    # Or just pretend?
    # Let's pretend for now to be stateless proxy.
    # We just acknowledge the account creation and give a dummy ID.
    
    # Verify JWS
    is_valid, payload, jwk, err = verify_proxy_jws(request)
    if not is_valid:
        return make_response(jsonify({"type": "malformed", "detail": err}), 400)
        
    # Return a fake account
    acct_url = f"{request.scheme}://{request.host}/acme/proxy/acct/1"
    
    resp_data = {
        "status": "valid",
        "contact": payload.get("contact", []),
        "orders": f"{acct_url}/orders"
    }
    
    resp = proxy_response(resp_data, 201)
    resp.headers['Location'] = acct_url
    return resp

@acme_proxy_bp.route('/new-order', methods=['POST'])
def new_order():
    svc = get_proxy_service()
    
    is_valid, payload, jwk, err = verify_proxy_jws(request)
    if not is_valid:
         return make_response(jsonify({"type": "malformed", "detail": err}), 400)
         
    try:
        identifiers = payload.get('identifiers')
        not_before = payload.get('notBefore')
        if not_before:
             not_before = datetime.fromisoformat(not_before.replace('Z', '+00:00'))
        
        order_data, order_id = svc.new_order(identifiers, not_before)
        
        order_url = f"{request.scheme}://{request.host}/acme/proxy/order/{order_id}"
        resp = proxy_response(order_data, 201)
        resp.headers['Location'] = order_url
        return resp
        
    except Exception as e:
        return make_response(jsonify({"type": "serverInternal", "detail": str(e)}), 500)

@acme_proxy_bp.route('/authz/<authz_id>', methods=['POST'])
def authz(authz_id):
    svc = get_proxy_service()
    # POST-as-GET
    is_valid, _, _, err = verify_proxy_jws(request)
    if not is_valid:
         return make_response(jsonify({"type": "malformed", "detail": err}), 400)

    result = svc.get_authz(authz_id)
    if not result:
        return make_response(jsonify({"type": "malformed", "detail": "Authz not found"}), 404)
    
    # get_authz returns (authz_data, identifier)
    data, _ = result
    return proxy_response(data)

@acme_proxy_bp.route('/challenge/<chall_id>', methods=['POST'])
def challenge(chall_id):
    svc = get_proxy_service()
    is_valid, _, _, err = verify_proxy_jws(request)
    if not is_valid:
         return make_response(jsonify({"type": "malformed", "detail": err}), 400)

    try:
        data, link_header = svc.respond_challenge(chall_id)
        resp = proxy_response(data)
        if link_header:
            resp.headers['Link'] = link_header
        return resp
    except Exception as e:
        return make_response(jsonify({"type": "serverInternal", "detail": str(e)}), 500)

@acme_proxy_bp.route('/order/<order_id>', methods=['POST'])
def get_order(order_id):
    """POST-as-GET for order status polling"""
    svc = get_proxy_service()
    is_valid, _, _, err = verify_proxy_jws(request)
    if not is_valid:
         return make_response(jsonify({"type": "malformed", "detail": err}), 400)

    try:
        data = svc.get_order(order_id)
        order_url = f"{request.scheme}://{request.host}/acme/proxy/order/{order_id}"
        resp = proxy_response(data)
        resp.headers['Location'] = order_url
        return resp
    except Exception as e:
        return make_response(jsonify({"type": "serverInternal", "detail": str(e)}), 500)

@acme_proxy_bp.route('/order/<order_id>/finalize', methods=['POST'])
def finalize(order_id):
    svc = get_proxy_service()
    is_valid, payload, _, err = verify_proxy_jws(request)
    if not is_valid:
         return make_response(jsonify({"type": "malformed", "detail": err}), 400)

    try:
        # Extract CSR from payload
        csr_b64 = payload.get('csr')
        # Convert to PEM for service
        
        import base64
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        
        # Add padding correctly
        csr_b64 += '=' * (4 - len(csr_b64) % 4)
        csr_der = base64.urlsafe_b64decode(csr_b64)
        csr = x509.load_der_x509_csr(csr_der, default_backend())
        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
        
        data = svc.finalize_order(order_id, csr_pem)
        
        order_url = f"{request.scheme}://{request.host}/acme/proxy/order/{order_id}"
        resp = proxy_response(data)
        resp.headers['Location'] = order_url
        return resp
    except Exception as e:
        return make_response(jsonify({"type": "serverInternal", "detail": str(e)}), 500)

@acme_proxy_bp.route('/cert/<cert_id>', methods=['POST'])
def cert(cert_id):
    svc = get_proxy_service()
    # POST-as-GET
    is_valid, _, _, err = verify_proxy_jws(request)
    if not is_valid:
         return make_response(jsonify({"type": "malformed", "detail": err}), 400)

    content, content_type, link_header = svc.get_certificate(cert_id)
    
    resp = make_response(content, 200)
    resp.headers['Content-Type'] = content_type
    
    # Add Link header with issuer cert (required by certbot)
    if link_header:
        resp.headers['Link'] = link_header
    
    # Add nonce
    svc_local = AcmeService()
    resp.headers['Replay-Nonce'] = svc_local.generate_nonce()
    
    return resp
