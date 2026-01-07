"""
mTLS Authentication Middleware
Intercept and process client certificates from reverse proxy headers
"""
from flask import request, session, g
from functools import wraps
from services.certificate_parser import CertificateParser
from services.mtls_auth_service import MTLSAuthService
import logging

logger = logging.getLogger(__name__)


def process_client_certificate():
    """
    Process client certificate from reverse proxy headers
    This should be called before each request to check for client cert
    """
    # Skip if user already authenticated via session
    if session.get('user_id'):
        return
    
    # Skip if mTLS not enabled
    if not MTLSAuthService.is_mtls_enabled():
        return
    
    # Get request headers
    headers = dict(request.headers)
    
    # Try to extract certificate info from headers
    cert_info = None
    
    # Try Nginx headers first
    if 'X-SSL-Client-Verify' in headers:
        cert_info = CertificateParser.extract_from_nginx_headers(headers)
    
    # Try Apache headers if Nginx failed
    if not cert_info and 'X-SSL-Client-S-DN' in headers:
        cert_info = CertificateParser.extract_from_apache_headers(headers)
    
    if not cert_info:
        # No client certificate present
        return
    
    # Authenticate via certificate
    user, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)
    
    if user:
        # Auto-login user
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session['auth_method'] = 'certificate'
        session['cert_id'] = auth_cert.id
        session['cert_serial'] = auth_cert.cert_serial
        
        # Store in request context
        g.user = user
        g.auth_cert = auth_cert
        g.auth_method = 'certificate'
        
        logger.info(f"Auto-login via certificate: user={user.username}, serial={auth_cert.cert_serial}")
    else:
        # Certificate present but authentication failed
        logger.warning(f"Certificate authentication failed: {error}")
        g.cert_error = error


def require_client_certificate(f):
    """
    Decorator to require client certificate authentication
    
    Usage:
        @app.route('/secure')
        @require_client_certificate
        def secure_endpoint():
            return "Authenticated via certificate"
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if authenticated via certificate
        if session.get('auth_method') != 'certificate':
            return {
                'error': 'Client certificate required',
                'message': 'This endpoint requires authentication via client certificate'
            }, 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def init_mtls_middleware(app):
    """
    Initialize mTLS middleware for Flask app
    
    Args:
        app: Flask application instance
    """
    @app.before_request
    def check_client_certificate():
        """Check for client certificate before each request"""
        process_client_certificate()
