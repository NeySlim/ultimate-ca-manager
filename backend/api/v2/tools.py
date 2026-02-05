"""
Certificate Tools API endpoints
SSL checker, decoders, converters, key matcher
"""
import ssl
import socket
import base64
import tempfile
import os
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, send_file
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID, ExtensionOID
from OpenSSL import crypto

tools_bp = Blueprint('tools', __name__, url_prefix='/api/v2/tools')


def get_extension_value(cert, oid):
    """Get extension value safely"""
    try:
        ext = cert.extensions.get_extension_for_oid(oid)
        return ext.value
    except x509.ExtensionNotFound:
        return None


def format_name(name):
    """Format X.509 Name to dict"""
    result = {}
    for attr in name:
        oid_name = attr.oid._name
        result[oid_name] = attr.value
    return result


def cert_to_dict(cert):
    """Convert certificate to detailed dict"""
    # Basic info
    result = {
        'subject': format_name(cert.subject),
        'issuer': format_name(cert.issuer),
        'serial_number': format(cert.serial_number, 'X'),
        'version': cert.version.name,
        'not_valid_before': cert.not_valid_before_utc.isoformat(),
        'not_valid_after': cert.not_valid_after_utc.isoformat(),
        'signature_algorithm': cert.signature_algorithm_oid._name,
    }
    
    # Validity status
    now = datetime.now(timezone.utc)
    if now < cert.not_valid_before_utc:
        result['status'] = 'not_yet_valid'
    elif now > cert.not_valid_after_utc:
        result['status'] = 'expired'
    else:
        result['status'] = 'valid'
    
    # Days until expiry
    days_left = (cert.not_valid_after_utc - now).days
    result['days_until_expiry'] = days_left
    
    # Public key info
    pub_key = cert.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        result['public_key'] = {
            'type': 'RSA',
            'size': pub_key.key_size,
            'exponent': pub_key.public_numbers().e
        }
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        result['public_key'] = {
            'type': 'ECDSA',
            'curve': pub_key.curve.name,
            'size': pub_key.key_size
        }
    else:
        result['public_key'] = {'type': type(pub_key).__name__}
    
    # Fingerprints
    result['fingerprints'] = {
        'sha1': cert.fingerprint(hashes.SHA1()).hex(':').upper(),
        'sha256': cert.fingerprint(hashes.SHA256()).hex(':').upper()
    }
    
    # Extensions
    result['extensions'] = {}
    
    # SANs
    san = get_extension_value(cert, ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    if san:
        result['extensions']['subject_alt_names'] = [str(name) for name in san]
    
    # Key Usage
    ku = get_extension_value(cert, ExtensionOID.KEY_USAGE)
    if ku:
        usages = []
        if ku.digital_signature: usages.append('digitalSignature')
        if ku.key_encipherment: usages.append('keyEncipherment')
        if ku.content_commitment: usages.append('nonRepudiation')
        if ku.data_encipherment: usages.append('dataEncipherment')
        if ku.key_agreement: usages.append('keyAgreement')
        if ku.key_cert_sign: usages.append('keyCertSign')
        if ku.crl_sign: usages.append('cRLSign')
        result['extensions']['key_usage'] = usages
    
    # Extended Key Usage
    eku = get_extension_value(cert, ExtensionOID.EXTENDED_KEY_USAGE)
    if eku:
        result['extensions']['extended_key_usage'] = [oid._name for oid in eku]
    
    # Basic Constraints
    bc = get_extension_value(cert, ExtensionOID.BASIC_CONSTRAINTS)
    if bc:
        result['extensions']['basic_constraints'] = {
            'ca': bc.ca,
            'path_length': bc.path_length
        }
        result['is_ca'] = bc.ca
    else:
        result['is_ca'] = False
    
    # Authority Key Identifier
    aki = get_extension_value(cert, ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
    if aki and aki.key_identifier:
        result['extensions']['authority_key_identifier'] = aki.key_identifier.hex(':').upper()
    
    # Subject Key Identifier
    ski = get_extension_value(cert, ExtensionOID.SUBJECT_KEY_IDENTIFIER)
    if ski:
        result['extensions']['subject_key_identifier'] = ski.key_identifier.hex(':').upper()
    
    return result


def csr_to_dict(csr):
    """Convert CSR to detailed dict"""
    result = {
        'subject': format_name(csr.subject),
        'signature_algorithm': csr.signature_algorithm_oid._name,
        'is_signature_valid': csr.is_signature_valid
    }
    
    # Public key info
    pub_key = csr.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        result['public_key'] = {
            'type': 'RSA',
            'size': pub_key.key_size,
            'exponent': pub_key.public_numbers().e
        }
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        result['public_key'] = {
            'type': 'ECDSA',
            'curve': pub_key.curve.name,
            'size': pub_key.key_size
        }
    else:
        result['public_key'] = {'type': type(pub_key).__name__}
    
    # Extensions from CSR attributes
    result['extensions'] = {}
    try:
        for attr in csr.attributes:
            if attr.oid == x509.oid.AttributeOID.EXTENSION_REQUEST:
                for ext in attr.value:
                    if ext.oid == ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                        san = ext.value
                        result['extensions']['subject_alt_names'] = [str(name) for name in san]
    except Exception:
        pass
    
    return result


def get_public_key_bytes(obj):
    """Get public key bytes for comparison"""
    if hasattr(obj, 'public_key'):
        pub_key = obj.public_key()
    else:
        pub_key = obj
    return pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )


@tools_bp.route('/check-ssl', methods=['POST'])
def check_ssl():
    """Check SSL certificate of a remote server"""
    data = request.get_json() or {}
    hostname = data.get('hostname', '').strip()
    port = data.get('port', 443)
    
    if not hostname:
        return jsonify({'error': 'Hostname is required'}), 400
    
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 443
    
    try:
        # Create SSL context
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # We want to see invalid certs too
        
        # Connect
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                # Get certificate chain
                der_cert = ssock.getpeercert(binary_form=True)
                cert = x509.load_der_x509_certificate(der_cert, default_backend())
                
                # Get cipher info
                cipher = ssock.cipher()
                tls_version = ssock.version()
                
                # Parse certificate
                cert_info = cert_to_dict(cert)
                cert_info['hostname'] = hostname
                cert_info['port'] = port
                cert_info['cipher'] = {
                    'name': cipher[0] if cipher else None,
                    'version': cipher[1] if cipher else None,
                    'bits': cipher[2] if cipher else None
                }
                cert_info['tls_version'] = tls_version
                
                # Check hostname match
                san = get_extension_value(cert, ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                hostname_match = False
                if san:
                    for name in san:
                        if isinstance(name, x509.DNSName):
                            if name.value == hostname:
                                hostname_match = True
                                break
                            # Wildcard matching
                            if name.value.startswith('*.'):
                                domain = name.value[2:]
                                if hostname.endswith(domain) and hostname.count('.') == domain.count('.') + 1:
                                    hostname_match = True
                                    break
                
                cert_info['hostname_match'] = hostname_match
                
                # Check if self-signed
                cert_info['self_signed'] = cert.subject == cert.issuer
                
                # Issues list
                issues = []
                if cert_info['status'] == 'expired':
                    issues.append('Certificate has expired')
                elif cert_info['status'] == 'not_yet_valid':
                    issues.append('Certificate is not yet valid')
                if not hostname_match:
                    issues.append(f'Hostname mismatch: {hostname} not in SANs')
                if cert_info['self_signed']:
                    issues.append('Self-signed certificate')
                if cert_info['days_until_expiry'] < 30 and cert_info['status'] == 'valid':
                    issues.append(f'Expires in {cert_info["days_until_expiry"]} days')
                
                cert_info['issues'] = issues
                cert_info['has_issues'] = len(issues) > 0
                
                return jsonify({'success': True, 'data': cert_info})
    
    except socket.timeout:
        return jsonify({'error': f'Connection timeout to {hostname}:{port}'}), 400
    except socket.gaierror:
        return jsonify({'error': f'Could not resolve hostname: {hostname}'}), 400
    except ConnectionRefusedError:
        return jsonify({'error': f'Connection refused by {hostname}:{port}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@tools_bp.route('/decode-csr', methods=['POST'])
def decode_csr():
    """Decode a CSR and return its contents"""
    data = request.get_json() or {}
    pem_data = data.get('pem', '').strip()
    
    if not pem_data:
        return jsonify({'error': 'CSR PEM data is required'}), 400
    
    try:
        # Try to load as PEM
        if '-----BEGIN' not in pem_data:
            pem_data = f"-----BEGIN CERTIFICATE REQUEST-----\n{pem_data}\n-----END CERTIFICATE REQUEST-----"
        
        csr = x509.load_pem_x509_csr(pem_data.encode(), default_backend())
        result = csr_to_dict(csr)
        
        return jsonify({'success': True, 'data': result})
    
    except Exception as e:
        return jsonify({'error': f'Failed to decode CSR: {str(e)}'}), 400


@tools_bp.route('/decode-cert', methods=['POST'])
def decode_cert():
    """Decode a certificate and return its contents"""
    data = request.get_json() or {}
    pem_data = data.get('pem', '').strip()
    
    if not pem_data:
        return jsonify({'error': 'Certificate PEM data is required'}), 400
    
    try:
        # Try to load as PEM
        if '-----BEGIN' not in pem_data:
            pem_data = f"-----BEGIN CERTIFICATE-----\n{pem_data}\n-----END CERTIFICATE-----"
        
        cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
        result = cert_to_dict(cert)
        
        return jsonify({'success': True, 'data': result})
    
    except Exception as e:
        return jsonify({'error': f'Failed to decode certificate: {str(e)}'}), 400


@tools_bp.route('/match-keys', methods=['POST'])
def match_keys():
    """Check if certificate, private key, and/or CSR match"""
    data = request.get_json() or {}
    cert_pem = data.get('certificate', '').strip()
    key_pem = data.get('private_key', '').strip()
    csr_pem = data.get('csr', '').strip()
    password = data.get('password', '')
    
    if not any([cert_pem, key_pem, csr_pem]):
        return jsonify({'error': 'At least one of certificate, private_key, or csr is required'}), 400
    
    results = {
        'items': [],
        'matches': [],
        'mismatches': []
    }
    
    public_keys = {}
    
    try:
        # Parse certificate
        if cert_pem:
            try:
                if '-----BEGIN' not in cert_pem:
                    cert_pem = f"-----BEGIN CERTIFICATE-----\n{cert_pem}\n-----END CERTIFICATE-----"
                cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
                pub_bytes = get_public_key_bytes(cert)
                public_keys['certificate'] = pub_bytes
                
                # Get CN for display
                cn = None
                for attr in cert.subject:
                    if attr.oid == NameOID.COMMON_NAME:
                        cn = attr.value
                        break
                
                results['items'].append({
                    'type': 'certificate',
                    'cn': cn,
                    'valid': True,
                    'fingerprint': cert.fingerprint(hashes.SHA256()).hex()[:16]
                })
            except Exception as e:
                results['items'].append({
                    'type': 'certificate',
                    'valid': False,
                    'error': str(e)
                })
        
        # Parse private key
        if key_pem:
            try:
                if '-----BEGIN' not in key_pem:
                    key_pem = f"-----BEGIN PRIVATE KEY-----\n{key_pem}\n-----END PRIVATE KEY-----"
                
                pwd = password.encode() if password else None
                try:
                    key = serialization.load_pem_private_key(key_pem.encode(), password=pwd, backend=default_backend())
                except TypeError:
                    key = serialization.load_pem_private_key(key_pem.encode(), password=None, backend=default_backend())
                
                pub_bytes = get_public_key_bytes(key.public_key())
                public_keys['private_key'] = pub_bytes
                
                # Key type info
                if isinstance(key, rsa.RSAPrivateKey):
                    key_info = f'RSA {key.key_size}-bit'
                elif isinstance(key, ec.EllipticCurvePrivateKey):
                    key_info = f'ECDSA {key.curve.name}'
                else:
                    key_info = type(key).__name__
                
                results['items'].append({
                    'type': 'private_key',
                    'key_type': key_info,
                    'valid': True
                })
            except Exception as e:
                results['items'].append({
                    'type': 'private_key',
                    'valid': False,
                    'error': str(e)
                })
        
        # Parse CSR
        if csr_pem:
            try:
                if '-----BEGIN' not in csr_pem:
                    csr_pem = f"-----BEGIN CERTIFICATE REQUEST-----\n{csr_pem}\n-----END CERTIFICATE REQUEST-----"
                csr = x509.load_pem_x509_csr(csr_pem.encode(), default_backend())
                pub_bytes = get_public_key_bytes(csr)
                public_keys['csr'] = pub_bytes
                
                # Get CN for display
                cn = None
                for attr in csr.subject:
                    if attr.oid == NameOID.COMMON_NAME:
                        cn = attr.value
                        break
                
                results['items'].append({
                    'type': 'csr',
                    'cn': cn,
                    'valid': True,
                    'signature_valid': csr.is_signature_valid
                })
            except Exception as e:
                results['items'].append({
                    'type': 'csr',
                    'valid': False,
                    'error': str(e)
                })
        
        # Compare public keys
        key_names = list(public_keys.keys())
        for i in range(len(key_names)):
            for j in range(i + 1, len(key_names)):
                name1, name2 = key_names[i], key_names[j]
                if public_keys[name1] == public_keys[name2]:
                    results['matches'].append({
                        'item1': name1,
                        'item2': name2,
                        'match': True
                    })
                else:
                    results['mismatches'].append({
                        'item1': name1,
                        'item2': name2,
                        'match': False
                    })
        
        # Overall status
        results['all_match'] = len(results['mismatches']) == 0 and len(results['matches']) > 0
        
        return jsonify({'success': True, 'data': results})
    
    except Exception as e:
        return jsonify({'error': f'Failed to match keys: {str(e)}'}), 400


@tools_bp.route('/convert', methods=['POST'])
def convert_certificate():
    """Convert certificate/key between formats"""
    data = request.get_json() or {}
    pem_data = data.get('pem', '').strip()
    input_type = data.get('input_type', 'certificate')  # certificate, private_key, csr
    output_format = data.get('output_format', 'der')  # der, pkcs12, pkcs7
    password = data.get('password', '')
    pkcs12_password = data.get('pkcs12_password', '')
    include_chain = data.get('include_chain', False)
    chain_pem = data.get('chain', '').strip()
    key_pem = data.get('private_key', '').strip()
    
    if not pem_data:
        return jsonify({'error': 'PEM data is required'}), 400
    
    try:
        result = {}
        
        if input_type == 'certificate':
            # Load certificate
            if '-----BEGIN' not in pem_data:
                pem_data = f"-----BEGIN CERTIFICATE-----\n{pem_data}\n-----END CERTIFICATE-----"
            cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
            
            if output_format == 'der':
                # PEM to DER
                der_data = cert.public_bytes(serialization.Encoding.DER)
                result = {
                    'format': 'der',
                    'data': base64.b64encode(der_data).decode(),
                    'filename': 'certificate.der'
                }
            
            elif output_format == 'pkcs12':
                # PEM to PKCS12
                if not key_pem:
                    return jsonify({'error': 'Private key is required for PKCS12 conversion'}), 400
                
                # Load private key
                pwd = password.encode() if password else None
                try:
                    key = serialization.load_pem_private_key(key_pem.encode(), password=pwd, backend=default_backend())
                except TypeError:
                    key = serialization.load_pem_private_key(key_pem.encode(), password=None, backend=default_backend())
                
                # Load chain if provided
                ca_certs = None
                if chain_pem:
                    ca_certs = []
                    for match in x509.load_pem_x509_certificates(chain_pem.encode()):
                        ca_certs.append(match)
                
                # Create PKCS12
                p12_password = pkcs12_password.encode() if pkcs12_password else None
                p12_data = serialization.pkcs12.serialize_key_and_certificates(
                    name=b"certificate",
                    key=key,
                    cert=cert,
                    cas=ca_certs,
                    encryption_algorithm=serialization.BestAvailableEncryption(p12_password) if p12_password else serialization.NoEncryption()
                )
                
                result = {
                    'format': 'pkcs12',
                    'data': base64.b64encode(p12_data).decode(),
                    'filename': 'certificate.p12'
                }
            
            elif output_format == 'pkcs7':
                # PEM to PKCS7 using OpenSSL
                certs = [crypto.load_certificate(crypto.FILETYPE_PEM, pem_data)]
                
                if chain_pem:
                    for cert_pem in chain_pem.split('-----END CERTIFICATE-----'):
                        if '-----BEGIN CERTIFICATE-----' in cert_pem:
                            cert_pem = cert_pem + '-----END CERTIFICATE-----'
                            certs.append(crypto.load_certificate(crypto.FILETYPE_PEM, cert_pem.encode()))
                
                # Create PKCS7
                p7 = crypto.PKCS7()
                for c in certs:
                    p7.set_type(crypto.PKCS7_SIGNED)
                
                # Use temp file for conversion
                with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                    f.write(pem_data)
                    if chain_pem:
                        f.write('\n')
                        f.write(chain_pem)
                    temp_pem = f.name
                
                try:
                    # Use openssl command for PKCS7
                    import subprocess
                    p7_data = subprocess.check_output([
                        'openssl', 'crl2pkcs7', '-nocrl', '-certfile', temp_pem
                    ])
                    result = {
                        'format': 'pkcs7',
                        'data': p7_data.decode(),
                        'filename': 'certificate.p7b'
                    }
                finally:
                    os.unlink(temp_pem)
            
            elif output_format == 'pem':
                # Already PEM, just return cleaned version
                result = {
                    'format': 'pem',
                    'data': cert.public_bytes(serialization.Encoding.PEM).decode(),
                    'filename': 'certificate.pem'
                }
        
        elif input_type == 'private_key':
            # Load key
            pwd = password.encode() if password else None
            try:
                key = serialization.load_pem_private_key(pem_data.encode(), password=pwd, backend=default_backend())
            except TypeError:
                key = serialization.load_pem_private_key(pem_data.encode(), password=None, backend=default_backend())
            
            if output_format == 'der':
                der_data = key.private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )
                result = {
                    'format': 'der',
                    'data': base64.b64encode(der_data).decode(),
                    'filename': 'private_key.der'
                }
            
            elif output_format == 'pem':
                # Re-export with or without encryption
                if pkcs12_password:
                    enc = serialization.BestAvailableEncryption(pkcs12_password.encode())
                else:
                    enc = serialization.NoEncryption()
                
                pem_out = key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=enc
                )
                result = {
                    'format': 'pem',
                    'data': pem_out.decode(),
                    'filename': 'private_key.pem'
                }
        
        elif input_type == 'csr':
            # Load CSR
            if '-----BEGIN' not in pem_data:
                pem_data = f"-----BEGIN CERTIFICATE REQUEST-----\n{pem_data}\n-----END CERTIFICATE REQUEST-----"
            csr = x509.load_pem_x509_csr(pem_data.encode(), default_backend())
            
            if output_format == 'der':
                der_data = csr.public_bytes(serialization.Encoding.DER)
                result = {
                    'format': 'der',
                    'data': base64.b64encode(der_data).decode(),
                    'filename': 'request.der'
                }
            elif output_format == 'pem':
                result = {
                    'format': 'pem',
                    'data': csr.public_bytes(serialization.Encoding.PEM).decode(),
                    'filename': 'request.pem'
                }
        
        if not result:
            return jsonify({'error': f'Unsupported conversion: {input_type} to {output_format}'}), 400
        
        return jsonify({'success': True, 'data': result})
    
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 400
