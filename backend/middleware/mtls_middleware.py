"""
mTLS Authentication Middleware
HYBRID: Supports both native Flask and reverse proxy certificate extraction
"""
from flask import current_app, request, session, g
from datetime import datetime
from functools import wraps
import threading
import time
from services.certificate_parser import CertificateParser
from services.mtls_auth_service import MTLSAuthService
import logging
from utils.datetime_utils import utc_now
from utils.admin_allowlist import is_exempt_path
from auth.session_start import begin_session

logger = logging.getLogger(__name__)

# An expired cookie replaced by a certificate login, kept a short while: the parallel
# calls still carrying it join that session instead of each opening its own.
SUCCESSOR_TTL = 60
_successors = {}  # expired cookie -> (new session id, deadline)
_SUCCESSOR_LOCKS = tuple(threading.Lock() for _ in range(64))


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

    # Reverse proxy headers — only trust from known proxy IPs. Must use the
    # real TCP peer (not request.remote_addr, which ProxyFix may have
    # rewritten from client-controlled X-Forwarded-For).
    from utils.trusted_proxy import immediate_peer_addr, is_request_from_trusted_proxy
    if not is_request_from_trusted_proxy():
        logger.debug(f"mTLS proxy headers ignored: {immediate_peer_addr()} not in trusted proxies")
        return None

    # request.headers is already a case-insensitive mapping. Do NOT wrap it
    # in dict(): WSGI reconstructs header names title-cased
    # (X-Ssl-Client-Verify), so exact-case lookups against
    # dict(request.headers) never match and proxy cert auth silently dies.
    headers = request.headers
    if 'X-SSL-Client-Verify' in headers:
        cert_info = CertificateParser.extract_from_nginx_headers(headers)
        if cert_info:
            return cert_info
    if 'X-SSL-Client-S-DN' in headers:
        cert_info = CertificateParser.extract_from_apache_headers(headers)
        if cert_info:
            return cert_info

    return None


def _is_file_request(path):
    """A static file (favicon, bundle, font): browsers may fetch these without the
    session cookie, so a login there would open a session nobody keeps."""
    return not path.startswith('/api/') and '.' in path.rsplit('/', 1)[-1]


def _names_no_stored_session():
    """A session cookie came with the request, but the store holds nothing under it."""
    return bool(_presented_cookie()) and not session


def _presented_cookie():
    return request.cookies.get(current_app.session_interface.get_cookie_name(current_app))


def _join_successor(old, user, auth_cert):
    """Take over the session that replaced cookie ``old`` if it is still this
    certificate's live session; False leaves the request to log in itself."""
    entry = _successors.get(old)
    if not entry or entry[1] < time.monotonic():
        return False
    iface = current_app.session_interface
    data = iface._retrieve_session_data(iface._get_store_id(entry[0]))
    if (not data or data.get('user_id') != user.id or data.get('cert_id') != auth_cert.id
            or data.get('session_version', 0) != (user.session_version or 0)):
        return False
    session.clear()
    session.update(data)
    session.sid = entry[0]
    return True


def _record_successor(old):
    """Store the new session now, so a parallel call can read it before this one ends."""
    iface = current_app.session_interface
    iface._upsert_session(current_app.permanent_session_lifetime, session,
                          iface._get_store_id(session.sid))
    now = time.monotonic()
    for key, (_sid, deadline) in list(_successors.items()):
        if deadline < now:
            _successors.pop(key, None)
    _successors[old] = (session.sid, now + SUCCESSOR_TTL)


def _open_certificate_session(user, auth_cert):
    begin_session(user)
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['auth_method'] = 'certificate'
    session['cert_id'] = auth_cert.id
    session['cert_serial'] = auth_cert.cert_serial
    session['login_time'] = utc_now().isoformat()
    session['last_activity'] = utc_now().isoformat()
    session.permanent = True


def process_client_certificate():
    """
    Process client certificate and auto-login if valid.
    Runs as before_request hook on every API call.
    
    Sources: native TLS peercert, Nginx headers, Apache headers.
    """
    # Protocol and probe paths read client certificates themselves; touching the
    # session there would keep a cookie's inactivity clock running from anywhere.
    if is_exempt_path(request.path) or _is_file_request(request.path):
        return
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
        stale = True
    else:
        stale = _names_no_stored_session()

    if not MTLSAuthService.is_mtls_enabled():
        return

    cert_info = _extract_certificate()
    if not cert_info:
        return

    # Store cert_info in g for /auth/methods to use without re-parsing
    g.mtls_cert_info = cert_info

    user, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)

    if user:
        old = _presented_cookie() if stale else None
        if old:
            # One login per expired cookie: the first call opens it, the others join
            with _SUCCESSOR_LOCKS[hash(old) % len(_SUCCESSOR_LOCKS)]:
                joined = _join_successor(old, user, auth_cert)
                if not joined:
                    _open_certificate_session(user, auth_cert)
                    _record_successor(old)
        else:
            joined = False
            _open_certificate_session(user, auth_cert)

        g.user = user
        g.auth_cert = auth_cert
        g.auth_method = 'certificate'

        if joined:
            return
        logger.info(f"mTLS auto-login: user={user.username}")
        
        # Audit log for mTLS login
        try:
            from services.audit_service import AuditService
            AuditService.log_auth(
                'login_success', username=user.username,
                user_id=user.id, details=f'mTLS auto-login (cert: {auth_cert.cert_serial})'
            )
        except Exception:
            pass
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
