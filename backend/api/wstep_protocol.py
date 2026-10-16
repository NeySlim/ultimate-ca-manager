"""
MS-WSTEP Protocol Implementation (WS-Trust X.509v3 Token Enrollment
Extensions) https://docs.microsoft.com/openspecs/windows_protocols/ms-wstep/

Three endpoints matching real ADCS CES naming convention, one per auth
binding (advertised to clients via XCEP's CAURI mechanism,
``services/xcep/policy_builder.py``):

- ``/ADCertificateService_CES_UsernamePassword/service.svc`` — initial
  enrollment, HTTP Basic auth (matches EST/XCEP's Basic-Auth pattern).
- ``/ADCertificateService_CES_Certificate/service.svc`` — renewal, the
  RST itself is WS-Security signed with the client's current certificate
  (see ``services/wstep/ws_security.py``); no HTTP-level auth.
- ``/ADCertificateService_CES_Kerberos/service.svc`` — initial enrollment
  or renewal for a domain-joined machine (GPO autoenrollment's usual
  path), authenticated via HTTP-transport-level ``Authorization:
  Negotiate`` (RFC 4559 — see ``services/kerberos/negotiate_auth.py``),
  not WS-Security like the other two bindings.

Both parse a ``RequestSecurityToken`` (RST) SOAP request and return a
``RequestSecurityTokenResponseCollection`` (RSTR) SOAP response, per
``services/wstep/rst_parser.py`` and ``services/wstep/rstr_builder.py``.
Errors are returned as SOAP faults (``services/wstep/soap_envelope.py``),
not plain-text bodies, since XML/SOAP clients parse faults specifically.
"""
import hmac
import logging

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from flask import Blueprint, Response, request

from models import CA, AuditLog, Certificate, SystemConfig, db
from services.ca_service import CAService
from services.kerberos import negotiate_auth
from services.wstep import CES_CERTIFICATE_PATH, CES_KERBEROS_PATH, CES_USERNAME_PASSWORD_PATH
from services.wstep import wstep_service
from services.wstep.cmc_response import build_cmc_full_pki_response
from services.wstep.rst_parser import RSTParseError, parse_rst
from services.wstep.rstr_builder import build_issue_response
from services.wstep.soap_envelope import build_soap_fault, extract_username_token
from utils.db_transaction import safe_commit
from utils.trusted_proxy import client_ip

logger = logging.getLogger(__name__)

bp = Blueprint('wstep_protocol', __name__)

# WS-Security signature blocks add real overhead over XCEP's GetPolicies
# budget; 128 KB is still generous for an actual CSR + signed envelope.
WSTEP_MAX_BODY_BYTES = 128 * 1024

SOAP_XML_MIME = 'application/soap+xml'


def _wstep_enabled():
    row = SystemConfig.query.filter_by(key='wstep_enabled').first()
    return bool(row and (row.value or '').lower() == 'true')


@bp.before_request
def _enforce_wstep_enabled():
    """When WSTEP is administratively disabled every endpoint here behaves
    as if not configured, matching EST/XCEP's ``_enforce_*_enabled``."""
    if not _wstep_enabled():
        return Response('WSTEP disabled', status=503)


def _read_wstep_body():
    """Read the request body, hard-capped at WSTEP_MAX_BODY_BYTES.

    Reads at most one byte past the cap so a chunked/unbounded body can't
    be buffered into memory before the size is known — same rationale as
    EST's ``_read_est_body_text``/XCEP's ``_read_xcep_body_text``.
    """
    raw = request.stream.read(WSTEP_MAX_BODY_BYTES + 1)
    if len(raw) > WSTEP_MAX_BODY_BYTES:
        return None, Response('Request body too large', status=413)
    return raw, None


