"""
Certificate Import Service - Unified parsing for CA and Certificate imports
"""
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import re
import base64
from utils.key_codec import private_key_to_pem


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
            except Exception:
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
                except Exception:
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
            except Exception:
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
        except Exception:
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
    from cryptography.x509.oid import ExtensionOID
    
    subject = cert.subject
    issuer = cert.issuer
    
    def get_name_attr(name_obj, oid):
        try:
            return name_obj.get_attributes_for_oid(oid)[0].value
        except Exception:
            return ''
    
    # Get serial number as hex string for comparison
    serial_hex = format(cert.serial_number, 'x').upper()
    
    # Extract SKI/AKI
    ski = None
    aki = None
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        ski = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        if ext.value.key_identifier:
            aki = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    
    # Extract SANs
    san_dns, san_ip, san_email, san_uri = [], [], [], []
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        from cryptography.x509 import DNSName, IPAddress, RFC822Name, UniformResourceIdentifier
        for name_entry in san_ext.value:
            if isinstance(name_entry, DNSName):
                san_dns.append(name_entry.value)
            elif isinstance(name_entry, IPAddress):
                san_ip.append(str(name_entry.value))
            elif isinstance(name_entry, RFC822Name):
                san_email.append(name_entry.value)
            elif isinstance(name_entry, UniformResourceIdentifier):
                san_uri.append(name_entry.value)
    except Exception:
        pass
    
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
        'ski': ski,
        'aki': aki,
        'san_dns': san_dns,
        'san_ip': san_ip,
        'san_email': san_email,
        'san_uri': san_uri,
    }


class AmbiguousImportTarget(ValueError):
    """Several records share the certificate's names and none can be told
    to be the one it belongs to."""


def _spki(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _record_identity(record):
    """The record's current certificate and public key: (x509 or None, SPKI or None).

    The key comes from the certificate when the record holds one; a record
    still waiting for its certificate is known by its stored private key,
    its signing request, or the cached public key of its HSM key (read as
    stored: nothing here may reach the HSM or commit).
    """
    stored_cert = None
    if record.crt:
        try:
            stored_cert = x509.load_pem_x509_certificate(base64.b64decode(record.crt), default_backend())
            return stored_cert, _spki(stored_cert.public_key())
        except Exception:
            stored_cert = None
    if record.prv:
        try:
            from utils.key_codec import load_pem_bytes
            key = serialization.load_pem_private_key(
                load_pem_bytes(record.prv, context=f"{type(record).__name__} {record.id}"), password=None)
            return stored_cert, _spki(key.public_key())
        except Exception:
            pass
    csr_stored = getattr(record, 'csr', None)
    if csr_stored:
        try:
            csr_pem = csr_stored.encode('utf-8') if csr_stored.startswith('-----BEGIN') else base64.b64decode(csr_stored)
            csr = x509.load_pem_x509_csr(csr_pem, default_backend())
            return stored_cert, _spki(csr.public_key())
        except Exception:
            pass
    hsm_key = getattr(record, 'hsm_key', None)
    cached = getattr(hsm_key, 'public_key_pem', None) if hsm_key is not None else None
    if cached:
        try:
            public_key = serialization.load_pem_public_key(
                cached.encode() if isinstance(cached, str) else cached)
            return stored_cert, _spki(public_key)
        except Exception:
            pass
    return stored_cert, None


def _select_existing(candidates, cert, kind):
    """Among *candidates*, the records sharing the certificate's names, the
    one the certificate belongs to; None when there is none (#347 review).

    The record holding the certificate's key wins: the very same certificate
    first, then the one whose certificate has the same issuer (a cross-signed
    CA holds the same key under several issuers), then the single record
    holding the key. A renewed certificate thus lands on its own record, not
    on a homonym that happened to come first. Without a key link a single
    candidate is the record being re-keyed; several cannot be told apart,
    and the import is refused rather than applied to whichever the database
    returned.
    """
    if not candidates:
        return None
    wanted = _spki(cert.public_key())
    same_key, same_issuer, exact = [], [], []
    for record in candidates:
        stored_cert, spki = _record_identity(record)
        if spki != wanted:
            continue
        same_key.append(record)
        if stored_cert is None or stored_cert.issuer != cert.issuer:
            continue
        same_issuer.append(record)
        if stored_cert.serial_number == cert.serial_number:
            exact.append(record)
    if exact:
        return exact[0]
    if len(same_issuer) == 1:
        return same_issuer[0]
    if len(same_key) == 1:
        return same_key[0]
    if same_key:
        raise AmbiguousImportTarget(
            f"{len(same_key)} existing {kind}s share this subject and hold this "
            f"certificate's key, none under this certificate's issuer; the record "
            f"to update cannot be determined")
    if len(candidates) == 1:
        return candidates[0]
    raise AmbiguousImportTarget(
        f"{len(candidates)} existing {kind}s share this subject and none holds this "
        f"certificate's key; the record to update cannot be determined")


def install_on_pending_ca(ca, cert_pem, username):
    """Install *cert_pem* on a CA still waiting for its certificate, through
    the same path as the dedicated upload (key match, validity, chain to the
    issuer, activation), and emit the lifecycle event.

    Returns (ca_dict, warnings); raises ValueError with a user-safe message
    when the certificate is refused (#347 review).
    """
    from services.ca_service import CAService
    from services.webhook_service import emit_ca_updated
    ca, warnings, _superseded = CAService.complete_external_ca(ca, cert_pem, username=username)
    # Snapshot before emit: subscribers may commit and expire the instance
    ca_dict = ca.to_dict()
    emit_ca_updated(ca_dict, actor=username, changes={'certificate': 'installed'})
    return ca_dict, warnings


def find_existing_ca(cert_info, cert):
    """
    The existing CA record *cert* belongs to, by subject, or None.
    Raises AmbiguousImportTarget when several CAs share the subject and
    none holds the certificate's key.
    """
    from models import CA
    candidates = CA.query.filter_by(subject=cert_info['subject']).order_by(CA.id).all()
    return _select_existing(candidates, cert, 'CA')


def find_existing_certificate(cert_info, cert):
    """
    The existing certificate record *cert* belongs to, by subject + issuer,
    or None. Raises AmbiguousImportTarget when several records share them
    and none holds the certificate's key.
    """
    from models import Certificate
    candidates = Certificate.query.filter_by(
        subject=cert_info['subject'],
        issuer=cert_info['issuer']
    ).order_by(Certificate.id).all()
    return _select_existing(candidates, cert, 'certificate')


def find_pending_csr_for_certificate(cert):
    """
    The pending CSR record (request stored, no certificate yet) whose public
    key is this certificate's, or None (#341).

    A certificate issued by an external CA for a CSR generated here has an
    issuer the CSR record never had, so subject/issuer matching cannot find
    it; the key pair is the one thing the two share.
    """
    from models import Certificate
    wanted = cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    from utils.cert_status import pending_requests
    pending = pending_requests().order_by(Certificate.id.desc()).all()
    for record in pending:
        try:
            stored = record.csr
            csr_pem = stored.encode('utf-8') if stored.startswith('-----BEGIN') else base64.b64decode(stored)
            csr = x509.load_pem_x509_csr(csr_pem, default_backend())
            spki = csr.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        except Exception:
            continue
        if spki == wanted:
            return record
    return None


def serialize_cert_to_pem(cert):
    """Serialize certificate to PEM format"""
    return cert.public_bytes(serialization.Encoding.PEM)


def serialize_key_to_pem(private_key):
    """Serialize private key to PEM format (unencrypted)"""
    if not private_key:
        return None
    return private_key_to_pem(private_key)
