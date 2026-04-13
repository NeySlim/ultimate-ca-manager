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
from config.settings import Config
import logging
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

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
    
    # RFC 8555 §8: prevent caching of ACME responses
    response.headers['Cache-Control'] = 'no-store'
    
    return response


def acme_error(error_type: str, detail: str, status_code: int = 400) -> Any:
    """Create ACME error response per RFC 7807 (Problem Details)
    
    Args:
        error_type: ACME error type (e.g., 'malformed', 'unauthorized')
        detail: Human-readable error description
        status_code: HTTP status code
        
    Returns:
        Flask Response object with application/problem+json
    """
    service = get_acme_service()
    
    error_data = {
        "type": f"urn:ietf:params:acme:error:{error_type}",
        "detail": detail,
        "status": status_code
    }
    
    response = make_response(jsonify(error_data), status_code)
    response.headers['Content-Type'] = 'application/problem+json'
    response.headers['Replay-Nonce'] = service.generate_nonce()
    response.headers['Link'] = f'<{service.base_url}/acme/directory>;rel="index"'
    
    return response


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
                    # KID provided — look up account to get key
                    try:
                        # Extract account ID from KID URL (account_id is a string token, not numeric)
                        acct_id = kid.rstrip('/').split('/')[-1]
                        account = AcmeAccount.query.filter_by(account_id=acct_id).first()
                        if account and account.status == 'valid':
                            key_to_verify = json.loads(account.jwk) if isinstance(account.jwk, str) else account.jwk
                        else:
                            return False, None, None, "Account not found or deactivated"
                    except (ValueError, TypeError):
                        return False, None, None, "Invalid KID format"
            
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
                    logger.error(f"RSA signature verification failed: {e}")
                    return False, None, None, "Signature verification failed"
                    
            elif alg.startswith('ES'):  # EC signatures (ES256, ES384, ES512)
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import ec, utils
                
                # Get hash algorithm and key size
                if alg == 'ES256':
                    hash_alg = hashes.SHA256()
                    key_size = 32
                elif alg == 'ES384':
                    hash_alg = hashes.SHA384()
                    key_size = 48
                elif alg == 'ES512':
                    hash_alg = hashes.SHA512()
                    key_size = 66
                else:
                    return False, None, None, f"Unsupported EC algorithm: {alg}"
                
                # JWS EC signatures use raw R||S format (RFC 7518 Section 3.4)
                # cryptography library expects DER-encoded signature
                try:
                    if len(signature_bytes) == 2 * key_size:
                        r = int.from_bytes(signature_bytes[:key_size], 'big')
                        s = int.from_bytes(signature_bytes[key_size:], 'big')
                        der_signature = utils.encode_dss_signature(r, s)
                    else:
                        der_signature = signature_bytes
                    
                    public_key.key.verify(
                        der_signature,
                        signing_input.encode('utf-8'),
                        ec.ECDSA(hash_alg)
                    )
                except Exception as e:
                    logger.error(f"EC signature verification failed: {e}")
                    return False, None, None, "Signature verification failed"
            else:
                return False, None, None, f"Unsupported signature algorithm: {alg}"
            
            # Signature valid!
            return True, payload, jwk, None
            
        except ImportError:
            logger.error("josepy library not installed — ACME JWS verification unavailable")
            return False, None, None, "JWS verification unavailable: josepy not installed"
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False, None, None, "Signature verification error"
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in JWS: {e}")
        return False, None, None, "Invalid JSON in JWS"
    except Exception as e:
        logger.error(f"JWS verification error: {e}")
        return False, None, None, "JWS verification error"


# ==================== ACME Directory ====================

