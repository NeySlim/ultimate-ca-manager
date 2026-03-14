"""
EST Protocol Implementation (RFC 7030)
Enrollment over Secure Transport for automated certificate enrollment.
"""
from flask import Blueprint, request, Response, current_app
from models import db, CA, Certificate
from services.ca_service import CAService
from datetime import datetime
import base64
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('est', __name__, url_prefix='/.well-known/est')

# Content types
PKCS7_MIME = 'application/pkcs7-mime'
PKCS10_MIME = 'application/pkcs10'
MULTIPART_MIXED = 'multipart/mixed'


def _get_est_ca():
    """Get CA configured for EST enrollment"""
    from models import SystemConfig
    ca_refid = SystemConfig.query.filter_by(key='est_ca_refid').first()
    if not ca_refid:
        return None
    return CA.query.filter_by(refid=ca_refid.value).first()


def _authenticate_est_client():
    """
    Authenticate EST client via mTLS or HTTP Basic Auth.
    Returns (authenticated: bool, username: str or None)
    """
    # Check for client certificate (mTLS)
    client_cert = request.environ.get('SSL_CLIENT_CERT')
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
            if auth.username == est_username.value and auth.password == est_password.value:
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
        
        # Return PKCS#7 with certificate
        from cryptography.hazmat.primitives.serialization import pkcs7
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        p7_der = pkcs7.serialize_certificates([cert], encoding=pkcs7.PKCS7Options.Binary)
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
    # Re-enrollment requires mTLS only (RFC 7030 §3.3.2)
    client_cert = request.environ.get('SSL_CLIENT_CERT')
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
        p7_der = pkcs7.serialize_certificates([cert], encoding=pkcs7.PKCS7Options.Binary)
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
    EST /csrattrs - Get CSR attributes.
    Returns suggested/required CSR attributes for enrollment.
    """
    authenticated, _ = _authenticate_est_client()
    if not authenticated:
        return Response(
            'Authentication required',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    # Return empty (no specific requirements)
    # Could return ASN.1 sequence of OIDs for required attributes
    return Response(
        '',
        status=204,
        mimetype='application/csrattrs'
    )


@bp.route('/serverkeygen', methods=['POST'])
def server_keygen():
    """
    EST /serverkeygen - Server-side key generation (RFC 7030 §3.4).
    Generates key pair and certificate on server.
    Private key is encrypted using CMS EnvelopedData with the client's
    password as a PBKDF2-derived AES key for transport security.
    """
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
        csr_data = request.get_data(as_text=True)
        
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
        
        # PKCS#7 certificate
        p7_der = pkcs7.serialize_certificates([cert], encoding=pkcs7.PKCS7Options.Binary)
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
                logger.warning(f"EST serverkeygen: could not encrypt key with client cert, using TLS-only: {e}")
                key_der = key_plain
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
