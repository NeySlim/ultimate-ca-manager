"""
Certificate Import Service - Unified parsing for CA and Certificate imports
"""
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import re


def parse_certificate_file(file_data, filename, password=None, import_key=True):
    """
    Parse certificate from various formats.
    Returns: (cert, private_key, format_detected)
    Raises: ValueError on parse error
    """
    cert = None
    private_key = None
    format_type = 'auto'
    
    # Auto-detect format
    if b'-----BEGIN' in file_data:
        format_type = 'pem'
    elif filename.endswith('.p12') or filename.endswith('.pfx'):
        format_type = 'pkcs12'
    elif filename.endswith('.p7b') or filename.endswith('.p7c'):
        format_type = 'pkcs7'
    else:
        format_type = 'der'
    
    if format_type == 'pem':
        # Extract just the PEM block if there's extra text
        pem_match = re.search(b'-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----', file_data, re.DOTALL)
        if pem_match:
            pem_data = pem_match.group(0)
        else:
            pem_data = file_data
        
        # Check if it's a PKCS7 PEM
        if b'-----BEGIN PKCS7-----' in file_data:
            try:
                from cryptography.hazmat.primitives.serialization import pkcs7
                certs = pkcs7.load_pem_pkcs7_certificates(file_data)
                if certs:
                    cert = certs[0]
            except:
                pass
        
        if not cert:
            cert = x509.load_pem_x509_certificate(pem_data, default_backend())
        
        # Try to extract private key
        if import_key and b'PRIVATE KEY' in file_data:
            key_match = re.search(b'-----BEGIN.*?PRIVATE KEY-----.+?-----END.*?PRIVATE KEY-----', file_data, re.DOTALL)
            if key_match:
                try:
                    private_key = serialization.load_pem_private_key(
                        key_match.group(0), 
                        password=password.encode() if password else None, 
                        backend=default_backend()
                    )
                except:
                    pass
                
    elif format_type == 'der':
        try:
            cert = x509.load_der_x509_certificate(file_data, default_backend())
        except Exception as der_err:
            # Maybe it's a PKCS7 DER
            try:
                from cryptography.hazmat.primitives.serialization import pkcs7
                certs = pkcs7.load_der_pkcs7_certificates(file_data)
                if certs:
                    cert = certs[0]
            except:
                raise der_err
        
    elif format_type == 'pkcs12':
        from cryptography.hazmat.primitives.serialization import pkcs12
        try:
            private_key, cert, chain = pkcs12.load_key_and_certificates(
                file_data, password.encode() if password else None, default_backend()
            )
        except Exception as e:
            if 'password' in str(e).lower() or 'mac' in str(e).lower():
                raise ValueError('Invalid password for PKCS12 file')
            raise
    
    elif format_type == 'pkcs7':
        from cryptography.hazmat.primitives.serialization import pkcs7
        try:
            certs = pkcs7.load_der_pkcs7_certificates(file_data)
        except:
            certs = pkcs7.load_pem_pkcs7_certificates(file_data)
        if certs:
            cert = certs[0]
    
    if not cert:
        raise ValueError('Could not parse certificate. Supported formats: PEM, DER, PKCS12 (.p12, .pfx), PKCS7 (.p7b)')
    
    return cert, private_key, format_type


def is_ca_certificate(cert):
    """Check if certificate has CA:TRUE basic constraint"""
    try:
        basic_constraints = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
        return basic_constraints.value.ca
    except x509.extensions.ExtensionNotFound:
        return False


def extract_cert_info(cert):
    """Extract common certificate information"""
    from cryptography.x509.oid import NameOID
    
    subject = cert.subject
    issuer = cert.issuer
    
    def get_name_attr(name_obj, oid):
        try:
            return name_obj.get_attributes_for_oid(oid)[0].value
        except:
            return ''
    
    # Get serial number as hex string for comparison
    serial_hex = format(cert.serial_number, 'x').upper()
    
    return {
        'cn': get_name_attr(subject, NameOID.COMMON_NAME),
        'org': get_name_attr(subject, NameOID.ORGANIZATION_NAME),
        'country': get_name_attr(subject, NameOID.COUNTRY_NAME),
        'subject': subject.rfc4514_string(),
        'issuer': issuer.rfc4514_string(),
        'is_self_signed': cert.subject == cert.issuer,
        'valid_from': cert.not_valid_before_utc,
        'valid_to': cert.not_valid_after_utc,
        'serial_number': cert.serial_number,
        'serial_hex': serial_hex,
    }


def find_existing_ca(cert_info):
    """
    Find existing CA by subject match.
    Returns: CA object or None
    """
    from models import CA
    # Match by subject (unique identifier for a CA)
    return CA.query.filter_by(subject=cert_info['subject']).first()


def find_existing_certificate(cert_info):
    """
    Find existing certificate by subject + issuer match.
    Returns: Certificate object or None
    """
    from models import Certificate
    # Match by subject AND issuer (together they identify a cert)
    return Certificate.query.filter_by(
        subject=cert_info['subject'],
        issuer=cert_info['issuer']
    ).first()


def serialize_cert_to_pem(cert):
    """Serialize certificate to PEM format"""
    return cert.public_bytes(serialization.Encoding.PEM)


def serialize_key_to_pem(private_key):
    """Serialize private key to PEM format (unencrypted)"""
    if not private_key:
        return None
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    )
