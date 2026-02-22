"""
mTLS Authentication Middleware
HYBRID: Supports both native Flask and reverse proxy certificate extraction
"""
from flask import request, session, g
from functools import wraps
from services.certificate_parser import CertificateParser
from services.mtls_auth_service import MTLSAuthService
import logging

logger = logging.getLogger(__name__)


def _extract_certificate():
    """Extract client certificate from any source (native TLS or reverse proxy headers)."""
    # Native Flask/Gunicorn (standalone mode)
    try:
        peercert = request.environ.get('peercert')
        if peercert:
            cert_info = CertificateParser.extract_from_flask_native(peercert)
            if cert_info:
                return cert_info
    except Exception as e:
        logger.debug(f"Native cert extraction failed: {e}")

    # Reverse proxy headers
    headers = dict(request.headers)
    if 'X-SSL-Client-Verify' in headers:
        cert_info = CertificateParser.extract_from_nginx_headers(headers)
        if cert_info:
            return cert_info
    if 'X-SSL-Client-S-DN' in headers:
        cert_info = CertificateParser.extract_from_apache_headers(headers)
        if cert_info:
            return cert_info

    return None


def process_client_certificate():
    """
    Process client certificate and auto-login if valid.
    Runs as before_request hook on every API call.
    
    Sources: native TLS peercert, Nginx headers, Apache headers.
    """
    # Already authenticated via certificate — skip
    if session.get('user_id') and session.get('auth_method') == 'certificate':
        return

    # Valid non-certificate session — respect it (don't overwrite password/LDAP/WebAuthn)
    if session.get('user_id'):
        from auth.unified import verify_request_auth
        if verify_request_auth():
            return
        # Stale session — clear and try mTLS
        logger.info("Stale session cleared, attempting mTLS re-auth")
        session.clear()

    if not MTLSAuthService.is_mtls_enabled():
        return

    cert_info = _extract_certificate()
    if not cert_info:
        return

    # Store cert_info in g for /auth/methods to use without re-parsing
    g.mtls_cert_info = cert_info

    user, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)

    if user:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session['auth_method'] = 'certificate'
        session['cert_id'] = auth_cert.id
        session['cert_serial'] = auth_cert.cert_serial
        session.permanent = True

        g.user = user
        g.auth_cert = auth_cert
        g.auth_method = 'certificate'

        logger.info(f"mTLS auto-login: user={user.username}")
    else:
        logger.debug(f"mTLS cert present but auth failed: {error}")
        g.cert_error = error


def require_client_certificate(f):
    """Decorator to require client certificate authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('auth_method') != 'certificate':
            return {
                'error': 'Client certificate required',
                'message': 'This endpoint requires authentication via client certificate'
            }, 403
        return f(*args, **kwargs)
    return decorated_function


def init_mtls_middleware(app):
    """Initialize mTLS before_request middleware."""
    @app.before_request
    def check_client_certificate():
        process_client_certificate()
