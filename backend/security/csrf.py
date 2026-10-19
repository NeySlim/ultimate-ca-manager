"""
CSRF Protection Module
Generates and validates CSRF tokens for state-changing requests.

Token flow:
1. On login/verify, server returns CSRF token in response
2. Client includes token in X-CSRF-Token header for POST/PUT/DELETE
3. Server validates token before processing request

Enforcement happens in one place: the ``before_request`` hook installed by
:func:`init_csrf_middleware`. A ``csrf_protect`` decorator used to sit beside
it with the same body minus the ``X-API-Key`` skip, so a route carrying it
would have answered 403 to an integration request the middleware lets through.
No route ever carried it. Anything that needs a narrower rule belongs in
``CSRF_EXEMPT_PATHS`` or in the middleware, where both doors see it.
"""

import os
import hmac
import hashlib
import secrets
import time
import logging
from typing import Optional, Tuple
from functools import wraps
from flask import request, g, session, current_app

from auth.unified import presented_api_key

logger = logging.getLogger(__name__)

# CSRF token validity (seconds)
CSRF_TOKEN_LIFETIME = 3600 * 24  # 24 hours

# Methods that require CSRF protection
CSRF_PROTECTED_METHODS = ['POST', 'PUT', 'DELETE', 'PATCH']

# Endpoints exempt from CSRF (public/external protocols)
CSRF_EXEMPT_PATHS = [
    '/api/v2/auth/login',       # Login (all methods: password, mtls, webauthn)
    '/api/v2/auth/forgot',      # Forgot password (no session yet)
    '/api/v2/auth/reset',       # Reset password (token-based)
    '/api/v2/auth/methods',     # Auth method detection (pre-login)
    # SSO flows triggered from outside the app (no session yet to mint a token)
    '/api/v2/sso/callback',     # OAuth2/SAML/OIDC callbacks
    '/api/v2/sso/login',        # SSO login redirects
    '/api/v2/sso/ldap/login',   # LDAP password login (pre-session)
    '/api/v2/sso/saml/metadata',  # SAML metadata exchange (public)
    '/api/v2/sso/available',    # Public auth method discovery
    # NOTE: /api/v2/mtls/enroll and /api/v2/mtls/enroll-import were listed here
    # as "bare-cert authentication (no prior session)", but both are
    # @require_auth() state-changing routes that bind a certificate to the
    # caller's account. Exempting them let a cross-site POST enrol an
    # attacker-supplied certificate onto the victim's account, giving the
    # attacker a credential for it. Session callers hold a CSRF token, and
    # X-API-Key requests are exempted by the middleware anyway, so neither
    # legitimate caller needs a blanket path exemption.
    '/api/health',              # Health checks
    '/api/v2/health',           # Health checks (v2)
]

# Protocol clients (ACME, SCEP, EST, OCSP, CRL, AIA, TSA, SSH setup, XCEP/WSTEP)
# hold no session and no token, so every path they reach is exempt. The list
# lives in utils.public_endpoints so the CSRF exemption, the http→https
# exemption, the safe-mode allowlist and the SPA catch-all cannot drift apart.
# is_exempt() matches by prefix, so the bare-path endpoints are appended with
# their trailing slash form covered by the prefixes.
from utils.public_endpoints import (  # noqa: E402
    ACME_PREFIXES,
    PROTOCOL_EXACT_PATHS,
    PROTOCOL_PREFIXES,
)

CSRF_EXEMPT_PROTOCOL_PATHS = tuple(PROTOCOL_PREFIXES) + tuple(ACME_PREFIXES)


class CSRFProtection:
    """
    CSRF token generation and validation.
    Uses HMAC-SHA256 with session-bound secrets.
    """
    
    _enabled = True
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if CSRF protection is enabled"""
        # CSRF_DISABLED only honored in development
        if os.getenv('CSRF_DISABLED', '').lower() == 'true':
            if os.getenv('FLASK_ENV') == 'development' or os.getenv('UCM_DEV_MODE') == 'true':
                return False
        return cls._enabled
    
    @classmethod
    def generate_token(cls, user_id: int) -> str:
        """
        Generate a CSRF token for the user.
        
        Token format: timestamp:nonce:signature
        """
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(16)
        
        # Create signature using SECRET_KEY + user_id
        secret = current_app.config.get('SECRET_KEY', '')
        message = f"{timestamp}:{nonce}:{user_id}"
        signature = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()  # Full 256-bit signature (no truncation)
        
        return f"{timestamp}:{nonce}:{signature}"
    
    @classmethod
    def validate_token(cls, token: str, user_id: int) -> Tuple[bool, str]:
        """
        Validate a CSRF token.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not token:
            return False, "Missing CSRF token"
        
        try:
            parts = token.split(':')
            if len(parts) != 3:
                return False, "Invalid token format"
            
            timestamp, nonce, provided_sig = parts
            
            # Check token age
            token_age = int(time.time()) - int(timestamp)
            if token_age > CSRF_TOKEN_LIFETIME:
                return False, "CSRF token expired"
            
            if token_age < 0:
                return False, "Invalid token timestamp"
            
            # Verify signature
            secret = current_app.config.get('SECRET_KEY', '')
            message = f"{timestamp}:{nonce}:{user_id}"
            expected_sig = hmac.new(
                secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(provided_sig, expected_sig):
                return False, "Invalid CSRF token"
            
            return True, ""
            
        except Exception as e:
            logger.warning(f"CSRF validation error: {e}")
            return False, "Token validation failed"
    
    @classmethod
    def is_exempt(cls, path: str) -> bool:
        """Check if path is exempt from CSRF protection"""
        if path in PROTOCOL_EXACT_PATHS:
            return True
        if path.startswith(CSRF_EXEMPT_PROTOCOL_PATHS):
            return True
        for exempt in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt):
                return True
        return False


def init_csrf_middleware(app):
    """
    Initialize CSRF middleware for the application.
    Adds CSRF validation to all state-changing requests.
    """
    
    @app.before_request
    def check_csrf():
        """Global CSRF check before each request"""
        if not CSRFProtection.is_enabled():
            return None
        
        # Only protect state-changing methods
        if request.method not in CSRF_PROTECTED_METHODS:
            return None
        
        # Check exempt paths
        if CSRFProtection.is_exempt(request.path):
            return None
        
        # Skip for API key auth (X-API-Key or Bearer): a browser never sends
        # either on its own, and a presented key never falls back to the session.
        if presented_api_key(request):
            return None
        
        # Get user_id from session or g (set by auth middleware)
        user_id = getattr(g, 'user_id', None) or session.get('user_id')
        if not user_id:
            # No user context, let auth middleware handle it
            return None
        
        # Get token from header
        token = request.headers.get('X-CSRF-Token')
        
        if not token:
            # Also check for token in JSON body (fallback for forms)
            try:
                if request.is_json and request.content_length and request.content_length > 0:
                    body = request.get_json(silent=True)
                    if body:
                        token = body.get('_csrf_token')
            except Exception as e:
                logger.warning(f"Failed to extract CSRF token from request body for {request.path}: {e}")
        
        is_valid, error = CSRFProtection.validate_token(token, user_id)
        
        if not is_valid:
            logger.warning(f"CSRF validation failed for {request.path}: {error}")
            from utils.response import error_response
            return error_response(f"CSRF validation failed: {error}", 403)
        
        return None
    
    logger.info("✅ CSRF protection middleware initialized")