def _check_credentials(username, password):
    if not username or not password:
        return False
    wstep_username = SystemConfig.query.filter_by(key='wstep_username').first()
    wstep_password = SystemConfig.query.filter_by(key='wstep_password').first()
    if not (wstep_username and wstep_password and wstep_username.value and wstep_password.value):
        return False

    # hmac.compare_digest on two `str` operands requires both to be
    # ASCII-only and raises TypeError otherwise -- a non-ASCII Basic-auth
    # username/password would 500 instead of the SOAP auth-failed fault
    # every other bad-credential case gets. bytes operands have no such
    # restriction, so encode first.
    username_match = hmac.compare_digest(username.encode('utf-8'), wstep_username.value.encode('utf-8'))
    from utils.password_hash import HASH_PREFIXES, verify_password
    if wstep_password.value.startswith(HASH_PREFIXES):
        password_match = verify_password(wstep_password.value, password)
    else:
        password_match = hmac.compare_digest(password.encode('utf-8'), wstep_password.value.encode('utf-8'))
    return username_match and password_match


def _authenticate_username_password(security_header):
    """WS-Security UsernameToken first (real client behavior — see the
    matching note on XCEP's ``_authenticate_xcep_client``), HTTP Basic as
    a fallback. Returns (authenticated: bool, username: str or None)."""
    token_username, token_password = extract_username_token(security_header)
    if token_username:
        return _check_credentials(token_username, token_password), token_username

    auth = request.authorization
    if auth and auth.username is not None and auth.password is not None:
        return _check_credentials(auth.username, auth.password), auth.username

    return False, None


def _resolve_wstep_ca():
    """Return (ca, error_response) for the single configured WSTEP CA."""
    ca_refid = SystemConfig.query.filter_by(key='wstep_ca_refid').first()
    if not ca_refid or not ca_refid.value:
        logger.warning("WSTEP request refused: WSTEP not configured")
        return None, _fault_response('WSTEP not configured', status=503)
    ca = CA.query.filter_by(refid=ca_refid.value).first()
    if not ca:
        logger.warning("WSTEP request refused: configured CA %r not found", ca_refid.value)
        return None, _fault_response('WSTEP not configured', status=503)
    return ca, None


def _validity_days():
    row = SystemConfig.query.filter_by(key='wstep_validity_days').first()
    try:
        return int(row.value) if row and row.value else 365
    except (TypeError, ValueError):
        return 365


def _fault_response(reason, status=500, relates_to=None):
    (logger.error if status >= 500 else logger.debug)("WSTEP fault (status=%s): %s", status, reason)
    body = build_soap_fault(reason, relates_to=relates_to)
    return Response(body, status=status, content_type=f'{SOAP_XML_MIME}; charset=utf-8')


def _request_id_for(cert):
    """The issued cert's own DB row ID, for RSTR's wstep:RequestID — see
    build_issue_response's docstring. None if the row can't be found
    (shouldn't happen; CAService.sign_csr_from_crypto just created it),
    in which case build_issue_response omits the element rather than
    faking a value."""
    db_cert = Certificate.query.filter_by(serial_number=str(cert.serial_number)).first()
    return db_cert.id if db_cert else None


def _cmc_response_der_for(ca, cert, parsed):
    """CMC full PKI response DER for build_issue_response's
    cmc_response_der, or None when not applicable — see cmc_response.py
    for why this is built at all. Only meaningful for CMC-wrapped
    requests (parsed.was_pkcs7_wrapped); real Windows clients sending a
    plain PKCS#10 BinarySecurityToken have no CMC bodyPartID to
    reference, and haven't been observed needing this. Failure here
    shouldn't fail the whole enrollment (the plain X509v3 token still
    works standalone for those requests) — logged and skipped."""
    if not parsed.was_pkcs7_wrapped:
        return None
    try:
        chain_pems = CAService.get_certificate_chain(ca.refid) or []
        chain_ders = [
            x509.load_pem_x509_certificate(
                pem.encode() if isinstance(pem, str) else pem
            ).public_bytes(Encoding.DER)
            for pem in chain_pems
        ]
        return build_cmc_full_pki_response(
            cert.public_bytes(Encoding.DER), chain_ders, parsed.cmc_body_part_id
        )
    except Exception as e:
        logger.warning("WSTEP: failed to build CMC full PKI response: %s", e)
        return None


