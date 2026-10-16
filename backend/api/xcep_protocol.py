"""
MS-XCEP Protocol Implementation (Certificate Enrollment Policy Protocol)
https://docs.microsoft.com/openspecs/windows_protocols/ms-xcep/

Read-only ``GetPolicies`` — lets Windows clients (MMC "Request New
Certificate", certreq, GPO autoenrollment) discover which certificate
templates/CAs UCM exposes for enrollment, and where to actually send an
enrollment request (MS-WSTEP, ``api/wstep_protocol.py``) via the CAURI
mechanism. Kerberos/SPNEGO auth is a later phase; this endpoint
authenticates with username/password only.

Credentials arrive as a WS-Security ``wsse:UsernameToken`` inside the
SOAP message header, not an HTTP ``Authorization: Basic`` header —
confirmed against the published MS-XCEP "Initial GetPolicies Client
Request" example. A real Windows client configured for this
UsernamePassword binding refuses to respond to an HTTP Basic challenge
(reports WS_E_SERVER_REQUIRES_BASIC_AUTH) since that's a different
security binding than the one it's using. HTTP Basic is still accepted
as a fallback (simpler to exercise from curl/tests), but the endpoint
never *challenges* for it — GET/HEAD probes get a plain 200, and POST
auth failures are reported as SOAP faults, not a 401.

The Kerberos binding (``ADPolicyProvider_CEP_Kerberos``, Phase 3) is the
opposite: it's pure HTTP-transport auth (``Authorization: Negotiate``, RFC
4559 — see ``services/kerberos/negotiate_auth.py``), so it's rejected
*before* the SOAP body is ever parsed, unlike UsernamePassword above.
"""
import hmac
import logging

from flask import Blueprint, Response, request

from models import CA, CertificateTemplate, SystemConfig
from services.kerberos import negotiate_auth
from services.wstep import CES_CERTIFICATE_PATH, CES_KERBEROS_PATH, CES_USERNAME_PASSWORD_PATH
from services.wstep.soap_envelope import build_soap_fault, extract_username_token
from services.xcep.request_parser import GetPoliciesParseError, parse_get_policies

logger = logging.getLogger(__name__)

bp = Blueprint('xcep_protocol', __name__)

# A GetPolicies SOAP request is a small, fixed-shape envelope with no
# attachments. 64 KB mirrors EST's body cap and is generous.
XCEP_MAX_BODY_BYTES = 64 * 1024

SOAP_XML_MIME = 'application/soap+xml'


def _xcep_enabled():
    row = SystemConfig.query.filter_by(key='xcep_enabled').first()
    return bool(row and (row.value or '').lower() == 'true')


@bp.before_request
def _enforce_xcep_enabled():
    """When XCEP is administratively disabled every endpoint here behaves
    as if not configured, matching EST's ``_enforce_est_enabled``."""
    if not _xcep_enabled():
        return Response('XCEP disabled', status=503)


def _read_xcep_body():
    """Read the request body, hard-capped at XCEP_MAX_BODY_BYTES.

    Reads at most one byte past the cap so a chunked/unbounded body can't
    be buffered into memory before the size is known — same rationale as
    EST's ``_read_est_body_text``.
    """
    raw = request.stream.read(XCEP_MAX_BODY_BYTES + 1)
    if len(raw) > XCEP_MAX_BODY_BYTES:
        return None, Response('Request body too large', status=413)
    return raw, None


def _check_credentials(username, password):
    if not username or not password:
        return False
    xcep_username = SystemConfig.query.filter_by(key='xcep_username').first()
    xcep_password = SystemConfig.query.filter_by(key='xcep_password').first()
    if not (xcep_username and xcep_password and xcep_username.value and xcep_password.value):
        return False

    # hmac.compare_digest on two `str` operands requires both to be
    # ASCII-only and raises TypeError otherwise -- a non-ASCII Basic-auth
    # username/password would 500 instead of the SOAP auth-failed fault
    # every other bad-credential case gets. bytes operands have no such
    # restriction, so encode first.
    username_match = hmac.compare_digest(username.encode('utf-8'), xcep_username.value.encode('utf-8'))
    from utils.password_hash import HASH_PREFIXES, verify_password
    if xcep_password.value.startswith(HASH_PREFIXES):
        password_match = verify_password(xcep_password.value, password)
    else:
        password_match = hmac.compare_digest(password.encode('utf-8'), xcep_password.value.encode('utf-8'))
    return username_match and password_match


