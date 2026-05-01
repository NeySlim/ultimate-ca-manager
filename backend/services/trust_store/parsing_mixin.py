"""
Parsing operations mixin for TrustStoreService
"""
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from typing import Dict

from utils.datetime_utils import utc_isoformat


class ParsingMixin:
    """Certificate parsing operations mixin"""
    
    @staticmethod
    def parse_certificate(cert_pem: bytes) -> Dict:
        """Parse a certificate and extract information."""
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        return {
            'subject': cert.subject.rfc4514_string(),
            'issuer': cert.issuer.rfc4514_string(),
            'serial_number': str(cert.serial_number),
            'not_valid_before': cert.not_valid_before_utc,
            'not_valid_after': cert.not_valid_after_utc,
            'is_ca': False,
            'key_usage': [],
            'extended_key_usage': [],
            'san': [],
        }
    
    @staticmethod
    def parse_certificate_details(cert_pem: bytes) -> Dict:
        """Parse full certificate details including all X.509 extensions."""
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        details = {
            'version': cert.version.name,
            'serial_number': format(cert.serial_number, 'x').upper(),
            'signature_algorithm': cert.signature_algorithm_oid._name,
            'subject': {},
            'issuer': {},
            'validity': {
                'not_before': utc_isoformat(cert.not_valid_before_utc),
                'not_after': utc_isoformat(cert.not_valid_after_utc)
            },
            'extensions': {},
            'public_key': {}
        }
        
        # Parse subject
        for attr in cert.subject:
            details['subject'][attr.oid._name] = attr.value
        
        # Parse issuer
        for attr in cert.issuer:
            details['issuer'][attr.oid._name] = attr.value
        
        # Parse public key info
        public_key = cert.public_key()
        if isinstance(public_key, rsa.RSAPublicKey):
            details['public_key'] = {
                'algorithm': 'RSA',
                'key_size': public_key.key_size,
                'public_exponent': public_key.public_numbers().e
            }
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            details['public_key'] = {
                'algorithm': 'EC',
                'curve': public_key.curve.name
            }
        
        # Parse extensions
        for ext in cert.extensions:
            ext_name = ext.oid._name
            try:
                if isinstance(ext.value, x509.SubjectAlternativeName):
                    sans = []
                    for san in ext.value:
                        if isinstance(san, x509.DNSName):
                            sans.append(f"DNS:{san.value}")
                        elif isinstance(san, x509.IPAddress):
                            sans.append(f"IP:{san.value}")
                        elif isinstance(san, x509.RFC822Name):
                            sans.append(f"email:{san.value}")
                        elif isinstance(san, x509.UniformResourceIdentifier):
                            sans.append(f"URI:{san.value}")
                    details['extensions']['subjectAltName'] = {
                        'critical': ext.critical,
                        'values': sans
                    }
                elif isinstance(ext.value, x509.KeyUsage):
                    usages = []
                    if ext.value.digital_signature: usages.append('Digital Signature')
                    if ext.value.key_encipherment: usages.append('Key Encipherment')
                    if ext.value.data_encipherment: usages.append('Data Encipherment')
                    if ext.value.key_agreement: usages.append('Key Agreement')
                    if ext.value.key_cert_sign: usages.append('Key Cert Sign')
                    if ext.value.crl_sign: usages.append('CRL Sign')
                    if ext.value.content_commitment: usages.append('Content Commitment')
                    details['extensions']['keyUsage'] = {
                        'critical': ext.critical,
                        'values': usages
                    }
                elif isinstance(ext.value, x509.ExtendedKeyUsage):
                    usages = [oid._name for oid in ext.value]
                    details['extensions']['extendedKeyUsage'] = {
                        'critical': ext.critical,
                        'values': usages
                    }
                elif isinstance(ext.value, x509.BasicConstraints):
                    details['extensions']['basicConstraints'] = {
                        'critical': ext.critical,
                        'ca': ext.value.ca,
                        'path_length': ext.value.path_length
                    }
                elif isinstance(ext.value, x509.SubjectKeyIdentifier):
                    details['extensions']['subjectKeyIdentifier'] = {
                        'critical': ext.critical,
                        'value': ext.value.digest.hex().upper()
                    }
                elif isinstance(ext.value, x509.AuthorityKeyIdentifier):
                    details['extensions']['authorityKeyIdentifier'] = {
                        'critical': ext.critical,
                        'keyid': ext.value.key_identifier.hex().upper() if ext.value.key_identifier else None
                    }
                elif isinstance(ext.value, x509.AuthorityInformationAccess):
                    aia_values = []
                    for desc in ext.value:
                        access_method = desc.access_method._name
                        location = desc.access_location.value
                        aia_values.append(f"{access_method}: {location}")
                    details['extensions']['authorityInfoAccess'] = {
                        'critical': ext.critical,
                        'values': aia_values
                    }
                elif isinstance(ext.value, x509.CRLDistributionPoints):
                    crl_points = []
                    for point in ext.value:
                        if point.full_name:
                            for name in point.full_name:
                                if hasattr(name, 'value'):
                                    crl_points.append(f"URI: {name.value}")
                        if point.relative_name:
                            crl_points.append(f"Relative: {point.relative_name.rfc4514_string()}")
                    details['extensions']['cRLDistributionPoints'] = {
                        'critical': ext.critical,
                        'values': crl_points if crl_points else ['Not specified']
                    }
                elif isinstance(ext.value, x509.CertificatePolicies):
                    policies = []
                    for policy in ext.value:
                        policy_info = f"Policy: {policy.policy_identifier.dotted_string}"
                        if policy.policy_qualifiers:
                            qualifiers = []
                            for qual in policy.policy_qualifiers:
                                if isinstance(qual, str):
                                    qualifiers.append(qual)
                                elif hasattr(qual, 'explicit_text') and qual.explicit_text:
                                    qualifiers.append(f"Text: {qual.explicit_text}")
                            if qualifiers:
                                policy_info += " (" + ", ".join(qualifiers) + ")"
                        policies.append(policy_info)
                    details['extensions']['certificatePolicies'] = {
                        'critical': ext.critical,
                        'values': policies
                    }
                elif isinstance(ext.value, x509.UnrecognizedExtension):
                    oid = ext.oid.dotted_string
                    ext_data = ext.value.value
                    
                    if oid == '2.16.840.1.113730.1.13':  # Netscape Comment
                        if ext_data[0] == 0x16:
                            length = ext_data[1]
                            comment = ext_data[2:2+length].decode('ascii', errors='ignore')
                            details['extensions']['netscapeComment'] = {
                                'critical': ext.critical,
                                'value': comment,
                                'oid': oid,
                                'display_name': 'OPNsense Comment'
                            }
                        else:
                            details['extensions'][f'Unknown OID ({oid})'] = {
                                'critical': ext.critical,
                                'value': f'<binary data, {len(ext_data)} bytes>'
                            }
                    elif oid == '2.16.840.1.113730.1.1':  # Netscape Cert Type
                        cert_types = []
                        if len(ext_data) >= 3:
                            bits = ext_data[2]
                            if bits & 0x80: cert_types.append('SSL Client')
                            if bits & 0x40: cert_types.append('SSL Server')
                            if bits & 0x20: cert_types.append('S/MIME')
                            if bits & 0x10: cert_types.append('Object Signing')
                            if bits & 0x08: cert_types.append('SSL CA')
                            if bits & 0x04: cert_types.append('S/MIME CA')
                            if bits & 0x02: cert_types.append('Object Signing CA')
                        details['extensions']['netscapeCertType'] = {
                            'critical': ext.critical,
                            'values': cert_types if cert_types else ['Unknown'],
                            'oid': oid,
                            'display_name': 'Netscape Certificate Type'
                        }
                    else:
                        details['extensions'][f'Unknown OID ({oid})'] = {
                            'critical': ext.critical,
                            'value': f'<{len(ext_data)} bytes>',
                            'oid': oid
                        }
                else:
                    details['extensions'][ext_name] = {
                        'critical': ext.critical,
                        'value': str(ext.value)
                    }
            except Exception as e:
                details['extensions'][ext_name] = {
                    'critical': ext.critical,
                    'error': str(e)
                }
        
        return details
