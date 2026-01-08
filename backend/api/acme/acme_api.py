"""
ACME Protocol API Endpoints (RFC 8555)
Implements the ACME server endpoints for automated certificate management
"""
from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
import json
from typing import Dict, Any

from models import db
from services.acme import AcmeService
from models.acme_models import AcmeAccount, AcmeOrder, AcmeChallenge

# Create blueprint
acme_bp = Blueprint('acme', __name__, url_prefix='/acme')

# Initialize ACME service
# Base URL will be set from request context
acme_service = None


def get_acme_service() -> AcmeService:
    """Get or create ACME service instance with current base URL"""
    global acme_service
    
    if acme_service is None:
        # Construct base URL from request
        base_url = f"{request.scheme}://{request.host}"
        acme_service = AcmeService(base_url=base_url)
    
    return acme_service


def acme_response(data: Dict[str, Any], status_code: int = 200) -> Any:
    """Create ACME-compliant response with proper headers
    
    Args:
        data: Response data
        status_code: HTTP status code
        
    Returns:
        Flask Response object
    """
    service = get_acme_service()
    
    response = make_response(jsonify(data), status_code)
    response.headers['Content-Type'] = 'application/json'
    
    # Add Replay-Nonce header (required by ACME)
    response.headers['Replay-Nonce'] = service.generate_nonce()
    
    # Add Link header to directory
    response.headers['Link'] = f'<{service.base_url}/acme/directory>;rel="index"'
    
    return response


def acme_error(error_type: str, detail: str, status_code: int = 400) -> Any:
    """Create ACME error response
    
    Args:
        error_type: ACME error type (e.g., 'malformed', 'unauthorized')
        detail: Human-readable error description
        status_code: HTTP status code
        
    Returns:
        Flask Response object
    """
    error_data = {
        "type": f"urn:ietf:params:acme:error:{error_type}",
        "detail": detail
    }
    
    return acme_response(error_data, status_code)


# ==================== ACME Directory ====================

@acme_bp.route('/directory', methods=['GET'])
def directory():
    """ACME directory endpoint (RFC 8555 Section 7.1.1)
    
    Returns available ACME endpoints and metadata
    """
    service = get_acme_service()
    
    directory_data = service.get_directory()
    
    # Add metadata
    directory_data['meta'] = {
        'termsOfService': f'{service.base_url}/acme/terms',
        'website': 'https://github.com/fabriziosalmi/ultimate-ca-manager',
        'caaIdentities': [request.host],
        'externalAccountRequired': False
    }
    
    return acme_response(directory_data)


# ==================== Nonce Management ====================

@acme_bp.route('/new-nonce', methods=['GET', 'HEAD'])
def new_nonce():
    """Generate new nonce (RFC 8555 Section 7.2)
    
    Returns empty response with Replay-Nonce header
    """
    service = get_acme_service()
    nonce = service.generate_nonce()
    
    response = make_response('', 204)
    response.headers['Replay-Nonce'] = nonce
    response.headers['Cache-Control'] = 'no-store'
    
    return response


# ==================== Account Management ====================

@acme_bp.route('/new-account', methods=['POST'])
def new_account():
    """Create or retrieve account (RFC 8555 Section 7.3)
    
    Request body (JWS):
        {
            "protected": {...},
            "payload": {
                "termsOfServiceAgreed": true,
                "contact": ["mailto:admin@example.com"]
            },
            "signature": "..."
        }
    """
    service = get_acme_service()
    
    try:
        # Parse JWS (JSON Web Signature)
        jws_data = request.get_json()
        
        if not jws_data:
            return acme_error('malformed', 'Request body must be JWS')
        
        # TODO: Validate JWS signature
        # For MVP, we'll extract payload directly
        
        # Decode protected header
        import base64
        protected_b64 = jws_data.get('protected', '')
        protected_json = base64.urlsafe_b64decode(protected_b64 + '==').decode()
        protected = json.loads(protected_json)
        
        # Get JWK from protected header
        jwk = protected.get('jwk')
        if not jwk:
            return acme_error('malformed', 'JWK required in protected header')
        
        # Decode payload
        payload_b64 = jws_data.get('payload', '')
        payload_json = base64.urlsafe_b64decode(payload_b64 + '==').decode()
        payload = json.loads(payload_json) if payload_json else {}
        
        # Extract account details
        contact = payload.get('contact', [])
        terms_agreed = payload.get('termsOfServiceAgreed', False)
        
        # Create or retrieve account
        account, is_new = service.create_account(
            jwk=jwk,
            contact=contact,
            terms_of_service_agreed=terms_agreed
        )
        
        # Build response
        account_url = f"{service.base_url}/acme/acct/{account.account_id}"
        
        response_data = {
            "status": account.status,
            "contact": json.loads(account.contact) if account.contact else [],
            "termsOfServiceAgreed": account.terms_of_service_agreed,
            "orders": f"{account_url}/orders"
        }
        
        response = acme_response(response_data, 201 if is_new else 200)
        response.headers['Location'] = account_url
        
        return response
        
    except Exception as e:
        return acme_error('serverInternal', f'Internal error: {str(e)}', 500)