def _audit_issuance(action, subject, username):
    from services.audit.staging import stage_audit_entry
    stage_audit_entry(
        action=action,
        resource_type='certificate',
        resource_name=subject,
        username=username,
        details=f'WSTEP enrollment from {client_ip()}',
    )
    safe_commit(logger, "WSTEP enrollment audit commit failed")


def _issue_and_respond(ca, parsed, username, action='certificate.issued', kerberos_principal=None):
    """Shared issuance + RSTR-building + audit logging for every CES
    binding that issues (as opposed to renews) a certificate, once that
    binding's own auth check has already succeeded.

    ``kerberos_principal``: only ever passed by ``issue_kerberos``'s call
    site below, for the AD-derived naked-CSR subject fallback (see
    ``wstep_service.issue``) -- ``issue_username_password`` has no Kerberos
    identity to give and must never pass anything into this.
    """
    cert_pem, error = wstep_service.issue(
        ca, parsed.csr_der, _validity_days(), require_pop=not parsed.was_pkcs7_wrapped,
        kerberos_principal=kerberos_principal, outer_signed_data=parsed.outer_signed_data,
    )
    if error:
        logger.warning("WSTEP issuance rejected for %r: %s", username, error)
        return _fault_response(error, status=400, relates_to=parsed.message_id)

    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        response_body = build_issue_response(
            cert, relates_to=parsed.message_id, request_id=_request_id_for(cert),
            cmc_response_der=_cmc_response_der_for(ca, cert, parsed),
        )
    except Exception as e:
        logger.error("WSTEP: failed to build RSTR: %s", e)
        return _fault_response('Internal server error', status=500, relates_to=parsed.message_id)

    _audit_issuance(action, cert.subject.rfc4514_string(), username)
    return Response(response_body, status=200, content_type=f'{SOAP_XML_MIME}; charset=utf-8')


@bp.route(CES_USERNAME_PASSWORD_PATH, methods=['GET', 'POST', 'HEAD'])
def issue_username_password():
    """WSTEP RST over the UsernamePassword-authenticated CES endpoint —
    initial enrollment only (no existing identity to renew from).

    Accepts GET/HEAD as well as POST so a reachability probe doesn't fall
    through to UCM's frontend SPA route (200 OK, HTML), but they don't
    trigger an HTTP Basic challenge — see the matching note on XCEP's
    ``get_policies`` for why that actively breaks a real client. Real
    credentials arrive as a WS-Security UsernameToken inside the RST's
    ``wsse:Security`` header, so auth can't be checked until the body is
    parsed; HTTP Basic remains a fallback for simpler test clients.
    """
    if request.method in ('GET', 'HEAD'):
        return Response('', status=200, content_type='text/html; charset=utf-8')

    cl = request.content_length
    if cl is not None and cl > WSTEP_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)

    body, err = _read_wstep_body()
    if err is not None:
        return err

    try:
        parsed = parse_rst(body)
    except RSTParseError as e:
        return _fault_response(f'Malformed request: {e}', status=400)

    authenticated, username = _authenticate_username_password(parsed.security_header)
    if not authenticated:
        return _fault_response('Authentication failed', status=400, relates_to=parsed.message_id)

    ca, ca_error = _resolve_wstep_ca()
    if ca_error:
        return ca_error

    return _issue_and_respond(ca, parsed, username)


