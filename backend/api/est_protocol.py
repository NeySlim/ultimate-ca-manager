"""
EST Protocol Implementation (RFC 7030)
Enrollment over Secure Transport for automated certificate enrollment.
"""
from flask import Blueprint, request, Response, current_app
from models import db, CA, Certificate
from services.ca_service import CAService
from services.audit_service import AuditService
from datetime import datetime
import base64
import hmac
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('est', __name__, url_prefix='/.well-known/est')

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
PKCS10_MIME = 'application/pkcs10'
MULTIPART_MIXED = 'multipart/mixed'


def _est_enabled():
    """Return True iff EST protocol is enabled in SystemConfig."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key='est_enabled').first()
    return bool(row and (row.value or '').lower() == 'true')


def _get_est_ca():
    """Get CA configured for EST enrollment"""
    from models import SystemConfig
    ca_refid = SystemConfig.query.filter_by(key='est_ca_refid').first()
    if not ca_refid:
        return None
    return CA.query.filter_by(refid=ca_refid.value).first()


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
        
        if est_username and est_password:
            from werkzeug.security import check_password_hash
            username_match = hmac.compare_digest(auth.username, est_username.value)
            # Support both hashed and legacy plaintext passwords
            if est_password.value.startswith(('scrypt:', 'pbkdf2:')):
                password_match = check_password_hash(est_password.value, auth.password)
            else:
                password_match = hmac.compare_digest(auth.password, est_password.value)
            if username_match and password_match:
                return True, auth.username
    
    return False, None


@bp.route('/cacerts', methods=['GET'])
def get_ca_certs():
    """
    EST /cacerts - Get CA certificate chain.
    Returns PKCS#7 degenerate certs-only message.
    """
    ca = _get_est_ca()
    if not ca:
        return Response('EST not configured', status=503)
    
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
        p7_der = pkcs7.serialize_certificates(certs, encoding=pkcs7.PKCS7Options.Binary)
        p7_b64 = base64.b64encode(p7_der).decode()
        
        return Response(
            p7_b64,
            status=200,
            mimetype=PKCS7_MIME,
            headers={
                'Content-Transfer-Encoding': 'base64'
            }
        )
    except Exception as e:
        logger.error(f"EST cacerts failed: {e}")
        return Response("Internal server error", status=500)


@bp.route('/simpleenroll', methods=['POST'])
def simple_enroll():
    """
    EST /simpleenroll - Enroll new certificate.
    Accepts PKCS#10 CSR, returns PKCS#7 certificate.
    """
    too_big = _enforce_body_limit()
    if too_big is not None:
        return too_big

    authenticated, username = _authenticate_est_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    ca = _get_est_ca()
    if not ca:
        return Response('EST not configured', status=503)
    
    try:
        # Get CSR from request body (base64 encoded PKCS#10)
        content_type = request.content_type or ''
        csr_data = request.get_data(as_text=True)
        
        if PKCS10_MIME in content_type:
            # Decode base64 CSR
            csr_der = base64.b64decode(csr_data)
            
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            csr = x509.load_der_x509_csr(csr_der, default_backend())
        else:
            # Try PEM format
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            csr = x509.load_pem_x509_csr(csr_data.encode(), default_backend())
        
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
            details=f'EST enrollment from {request.remote_addr}'
        )
        db.session.add(log)
        db.session.commit()
        
        # Return PKCS#7 with certificate + CA chain (RFC 7030 §4.2.3)
        from cryptography.hazmat.primitives.serialization import pkcs7
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        certs_for_p7 = [cert]
        
        # Include issuing CA chain
        chain = CAService.get_certificate_chain(ca.refid)
        for chain_pem in chain:
            chain_cert = x509.load_pem_x509_certificate(chain_pem.encode(), default_backend())
            certs_for_p7.append(chain_cert)
        
        p7_der = pkcs7.serialize_certificates(certs_for_p7, encoding=pkcs7.PKCS7Options.Binary)
        p7_b64 = base64.b64encode(p7_der).decode()
        
        return Response(
            p7_b64,
            status=200,
            mimetype=PKCS7_MIME,
            headers={
                'Content-Transfer-Encoding': 'base64'
            }
        )
        
    except Exception as e:
        logger.error(f"EST simpleenroll failed: {e}")
        return Response("Enrollment failed", status=400)


@bp.route('/simplereenroll', methods=['POST'])
def simple_reenroll():
    """
    EST /simplereenroll - Renew existing certificate (RFC 7030 §3.3.2).
    Requires mTLS — client MUST present a valid certificate.
    Does NOT accept HTTP Basic Auth (unlike simpleenroll).
    """
    too_big = _enforce_body_limit()
    if too_big is not None:
        return too_big

    # Re-enrollment requires mTLS only (RFC 7030 §3.3.2)
    client_cert = _trusted_client_cert()
    if not client_cert:
        return Response(
            'Client certificate required for re-enrollment',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    ca = _get_est_ca()
    if not ca:
        return Response('EST not configured', status=503)
    
    # Process enrollment directly (not delegating to simple_enroll which allows Basic auth)
    try:
        content_type = request.content_type or ''
        csr_data = request.get_data(as_text=True)
        
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        
        if PKCS10_MIME in content_type:
            csr_der = base64.b64decode(csr_data)
            csr = x509.load_der_x509_csr(csr_der, default_backend())
        else:
            csr = x509.load_pem_x509_csr(csr_data.encode(), default_backend())
        
        # Verify client cert subject matches CSR subject (RFC 7030 §3.3.2)
        try:
            client_cert_obj = x509.load_pem_x509_certificate(
                client_cert.encode() if isinstance(client_cert, str) else client_cert,
                default_backend()
            )
            if client_cert_obj.subject != csr.subject:
                logger.warning(f"EST reenroll: client cert subject {client_cert_obj.subject} does not match CSR subject {csr.subject}")
                return Response('CSR subject does not match client certificate', status=403)
        except Exception as e:
            logger.error(f"EST reenroll: failed to parse client cert: {e}")
            return Response('Invalid client certificate', status=400)
        
        from models import SystemConfig
        validity_days = SystemConfig.query.filter_by(key='est_validity_days').first()
        days = int(validity_days.value) if validity_days else 365
        
        cert_pem, serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=csr, validity_days=days, source='est'
        )
        
        from models import AuditLog
        log = AuditLog(
            action='certificate.renewed',
            resource_type='certificate',
            resource_name=csr.subject.rfc4514_string(),
            username='mtls-client',
            details=f'EST re-enrollment via mTLS from {request.remote_addr}'
        )
        db.session.add(log)
        db.session.commit()
        
        from cryptography.hazmat.primitives.serialization import pkcs7
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        certs_for_p7 = [cert]
        
        # Include issuing CA chain (RFC 7030 §4.2.3)
        chain = CAService.get_certificate_chain(ca.refid)
        for chain_pem in chain:
            chain_cert = x509.load_pem_x509_certificate(chain_pem.encode(), default_backend())
            certs_for_p7.append(chain_cert)
        
        p7_der = pkcs7.serialize_certificates(certs_for_p7, encoding=pkcs7.PKCS7Options.Binary)
        p7_b64 = base64.b64encode(p7_der).decode()
        
        return Response(
            p7_b64, status=200, mimetype=PKCS7_MIME,
            headers={'Content-Transfer-Encoding': 'base64'}
        )
        
    except Exception as e:
        logger.error(f"EST simplereenroll failed: {e}")
        return Response("Re-enrollment failed", status=400)


@bp.route('/csrattrs', methods=['GET'])
def get_csr_attrs():
    """
    EST /csrattrs - Get CSR attributes (RFC 7030 §4.5.2).
    Returns suggested/required CSR attributes for enrollment as
    ASN.1 DER-encoded SEQUENCE of OIDs, base64-encoded.
    """
    authenticated, _ = _authenticate_est_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    # Build ASN.1 DER-encoded CsrAttrs per RFC 7030 §4.5.2
    # CsrAttrs ::= SEQUENCE SIZE (1..MAX) OF AttrOrOID
    # AttrOrOID ::= CHOICE { oid OBJECT IDENTIFIER, attribute Attribute }
    #
    # We return commonly requested OIDs:
    #   - subjectAltName (2.5.29.17)
    #   - keyUsage (2.5.29.15)
    #   - extendedKeyUsage (2.5.29.37)
    #   - challengePassword (1.2.840.113549.1.9.7)
    try:
        from pyasn1.type import univ, tag
        from pyasn1.codec.der import encoder as der_encoder
        
        oids = [
            univ.ObjectIdentifier((2, 5, 29, 17)),   # subjectAltName
            univ.ObjectIdentifier((2, 5, 29, 15)),   # keyUsage
            univ.ObjectIdentifier((2, 5, 29, 37)),   # extendedKeyUsage
            univ.ObjectIdentifier((1, 2, 840, 113549, 1, 9, 7)),  # challengePassword
        ]
        
        seq = univ.Sequence()
        for i, oid in enumerate(oids):
            seq.setComponentByPosition(i, oid)
        
        der_bytes = der_encoder.encode(seq)
        b64_content = base64.b64encode(der_bytes).decode('ascii')
        
        return Response(
            b64_content,
            status=200,
            mimetype='application/csrattrs',
            headers={'Content-Transfer-Encoding': 'base64'}
        )
    except ImportError:
        # pyasn1 not available — return hardcoded DER
        # SEQUENCE { OID 2.5.29.17, OID 2.5.29.15, OID 2.5.29.37 }
        der_hex = '300e0603551d110603551d0f0603551d25'
        der_bytes = bytes.fromhex(der_hex)
        b64_content = base64.b64encode(der_bytes).decode('ascii')
        
        return Response(
            b64_content,
            status=200,
            mimetype='application/csrattrs',
            headers={'Content-Transfer-Encoding': 'base64'}
        )


@bp.route('/serverkeygen', methods=['POST'])
def server_keygen():
    """
    EST /serverkeygen - Server-side key generation (RFC 7030 §3.4).
    Generates key pair and certificate on server.
    Private key is encrypted using CMS EnvelopedData with the client's
    password as a PBKDF2-derived AES key for transport security.
    """
    # Defensive: cap body size before parsing. RSA keygen is the most
    # CPU-intensive EST endpoint, so reject obviously-bogus payloads
    # early to limit the damage from a leaked Basic-Auth credential.
    too_big = _enforce_body_limit()
    if too_big is not None:
        return too_big

    authenticated, username = _authenticate_est_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )

    ca = _get_est_ca()
    if not ca:
        return Response('EST not configured', status=503)

    # Capture remote IP for audit BEFORE any failure path so denials
    # are visible too.
    remote_ip = request.remote_addr or 'unknown'
    auth_method = 'mtls' if _trusted_client_cert() else 'basic'

    try:
        csr_data = request.get_data(as_text=True)
        if not csr_data or len(csr_data) > EST_MAX_BODY_BYTES:
            return Response('Invalid CSR', status=400)
        
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption, BestAvailableEncryption, pkcs7
        )
        
        # Parse CSR to get subject
        csr_der = base64.b64decode(csr_data)
        csr = x509.load_der_x509_csr(csr_der, default_backend())

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
        
        # Create new CSR with server-generated key
        new_csr = x509.CertificateSigningRequestBuilder().subject_name(
            csr.subject
        ).sign(key, hashes.SHA256(), default_backend())
        
        from models import SystemConfig
        validity_days = SystemConfig.query.filter_by(key='est_validity_days').first()
        days = int(validity_days.value) if validity_days else 365
        
        cert_pem, serial = CAService.sign_csr_from_crypto(
            ca=ca, csr=new_csr, validity_days=days, source='est'
        )
        
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        
        # PKCS#7 certificate + CA chain (RFC 7030 §4.2.3)
        certs_for_p7 = [cert]
        chain = CAService.get_certificate_chain(ca.refid)
        for chain_pem in chain:
            chain_cert = x509.load_pem_x509_certificate(chain_pem.encode(), default_backend())
            certs_for_p7.append(chain_cert)
        
        p7_der = pkcs7.serialize_certificates(certs_for_p7, encoding=pkcs7.PKCS7Options.Binary)
        p7_b64 = base64.b64encode(p7_der).decode()
        
        # Private key — encrypt with password if Basic Auth was used (RFC 7030 §4.4.2)
        auth = request.authorization
        if auth and auth.password:
            key_der = key.private_bytes(
                encoding=Encoding.DER,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=BestAvailableEncryption(auth.password.encode())
            )
        else:
            # mTLS client — encrypt with newly issued certificate's public key
            # RFC 7030 §4.4.2: use CMS EnvelopedData or asymmetric encryption
            from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
            key_plain = key.private_bytes(
                encoding=Encoding.DER,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=NoEncryption()
            )
            try:
                # Encrypt private key with the client's new certificate public key
                client_pub = cert.public_key()
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                import secrets as sec_mod
                # AES-256-CBC wrap: encrypt key material, then encrypt AES key with RSA
                aes_key = sec_mod.token_bytes(32)
                aes_iv = sec_mod.token_bytes(16)
                aes_cipher = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv))
                encryptor = aes_cipher.encryptor()
                # PKCS#7 pad
                pad_len = 16 - (len(key_plain) % 16)
                padded = key_plain + bytes([pad_len] * pad_len)
                encrypted_key_data = encryptor.update(padded) + encryptor.finalize()
                # Encrypt AES key with RSA-OAEP
                encrypted_aes_key = client_pub.encrypt(
                    aes_key,
                    asym_padding.OAEP(
                        mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                # Combine: IV + encrypted AES key length (2 bytes) + encrypted AES key + encrypted data
                enc_key_len = len(encrypted_aes_key).to_bytes(2, 'big')
                key_der = aes_iv + enc_key_len + encrypted_aes_key + encrypted_key_data
                logger.info("EST serverkeygen: private key encrypted with client public key")
            except Exception as e:
                logger.error(f"EST serverkeygen: failed to encrypt private key: {e}")
                return Response('Server key generation failed: unable to encrypt private key', status=500)
        key_b64 = base64.b64encode(key_der).decode()
        
        # Create multipart response
        boundary = 'est-boundary-' + serial[:8]
        body = f"""--{boundary}\r
Content-Type: application/pkcs8\r
Content-Transfer-Encoding: base64\r
\r
{key_b64}\r
--{boundary}\r
Content-Type: application/pkcs7-mime; smime-type=certs-only\r
Content-Transfer-Encoding: base64\r
\r
{p7_b64}\r
--{boundary}--\r
"""
        
        return Response(
            body,
            status=200,
            mimetype=f'{MULTIPART_MIXED}; boundary={boundary}'
        )
        
    except Exception as e:
        logger.error(f"EST serverkeygen failed: {e}")
        return Response("Server key generation failed", status=400)
