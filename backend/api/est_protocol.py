"""
EST Protocol Implementation (RFC 7030)
Enrollment over Secure Transport for automated certificate enrollment.
"""
from flask import Blueprint, request, Response
from models import db, CA
from services.ca_service import CAService
from services.audit_service import AuditService
from utils.trusted_proxy import client_ip
from utils.db_transaction import safe_commit
from utils.est_cms import build_server_generated_key_cms
import base64
import hmac
import json
import logging
import re

from cryptography.hazmat.primitives import serialization as _crypto_serialization

logger = logging.getLogger(__name__)

bp = Blueprint('est', __name__, url_prefix='/.well-known/est')


def _labelled_route(rule, methods, endpoint):
    """Register an EST operation at both the default and labelled paths.

    RFC 7030 §3.2.2: ``/.well-known/est/<label>/<operation>`` selects a
    specific CA/policy, while ``/.well-known/est/<operation>`` keeps serving
    the default configured CA (unchanged behaviour for existing clients).
    """

    def decorator(view_func):
        bp.add_url_rule(
            rule,
            endpoint=endpoint,
            view_func=lambda **kw: view_func(label=None, **kw),
            methods=methods,
        )
        bp.add_url_rule(
            f'/<label>{rule}',
            endpoint=f'{endpoint}_labelled',
            view_func=view_func,
            methods=methods,
        )
        return view_func

    return decorator

# Hard upper bound on EST request bodies. A PKCS#10 CSR with a 4096-bit
# RSA key + EC SAN list rarely exceeds 4 KB; 64 KB is generous and
# still rules out resource exhaustion / accidental upload of a binary.
EST_MAX_BODY_BYTES = 64 * 1024


def _enforce_body_limit():
    """Return a 413 Response if the incoming request body exceeds
    EST_MAX_BODY_BYTES, else None. Called explicitly from each EST
    enrollment route — kept out of @before_request so /cacerts and
    /csrattrs (GET) are unaffected."""
    cl = request.content_length
    if cl is not None and cl > EST_MAX_BODY_BYTES:
        return Response('Request body too large', status=413)
    return None


def _read_est_body_text():
    """Read the EST request body as text, hard-capped at EST_MAX_BODY_BYTES.

    ``_enforce_body_limit`` only inspects Content-Length, which a chunked
    (Content-Length-less) request omits — so the cap must also be enforced at
    read time. Reads at most one byte past the cap from the request stream so a
    malicious unbounded/chunked body cannot be buffered into memory.

    Returns ``(text_or_None, error_response_or_None)``.
    """
    raw = request.stream.read(EST_MAX_BODY_BYTES + 1)
    if len(raw) > EST_MAX_BODY_BYTES:
        return None, Response('Request body too large', status=413)
    try:
        return raw.decode('utf-8'), None
    except UnicodeDecodeError:
        return None, Response('Invalid request body encoding', status=400)


@bp.before_request
def _enforce_est_enabled():
    """RFC 7030: when EST is administratively disabled, every endpoint
    under /.well-known/est MUST behave as if not configured. Returning
    503 also keeps clients from believing the service is silently
    available."""
    if not _est_enabled():
        return Response('EST disabled', status=503)


# Content types
PKCS7_MIME = 'application/pkcs7-mime'
PKCS7_CERTS_ONLY = f'{PKCS7_MIME}; smime-type=certs-only'
PKCS10_MIME = 'application/pkcs10'
MULTIPART_MIXED = 'multipart/mixed'

DECRYPT_KEY_IDENTIFIER_OID = '1.2.840.113549.1.9.16.2.37'
ASYMMETRIC_DECRYPT_KEY_IDENTIFIER_OID = '1.2.840.113549.1.9.16.2.54'


