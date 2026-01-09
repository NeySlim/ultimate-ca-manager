"""
Certificate Parser Service
Parse X.509 certificates and extract information
"""
from typing import Dict, Optional
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
import re
from datetime import datetime, timezone


class CertificateParser:
    """Parse and extract information from X.509 certificates"""
    
    @staticmethod
    def parse_pem_certificate(pem_data: str) -> Optional[x509.Certificate]:
        """
        Parse PEM-encoded certificate
        
        Args:
            pem_data: PEM-encoded certificate string
            
        Returns:
            x509.Certificate object or None if parsing fails
        """
        try:
            # Remove header/footer if present and clean up
            pem_data = pem_data.strip()
            
            # Handle URL-encoded or escaped newlines
            pem_data = pem_data.replace('\\n', '\n')
            pem_data = pem_data.replace('%0A', '\n')
            
            # Ensure proper PEM format
            if not pem_data.startswith('-----BEGIN CERTIFICATE-----'):
                pem_data = '-----BEGIN CERTIFICATE-----\n' + pem_data
            if not pem_data.endswith('-----END CERTIFICATE-----'):
                pem_data = pem_data + '\n-----END CERTIFICATE-----'
            
            cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
            return cert
            
        except Exception as e:
            print(f"Error parsing certificate: {e}")
            return None
    
    @staticmethod
    def extract_certificate_info(cert: x509.Certificate) -> Dict:
        """
        Extract detailed information from certificate
        
        Args:
            cert: x509.Certificate object
            
        Returns:
            Dictionary with certificate information
        """
        # Extract subject DN
        subject_parts = []
        for attr in cert.subject:
            subject_parts.append(f"{attr.oid._name}={attr.value}")
        subject_dn = ", ".join(subject_parts)
        
        # Extract issuer DN
        issuer_parts = []
        for attr in cert.issuer:
            issuer_parts.append(f"{attr.oid._name}={attr.value}")
        issuer_dn = ", ".join(issuer_parts)
        
        # Get serial number (hex format)
        serial = format(cert.serial_number, 'X')
        
        # Calculate fingerprint (SHA256)
        fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
        
        # Get validity dates
        valid_from = cert.not_valid_before_utc if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before
        valid_until = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after
        
        # Extract common name
        cn = None
        try:
            cn_attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            if cn_attrs:
                cn = cn_attrs[0].value
        except:
            pass
        
        # Extract email from SAN or subject
        email = None
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            emails = san_ext.value.get_values_for_type(x509.RFC822Name)
            if emails:
                email = emails[0]
        except:
            # Try to get email from subject
            try:
                email_attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.EMAIL_ADDRESS)
                if email_attrs:
                    email = email_attrs[0].value
            except:
                pass
        
        return {
            'subject_dn': subject_dn,
            'issuer_dn': issuer_dn,
            'serial': serial,
            'fingerprint_sha256': fingerprint,
            'fingerprint': fingerprint,  # Backward compatibility
            'common_name': cn,
            'email': email,
            'valid_from': valid_from,
            'valid_until': valid_until,
            'is_valid': datetime.now(timezone.utc) >= valid_from and datetime.now(timezone.utc) <= valid_until
        }
    
    @staticmethod
    def parse_dn_string(dn_string: str) -> Dict[str, str]:
        """
        Parse a Distinguished Name string into components
        
        Args:
            dn_string: DN string like "CN=John Doe,O=ACME Corp,C=US"
            
        Returns:
            Dictionary with DN components
        """
        components = {}
        
        # Split by comma (but not escaped commas)
        parts = re.split(r'(?<!\\),', dn_string)
        
        for part in parts:
            part = part.strip()
            if '=' in part:
                key, value = part.split('=', 1)
                key = key.strip().upper()
                value = value.strip()
                # Unescape escaped characters
                value = value.replace('\\,', ',')
                components[key] = value
        
        return components
    
    @staticmethod
    def extract_from_nginx_headers(headers: Dict[str, str]) -> Optional[Dict]:
        """
        Extract certificate info from Nginx reverse proxy headers
        
        Expected headers from Nginx:
        - X-SSL-Client-Cert: PEM certificate
        - X-SSL-Client-Verify: SUCCESS/FAILED
        - X-SSL-Client-S-DN: Subject DN
        - X-SSL-Client-I-DN: Issuer DN (optional)
        - X-SSL-Client-Serial: Serial number (hex)
        - X-SSL-Client-Fingerprint: SHA256 fingerprint (optional)
        
        Args:
            headers: Request headers dictionary
            
        Returns:
            Dictionary with certificate info or None
        """
        # Check if client cert verification succeeded
        verify_status = headers.get('X-SSL-Client-Verify', '').upper()
        if verify_status != 'SUCCESS':
            return None
        
        cert_pem = headers.get('X-SSL-Client-Cert')
        subject_dn = headers.get('X-SSL-Client-S-DN')
        issuer_dn = headers.get('X-SSL-Client-I-DN')
        serial = headers.get('X-SSL-Client-Serial')
        fingerprint = headers.get('X-SSL-Client-Fingerprint')
        
        # If we have the full certificate, parse it
        if cert_pem:
            cert = CertificateParser.parse_pem_certificate(cert_pem)
            if cert:
                return CertificateParser.extract_certificate_info(cert)
        
        # Otherwise, use header values
        if subject_dn:
            dn_parts = CertificateParser.parse_dn_string(subject_dn)
            
            return {
                'subject_dn': subject_dn,
                'issuer_dn': issuer_dn,
                'serial': serial,
                'fingerprint': fingerprint,
                'common_name': dn_parts.get('CN'),
                'email': dn_parts.get('EMAILADDRESS') or dn_parts.get('EMAIL'),
                'valid_from': None,
                'valid_until': None,
                'is_valid': True  # Nginx already verified
            }
        
        return None
    
    @staticmethod
    def extract_from_apache_headers(headers: Dict[str, str]) -> Optional[Dict]:
        """
        Extract certificate info from Apache reverse proxy headers
        
        Expected headers from Apache:
        - X-SSL-Client-Cert: PEM certificate
        - X-SSL-Client-Verify: SUCCESS/FAILED
        - X-SSL-Client-S-DN: Subject DN
        - X-SSL-Client-I-DN: Issuer DN
        - X-SSL-Client-M-Serial: Serial number
        
        Args:
            headers: Request headers dictionary
            
        Returns:
            Dictionary with certificate info or None
        """
        # Similar to Nginx, just different header names for some fields
        verify_status = headers.get('X-SSL-Client-Verify', '').upper()
        if verify_status != 'SUCCESS':
            return None
        
        cert_pem = headers.get('X-SSL-Client-Cert')
        subject_dn = headers.get('X-SSL-Client-S-DN')
        issuer_dn = headers.get('X-SSL-Client-I-DN')
        serial = headers.get('X-SSL-Client-M-Serial')  # Apache uses M-Serial
        
        if cert_pem:
            cert = CertificateParser.parse_pem_certificate(cert_pem)
            if cert:
                return CertificateParser.extract_certificate_info(cert)
        
        if subject_dn:
            dn_parts = CertificateParser.parse_dn_string(subject_dn)
            
            return {
                'subject_dn': subject_dn,
                'issuer_dn': issuer_dn,
                'serial': serial,
                'fingerprint': None,
                'common_name': dn_parts.get('CN'),
                'email': dn_parts.get('EMAILADDRESS') or dn_parts.get('EMAIL'),
                'valid_from': None,
                'valid_until': None,
                'is_valid': True
            }
        
        return None
    
    @staticmethod
    def extract_from_flask_native(peercert) -> Optional[Dict[str, any]]:
        """
        Extract certificate info from native Flask/werkzeug peercert
        
        This method handles certificates extracted directly from the SSL layer
        when Flask is running with client cert verification enabled.
        
        Args:
            peercert: DER-encoded certificate bytes or dict from request.environ['peercert']
        
        Returns:
            Dict with certificate information or None
        """
        try:
            # peercert can be bytes (DER) or dict
            if isinstance(peercert, bytes):
                # DER format - parse it
                from cryptography.x509 import load_der_x509_certificate
                from cryptography.hazmat.backends import default_backend
                
                cert = load_der_x509_certificate(peercert, default_backend())
                
                # Extract subject
                subject_parts = {}
                for attr in cert.subject:
                    subject_parts[attr.oid._name.upper()] = attr.value
                
                # Build DN string
                subject_dn = ', '.join([f'{k}={v}' for k, v in subject_parts.items()])
                
                # Get serial as hex
                serial = format(cert.serial_number, 'X')
                
                # Calculate fingerprint
                import hashlib
                fingerprint = hashlib.sha256(peercert).hexdigest().upper()
                
                return {
                    'cert_pem': cert.public_bytes(encoding=serialization.Encoding.PEM).decode('utf-8'),
                    'subject_dn': subject_dn,
                    'issuer_dn': ', '.join([f'{attr.oid._name.upper()}={attr.value}' for attr in cert.issuer]),
                    'serial': serial,
                    'fingerprint': fingerprint,
                    'common_name': subject_parts.get('COMMONNAME') or subject_parts.get('CN'),
                    'email': subject_parts.get('EMAILADDRESS'),
                    'valid_from': cert.not_valid_before_utc,
                    'valid_until': cert.not_valid_after_utc,
                    'is_valid': True
                }
            
            elif isinstance(peercert, dict):
                # Already parsed dict (older Python SSL)
                subject_dn = ', '.join([f'{k}={v}' for k, v in peercert.get('subject', [])][0])
                return {
                    'subject_dn': subject_dn,
                    'serial': peercert.get('serialNumber', '').upper(),
                    'common_name': dict(peercert.get('subject', [])[0]).get('commonName'),
                    'is_valid': True
                }
                
        except Exception as e:
            logger.error(f"Error extracting native Flask certificate: {e}")
            return None
        
        return None
