"""
MS-WSTEP Protocol Implementation (WS-Trust X.509v3 Token Enrollment
Extensions) https://docs.microsoft.com/openspecs/windows_protocols/ms-wstep/

Three endpoints matching real ADCS CES naming convention, one per auth
binding (advertised to clients via XCEP's CAURI mechanism,
``services/xcep/policy_builder.py``):

- ``/ADCertificateService_CES_UsernamePassword/service.svc`` — initial
  enrollment, HTTP Basic auth (matches EST/XCEP's Basic-Auth pattern).
- ``/ADCertificateService_CES_Certificate/service.svc`` — renewal, by the
  client's current certificate: a WS-Security signature of the RST
  (``services/wstep/ws_security.py``) or the TLS client certificate, which
  must also sign the CMS request.
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

from models import AuditLog, Certificate, SystemConfig, db
from services.ca_service import CAService
from services.kerberos import negotiate_auth
from services.wstep import CES_CERTIFICATE_PATH, CES_KERBEROS_PATH, CES_USERNAME_PASSWORD_PATH
from services.wstep import wstep_service
from services.wstep.cmc_response import build_cmc_full_pki_response
from services.wstep.rst_parser import (REQUEST_TYPE_ISSUE, REQUEST_TYPE_QUERY_TOKEN_STATUS, RSTParseError,
                                      parse_rst)
from services.wstep.rstr_builder import build_issue_response, build_pending_response
from services.wstep.soap_envelope import DS_NS, build_soap_fault, extract_username_token, message_expired
from utils.client_cert import trusted_client_cert
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
    from services.windows_profiles import serving_profile
    profile = serving_profile()
    wstep_username = profile.wstep_username if profile is not None else None
    wstep_password = profile.wstep_password if profile is not None else None
    if not (wstep_username and wstep_password):
        return False

    # hmac.compare_digest on two `str` operands requires both to be
    # ASCII-only and raises TypeError otherwise -- a non-ASCII Basic-auth
    # username/password would 500 instead of the SOAP auth-failed fault
    # every other bad-credential case gets. bytes operands have no such
    # restriction, so encode first.
    username_match = hmac.compare_digest(username.encode('utf-8'), wstep_username.encode('utf-8'))
    from utils.password_hash import HASH_PREFIXES, verify_password
    if wstep_password.startswith(HASH_PREFIXES):
        password_match = verify_password(wstep_password, password)
    else:
        password_match = hmac.compare_digest(password.encode('utf-8'), wstep_password.encode('utf-8'))
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


def _resolve_wstep_ca(profile):
    """Return (ca, error_response) for the issuing CA of *profile*."""
    from services.windows_profiles import issuing_ca
    if profile is None or not profile.issuing_ca_refid:
        logger.warning("WSTEP request refused: WSTEP not configured")
        return None, _fault_response('WSTEP not configured', status=503)
    ca = issuing_ca(profile)
    if not ca:
        logger.warning("WSTEP request refused: configured CA %r not found", profile.issuing_ca_refid)
        return None, _fault_response('WSTEP not configured', status=503)
    return ca, None


def _validity_days(profile):
    return (profile.validity_days if profile is not None and profile.validity_days else 365)


def _fault_response(reason, status=500, relates_to=None, subcode=None, request_id=None,
                    invalid_request=None):
    # SOAP 1.2 HTTP binding: env:Sender (the request is at fault) goes as 400, env:Receiver as 500
    code = 's:Sender' if status < 500 else 's:Receiver'
    (logger.error if status >= 500 else logger.debug)("WSTEP fault (status=%s): %s", status, reason)
    body = build_soap_fault(reason, code=code, relates_to=relates_to, subcode=subcode,
                            request_id=request_id, invalid_request=invalid_request)
    return Response(body, status=status, content_type=f'{SOAP_XML_MIME}; charset=utf-8')


def _error_status(error):
    return 500 if isinstance(error, wstep_service.ServerError) else 400


def _parse_request(body):
    """``(parsed, fault)``: the RST, or the fault answering it. MS-WSTEP 3.1.4.2.1
    serves Issue only (renewal included); an expired wsu:Timestamp is refused."""
    try:
        parsed = parse_rst(body)
    except RSTParseError as e:
        return None, _fault_response(f'Malformed request: {e}', status=400, relates_to=e.message_id)
    if parsed.request_type not in (REQUEST_TYPE_ISSUE, REQUEST_TYPE_QUERY_TOKEN_STATUS):
        return None, _fault_response('Unsupported wst:RequestType: only Issue and QueryTokenStatus '
                                     'are served', status=400, relates_to=parsed.message_id)
    # WSS 1.1 section 12: on SOAP 1.2 its fault codes are subcodes of env:Sender
    if message_expired(parsed.security_header):
        return None, _fault_response('The message has expired (wsu:Timestamp)', status=400,
                                     relates_to=parsed.message_id, subcode='wsse:MessageExpired')
    return parsed, None


def _request_id_for(cert):
    """The issued cert's own DB row ID, for RSTR's wstep:RequestID — see
    build_issue_response's docstring. None if the row can't be found
    (shouldn't happen; CAService.sign_csr_from_crypto just created it),
    in which case build_issue_response omits the element rather than
    faking a value."""
    db_cert = Certificate.query.filter_by(serial_number=str(cert.serial_number)).first()
    return db_cert.id if db_cert else None


def _cmc_response_der_for(ca, cert, parsed):
    """CMC full PKI response DER for build_issue_response's cmc_response_der,
    which MS-WSTEP 3.1.4.1.3.2 requires for every request. A PKCS#10 outside a
    CMC PKIData is a Simple PKI Request, referenced by bodyPartID 1 (RFC 5272 6.1.1). Failure
    here doesn't fail the enrollment (the X509v3 token still works alone):
    logged and skipped."""
    body_part_id = parsed.cmc_body_part_id if parsed.cmc_body_part_id is not None else 1
    try:
        chain_pems = CAService.get_certificate_chain(ca.refid) or []
        chain_ders = [
            x509.load_pem_x509_certificate(
                pem.encode() if isinstance(pem, str) else pem
            ).public_bytes(Encoding.DER)
            for pem in chain_pems
        ]
        return build_cmc_full_pki_response(
            cert.public_bytes(Encoding.DER), chain_ders, body_part_id
        )
    except Exception as e:
        logger.warning("WSTEP: failed to build CMC full PKI response: %s", e)
        return None


def _audit_issuance(action, subject, username, details, success=True, resource_id=None):
    from services.audit.staging import stage_audit_entry
    stage_audit_entry(
        action=action,
        resource_type='certificate',
        resource_id=resource_id,
        resource_name=subject,
        username=username,
        details=details,
        success=success,
    )
    safe_commit(logger, "WSTEP audit commit failed")


# Seconds the pending response suggests before QueryTokenStatus (CMC pendTime)
PENDING_RETRY_SECONDS = 300


def _rstr(body):
    return Response(body, status=200, content_type=f'{SOAP_XML_MIME}; charset=utf-8')


def _renewed_certificate_standing(ca, approval):
    """An approved renewal is refused only when the certificate it renews
    was revoked; any other status (expired, no longer on record) delivers it."""
    from services import protocol_approval
    from services.cert.issued_lookup import REVOKED, issued_certificate_status
    renewal_of = protocol_approval.request_data(approval).get('renewal_of')
    if not renewal_of:
        return True
    _row, status = issued_certificate_status(ca, x509.load_pem_x509_certificate(renewal_of.encode()))
    return status != REVOKED


def _answer_held(ca, parsed, approval):
    """MS-WSTEP 3.1.4.2.1.1/3.1.4.2.1.2: a pending RSTR while the request
    waits, the certificate once approved, a fault (InvalidRequest) once
    denied; a decision is delivered once."""
    from datetime import datetime, timedelta, timezone
    from services import protocol_approval
    from services.wstep.approval import issued_certificate
    from services.wstep.cmc_response import build_cmc_pending_response
    if approval.status == 'approved' and protocol_approval.request_data(approval).get('delivered_at'):
        # Delivered once: its certificate again while it exists, never judged again
        cert = issued_certificate(approval)
        if cert is None:
            return _fault_response(protocol_approval.CERTIFICATE_WITHDRAWN, status=400,
                                   relates_to=parsed.message_id, request_id=approval.id,
                                   invalid_request=True)
        return _rstr(build_issue_response(cert, relates_to=parsed.message_id, request_id=approval.id,
                                          cmc_response_der=_cmc_response_der_for(ca, cert, parsed)))
    if approval.status == 'approved':
        cert = issued_certificate(approval)
        if cert is None:
            protocol_approval.close_withdrawn(approval)
        elif not _renewed_certificate_standing(ca, approval):
            protocol_approval.close_withdrawn(approval, protocol_approval.RENEWED_REVOKED)
        else:
            body = build_issue_response(cert, relates_to=parsed.message_id, request_id=approval.id,
                                        cmc_response_der=_cmc_response_der_for(ca, cert, parsed))
            protocol_approval.mark_delivered(approval)
            return _rstr(body)
    if approval.status in ('rejected', 'expired', 'cancelled'):
        protocol_approval.mark_delivered(approval)
        return _fault_response(protocol_approval.decision_reason(approval), status=400,
                               relates_to=parsed.message_id, request_id=approval.id,
                               invalid_request=True)
    try:
        cmc = build_cmc_pending_response(
            parsed.cmc_body_part_id, str(approval.id).encode(),
            datetime.now(timezone.utc) + timedelta(seconds=PENDING_RETRY_SECONDS))
    except Exception as e:
        logger.warning("WSTEP: failed to build the pending CMC response: %s", e)
        cmc = None
    return _rstr(build_pending_response(approval.id, relates_to=parsed.message_id,
                                        cmc_response_der=cmc))


def _query_token_status(ca, parsed, identity):
    """MS-WSTEP 3.1.4.2.1.2: the status of a request answered pending, for
    the requester that made it."""
    from services.wstep.approval import request_for
    approval = request_for(parsed.request_id, ca, identity)
    if approval is None:
        return _fault_response('Unknown RequestID', status=400, relates_to=parsed.message_id,
                               request_id=parsed.request_id, invalid_request=False)
    return _answer_held(ca, parsed, approval)


def _issue_and_respond(ca, parsed, username, *, profile, kerberos_principal=None):
    """Shared issuance + RSTR-building + audit logging for every CES
    binding that issues (as opposed to renews) a certificate, once that
    binding's own auth check has already succeeded, under ``profile``.

    ``kerberos_principal``: only ever passed by ``issue_kerberos``'s call
    site below, for the AD-derived naked-CSR subject fallback (see
    ``wstep_service.issue``) -- ``issue_username_password`` has no Kerberos
    identity to give and must never pass anything into this.
    """
    from services.wstep.approval import make_gate
    identity = f'kerberos:{kerberos_principal}' if kerberos_principal else f'user:{username}'
    if parsed.request_type == REQUEST_TYPE_QUERY_TOKEN_STATUS:
        return _query_token_status(ca, parsed, identity)
    gate = make_gate(ca, operation='issue', identity=identity, profile=profile, extra={
        'kerberos_principal': kerberos_principal, 'require_pop': not parsed.was_pkcs7_wrapped})
    try:
        cert_pem, error = wstep_service.issue(
            ca, parsed.csr_der, _validity_days(profile), require_pop=not parsed.was_pkcs7_wrapped,
            kerberos_principal=kerberos_principal, outer_signed_data=parsed.outer_signed_data,
            gate=gate, profile=profile,
        )
    except wstep_service.HeldForApproval as held:
        return _answer_held(ca, parsed, held.approval)
    if error:
        logger.warning("WSTEP issuance rejected for %r: %s", username, error)
        if kerberos_principal:
            from services.windows_profiles import audit_kerberos_refusal, kerberos_route
            audit_kerberos_refusal('CES', kerberos_principal, kerberos_route(kerberos_principal)[1],
                                   profile, error)
        return _fault_response(error, status=_error_status(error), relates_to=parsed.message_id)

    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        request_id = _request_id_for(cert)
        response_body = build_issue_response(
            cert, relates_to=parsed.message_id, request_id=request_id,
            cmc_response_der=_cmc_response_der_for(ca, cert, parsed),
        )
    except Exception as e:
        logger.error("WSTEP: failed to build RSTR: %s", e)
        return _fault_response('Internal server error', status=500, relates_to=parsed.message_id)

    # A Kerberos request signed by a certificate of this CA renews it (the Kerberos binding renews too)
    old_serial = wstep_service.renewed_serial(ca, parsed.outer_signed_data) if kerberos_principal else None
    served = f'profile {profile.name}' + (f', realm {profile.realm}' if kerberos_principal else '')
    if old_serial is not None:
        action, details = 'certificate.renewed', (
            f'WSTEP renewal from {client_ip()}: old serial {old_serial}, '
            f'new serial {cert.serial_number} ({served})')
    else:
        action = 'certificate.issued'
        details = f'WSTEP enrollment from {client_ip()}: serial {cert.serial_number} ({served})'
    _audit_issuance(action, cert.subject.rfc4514_string(), username,
                    resource_id=str(request_id) if request_id else None, details=details)
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

    parsed, fault = _parse_request(body)
    if fault is not None:
        return fault

    authenticated, username = _authenticate_username_password(parsed.security_header)
    if not authenticated:
        return _fault_response('Authentication failed', status=400, relates_to=parsed.message_id)

    # A2: the shared account serves the default profile alone
    from services.windows_profiles import serving_profile
    profile = serving_profile()
    ca, ca_error = _resolve_wstep_ca(profile)
    if ca_error:
        return ca_error

    return _issue_and_respond(ca, parsed, username, profile=profile)


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

    connection_key = client_ip()
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

    body, err = _read_wstep_body()
    if err is not None:
        return err

    parsed, fault = _parse_request(body)
    if fault is not None:
        return fault

    from services.windows_profiles import serve_kerberos
    profile = serve_kerberos(result.client_principal, 'CES')
    if profile is None:
        # Authenticated (RFC 4559): a refused realm is the request's fault, never a new challenge
        return _fault_response(wstep_service.REALM_NOT_SERVED, status=400, relates_to=parsed.message_id)
    logger.info("WSTEP: request of %s served by profile %s", result.client_principal, profile.name)

    ca, ca_error = _resolve_wstep_ca(profile)
    if ca_error:
        return ca_error

    response = _issue_and_respond(
        ca, parsed, result.client_principal, profile=profile, kerberos_principal=result.client_principal,
    )
    if result.response_token_b64 and response.status_code == 200:
        response.headers['WWW-Authenticate'] = f'Negotiate {result.response_token_b64}'
    return response


def _carries_xml_signature(security_header):
    return security_header is not None and security_header.find(f'{{{DS_NS}}}Signature') is not None


def _presented_certificate(parsed):
    """``(cert, username, error)``: the certificate that signed the RST (XML-DSig) or the
    TLS client certificate, its key proven either way."""
    if _carries_xml_signature(parsed.security_header):
        cert, error = wstep_service.signed_request_certificate(parsed.security_header, parsed.csr_element)
        return cert, 'wstep-ws-security', error
    cert, error = wstep_service.tls_client_certificate(trusted_client_cert(logger, 'WSTEP'))
    return cert, 'wstep-client-cert', error


def _query_certificate(parsed):
    """``(cert, fault)`` of a QueryTokenStatus on the Certificate binding: the certificate
    that signed the RST (XML-DSig) or the TLS client certificate."""
    from services.wstep import ws_security
    if _carries_xml_signature(parsed.security_header):
        try:
            signing_der, _signed = ws_security.verify_signed_request(parsed.security_header)
            return x509.load_der_x509_certificate(signing_der), None
        except Exception as e:
            return None, _fault_response(f'Authentication failed: {e}', status=400,
                                         relates_to=parsed.message_id)
    cert, error = wstep_service.tls_client_certificate(trusted_client_cert(logger, 'WSTEP'))
    if error:
        return None, _fault_response('Authentication failed', status=400, relates_to=parsed.message_id)
    return cert, None


TLS_RENEWAL_REFUSED = ('Certificate renewal over TLS is served only for a profile whose issuing CA is the '
                       'mTLS trusted CA or under it; renew over the Kerberos binding')


def _query_token_status_by_certificate(parsed, cert):
    """QueryTokenStatus on the Certificate binding: the certificate names the requester,
    the request names its CA."""
    from services.wstep.approval import certificate_identity, held_ca, request_for
    from services import protocol_approval
    approval = request_for(parsed.request_id, None, certificate_identity(cert))
    ca = held_ca(protocol_approval.request_data(approval)) if approval is not None else None
    if ca is None:
        return _fault_response('Unknown RequestID', status=400, relates_to=parsed.message_id,
                               request_id=parsed.request_id, invalid_request=False)
    return _answer_held(ca, parsed, approval)


@bp.route(CES_CERTIFICATE_PATH, methods=['GET', 'POST', 'HEAD'])
def renew_certificate_bound():
    """WSTEP RST over the Certificate-authenticated CES endpoint — renewal,
    authenticated either by a WS-Security XML-DSig of the RST or, as Windows
    does, by the TLS client certificate that also signs the CMS request.
    Served by the profile recorded on the presented certificate, whatever the
    default profile's state, under that profile's issuing CA.

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

    body, err = _read_wstep_body()
    if err is not None:
        return err

    parsed, fault = _parse_request(body)
    if fault is not None:
        return fault

    if parsed.request_type == REQUEST_TYPE_QUERY_TOKEN_STATUS:
        cert, fault = _query_certificate(parsed)
        return fault if fault is not None else _query_token_status_by_certificate(parsed, cert)

    cert, username, error = _presented_certificate(parsed)
    if error:
        logger.warning("WSTEP renewal rejected: %s", error)
        return _fault_response(error, status=400, relates_to=parsed.message_id)

    from services.windows_profiles import presented_certificate_profile
    from utils.client_cert import native_tls_admits
    from services.windows_profiles import issuing_ca
    profile, error, served = presented_certificate_profile(cert)
    ca, status = None, None
    if error is None and profile is not None:
        ca = issuing_ca(profile)
        if ca is None:
            # A refusal of a stored certificate like any other: audited below with its profile
            error, status = f'The Windows enrollment profile {profile.name} has no issuing CA', 503
        # A5: the native listener anchors on the mTLS CA alone; a proxy terminating TLS answers for its own
        elif username == 'wstep-client-cert' and request.environ.get('peercert') and not native_tls_admits(ca):
            error = TLS_RENEWAL_REFUSED
    elif error is None:
        error = 'Signing certificate is not recognized'
    if error is None:
        from services.wstep.approval import make_gate
        signed = username == 'wstep-ws-security'
        gate = make_gate(ca, operation='renew', profile=profile,
                         extra={'require_pop': signed and not parsed.was_pkcs7_wrapped})
        try:
            if signed:
                cert_pem, error = wstep_service.renew(
                    ca, cert, parsed.csr_der, _validity_days(profile), require_pop=not parsed.was_pkcs7_wrapped,
                    outer_signed_data=parsed.outer_signed_data, gate=gate, profile=profile)
            else:
                # Windows authenticates here with its TLS client certificate, no XML-DSig
                cert_pem, error = wstep_service.renew_with_client_certificate(
                    ca, cert, parsed.csr_der, parsed.outer_signed_data, _validity_days(profile), gate=gate,
                    profile=profile)
        except wstep_service.HeldForApproval as held:
            return _answer_held(ca, parsed, held.approval)
    if error:
        logger.warning("WSTEP renewal rejected (%s): %s", served or 'not stored', error)
        # Audited only for a certificate stored here, its key proven: an anonymous refusal would fill the log
        if served:
            _audit_issuance('certificate.renewed', None, username, success=False, details=(
                f'WSTEP renewal refused from {client_ip()}: {error} '
                f'(old serial {cert.serial_number}, {served})'))
        if isinstance(error, wstep_service.SubjectHeldByAnother):
            from services.windows_profiles import audit_renewal_refusal
            audit_renewal_refusal('CES', cert.serial_number, profile, error)
        return _fault_response(error, status=status or _error_status(error), relates_to=parsed.message_id)

    try:
        new_cert = x509.load_pem_x509_certificate(cert_pem.encode())
        request_id = _request_id_for(new_cert)
        response_body = build_issue_response(
            new_cert, relates_to=parsed.message_id, request_id=request_id,
            cmc_response_der=_cmc_response_der_for(ca, new_cert, parsed),
        )
    except Exception as e:
        logger.error("WSTEP: failed to build RSTR: %s", e)
        return _fault_response('Internal server error', status=500, relates_to=parsed.message_id)

    _audit_issuance(
        'certificate.renewed', new_cert.subject.rfc4514_string(), username,
        resource_id=str(request_id) if request_id else None,
        details=(f'WSTEP renewal from {client_ip()}: old serial {cert.serial_number}, '
                 f'new serial {new_cert.serial_number} ({served})'),
    )
    return Response(response_body, status=200, content_type=f'{SOAP_XML_MIME}; charset=utf-8')