@acme_bp.route('/directory', methods=['GET'])
def directory():
    """ACME directory endpoint (RFC 8555 Section 7.1.1)
    
    Returns available ACME endpoints and metadata
    """
    service = get_acme_service()
    
    directory_data = service.get_directory()
    
    # Check if EAB is required
    from models import SystemConfig
    eab_config = SystemConfig.query.filter_by(key='acme_eab_required').first()
    eab_required = (eab_config.value if eab_config else 'false').lower() == 'true'
    
    # Add metadata
    directory_data['meta'] = {
        'termsOfService': f'{service.base_url}/acme/terms',
        'website': 'https://github.com/fabriziosalmi/ultimate-ca-manager',
        'caaIdentities': [request.host],
        'externalAccountRequired': eab_required
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
        only_return_existing = payload.get('onlyReturnExisting', False)
        
        # Handle onlyReturnExisting (RFC 8555 Section 7.3.1)
        if only_return_existing:
            thumbprint = service._compute_jwk_thumbprint(jwk)
            existing = AcmeAccount.query.filter_by(jwk_thumbprint=thumbprint).first()
            if not existing:
                return acme_error('accountDoesNotExist', 'Account does not exist', 400)
            account_url = f"{service.base_url}/acme/acct/{existing.account_id}"
            response_data = {
                "status": existing.status,
                "contact": json.loads(existing.contact) if existing.contact else [],
                "termsOfServiceAgreed": existing.terms_of_service_agreed,
                "orders": f"{account_url}/orders"
            }
            response = acme_response(response_data, 200)
            response.headers['Location'] = account_url
            return response
        
        # Validate EAB if required (RFC 8555 §7.3.4)
        eab_data = payload.get('externalAccountBinding')
        from models import SystemConfig
        eab_config = SystemConfig.query.filter_by(key='acme_eab_required').first()
        eab_required = (eab_config.value if eab_config else 'false').lower() == 'true'
        
        if eab_required and not eab_data:
            return acme_error('externalAccountRequired', 'External account binding required')
        
        if eab_data:
            eab_valid, eab_error = service.validate_eab(eab_data, jwk)
            if not eab_valid:
                return acme_error('malformed', f'Invalid external account binding: {eab_error}')
        
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
        logger.error(f"ACME new-account error: {e}")
        return acme_error('serverInternal', 'Internal server error', 500)


@acme_bp.route('/acct/<account_id>', methods=['POST'])
def account_info(account_id: str):
    """Get/update account information (RFC 8555 Section 7.3.1-7.3.2)"""
    service = get_acme_service()
    
    account = service.get_account_by_kid(account_id)
    
    if not account:
        return acme_error('accountDoesNotExist', 'Account not found', 404)
    
    # Verify JWS
    jws_data = request.get_json()
    if jws_data:
        expected_url = f"{service.base_url}/acme/acct/{account_id}"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        # Handle account deactivation (RFC 8555 Section 7.3.6)
        if payload and payload.get('status') == 'deactivated':
            account.status = 'deactivated'
            db.session.commit()
        
        # Handle contact update (RFC 8555 Section 7.3.2)
        if payload and 'contact' in payload:
            account.contact = json.dumps(payload['contact'])
            db.session.commit()
    
    account_url = f"{service.base_url}/acme/acct/{account.account_id}"
    
    response_data = {
        "status": account.status,
        "contact": json.loads(account.contact) if account.contact else [],
        "orders": f"{account_url}/orders"
    }
    
    response = acme_response(response_data)
    response.headers['Location'] = account_url
    
    return response


@acme_bp.route('/acct/<account_id>/orders', methods=['POST'])
def account_orders(account_id: str):
    """List account orders (RFC 8555 §7.1.2.1)"""
    service = get_acme_service()
    
    account = service.get_account_by_kid(account_id)
    if not account:
        return acme_error('accountDoesNotExist', 'Account not found', 404)
    
    if account.status == 'deactivated':
        return acme_error('unauthorized', 'Account is deactivated', 401)
    
    # Verify JWS (POST-as-GET)
    jws_data = request.get_json()
    if jws_data:
        expected_url = f"{service.base_url}/acme/acct/{account_id}/orders"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
    
    # Get orders for this account
    orders = AcmeOrder.query.filter_by(account_id=account_id).order_by(
        AcmeOrder.created_at.desc()
    ).all()
    
    order_urls = [
        f"{service.base_url}/acme/order/{order.order_id}"
        for order in orders
    ]
    
    response_data = {
        "orders": order_urls
    }
    
    return acme_response(response_data)


# ==================== Order Management ====================

@acme_bp.route('/new-authz', methods=['POST'])
def new_authz():
    """Pre-authorization for identifiers (RFC 8555 §7.4.1)
    
    Allows clients to pre-authorize identifiers before placing an order.
    """
    service = get_acme_service()
    
    try:
        jws_data = request.get_json()
        if not jws_data:
            return acme_error('malformed', 'Request body required')
        
        expected_url = f"{service.base_url}/acme/new-authz"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        # Must use kid (account required)
        protected = json.loads(base64.urlsafe_b64decode(jws_data['protected'] + '=='))
        kid = protected.get('kid', '')
        account_id = kid.split('/')[-1] if kid else None
        
        if not account_id:
            return acme_error('malformed', 'Account kid required')
        
        account = service.get_account_by_kid(account_id)
        if not account:
            return acme_error('accountDoesNotExist', 'Account not found', 404)
        
        if account.status == 'deactivated':
            return acme_error('unauthorized', 'Account is deactivated', 401)
        
        # Validate identifier
        identifier = payload.get('identifier')
        if not identifier or 'type' not in identifier or 'value' not in identifier:
            return acme_error('malformed', 'Valid identifier required')
        
        if identifier['type'] != 'dns':
            return acme_error('unsupportedIdentifier', f'Identifier type {identifier["type"]} not supported')
        
        auth = service.create_pre_authorization(account_id, identifier)
        
        authz_url = f"{service.base_url}/acme/authz/{auth.authorization_id}"
        
        # Build challenges
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
            challenges.append(challenge_data)
        
        response_data = {
            "status": auth.status,
            "identifier": json.loads(auth.identifier),
            "challenges": challenges,
            "expires": auth.expires.isoformat() + 'Z'
        }
        
        if auth.wildcard:
            response_data["wildcard"] = True
        
        response = acme_response(response_data, status_code=201)
        response.headers['Location'] = authz_url
        
        return response
        
    except Exception as e:
        logger.error(f"newAuthz error: {e}", exc_info=True)
        return acme_error('serverInternal', 'Internal server error', 500)


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
        
        # Reject deactivated accounts (RFC 8555 §7.3.6)
        if account.status == 'deactivated':
            return acme_error('unauthorized', 'Account is deactivated', 401)
        
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
        logger.error(f"ACME new-order error: {e}")
        return acme_error('serverInternal', 'Internal server error', 500)


@acme_bp.route('/order/<order_id>', methods=['POST'])
def order_info(order_id: str):
    """Get order status (RFC 8555 Section 7.4) — POST-as-GET"""
    service = get_acme_service()
    
    # Verify JWS (POST-as-GET: empty payload)
    jws_data = request.get_json()
    if jws_data:
        expected_url = f"{service.base_url}/acme/order/{order_id}"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        # RFC 8555 §6.3: POST-as-GET payload must be empty
        if payload:
            return acme_error('malformed', 'POST-as-GET must have empty payload')
    
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
    
    # Add Retry-After for pending/processing orders (RFC 8555 Section 7.4)
    if order.status in ('pending', 'processing'):
        response.headers['Retry-After'] = '3'
    
    return response


@acme_bp.route('/order/<order_id>/finalize', methods=['POST'])
def finalize_order(order_id: str):
    """Finalize order with CSR (RFC 8555 Section 7.4)"""
    service = get_acme_service()
    
    try:
        jws_data = request.get_json()
        
        if not jws_data:
            return acme_error('malformed', 'Request body must be JWS')
        
        # Verify JWS
        expected_url = f"{service.base_url}/acme/order/{order_id}/finalize"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        if not payload:
            return acme_error('malformed', 'Payload required for finalize')
        
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
        
        if order.certificate_url:
            response_data["certificate"] = order.certificate_url
        
        response = acme_response(response_data)
        response.headers['Location'] = order_url
        
        return response
        
    except Exception as e:
        logger.error(f"ACME get-order error: {e}")
        return acme_error('serverInternal', 'Internal server error', 500)


# ==================== Authorization & Challenge ====================

@acme_bp.route('/authz/<authorization_id>', methods=['POST'])
def authorization_info(authorization_id: str):
    """Get authorization status (RFC 8555 Section 7.5) — POST-as-GET"""
    from models.acme_models import AcmeAuthorization
    
    service = get_acme_service()
    
    # Verify JWS (POST-as-GET: empty payload)
    jws_data = request.get_json()
    if jws_data:
        expected_url = f"{service.base_url}/acme/authz/{authorization_id}"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        # RFC 8555 §6.3: POST-as-GET payload must be empty
        if payload:
            return acme_error('malformed', 'POST-as-GET must have empty payload')
    
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
    
    try:
        jws_data = request.get_json()
        
        if not jws_data:
            return acme_error('malformed', 'Request body must be JWS')
        
        # Verify JWS
        # Challenge URLs use the challenge-specific URL, not a fixed pattern
        # Try to find the challenge first to get its URL for verification
        challenge = AcmeChallenge.query.filter(
            AcmeChallenge.url.endswith(f'/{challenge_id}')
        ).first()
        if not challenge:
            challenge = AcmeChallenge.query.filter_by(challenge_id=challenge_id).first()
        
        if not challenge:
            return acme_error('challengeDoesNotExist', 'Challenge not found', 404)
        
        expected_url = challenge.url or f"{service.base_url}/acme/challenge/{challenge_id}"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        # Get account from KID
        protected_b64 = jws_data.get('protected', '')
        protected_b64 += '=' * (4 - len(protected_b64) % 4)
        protected_json = base64.urlsafe_b64decode(protected_b64).decode()
        protected = json.loads(protected_json)
        
        kid = protected.get('kid', '')
        account_id = kid.split('/')[-1] if kid else None
        
        account = service.get_account_by_kid(account_id)
        if not account:
            return acme_error('accountDoesNotExist', 'Account not found', 404)
        
        # Reject deactivated accounts (RFC 8555 §7.3.6)
        if account.status == 'deactivated':
            return acme_error('unauthorized', 'Account is deactivated', 401)
        
        # Trigger validation based on challenge type
        if challenge.type == "http-01":
            success = service.validate_http01_challenge(challenge, account)
        elif challenge.type == "dns-01":
            success = service.validate_dns01_challenge(challenge, account)
        elif challenge.type == "tls-alpn-01":
            success = service.validate_tls_alpn01_challenge(challenge, account)
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
        
        response = acme_response(response_data)
        
        # Add Link header pointing to parent authorization (rel="up")
        authz_url = f"{service.base_url}/acme/authz/{challenge.authorization.authorization_id}"
        response.headers.add('Link', f'<{authz_url}>;rel="up"')
        
        return response
        
    except Exception as e:
        logger.error(f"ACME challenge error: {e}")
        return acme_error('serverInternal', 'Internal server error', 500)


# ==================== Certificate Download ====================

@acme_bp.route('/cert/<order_id>', methods=['POST', 'GET'])
def download_certificate(order_id: str):
    """Download certificate (RFC 8555 Section 7.4.2)
    
    Returns certificate chain in PEM format.
    Accepts POST (POST-as-GET with JWS) and GET for compatibility.
    """
    service = get_acme_service()
    
    # Verify JWS for POST requests (POST-as-GET)
    if request.method == 'POST':
        jws_data = request.get_json()
        if jws_data:
            expected_url = f"{service.base_url}/acme/cert/{order_id}"
            is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
            if not is_valid:
                return acme_error('malformed', f'Invalid JWS: {error}')
            # RFC 8555 §6.3: POST-as-GET payload must be empty
            if payload:
                return acme_error('malformed', 'POST-as-GET must have empty payload')
    
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
    if not cert_pem.strip().startswith('-----BEGIN CERTIFICATE-----'):
        # Certificate might be raw DER, wrap it
        cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_pem}\n-----END CERTIFICATE-----"
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
        if not ca_cert_pem.strip().startswith('-----BEGIN CERTIFICATE-----'):
            # CA cert might be raw DER, wrap it
            ca_cert_pem = f"-----BEGIN CERTIFICATE-----\n{ca_cert_pem}\n-----END CERTIFICATE-----"
        chain_pems.append(ca_cert_pem.strip())
        
        # Move up the chain
        current_caref = ca.caref
    
    # Join with single newline (standard PEM chain format)
    pem_chain = '\n'.join(chain_pems) + '\n'
    
    # Return PEM chain
    response = make_response(pem_chain, 200)
    response.headers['Content-Type'] = 'application/pem-certificate-chain'
    response.headers['Replay-Nonce'] = service.generate_nonce()
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Link'] = f'<{service.base_url}/acme/directory>;rel="index"'
    
    return response