def _require_pkcs10_content_type():
    """Warn when the RFC 7030 PKCS#10 media type is missing, without
    refusing. Existing integrations post CSRs with curl's default
    Content-Type (or none at all); a 415 broke them on upgrade."""
    mimetype = (request.mimetype or '').lower()
    if mimetype != PKCS10_MIME:
        logger.warning(
            "EST request Content-Type is %r; RFC 7030 specifies "
            "application/pkcs10 (accepted for compatibility, deprecated)",
            mimetype or 'missing',
        )
    return None


def _decode_est_csr(csr_data):
    """Decode a PKCS#10 request: base64 DER per RFC 7030, with a PEM
    fallback for legacy clients that post the CSR as-is."""
    if isinstance(csr_data, bytes):
        csr_text = csr_data.decode('utf-8', errors='replace')
    else:
        csr_text = csr_data
    if '-----BEGIN' in csr_text:
        # PEM body: extract the base64 between the armor lines
        lines = [
            line.strip() for line in csr_text.splitlines()
            if line.strip() and not line.startswith('-----')
        ]
        logger.warning(
            "EST request posted a PEM CSR; RFC 7030 specifies base64 DER "
            "(accepted for compatibility, deprecated)"
        )
        return base64.b64decode(''.join(lines), validate=True)
    normalized = ''.join(csr_text.split())
    return base64.b64decode(normalized, validate=True)


def _certs_only_base64(cert):
    """Serialize exactly one issued certificate as a certs-only response."""
    from cryptography.hazmat.primitives.serialization import pkcs7
    der = pkcs7.serialize_certificates(
        [cert], encoding=_crypto_serialization.Encoding.DER
    )
    return base64.b64encode(der).decode('ascii')


def _certs_only_response(cert, ca=None):
    """RFC 7030 §4.2.3: the enroll response contains only the issued
    certificate. Legacy clients that built their TLS bundle from this
    response (without calling /cacerts) can opt back into receiving the CA
    chain with est_response_include_chain=true."""
    certs = [cert]
    if ca is not None:
        try:
            from models import SystemConfig
            row = SystemConfig.query.filter_by(
                key='est_response_include_chain'
            ).first()
            if row and str(row.value).lower() == 'true':
                from cryptography import x509 as _x509
                from services.ca_service import CAService
                for pem in CAService.get_certificate_chain(ca.refid) or []:
                    try:
                        chain_cert = _x509.load_pem_x509_certificate(
                            pem.encode() if isinstance(pem, str) else pem
                        )
                        if chain_cert.serial_number != cert.serial_number:
                            certs.append(chain_cert)
                    except Exception:
                        continue
        except Exception as exc:
            logger.warning("EST: failed to append CA chain to response: %s", exc)

    from cryptography.hazmat.primitives.serialization import pkcs7
    der = pkcs7.serialize_certificates(
        certs, encoding=_crypto_serialization.Encoding.DER
    )
    return Response(
        base64.b64encode(der).decode('ascii'),
        status=200,
        content_type=PKCS7_CERTS_ONLY,
        headers={'Content-Transfer-Encoding': 'base64'},
    )


def _subject_alt_name(cert_or_csr):
    from cryptography import x509
    try:
        return cert_or_csr.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
    except x509.ExtensionNotFound:
        return None


def _san_values(cert_or_csr):
    """SAN entries as a set of (type, value) pairs — order and the
    extension's critical flag are irrelevant to the identity match."""
    ext = _subject_alt_name(cert_or_csr)
    if ext is None:
        return None
    return {(type(name).__name__, str(getattr(name, 'value', name)))
            for name in ext.value}


def _reenroll_san_matches(client_cert_obj, csr):
    """RFC 7030 §4.2.2: re-enroll must keep the same identity. Compare SANs
    as sets (clients reorder entries and toggle criticality when regenerating
    CSRs); a CSR without SAN is accepted — pre-2.200 issued it as-is."""
    csr_sans = _san_values(csr)
    if csr_sans is None:
        return True
    cert_sans = _san_values(client_cert_obj) or set()
    return csr_sans == cert_sans


