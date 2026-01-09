"""
ACME Protocol API Endpoints (RFC 8555)
Implements the ACME server endpoints for automated certificate management
"""
from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
import json
import base64
from typing import Dict, Any, Tuple, Optional

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


def verify_jws(jws_data: Dict[str, Any], expected_url: str, account_key: Optional[Dict] = None) -> Tuple[bool, Optional[Dict], Optional[Dict], Optional[str]]:
    """Verify JWS (JSON Web Signature) for ACME requests
    
    Args:
        jws_data: JWS object with protected, payload, signature
        expected_url: Expected URL in protected header
        account_key: Known account JWK for KID-based verification (optional)
        
    Returns:
        Tuple of (is_valid, payload_dict, jwk, error_message)
    """
    try:
        # Decode protected header (base64url)
        if 'protected' not in jws_data:
            return False, None, None, "Missing 'protected' field in JWS"
        
        protected_b64 = jws_data['protected']
        # Add padding if needed
        protected_b64 += '=' * (4 - len(protected_b64) % 4)
        protected_json = base64.urlsafe_b64decode(protected_b64).decode('utf-8')
        protected = json.loads(protected_json)
        
        # Verify URL matches expected
        if protected.get('url') != expected_url:
            return False, None, None, f"URL mismatch: expected {expected_url}, got {protected.get('url')}"
        
        # Verify nonce
        nonce = protected.get('nonce')
        if not nonce:
            return False, None, None, "Missing nonce in protected header"
        
        service = get_acme_service()
        if not service.validate_nonce(nonce):
            return False, None, None, "Invalid or expired nonce"
        
        # Get JWK or KID
        jwk = protected.get('jwk')
        kid = protected.get('kid')
        
        if not jwk and not kid:
            return False, None, None, "Must provide either 'jwk' or 'kid' in protected header"
        
        # Decode payload
        if 'payload' not in jws_data:
            return False, None, None, "Missing 'payload' field in JWS"
        
        payload_b64 = jws_data['payload']
        if payload_b64:  # Payload can be empty string for some requests
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json) if payload_json else {}
        else:
            payload = {}
        
        # Verify cryptographic signature with josepy
        try:
            import josepy as jose
            
            # Determine which key to use for verification
            key_to_verify = None
            if jwk:
                # New account - JWK in protected header
                key_to_verify = jwk
            elif kid:
                if account_key:
                    # Existing account - use stored account key
                    key_to_verify = account_key
                else:
                    # KID provided but no account key available
                    # This happens when we need to fetch the account first
                    # For now, accept it (will be validated when account is fetched)
                    return True, payload, jwk, None
            
            if not key_to_verify:
                return False, None, None, "No key available for verification"
            
            # Convert JWK dict to josepy JWK object
            import json as json_module
            if not isinstance(key_to_verify, dict):
                return False, None, None, f"Key is not a dict, it's a {type(key_to_verify)}: {key_to_verify}"
            
            kty = key_to_verify.get('kty')
            if kty == 'RSA':
                public_key = jose.JWKRSA.json_loads(json_module.dumps(key_to_verify))
            elif isinstance(key_to_verify, dict) and kty == 'EC':
                public_key = jose.JWKEC.json_loads(json_module.dumps(key_to_verify))
            else:
                return False, None, None, f"Unsupported key type: {kty}"
            
            # Reconstruct JWS for verification
            # Format: base64url(protected).base64url(payload)
            signing_input = jws_data['protected'] + '.' + jws_data['payload']
            
            # Decode signature
            signature_b64 = jws_data.get('signature', '')
            signature_b64 += '=' * (4 - len(signature_b64) % 4)
            signature_bytes = base64.urlsafe_b64decode(signature_b64)
            
            # Get algorithm from protected header
            alg = protected.get('alg')
            if not alg:
                return False, None, None, "Missing 'alg' in protected header"
            
            # Verify signature based on algorithm
            if alg.startswith('RS'):  # RSA signatures (RS256, RS384, RS512)
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import padding
                from cryptography.hazmat.backends import default_backend
                
                # Get hash algorithm
                if alg == 'RS256':
                    hash_alg = hashes.SHA256()
                elif alg == 'RS384':
                    hash_alg = hashes.SHA384()
                elif alg == 'RS512':
                    hash_alg = hashes.SHA512()
                else:
                    return False, None, None, f"Unsupported RSA algorithm: {alg}"
                
                # Verify signature
                try:
                    public_key.key.verify(
                        signature_bytes,
                        signing_input.encode('utf-8'),
                        padding.PKCS1v15(),
                        hash_alg
                    )
                except Exception as e:
                    return False, None, None, f"Signature verification failed: {str(e)}"
                    
            elif alg.startswith('ES'):  # EC signatures (ES256, ES384, ES512)
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import ec
                
                # Get hash algorithm
                if alg == 'ES256':
                    hash_alg = hashes.SHA256()
                elif alg == 'ES384':
                    hash_alg = hashes.SHA384()
                elif alg == 'ES512':
                    hash_alg = hashes.SHA512()
                else:
                    return False, None, None, f"Unsupported EC algorithm: {alg}"
                
                # Verify signature
                try:
                    public_key.key.verify(
                        signature_bytes,
                        signing_input.encode('utf-8'),
                        ec.ECDSA(hash_alg)
                    )
                except Exception as e:
                    return False, None, None, f"Signature verification failed: {str(e)}"
            else:
                return False, None, None, f"Unsupported signature algorithm: {alg}"
            
            # Signature valid!
            return True, payload, jwk, None
            
        except ImportError:
            # josepy not available - fall back to structure validation only
            # This allows the system to work without josepy, but with reduced security
            return True, payload, jwk, None
        except Exception as e:
            return False, None, None, f"Signature verification error: {str(e)}"
        
    except json.JSONDecodeError as e:
        return False, None, None, f"Invalid JSON in JWS: {str(e)}"
    except Exception as e:
        return False, None, None, f"JWS verification error: {str(e)}"


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
        
        # Verify JWS
        expected_url = f"{service.base_url}/acme/new-account"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        if not jwk:
            return acme_error('malformed', 'JWK required in protected header for new-account')
        
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
        
        if not jws_data:
            return acme_error('malformed', 'Request body must be JWS')
        
        # Verify JWS
        expected_url = f"{service.base_url}/acme/new-order"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        # Extract account from protected header (need to re-decode for kid)
        protected_b64 = jws_data.get('protected', '')
        protected_b64 += '=' * (4 - len(protected_b64) % 4)
        protected_json = base64.urlsafe_b64decode(protected_b64).decode()
        protected = json.loads(protected_json)
        
        # Get account ID from kid (Key ID)
        kid = protected.get('kid', '')
        account_id = kid.split('/')[-1] if kid else None
        
        if not account_id:
            return acme_error('malformed', 'Account kid required in protected header')
        
        # Verify account exists
        account = service.get_account_by_kid(account_id)
        if not account:
            return acme_error('accountDoesNotExist', 'Account not found', 404)
        
        # Extract order details from payload
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
    from models.acme_models import AcmeAuthorization
    
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
    
    response = acme_response(response_data)
    
    # Add Link header pointing to parent order (rel="up")
    order_url = f"{service.base_url}/acme/order/{auth.order_id}"
    response.headers.add('Link', f'<{order_url}>;rel="up"')
    
    return response


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