@acme_bp.route('/acct/<account_id>', methods=['POST'])
def account_info(account_id: str):
    """Get account information (RFC 8555 Section 7.3.1)"""
    service = get_acme_service()
    
    account = service.get_account_by_kid(account_id)
    
    if not account:
        return acme_error('accountDoesNotExist', 'Account not found', 404)
    
    account_url = f"{service.base_url}/acme/acct/{account.account_id}"
    
    response_data = {
        "status": account.status,
        "contact": json.loads(account.contact) if account.contact else [],
        "orders": f"{account_url}/orders"
    }
    
    response = acme_response(response_data)
    response.headers['Location'] = account_url
    
    return response


# ==================== Order Management ====================

@acme_bp.route('/new-order', methods=['POST'])
def new_order():
    """Create new certificate order (RFC 8555 Section 7.4)
    
    Request payload:
        {
            "identifiers": [
                {"type": "dns", "value": "example.com"},
                {"type": "dns", "value": "*.example.com"}
            ],
            "notBefore": "2024-01-01T00:00:00Z",  # optional
            "notAfter": "2025-01-01T00:00:00Z"     # optional
        }
    """
    service = get_acme_service()
    
    try:
        jws_data = request.get_json()
        
        # Decode protected header to get account
        import base64
        protected_b64 = jws_data.get('protected', '')
        protected_json = base64.urlsafe_b64decode(protected_b64 + '==').decode()
        protected = json.loads(protected_json)
        
        # Get account ID from kid (Key ID)
        kid = protected.get('kid', '')
        account_id = kid.split('/')[-1] if kid else None
        
        if not account_id:
            return acme_error('malformed', 'Account kid required')
        
        # Verify account exists
        account = service.get_account_by_kid(account_id)
        if not account:
            return acme_error('accountDoesNotExist', 'Account not found', 404)
        
        # Decode payload
        payload_b64 = jws_data.get('payload', '')
        payload_json = base64.urlsafe_b64decode(payload_b64 + '==').decode()
        payload = json.loads(payload_json)
        
        # Extract order details
        identifiers = payload.get('identifiers', [])
        if not identifiers:
            return acme_error('malformed', 'At least one identifier required')
        
        # Parse optional dates
        not_before = payload.get('notBefore')
        not_after = payload.get('notAfter')
        
        if not_before:
            not_before = datetime.fromisoformat(not_before.replace('Z', '+00:00'))
        if not_after:
            not_after = datetime.fromisoformat(not_after.replace('Z', '+00:00'))
        
        # Create order
        order = service.create_order(
            account_id=account.account_id,
            identifiers=identifiers,
            not_before=not_before,
            not_after=not_after
        )
        
        # Build response
        order_url = f"{service.base_url}/acme/order/{order.order_id}"
        
        # Get authorization URLs
        authz_urls = [
            f"{service.base_url}/acme/authz/{auth.authorization_id}"
            for auth in order.authorizations
        ]
        
        response_data = {
            "status": order.status,
            "expires": order.expires.isoformat() + 'Z',
            "identifiers": json.loads(order.identifiers),
            "authorizations": authz_urls,
            "finalize": f"{order_url}/finalize"
        }
        
        if order.not_before:
            response_data["notBefore"] = order.not_before.isoformat() + 'Z'
        if order.not_after:
            response_data["notAfter"] = order.not_after.isoformat() + 'Z'
        
        response = acme_response(response_data, 201)
        response.headers['Location'] = order_url
        
        return response
        
    except Exception as e:
        return acme_error('serverInternal', f'Internal error: {str(e)}', 500)


@acme_bp.route('/order/<order_id>', methods=['POST'])
def order_info(order_id: str):
    """Get order status (RFC 8555 Section 7.4)"""
    service = get_acme_service()
    
    order = service.get_order(order_id)
    
    if not order:
        return acme_error('orderDoesNotExist', 'Order not found', 404)
    
    order_url = f"{service.base_url}/acme/order/{order.order_id}"
    
    # Get authorization URLs
    authz_urls = [
        f"{service.base_url}/acme/authz/{auth.authorization_id}"
        for auth in order.authorizations
    ]
    
    response_data = {
        "status": order.status,
        "expires": order.expires.isoformat() + 'Z',
        "identifiers": json.loads(order.identifiers),
        "authorizations": authz_urls,
        "finalize": f"{order_url}/finalize"
    }
    
    if order.certificate_url:
        response_data["certificate"] = order.certificate_url
    
    response = acme_response(response_data)
    response.headers['Location'] = order_url
    
    return response