def _authenticate_xcep_client(security_header):
    """WS-Security UsernameToken first (real client behavior), HTTP Basic
    as a fallback (simpler to exercise from curl/tests). Returns
    (authenticated: bool, username: str or None)."""
    token_username, token_password = extract_username_token(security_header)
    if token_username:
        return _check_credentials(token_username, token_password), token_username

    auth = request.authorization
    if auth and auth.username is not None and auth.password is not None:
        return _check_credentials(auth.username, auth.password), auth.username

    return False, None


def _resolve_xcep_ca():
    """Return (ca, error_response) for the single configured XCEP CA."""
    ca_refid = SystemConfig.query.filter_by(key='xcep_ca_refid').first()
    if not ca_refid or not ca_refid.value:
        logger.warning("XCEP request refused: XCEP not configured")
        return None, build_soap_fault('XCEP not configured')
    ca = CA.query.filter_by(refid=ca_refid.value).first()
    if not ca:
        logger.warning("XCEP request refused: configured CA %r not found", ca_refid.value)
        return None, build_soap_fault('XCEP not configured')
    return ca, None


def _handle_get_policies(parsed):
    """Shared GetPoliciesResponse construction for every CEP binding, once
    that binding's own auth check has already succeeded. Not itself
    binding-specific: the CAURI collection it builds advertises every
    configured WSTEP CES endpoint regardless of which CEP endpoint a client
    happened to poll, exactly like real ADCS.
    """
    ca, ca_error = _resolve_xcep_ca()
    if ca_error:
        return Response(ca_error, status=503, content_type=f'{SOAP_XML_MIME}; charset=utf-8')

    try:
        templates = CertificateTemplate.query.filter_by(is_active=True).all()
        from services.xcep.policy_builder import (
            AUTH_CLIENT_CERTIFICATE,
            AUTH_KERBEROS,
            AUTH_USERNAME_PASSWORD,
            build_get_policies_response,
        )
        # UsernamePassword/Certificate are always advertised, regardless of
        # whether WSTEP is currently enabled: MS-XCEP's CAURICollection
        # requires at least one cAURI entry (minOccurs="1"), so an empty
        # list here would itself make the response schema-invalid. If WSTEP
        # is administratively disabled, hitting these URLs 503s cleanly
        # (same as EST/SCEP's own "advertised but not configured" behavior)
        # rather than never being discoverable at all. Kerberos is the odd
        # one out: unlike the other two bindings it needs real AD Kerberos
        # infrastructure (a keytab) an admin may never set up, so it's only
        # advertised once actually configured — a client should never waste
        # a bind attempt on a mechanism guaranteed to fail.
        base = request.url_root.rstrip('/')
        enrollment_uris = [
            (AUTH_USERNAME_PASSWORD, f'{base}{CES_USERNAME_PASSWORD_PATH}', False),
            (AUTH_CLIENT_CERTIFICATE, f'{base}{CES_CERTIFICATE_PATH}', True),
        ]
        if negotiate_auth.is_library_available() and negotiate_auth.is_configured():
            enrollment_uris.append((AUTH_KERBEROS, f'{base}{CES_KERBEROS_PATH}', False))
        xml_body = build_get_policies_response(
            ca, templates, enrollment_uris=enrollment_uris, message_id=parsed.message_id,
        )
        return Response(xml_body, status=200, content_type=f'{SOAP_XML_MIME}; charset=utf-8')
    except Exception as e:
        logger.error(f"XCEP GetPolicies failed: {e}")
        return Response(
            build_soap_fault('Internal server error', relates_to=parsed.message_id),
            status=500, content_type=f'{SOAP_XML_MIME}; charset=utf-8',
        )