def _copy_csr_extensions(builder, csr):
    """Copy requested extensions while replacing the ignored CSR public key."""
    for extension in csr.extensions:
        builder = builder.add_extension(extension.value, extension.critical)
    return builder


def _server_keygen_identifiers(csr):
    identifiers = {}
    for attribute in csr.attributes:
        oid = attribute.oid.dotted_string
        if oid in (
            DECRYPT_KEY_IDENTIFIER_OID,
            ASYMMETRIC_DECRYPT_KEY_IDENTIFIER_OID,
        ):
            identifiers[oid] = attribute.value
    if identifiers:
        logger.info(
            'EST serverkeygen: parsed key identifier attribute(s): %s',
            ', '.join(sorted(identifiers)),
        )
    else:
        logger.info(
            'EST serverkeygen: no decrypt key identifier supplied; '
            'using authentication-derived key protection'
        )
    return identifiers


def _certificate_key_identifier(cert):
    from cryptography import x509
    try:
        return cert.extensions.get_extension_for_class(
            x509.SubjectKeyIdentifier
        ).value.digest
    except x509.ExtensionNotFound:
        return x509.SubjectKeyIdentifier.from_public_key(
            cert.public_key()
        ).digest


def _fallback_csrattrs_der():
    """Return a valid DER CsrAttrs when pyasn1 is unavailable."""
    # RFC 7030 §4.5 example shape: an OID plus an extensionRequest
    # Attribute whose SET contains the requested certificate extension OIDs.
    return bytes.fromhex(
        '3029'
        '06092a864886f70d010907'
        '301c06092a864886f70d01090e310f'
        '0603551d0f0603551d110603551d25'
    )


def _build_csrattrs_der():
    try:
        from pyasn1.type import univ
        from pyasn1.codec.der import encoder as der_encoder
    except ImportError:
        return _fallback_csrattrs_der()

    attrs = univ.SequenceOf(componentType=univ.Any())
    challenge_password = univ.ObjectIdentifier('1.2.840.113549.1.9.7')
    attrs.append(univ.Any(der_encoder.encode(challenge_password)))

    extension_request = univ.Sequence()
    extension_request.setComponentByPosition(
        0, univ.ObjectIdentifier('1.2.840.113549.1.9.14')
    )
    requested_extensions = univ.SetOf(componentType=univ.ObjectIdentifier())
    for oid in ('2.5.29.17', '2.5.29.15', '2.5.29.37'):
        requested_extensions.append(univ.ObjectIdentifier(oid))
    extension_request.setComponentByPosition(1, requested_extensions)
    attrs.append(univ.Any(der_encoder.encode(extension_request)))
    return der_encoder.encode(attrs)