# ==================== Certificate Revocation ====================

@acme_bp.route('/revoke-cert', methods=['POST'])
def revoke_cert():
    """Revoke certificate (RFC 8555 Section 7.6)"""
    service = get_acme_service()
    
    try:
        jws_data = request.get_json()
        
        if not jws_data:
            return acme_error('malformed', 'Request body must be JWS')
        
        expected_url = f"{service.base_url}/acme/revoke-cert"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        if not payload:
            return acme_error('malformed', 'Payload required')
        
        # Extract certificate DER
        cert_b64 = payload.get('certificate', '')
        if not cert_b64:
            return acme_error('malformed', 'Certificate required in payload')
        
        reason = payload.get('reason', 0)  # RFC 5280 CRLReason
        
        # Decode certificate
        cert_der = base64.urlsafe_b64decode(cert_b64 + '==')
        
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        cert_obj = x509.load_der_x509_certificate(cert_der, default_backend())
        
        # Find certificate in database by serial number
        from models import Certificate
        serial_hex = format(cert_obj.serial_number, 'x').upper()
        
        cert = Certificate.query.filter(
            Certificate.serial.ilike(f'%{serial_hex}%')
        ).first()
        
        if not cert:
            return acme_error('serverInternal', 'Certificate not found', 404)
        
        # Revoke certificate
        try:
            from services.cert_service import CertificateService
            CertificateService.revoke_certificate(
                cert_id=cert.id,
                reason='keyCompromise' if reason == 1 else 'unspecified',
                username='acme'
            )
        except Exception as e:
            logger.error(f"ACME revocation failed: {e}")
            return acme_error('serverInternal', 'Revocation failed', 500)
        
        # RFC 8555 §7.6: successful revocation returns 200 with proper headers
        response = make_response('', 200)
        response.headers['Replay-Nonce'] = service.generate_nonce()
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Link'] = f'<{service.base_url}/acme/directory>;rel="index"'
        return response
        
    except Exception as e:
        logger.error(f"ACME revoke-cert error: {e}")
        return acme_error('serverInternal', 'Internal server error', 500)


