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
        return Response(str(e), status=500)


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
        return Response(str(e), status=400)


@bp.route('/simplereenroll', methods=['POST'])
def simple_reenroll():
    """
    EST /simplereenroll - Renew existing certificate.
    Same as simpleenroll but requires valid client certificate.
    """
    # Re-enrollment requires mTLS (client must present valid cert)
    client_cert = request.environ.get('SSL_CLIENT_CERT')
    if not client_cert:
        return Response(
            'Client certificate required for re-enrollment',
            status=401,
            headers={'WWW-Authenticate': 'Basic realm="EST"'}
        )
    
    # Validate client cert is not expired and issued by our CA
    ca = _get_est_ca()
    if not ca:
        return Response('EST not configured', status=503)
    
    # Process same as simpleenroll
    return simple_enroll()


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
    EST /serverkeygen - Server-side key generation.
    Generates key pair and certificate on server.
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
        # Get subject from request
        csr_data = request.get_data(as_text=True)
        
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption, pkcs7
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
        
        # Get validity
        from models import SystemConfig
        validity_days = SystemConfig.query.filter_by(key='est_validity_days').first()
        days = int(validity_days.value) if validity_days else 365
        
        # Sign
        cert_pem, serial = CAService.sign_csr_from_crypto(
            ca=ca,
            csr=new_csr,
            validity_days=days,
            source='est'
        )
        
        # Return multipart with cert and private key
        cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
        
        # PKCS#7 certificate
        p7_der = pkcs7.serialize_certificates([cert], encoding=pkcs7.PKCS7Options.Binary)
        p7_b64 = base64.b64encode(p7_der).decode()
        
        # Private key in PKCS#8 format
        key_der = key.private_bytes(
            encoding=Encoding.DER,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        )
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
        return Response(str(e), status=400)