@bp.route(CES_KERBEROS_PATH, methods=['GET', 'POST', 'HEAD'])
def issue_kerberos():
    """WSTEP RST over the Kerberos-authenticated CES endpoint — what GPO
    machine autoenrollment uses for both initial enrollment and renewal,
    since it authenticates via the machine's own Kerberos identity rather
    than an existing certificate (contrast with the Certificate-bound
    endpoint above, which is renewal-only by construction).

    Auth is HTTP-transport-level (``Authorization: Negotiate``), so unlike
    the UsernamePassword endpoint it's checked *before* the body is read at
    all — same reject-before-work shape as ``_enforce_wstep_enabled``.
    """
    if request.method in ('GET', 'HEAD'):
        return Response('', status=200, content_type='text/html; charset=utf-8')

    if not negotiate_auth.is_library_available():
        logger.warning(
            "Kerberos/SPNEGO CES request rejected: pyspnego's GSSAPI backend "
            "isn't installed (pip install pyspnego[kerberos])"
        )
        return Response('Kerberos binding not configured', status=503)
    if not negotiate_auth.is_configured():
        logger.warning("Kerberos/SPNEGO CES request rejected: Kerberos not enabled/configured")
        return Response('Kerberos binding not configured', status=503)

    cl = request.content_length
    if cl is not None and cl > WSTEP_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)

    connection_key = request.environ.get('REMOTE_ADDR')
    result = negotiate_auth.authenticate_negotiate(request.headers.get('Authorization'), connection_key)
    if result.status != 'authenticated':
        if result.status not in ('challenge', 'continue'):
            logger.warning("WSTEP Kerberos auth failed: %s", result.error)
        # 'continue': an intermediate SPNEGO leg (e.g. a request-mic round) --
        # the real-world client may open a fresh TCP connection per leg, so
        # this is keyed on source IP, not the full connection tuple (see
        # services/kerberos/negotiate_auth.py's module docstring).
        headers = {'WWW-Authenticate': f'Negotiate {result.response_token_b64}' if result.response_token_b64 else 'Negotiate'}
        return Response('', status=401, headers=headers)

    ca, ca_error = _resolve_wstep_ca()
    if ca_error:
        return ca_error

    body, err = _read_wstep_body()
    if err is not None:
        return err

    try:
        parsed = parse_rst(body)
    except RSTParseError as e:
        return _fault_response(f'Malformed request: {e}', status=400)

    response = _issue_and_respond(
        ca, parsed, result.client_principal, kerberos_principal=result.client_principal,
    )
    if result.response_token_b64 and response.status_code == 200:
        response.headers['WWW-Authenticate'] = f'Negotiate {result.response_token_b64}'
    return response


@bp.route(CES_CERTIFICATE_PATH, methods=['GET', 'POST', 'HEAD'])
def renew_certificate_bound():
    """WSTEP RST over the Certificate-authenticated CES endpoint —
    renewal, authenticated via WS-Security XML-DSig signing of the RST
    with the client's current certificate's private key, not HTTP-level
    auth.

    Accepts GET/HEAD as well as POST — same rationale as the
    UsernamePassword endpoint above, though this binding has no HTTP-level
    auth to challenge (the RST's own signature is the auth), so GET/HEAD
    just need to avoid falling through to the frontend SPA route.
    """
    cl = request.content_length
    if cl is not None and cl > WSTEP_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)

    if request.method in ('GET', 'HEAD'):
        return Response('', status=200, content_type='text/html; charset=utf-8')

    ca, ca_error = _resolve_wstep_ca()
    if ca_error:
        return ca_error

    body, err = _read_wstep_body()
    if err is not None:
        return err

    try:
        parsed = parse_rst(body)
    except RSTParseError as e:
        return _fault_response(f'Malformed request: {e}', status=400)

    cert_pem, error = wstep_service.renew(
        ca, parsed.csr_der, parsed.security_header, parsed.csr_element, _validity_days(),
        require_pop=not parsed.was_pkcs7_wrapped,
    )
    if error:
        logger.warning("WSTEP renewal rejected: %s", error)
        return _fault_response(error, status=400, relates_to=parsed.message_id)

    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        response_body = build_issue_response(
            cert, relates_to=parsed.message_id, request_id=_request_id_for(cert),
            cmc_response_der=_cmc_response_der_for(ca, cert, parsed),
        )
    except Exception as e:
        logger.error("WSTEP: failed to build RSTR: %s", e)
        return _fault_response('Internal server error', status=500, relates_to=parsed.message_id)

    _audit_issuance('certificate.renewed', cert.subject.rfc4514_string(), 'wstep-client-cert')
    return Response(response_body, status=200, content_type=f'{SOAP_XML_MIME}; charset=utf-8')