# ==================== Key Change ====================

@acme_bp.route('/key-change', methods=['POST'])
def key_change():
    """Key change (RFC 8555 Section 7.3.5)"""
    service = get_acme_service()
    
    try:
        jws_data = request.get_json()
        
        if not jws_data:
            return acme_error('malformed', 'Request body must be JWS')
        
        expected_url = f"{service.base_url}/acme/key-change"
        is_valid, payload, jwk, error = verify_jws(jws_data, expected_url)
        
        if not is_valid:
            return acme_error('malformed', f'Invalid JWS: {error}')
        
        if not payload:
            return acme_error('malformed', 'Payload required')
        
        # Extract inner JWS (key change is double-wrapped)
        # The outer JWS is signed with the old key, inner with the new key
        # For now, extract account and new key from payload
        account_url = payload.get('account', '')
        old_key = payload.get('oldKey', {})
        
        account_id = account_url.split('/')[-1] if account_url else None
        if not account_id:
            return acme_error('malformed', 'Account URL required')
        
        account = service.get_account_by_kid(account_id)
        if not account:
            return acme_error('accountDoesNotExist', 'Account not found', 404)
        
        # Verify oldKey matches account's current JWK
        current_jwk = json.loads(account.jwk) if isinstance(account.jwk, str) else account.jwk
        if not old_key or old_key != current_jwk:
            return acme_error('malformed', 'Old key does not match account key')
        
        # Verify new key differs from old key
        if jwk == current_jwk:
            return acme_error('malformed', 'New key must differ from old key')
        
        # Update account JWK
        if jwk:
            try:
                account.jwk = json.dumps(jwk)
                account.jwk_thumbprint = service._compute_jwk_thumbprint(jwk)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to update account key: {e}")
                return acme_error('serverInternal', 'Failed to update account key', 500)
        
        account_url_full = f"{service.base_url}/acme/acct/{account.account_id}"
        response_data = {
            "status": account.status,
            "contact": json.loads(account.contact) if account.contact else [],
            "orders": f"{account_url_full}/orders"
        }
        
        response = acme_response(response_data)
        response.headers['Location'] = account_url_full
        return response
        
    except Exception as e:
        logger.error(f"ACME key-change error: {e}")
        return acme_error('serverInternal', 'Internal server error', 500)


# ==================== Health Check ====================

@acme_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint (not part of ACME spec)"""
    return jsonify({
        "status": "healthy",
        "service": "ACME Server",
        "version": Config.APP_VERSION,
        "timestamp": utc_now().isoformat() + 'Z'
    })


# Export blueprint
__all__ = ['acme_bp']