@bp.route('/ADPolicyProvider_CEP_UsernamePassword/service.svc', methods=['GET', 'POST', 'HEAD'])
def get_policies():
    """MS-XCEP GetPolicies over the UsernamePassword-authenticated CEP
    endpoint. The URL shape follows Microsoft's own convention of
    encoding the auth binding in the CEP path.

    Accepts GET/HEAD as well as POST so a client's initial reachability
    probe doesn't fall through to UCM's frontend SPA catch-all route
    (200 OK, HTML) — but unlike an earlier version of this endpoint,
    GET/HEAD do **not** trigger an HTTP Basic challenge, since that
    actively breaks a real client expecting message-level (UsernameToken)
    auth instead (see module docstring).
    """
    if request.method in ('GET', 'HEAD'):
        return Response('', status=200, content_type='text/html; charset=utf-8')

    cl = request.content_length
    if cl is not None and cl > XCEP_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)

    body, err = _read_xcep_body()
    if err is not None:
        return err

    try:
        parsed = parse_get_policies(body)
    except GetPoliciesParseError as e:
        return Response(
            build_soap_fault(f'Malformed request: {e}'),
            status=400, content_type=f'{SOAP_XML_MIME}; charset=utf-8',
        )

    authenticated, _username = _authenticate_xcep_client(parsed.security_header)
    if not authenticated:
        return Response(
            build_soap_fault('Authentication failed', relates_to=parsed.message_id),
            status=400, content_type=f'{SOAP_XML_MIME}; charset=utf-8',
        )

    return _handle_get_policies(parsed)


@bp.route('/ADPolicyProvider_CEP_Kerberos/service.svc', methods=['GET', 'POST', 'HEAD'])
def get_policies_kerberos():
    """MS-XCEP GetPolicies over the Kerberos-authenticated CEP endpoint —
    what GPO machine autoenrollment actually uses, since it can't prompt
    for a username/password. Auth is HTTP-transport-level (``Authorization:
    Negotiate``, RFC 4559), not WS-Security, so it's checked *before* the
    SOAP body is read at all — same reject-before-work shape as
    ``_enforce_xcep_enabled``.
    """
    if request.method in ('GET', 'HEAD'):
        return Response('', status=200, content_type='text/html; charset=utf-8')

    if not negotiate_auth.is_library_available():
        logger.warning(
            "Kerberos/SPNEGO CEP request rejected: pyspnego's GSSAPI backend "
            "isn't installed (pip install pyspnego[kerberos])"
        )
        return Response('Kerberos binding not configured', status=503)
    if not negotiate_auth.is_configured():
        logger.warning("Kerberos/SPNEGO CEP request rejected: Kerberos not enabled/configured")
        return Response('Kerberos binding not configured', status=503)

    cl = request.content_length
    if cl is not None and cl > XCEP_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)

    connection_key = request.environ.get('REMOTE_ADDR')
    result = negotiate_auth.authenticate_negotiate(request.headers.get('Authorization'), connection_key)
    if result.status in ('challenge', 'continue'):
        # 'continue': an intermediate SPNEGO leg (e.g. a request-mic round) --
        # same shape as 'challenge', just with a continuation token. The
        # real-world client may open a fresh TCP connection per leg, so this
        # is keyed on source IP, not the full connection tuple (see
        # services/kerberos/negotiate_auth.py's module docstring).
        headers = {'WWW-Authenticate': f'Negotiate {result.response_token_b64}' if result.response_token_b64 else 'Negotiate'}
        return Response('', status=401, headers=headers)
    if result.status != 'authenticated':
        logger.warning("XCEP Kerberos auth failed: %s", result.error)
        return Response('', status=401, headers={'WWW-Authenticate': 'Negotiate'})

    body, err = _read_xcep_body()
    if err is not None:
        return err

    try:
        parsed = parse_get_policies(body)
    except GetPoliciesParseError as e:
        return Response(
            build_soap_fault(f'Malformed request: {e}'),
            status=400, content_type=f'{SOAP_XML_MIME}; charset=utf-8',
        )

    response = _handle_get_policies(parsed)
    if result.response_token_b64:
        response.headers['WWW-Authenticate'] = f'Negotiate {result.response_token_b64}'
    return response