def _est_enabled():
    """Return True iff EST protocol is enabled in SystemConfig."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key='est_enabled').first()
    return bool(row and (row.value or '').lower() == 'true')


_EST_LABELS_KEY = 'est_labels'
_LABEL_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')


def _est_label_map():
    """Return the configured {label: ca_refid} map, or {} when unset/invalid.

    RFC 7030 §3.2.2 lets a server distinguish CAs/policies with an arbitrary
    path label. Labels are **opt-in per deployment**: only CAs the operator
    explicitly lists here are reachable, so adding label support does not
    silently expose every CA in the system to EST enrollment.
    """
    from models import SystemConfig

    row = SystemConfig.query.filter_by(key=_EST_LABELS_KEY).first()
    if not row or not row.value:
        return {}
    try:
        parsed = json.loads(row.value)
    except (TypeError, ValueError) as e:
        logger.warning(f"Invalid {_EST_LABELS_KEY} configuration: {e}")
        return {}
    if not isinstance(parsed, dict):
        logger.warning(f"{_EST_LABELS_KEY} must be a JSON object")
        return {}
    return {
        label: refid for label, refid in parsed.items()
        if isinstance(label, str) and _LABEL_RE.match(label)
        and isinstance(refid, str) and refid
    }


def _get_est_ca(label=None):
    """Get the CA serving this EST request.

    With a label, resolve it through the configured label map; an unknown
    label yields None rather than falling back to the default CA, so a client
    can never be silently enrolled against a different authority than the one
    it addressed. Without a label, the single configured EST CA.
    """
    from models import SystemConfig

    if label is not None:
        ca_refid = _est_label_map().get(label)
        if not ca_refid:
            return None
        return CA.query.filter_by(refid=ca_refid).first()

    ca_refid = SystemConfig.query.filter_by(key='est_ca_refid').first()
    if not ca_refid:
        return None
    return CA.query.filter_by(refid=ca_refid.value).first()


def _resolve_est_ca(label=None):
    """Return ``(ca, error_response)`` for this request's CA.

    The two failure modes are distinct and must not be conflated: an unknown
    **label** is a wrong address (404 Not Found), whereas a missing default CA
    means the operator never configured EST (503, the historical response).

    Both used to return silently, so a client that reached this endpoint and
    was turned away left no trace — the same "did it even arrive" ambiguity
    SCEP had before its configuration-driven refusals were logged.
    """
    ca = _get_est_ca(label)
    if ca:
        return ca, None
    if label is not None:
        logger.warning("EST request refused: unknown label %r", label)
        return None, Response('Unknown EST label', status=404)
    logger.warning("EST request refused: EST not configured")
    return None, Response('EST not configured', status=503)


def _trusted_client_cert():
    """
    Return the PEM client certificate ONLY when it can be trusted.

    Sources:
      - request.environ['peercert'] (native gunicorn TLS) — always safe.
      - SSL_CLIENT_CERT / SSL_CLIENT_VERIFY (reverse proxy) — only when
        the immediate peer is a trusted proxy AND verify == 'SUCCESS'.

    Without this gate any attacker who can reach gunicorn directly (or
    poison the header through a mis-configured proxy) can forge an
    arbitrary client certificate and obtain a signed cert from the EST
    CA.
    """
    # Native TLS: gunicorn populates request.environ['peercert'] only after
    # validating the chain against the configured CA — safe to trust.
    if request.environ.get('peercert'):
        return request.environ['peercert']

    from utils.trusted_proxy import is_request_from_trusted_proxy
    if not is_request_from_trusted_proxy():
        # Untrusted peer is sending SSL_CLIENT_CERT — likely a spoof.
        if request.environ.get('SSL_CLIENT_CERT') or request.headers.get('X-SSL-Client-Cert'):
            logger.warning(
                "EST: ignoring SSL_CLIENT_CERT from untrusted peer %s",
                request.remote_addr,
            )
        return None

    verify = (
        request.environ.get('SSL_CLIENT_VERIFY')
        or request.headers.get('X-SSL-Client-Verify')
        or ''
    ).upper()
    if verify and verify != 'SUCCESS':
        logger.warning("EST: SSL_CLIENT_VERIFY=%s — refusing client cert", verify)
        return None

    return (
        request.environ.get('SSL_CLIENT_CERT')
        or request.headers.get('X-SSL-Client-Cert')
    )


def _authenticate_est_client():
    """
    Authenticate EST client via mTLS or HTTP Basic Auth.
    Returns (authenticated: bool, username: str or None)
    """
    # Check for client certificate (mTLS) — only trust when verified
    client_cert = _trusted_client_cert()
    if client_cert:
        # Client authenticated via mTLS
        return True, 'mtls-client'
    
    # Check HTTP Basic Auth
    auth = request.authorization
    if auth:
        # Verify against EST credentials in config
        from models import SystemConfig
        est_username = SystemConfig.query.filter_by(key='est_username').first()
        est_password = SystemConfig.query.filter_by(key='est_password').first()
        
        if est_username and est_password and est_username.value and est_password.value:
            from werkzeug.security import check_password_hash
            # auth.username/password may be None for malformed headers
            if auth.username is None or auth.password is None:
                return False, None
            username_match = hmac.compare_digest(auth.username, est_username.value)
            # Support both hashed and legacy plaintext passwords
            if est_password.value.startswith(('scrypt:', 'pbkdf2:')):
                password_match = check_password_hash(est_password.value, auth.password)
            else:
                password_match = hmac.compare_digest(auth.password, est_password.value)
            if username_match and password_match:
                return True, auth.username
    
    return False, None


def _validate_est_csr(csr):
    """Common EST CSR validation.

    Returns ``(ok, response_or_None)``. Enforces:
      * Proof of Possession — the CSR's self-signature MUST verify.
        Without this an attacker who stole a Basic-Auth credential could
        submit a CSR built around a public key they don't control and
        get a certificate that someone else owns.
      * Non-empty CommonName — refuse blank subjects so a compromised
        credential can't mint a wildcard / catch-all certificate by
        submitting an empty CSR.
    """
    try:
        if not csr.is_signature_valid:
            logger.warning(
                "EST: CSR self-signature invalid (subject=%s)",
                csr.subject.rfc4514_string(),
            )
            return False, Response(
                'CSR signature invalid (proof of possession failed)',
                status=400,
            )
    except Exception as e:
        logger.warning("EST: CSR self-signature check raised: %s", e)
        return False, Response('CSR signature invalid', status=400)

    from cryptography.x509.oid import NameOID
    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if not cn_attrs or not str(cn_attrs[0].value).strip():
        return False, Response('CSR subject must include a non-empty CN', status=400)

    # Key-strength policy — never certify a weak/exotic key (e.g. 512-bit RSA).
    from utils.key_type import validate_enrollment_public_key
    key_err = validate_enrollment_public_key(csr.public_key())
    if key_err:
        logger.warning("EST: rejecting weak enrollment key: %s", key_err)
        return False, Response(key_err, status=400)

    return True, None


@_labelled_route('/cacerts', methods=['GET'], endpoint='get_ca_certs')
def get_ca_certs(label=None):
    """
    EST /cacerts - Get CA certificate chain.
    Returns PKCS#7 degenerate certs-only message.
    """
    ca, ca_error = _resolve_est_ca(label)
    if ca_error:
        return ca_error
    
    try:
        # Build certificate chain
        chain = CAService.get_certificate_chain(ca.refid)
        
        # Create PKCS#7 certs-only
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs7
        from cryptography.hazmat.backends import default_backend
        
        certs = []
        for pem in chain:
            cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())
            certs.append(cert)
        
        # Serialize as PKCS#7 degenerate (certs-only)
        p7_der = pkcs7.serialize_certificates(certs, encoding=_crypto_serialization.Encoding.DER)
        p7_b64 = base64.b64encode(p7_der).decode()
        
        return Response(
            p7_b64,
            status=200,
            content_type=PKCS7_CERTS_ONLY,
            headers={
                'Content-Transfer-Encoding': 'base64'
            }
        )
    except Exception as e:
        logger.error(f"EST cacerts failed: {e}")
        return Response("Internal server error", status=500)


@_labelled_route('/simpleenroll', methods=['POST'], endpoint='simple_enroll')
def simple_enroll(label=None):
    """
    EST /simpleenroll - Enroll new certificate.
    Accepts PKCS#10 CSR, returns PKCS#7 certificate.
    """
    too_big = _enforce_body_limit()
    if too_big is not None:
        return too_big
    bad_content_type = _require_pkcs10_content_type()
    if bad_content_type is not None:
        return bad_content_type

    authenticated, username = _authenticate_est_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    ca, ca_error = _resolve_est_ca(label)
    if ca_error:
        return ca_error
    
    try:
        # Get CSR from request body (base64 encoded PKCS#10), capped read
        csr_data, err = _read_est_body_text()
        if err is not None:
            return err

        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        csr = x509.load_der_x509_csr(
            _decode_est_csr(csr_data), default_backend()
        )

        ok, deny = _validate_est_csr(csr)
        if not ok:
            return deny

        # Get validity from config
        from models import SystemConfig
        validity_days = SystemConfig.query.filter_by(key='est_validity_days').first()
        days = int(validity_days.value) if validity_days else 365
        
        # Sign the CSR
        cert_pem, serial = CAService.sign_csr_from_crypto(
            ca=ca,
            csr=csr,
            validity_days=days,
            source='est'
        )
        
        # Create audit log
        from models import AuditLog
        log = AuditLog(
            action='certificate.issued',
            resource_type='certificate',
            resource_name=csr.subject.rfc4514_string(),
            username=username,
            details=f'EST enrollment from {client_ip()}'
        )
        db.session.add(log)
        if not safe_commit(logger, "EST enrollment commit failed"):
            pass
        
        # RFC 7030 §4.2.3 requires only the newly issued certificate.
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        return _certs_only_response(cert, ca=ca)
        
    except Exception as e:
        logger.error(f"EST simpleenroll failed: {e}")
        return Response("Enrollment failed", status=400)


@_labelled_route('/simplereenroll', methods=['POST'], endpoint='simple_reenroll')
def simple_reenroll(label=None):
    """
    EST /simplereenroll - Renew existing certificate (RFC 7030 §3.3.2).
    Requires mTLS — client MUST present a valid certificate.
    Does NOT accept HTTP Basic Auth (unlike simpleenroll).
    """
    too_big = _enforce_body_limit()
    if too_big is not None:
        return too_big
    bad_content_type = _require_pkcs10_content_type()
    if bad_content_type is not None:
        return bad_content_type

    # Re-enrollment requires mTLS only (RFC 7030 §3.3.2)
    client_cert = _trusted_client_cert()
    if not client_cert:
        return Response(
            'Client certificate required for re-enrollment',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    ca, ca_error = _resolve_est_ca(label)
    if ca_error:
        return ca_error
    
    # Process enrollment directly (not delegating to simple_enroll which allows Basic auth)
    try:
        csr_data, err = _read_est_body_text()
        if err is not None:
            return err

        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        csr = x509.load_der_x509_csr(
            _decode_est_csr(csr_data), default_backend()
        )

        ok, deny = _validate_est_csr(csr)
        if not ok:
            return deny

        # Verify client cert subject matches CSR subject (RFC 7030 §3.3.2)
        try:
            client_cert_obj = x509.load_pem_x509_certificate(
                client_cert.encode() if isinstance(client_cert, str) else client_cert,
                default_backend()
            )
            if client_cert_obj.subject != csr.subject:
                logger.warning(f"EST reenroll: client cert subject {client_cert_obj.subject} does not match CSR subject {csr.subject}")
                return Response('CSR subject does not match client certificate', status=403)
            if not _reenroll_san_matches(client_cert_obj, csr):
                logger.warning(
                    'EST reenroll: CSR SubjectAltName differs from client certificate'
                )
                return Response(
                    'CSR SubjectAltName does not match client certificate',
                    status=403,
                )
        except Exception as e:
            logger.error(f"EST reenroll: failed to parse client cert: {e}")
            return Response('Invalid client certificate', status=400)
        
        from models import SystemConfig
        validity_days = SystemConfig.query.filter_by(key='est_validity_days').first()
        days = int(validity_days.value) if validity_days else 365
        
        cert_pem, serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=days, source='est',
            renewal_of=client_cert_obj,
        )

        from models import AuditLog
        log = AuditLog(
            action='certificate.renewed',
            resource_type='certificate',
            resource_name=csr.subject.rfc4514_string(),
            username='mtls-client',
            details=f'EST re-enrollment via mTLS from {client_ip()}'
        )
        db.session.add(log)
        if not safe_commit(logger, "EST re-enrollment commit failed"):
            pass
        
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        return _certs_only_response(cert, ca=ca)
        
    except Exception as e:
        logger.error(f"EST simplereenroll failed: {e}")
        return Response("Re-enrollment failed", status=400)


@_labelled_route('/csrattrs', methods=['GET'], endpoint='get_csr_attrs')
def get_csr_attrs(label=None):
    """
    EST /csrattrs - Get CSR attributes (RFC 7030 §4.5.2).
    Returns suggested/required CSR attributes for enrollment as a
    DER-encoded CsrAttrs sequence, base64-encoded.
    """
    # RFC 7030 §4.5 recommends serving CSR attributes without requiring
    # client authentication.
    # Build ASN.1 DER-encoded CsrAttrs per RFC 7030 §4.5.2
    # CsrAttrs ::= SEQUENCE SIZE (1..MAX) OF AttrOrOID
    # AttrOrOID ::= CHOICE { oid OBJECT IDENTIFIER, attribute Attribute }
    #
    # Request challengePassword as an OID and descriptive certificate
    # extensions as values of an extensionRequest Attribute.
    der_bytes = _build_csrattrs_der()
    b64_content = base64.b64encode(der_bytes).decode('ascii')
    return Response(
        b64_content,
        status=200,
        mimetype='application/csrattrs',
        headers={'Content-Transfer-Encoding': 'base64'}
    )


@_labelled_route('/serverkeygen', methods=['POST'], endpoint='server_keygen')
def server_keygen(label=None):
    """
    EST /serverkeygen - Server-side key generation (RFC 7030 §3.4).
    Generates key pair and certificate on server. Basic-authenticated
    clients receive password-encrypted PKCS#8; mTLS clients receive CMS
    SignedData protected by KeyTransRecipientInfo EnvelopedData.
    """
    # Defensive: cap body size before parsing. RSA keygen is the most
    # CPU-intensive EST endpoint, so reject obviously-bogus payloads
    # early to limit the damage from a leaked Basic-Auth credential.
    too_big = _enforce_body_limit()
    if too_big is not None:
        return too_big
    bad_content_type = _require_pkcs10_content_type()
    if bad_content_type is not None:
        return bad_content_type

    authenticated, username = _authenticate_est_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )

    ca, ca_error = _resolve_est_ca(label)
    if ca_error:
        return ca_error

    # Capture remote IP for audit BEFORE any failure path so denials
    # are visible too.
    remote_ip = client_ip()
    auth_method = 'mtls' if _trusted_client_cert() else 'basic'

    try:
        csr_data, err = _read_est_body_text()
        if err is not None:
            return err
        if not csr_data:
            return Response('Invalid CSR', status=400)
        
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, BestAvailableEncryption
        )
        
        # RFC 7030 §4.4.1 requires the request public key and signature to be
        # ignored. Only the requested subject, attributes, and extensions are
        # consumed before a fresh key pair is generated below.
        csr = x509.load_der_x509_csr(
            _decode_est_csr(csr_data), default_backend()
        )
        key_identifiers = _server_keygen_identifiers(csr)
        mtls_cert_obj = None
        if auth_method == 'mtls':
            client_cert_pem = _trusted_client_cert()
            try:
                mtls_cert_obj = x509.load_pem_x509_certificate(
                    client_cert_pem.encode()
                    if isinstance(client_cert_pem, str)
                    else client_cert_pem,
                    default_backend(),
                )
            except Exception as e:
                logger.error(f"EST serverkeygen: bad client mTLS cert: {e}")
                return Response('Invalid client mTLS certificate', status=400)

            symmetric_id = key_identifiers.get(DECRYPT_KEY_IDENTIFIER_OID)
            if symmetric_id is not None:
                logger.warning(
                    'EST serverkeygen: symmetric DecryptKeyIdentifier is unsupported'
                )
                return Response('Requested symmetric key is unavailable', status=400)
            asymmetric_id = key_identifiers.get(
                ASYMMETRIC_DECRYPT_KEY_IDENTIFIER_OID
            )
            if (
                asymmetric_id is not None
                and not hmac.compare_digest(
                    asymmetric_id, _certificate_key_identifier(mtls_cert_obj)
                )
            ):
                logger.warning(
                    'EST serverkeygen: AsymmetricDecryptKeyIdentifier does not '
                    'match the authenticated client certificate'
                )
                return Response('Requested asymmetric key is unavailable', status=400)
            if not isinstance(mtls_cert_obj.public_key(), rsa.RSAPublicKey):
                return Response('Unsupported client key transport', status=400)

        # RFC 7030 implies the subject in the CSR identifies the
        # enrollee. We refuse empty / whitespace-only CNs so a
        # compromised credential can't mint a wildcard or CA-shaped
        # certificate by submitting a blank CSR.
        from cryptography.x509.oid import NameOID
        cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not cn_attrs or not str(cn_attrs[0].value).strip():
            AuditService.log_action(
                action='est_serverkeygen_denied',
                resource_type='est',
                details=(
                    f'EST /serverkeygen rejected empty subject CN '
                    f'(auth={auth_method}, user={username}, ip={remote_ip})'
                ),
                success=False,
            )
            return Response('CSR subject must include a non-empty CN', status=400)
        subject_cn = str(cn_attrs[0].value).strip()

        # Audit BEFORE issuing — keeps a record even if signing fails
        # mid-flight or the response is dropped on the wire.
        AuditService.log_action(
            action='est_serverkeygen_request',
            resource_type='est',
            resource_name=subject_cn,
            details=(
                f'EST /serverkeygen subject_cn={subject_cn} '
                f'auth={auth_method} user={username} ip={remote_ip}'
            ),
            success=True,
        )
        
        # Generate new key pair
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Create a new CSR with the server-generated key while retaining the
        # subject and requested extensions (including SubjectAltName).
        new_csr_builder = x509.CertificateSigningRequestBuilder().subject_name(
            csr.subject
        )
        new_csr_builder = _copy_csr_extensions(new_csr_builder, csr)
        new_csr = new_csr_builder.sign(key, hashes.SHA256(), default_backend())
        
        from models import SystemConfig
        validity_days = SystemConfig.query.filter_by(key='est_validity_days').first()
        days = int(validity_days.value) if validity_days else 365
        
        cert_pem, serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=new_csr, validity_days=days, source='est'
        )
        
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        
        # The certificate part exactly matches /simpleenroll: one certificate.
        p7_b64 = _certs_only_base64(cert)

        if auth_method == 'basic':
            # RFC 7030 §4.4.2 permits password-encrypted PKCS#8 for clients
            # authenticated with HTTP Basic credentials.
            auth = request.authorization
            key_der = key.private_bytes(
                encoding=Encoding.DER,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=BestAvailableEncryption(auth.password.encode())
            )
            key_content_type = 'application/pkcs8'
        else:
            try:
                key_der = build_server_generated_key_cms(
                    key, cert, mtls_cert_obj
                )
            except ValueError as e:
                logger.warning(f"EST serverkeygen: unsupported key transport: {e}")
                return Response('Unsupported client key transport', status=400)
            except Exception as e:
                logger.error(f"EST serverkeygen: failed to wrap private key: {e}")
                return Response(
                    'Server key generation failed: unable to encrypt private key',
                    status=500,
                )
            key_content_type = (
                'application/pkcs7-mime; smime-type=server-generated-key'
            )
        key_b64 = base64.b64encode(key_der).decode('ascii')
        
        # Create multipart response
        boundary = 'est-boundary-' + str(serial)[:8]
        body = f"""--{boundary}\r
Content-Type: {PKCS7_CERTS_ONLY}\r
Content-Transfer-Encoding: base64\r
\r
{p7_b64}\r
--{boundary}\r
Content-Type: {key_content_type}\r
Content-Transfer-Encoding: base64\r
\r
{key_b64}\r
--{boundary}--\r
"""
        
        return Response(
            body,
            status=200,
            content_type=f'{MULTIPART_MIXED}; boundary={boundary}'
        )
        
    except Exception as e:
        logger.error(f"EST serverkeygen failed: {e}")
        return Response("Server key generation failed", status=400)
