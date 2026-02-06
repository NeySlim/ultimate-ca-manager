"""
CSRF Protection Module
Generates and validates CSRF tokens for state-changing requests.

Token flow:
1. On login/verify, server returns CSRF token in response
2. Client includes token in X-CSRF-Token header for POST/PUT/DELETE
3. Server validates token before processing request
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

logger = logging.getLogger(__name__)

# CSRF token validity (seconds)
CSRF_TOKEN_LIFETIME = 3600 * 24  # 24 hours

# Methods that require CSRF protection
CSRF_PROTECTED_METHODS = ['POST', 'PUT', 'DELETE', 'PATCH']

# Endpoints exempt from CSRF (public/external protocols)
CSRF_EXEMPT_PATHS = [
    '/api/v2/auth/login',  # Login needs to work without token
    '/acme/',              # ACME protocol
    '/scep/',              # SCEP protocol  
    '/.well-known/acme',   # ACME challenge
    '/ocsp',               # OCSP protocol
    '/cdp/',               # CRL distribution
    '/api/health',         # Health checks
]


class CSRFProtection:
    """
    CSRF token generation and validation.
    Uses HMAC-SHA256 with session-bound secrets.
    """
    
    _enabled = True
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if CSRF protection is enabled"""
        # Can be disabled via env for testing
        return cls._enabled and os.getenv('CSRF_DISABLED', '').lower() != 'true'
    
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
        ).hexdigest()[:32]  # Truncate for shorter token
        
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
            ).hexdigest()[:32]
            
            if not hmac.compare_digest(provided_sig, expected_sig):
                return False, "Invalid CSRF token"
            
            return True, ""
            
        except Exception as e:
            logger.warning(f"CSRF validation error: {e}")
            return False, "Token validation failed"
    
    @classmethod
    def is_exempt(cls, path: str) -> bool:
        """Check if path is exempt from CSRF protection"""
        for exempt in CSRF_EXEMPT_PATHS:
            if path.startswith(exempt):
                return True
        return False


def csrf_protect(f):
    """
    Decorator to enforce CSRF protection on a route.
    
    Usage:
        @bp.route('/api/v2/users', methods=['POST'])
        @csrf_protect
        def create_user():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not CSRFProtection.is_enabled():
            return f(*args, **kwargs)
        
        # Only protect state-changing methods
        if request.method not in CSRF_PROTECTED_METHODS:
            return f(*args, **kwargs)
        
        # Check exempt paths
        if CSRFProtection.is_exempt(request.path):
            return f(*args, **kwargs)
        
        # Get user_id from session or JWT
        user_id = getattr(g, 'user_id', None) or session.get('user_id')
        if not user_id:
            # No user context, skip CSRF (auth will fail anyway)
            return f(*args, **kwargs)
        
        # Get token from header
        token = request.headers.get('X-CSRF-Token')
        
        if not token:
            # Also check for token in JSON body (fallback)
            if request.is_json:
                token = request.json.get('_csrf_token')
        
        is_valid, error = CSRFProtection.validate_token(token, user_id)
        
        if not is_valid:
            logger.warning(f"CSRF validation failed for {request.path}: {error}")
            from utils.response import error_response
            return error_response(f"CSRF validation failed: {error}", 403)
        
        return f(*args, **kwargs)
    
    return decorated_function


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
        
        # Skip for API key auth (external integrations)
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('ApiKey '):
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
            if request.is_json and request.json:
                token = request.json.get('_csrf_token')
        
        is_valid, error = CSRFProtection.validate_token(token, user_id)
        
        if not is_valid:
            logger.warning(f"CSRF validation failed for {request.path}: {error}")
            from utils.response import error_response
            return error_response(f"CSRF validation failed: {error}", 403)
        
        return None
    
    logger.info("✅ CSRF protection middleware initialized")