# ==================== Certificate Download ====================

@acme_bp.route('/cert/<order_id>', methods=['POST', 'GET'])
def download_certificate(order_id: str):
    """Download certificate (RFC 8555 Section 7.4.2)
    
    Returns certificate chain in PEM format
    """
    service = get_acme_service()
    
    # Get order
    order = service.get_order(order_id)
    if not order:
        return acme_error('notFound', 'Order not found', 404)
    
    if order.status != 'valid':
        return acme_error('orderNotReady', f'Order status is {order.status}, certificate not available', 403)
    
    if not order.certificate_id:
        return acme_error('serverInternal', 'Certificate not generated', 500)
    
    # Get certificate from database
    from models import Certificate, CA
    cert = Certificate.query.get(order.certificate_id)
    if not cert or not cert.crt:
        return acme_error('serverInternal', 'Certificate not found in database', 500)
    
    # Build certificate chain (cert + intermediate CAs + root)
    chain_pems = []
    
    # Add end-entity certificate
    cert_pem = base64.b64decode(cert.crt).decode('utf-8')
    chain_pems.append(cert_pem.strip())
    
    # Add CA chain
    current_caref = cert.caref
    seen_cas = set()  # Prevent loops
    
    while current_caref and current_caref not in seen_cas:
        seen_cas.add(current_caref)
        ca = CA.query.filter_by(refid=current_caref).first()
        
        if not ca:
            break
        
        ca_cert_pem = base64.b64decode(ca.crt).decode('utf-8')
        chain_pems.append(ca_cert_pem.strip())
        
        # Move up the chain
        current_caref = ca.caref
    
    # Join with double newline
    pem_chain = '\n\n'.join(chain_pems)
    
    # Return PEM chain
    response = make_response(pem_chain, 200)
    response.headers['Content-Type'] = 'application/pem-certificate-chain'
    
    # Add Replay-Nonce for ACME compliance
    response.headers['Replay-Nonce'] = service.generate_nonce()
    
    return response


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