@acme_bp.route('/order/<order_id>/finalize', methods=['POST'])
def finalize_order(order_id: str):
    """Finalize order with CSR (RFC 8555 Section 7.4)"""
    service = get_acme_service()
    
    try:
        jws_data = request.get_json()
        
        # Decode payload
        import base64
        payload_b64 = jws_data.get('payload', '')
        payload_json = base64.urlsafe_b64decode(payload_b64 + '==').decode()
        payload = json.loads(payload_json)
        
        # Extract CSR
        csr_b64 = payload.get('csr', '')
        if not csr_b64:
            return acme_error('malformed', 'CSR required')
        
        # Decode CSR (DER format in ACME)
        csr_der = base64.urlsafe_b64decode(csr_b64 + '==')
        
        # Convert DER to PEM
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization
        
        csr = x509.load_der_x509_csr(csr_der, default_backend())
        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
        
        # Finalize order
        success, error = service.finalize_order(order_id, csr_pem)
        
        if not success:
            return acme_error('badCSR', error)
        
        # Return updated order
        order = service.get_order(order_id)
        order_url = f"{service.base_url}/acme/order/{order.order_id}"
        
        authz_urls = [
            f"{service.base_url}/acme/authz/{auth.authorization_id}"
            for auth in order.authorizations
        ]
        
        response_data = {
            "status": order.status,
            "expires": order.expires.isoformat() + 'Z',
            "identifiers": json.loads(order.identifiers),
            "authorizations": authz_urls,
            "finalize": f"{order_url}/finalize"
        }
        
        response = acme_response(response_data)
        response.headers['Location'] = order_url
        
        return response
        
    except Exception as e:
        return acme_error('serverInternal', f'Internal error: {str(e)}', 500)


# ==================== Authorization & Challenge ====================

@acme_bp.route('/authz/<authorization_id>', methods=['POST'])
def authorization_info(authorization_id: str):
    """Get authorization status (RFC 8555 Section 7.5)"""
    from backend.models.acme_models import AcmeAuthorization
    
    service = get_acme_service()
    
    auth = AcmeAuthorization.query.filter_by(
        authorization_id=authorization_id
    ).first()
    
    if not auth:
        return acme_error('authzDoesNotExist', 'Authorization not found', 404)
    
    # Build challenges list
    challenges = []
    for challenge in auth.challenges:
        challenge_data = {
            "type": challenge.type,
            "status": challenge.status,
            "url": challenge.url,
            "token": challenge.token
        }
        
        if challenge.validated:
            challenge_data["validated"] = challenge.validated.isoformat() + 'Z'
        
        if challenge.error:
            challenge_data["error"] = json.loads(challenge.error)
        
        challenges.append(challenge_data)
    
    response_data = {
        "status": auth.status,
        "identifier": json.loads(auth.identifier),
        "challenges": challenges,
        "expires": auth.expires.isoformat() + 'Z'
    }
    
    return acme_response(response_data)


@acme_bp.route('/challenge/<challenge_id>', methods=['POST'])
def respond_to_challenge(challenge_id: str):
    """Respond to challenge and trigger validation (RFC 8555 Section 7.5.1)"""
    service = get_acme_service()
    
    # Extract challenge ID from URL path
    # In practice, challenge ID is embedded in the URL
    # For simplicity, we'll accept it as a parameter
    
    try:
        jws_data = request.get_json()
        
        # Decode protected to get account
        import base64
        protected_b64 = jws_data.get('protected', '')
        protected_json = base64.urlsafe_b64decode(protected_b64 + '==').decode()
        protected = json.loads(protected_json)
        
        kid = protected.get('kid', '')
        account_id = kid.split('/')[-1] if kid else None
        
        account = service.get_account_by_kid(account_id)
        if not account:
            return acme_error('accountDoesNotExist', 'Account not found', 404)
        
        # Find challenge by URL pattern
        # In real implementation, challenge_id would be extracted from URL
        challenge = AcmeChallenge.query.filter(
            AcmeChallenge.url.like(f'%{challenge_id}%')
        ).first()
        
        if not challenge:
            return acme_error('challengeDoesNotExist', 'Challenge not found', 404)
        
        # Trigger validation based on challenge type
        if challenge.type == "http-01":
            success = service.validate_http01_challenge(challenge, account)
        elif challenge.type == "dns-01":
            success = service.validate_dns01_challenge(challenge, account)
        else:
            return acme_error('unsupportedType', f'Challenge type {challenge.type} not supported')
        
        # Build response
        response_data = {
            "type": challenge.type,
            "status": challenge.status,
            "url": challenge.url,
            "token": challenge.token
        }
        
        if challenge.validated:
            response_data["validated"] = challenge.validated.isoformat() + 'Z'
        
        if challenge.error:
            response_data["error"] = json.loads(challenge.error)
        
        return acme_response(response_data)
        
    except Exception as e:
        return acme_error('serverInternal', f'Internal error: {str(e)}', 500)


# ==================== Health Check ====================

@acme_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint (not part of ACME spec)"""
    return jsonify({
        "status": "healthy",
        "service": "ACME Server",
        "version": "1.8.0-beta",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


# Export blueprint
__all__ = ['acme_bp']
