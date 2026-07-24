"""
MS-XCEP Protocol Implementation (Certificate Enrollment Policy Protocol)
https://docs.microsoft.com/openspecs/windows_protocols/ms-xcep/

Phase 1: read-only ``GetPolicies`` — lets Windows clients (MMC "Request
New Certificate", certreq, GPO autoenrollment) discover which certificate
templates/CAs UCM exposes for enrollment. Issuance (MS-WSTEP) and
Kerberos/SPNEGO auth are later phases; this endpoint authenticates with
username/password only, matching EST's Basic-Auth path — XCEP policy
retrieval is lightly authenticated by design, real hardening happens at
WSTEP issuance time.
"""
from flask import Blueprint, request, Response
from models import CA, SystemConfig, CertificateTemplate
import hmac
import logging

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


def _read_xcep_body_text():
    """Read the request body as text, hard-capped at XCEP_MAX_BODY_BYTES.

    Reads at most one byte past the cap so a chunked/unbounded body can't
    be buffered into memory before the size is known — same rationale as
    EST's ``_read_est_body_text``.
    """
    raw = request.stream.read(XCEP_MAX_BODY_BYTES + 1)
    if len(raw) > XCEP_MAX_BODY_BYTES:
        return None, Response('Request body too large', status=413)
    try:
        return raw.decode('utf-8'), None
    except UnicodeDecodeError:
        return None, Response('Invalid request body encoding', status=400)


def _authenticate_xcep_client():
    """Username/password only for Phase 1 (see module docstring).
    Returns (authenticated: bool, username: str or None)."""
    auth = request.authorization
    if not auth:
        return False, None

    xcep_username = SystemConfig.query.filter_by(key='xcep_username').first()
    xcep_password = SystemConfig.query.filter_by(key='xcep_password').first()
    if not (xcep_username and xcep_password and xcep_username.value and xcep_password.value):
        return False, None

    if auth.username is None or auth.password is None:
        return False, None

    username_match = hmac.compare_digest(auth.username, xcep_username.value)
    from werkzeug.security import check_password_hash
    if xcep_password.value.startswith(('scrypt:', 'pbkdf2:')):
        password_match = check_password_hash(xcep_password.value, auth.password)
    else:
        password_match = hmac.compare_digest(auth.password, xcep_password.value)

    if username_match and password_match:
        return True, auth.username
    return False, None


def _resolve_xcep_ca():
    """Return (ca, error_response) for the single configured XCEP CA."""
    ca_refid = SystemConfig.query.filter_by(key='xcep_ca_refid').first()
    if not ca_refid or not ca_refid.value:
        logger.warning("XCEP request refused: XCEP not configured")
        return None, Response('XCEP not configured', status=503)
    ca = CA.query.filter_by(refid=ca_refid.value).first()
    if not ca:
        logger.warning("XCEP request refused: configured CA %r not found", ca_refid.value)
        return None, Response('XCEP not configured', status=503)
    return ca, None


@bp.route('/ADPolicyProvider_CEP_UsernamePassword/service.svc', methods=['POST'])
def get_policies():
    """MS-XCEP GetPolicies over the UsernamePassword-authenticated CEP
    endpoint. The URL shape follows Microsoft's own convention of
    encoding the auth binding in the CEP path (Kerberos/Certificate
    variants land in Phase 3 once SPNEGO auth exists)."""
    cl = request.content_length
    if cl is not None and cl > XCEP_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)

    authenticated, _username = _authenticate_xcep_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="XCEP"'},
        )

    ca, ca_error = _resolve_xcep_ca()
    if ca_error:
        return ca_error

    # The request body is currently unparsed: GetPolicies carries no
    # client-supplied filtering UCM needs for Phase 1 (every pinned/active
    # template is offered). Still enforce the body cap so a client can't
    # send an oversized payload, and surface malformed encoding early.
    _body_text, err = _read_xcep_body_text()
    if err is not None:
        return err

    try:
        templates = CertificateTemplate.query.filter_by(is_active=True).all()
        from services.xcep.policy_builder import build_get_policies_response
        xml_body = build_get_policies_response(ca, templates)
        return Response(xml_body, status=200, content_type=f'{SOAP_XML_MIME}; charset=utf-8')
    except Exception as e:
        logger.error(f"XCEP GetPolicies failed: {e}")
        return Response('Internal server error', status=500)
