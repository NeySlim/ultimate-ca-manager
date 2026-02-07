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
        return jsonify({'error': 'CSR data is required'}), 400
    
    try:
        csr = None
        
        # Check for BASE64-encoded binary (DER)
        if pem_data.startswith('BASE64:'):
            raw_bytes = base64.b64decode(pem_data[7:])
            csr = x509.load_der_x509_csr(raw_bytes, default_backend())
        else:
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
        return jsonify({'error': 'Certificate data is required'}), 400
    
    try:
        cert = None
        
        # Check for BASE64-encoded binary (DER)
        if pem_data.startswith('BASE64:'):
            raw_bytes = base64.b64decode(pem_data[7:])
            cert = x509.load_der_x509_certificate(raw_bytes, default_backend())
        else:
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
    
    def load_cert_any_format(data):
        """Load certificate from PEM or DER"""
        if data.startswith('BASE64:'):
            raw = base64.b64decode(data[7:])
            return x509.load_der_x509_certificate(raw, default_backend())
        if '-----BEGIN' not in data:
            data = f"-----BEGIN CERTIFICATE-----\n{data}\n-----END CERTIFICATE-----"
        return x509.load_pem_x509_certificate(data.encode(), default_backend())
    
    def load_key_any_format(data, pwd):
        """Load private key from PEM or DER"""
        pwd_bytes = pwd.encode() if pwd else None
        if data.startswith('BASE64:'):
            raw = base64.b64decode(data[7:])
            try:
                return serialization.load_der_private_key(raw, password=pwd_bytes, backend=default_backend())
            except TypeError:
                return serialization.load_der_private_key(raw, password=None, backend=default_backend())
        if '-----BEGIN' not in data:
            data = f"-----BEGIN PRIVATE KEY-----\n{data}\n-----END PRIVATE KEY-----"
        try:
            return serialization.load_pem_private_key(data.encode(), password=pwd_bytes, backend=default_backend())
        except TypeError:
            return serialization.load_pem_private_key(data.encode(), password=None, backend=default_backend())
    
    def load_csr_any_format(data):
        """Load CSR from PEM or DER"""
        if data.startswith('BASE64:'):
            raw = base64.b64decode(data[7:])
            return x509.load_der_x509_csr(raw, default_backend())
        if '-----BEGIN' not in data:
            data = f"-----BEGIN CERTIFICATE REQUEST-----\n{data}\n-----END CERTIFICATE REQUEST-----"
        return x509.load_pem_x509_csr(data.encode(), default_backend())
    
    try:
        # Parse certificate
        if cert_pem:
            try:
                cert = load_cert_any_format(cert_pem)
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
                key = load_key_any_format(key_pem, password)
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
                csr = load_csr_any_format(csr_pem)
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
    """Convert certificate/key between formats
    
    Supports input formats: PEM, DER, PKCS12/PFX, PKCS7/P7B
    Supports output formats: PEM, DER, PKCS12, PKCS7
    
    Input can be:
    - PEM text (-----BEGIN ... -----)
    - Base64-encoded binary with 'BASE64:' prefix
    """
    data = request.get_json() or {}
    input_data = data.get('pem', '').strip()
    input_type = data.get('input_type', 'auto')  # auto, certificate, private_key, csr, pkcs12, pkcs7
    output_format = data.get('output_format', 'pem')  # pem, der, pkcs12, pkcs7
    password = data.get('password', '')  # Input file password (for encrypted keys or P12)
    pkcs12_password = data.get('pkcs12_password', '')  # Output P12 password
    chain_pem = data.get('chain', '').strip()
    key_pem = data.get('private_key', '').strip()
    
    if not input_data:
        return jsonify({'error': 'Input data is required'}), 400
    
    try:
        import subprocess
        
        # Check if input is base64-encoded binary
        raw_bytes = None
        if input_data.startswith('BASE64:'):
            raw_bytes = base64.b64decode(input_data[7:])
            input_data = None
        
        # Auto-detect format and parse
        certs = []
        keys = []
        csrs = []
        detected_format = 'unknown'
        
        # Try to parse the input
        if raw_bytes:
            # Binary data - try different formats
            
            # Try PKCS12 first
            try:
                p12_pwd = password.encode() if password else None
                private_key, cert, additional_certs = serialization.pkcs12.load_key_and_certificates(
                    raw_bytes, p12_pwd, default_backend()
                )
                detected_format = 'pkcs12'
                if cert:
                    certs.append(cert)
                if additional_certs:
                    certs.extend(additional_certs)
                if private_key:
                    keys.append(private_key)
            except Exception:
                pass
            
            # Try DER certificate
            if detected_format == 'unknown':
                try:
                    cert = x509.load_der_x509_certificate(raw_bytes, default_backend())
                    certs.append(cert)
                    detected_format = 'der_cert'
                except Exception:
                    pass
            
            # Try DER private key
            if detected_format == 'unknown':
                try:
                    key = serialization.load_der_private_key(raw_bytes, password=password.encode() if password else None, backend=default_backend())
                    keys.append(key)
                    detected_format = 'der_key'
                except Exception:
                    pass
            
            # Try DER CSR
            if detected_format == 'unknown':
                try:
                    csr = x509.load_der_x509_csr(raw_bytes, default_backend())
                    csrs.append(csr)
                    detected_format = 'der_csr'
                except Exception:
                    pass
            
            # Try PKCS7/P7B (use OpenSSL)
            if detected_format == 'unknown':
                try:
                    with tempfile.NamedTemporaryFile(suffix='.p7b', delete=False) as f:
                        f.write(raw_bytes)
                        temp_p7b = f.name
                    try:
                        # Extract certs from P7B
                        pem_output = subprocess.check_output([
                            'openssl', 'pkcs7', '-print_certs', '-in', temp_p7b, '-inform', 'DER'
                        ], stderr=subprocess.DEVNULL)
                        # Parse extracted PEM certs
                        for c in x509.load_pem_x509_certificates(pem_output):
                            certs.append(c)
                        detected_format = 'pkcs7'
                    finally:
                        os.unlink(temp_p7b)
                except Exception:
                    pass
        
        else:
            # Text data (PEM format)
            detected_format = 'pem'
            
            # Parse certificates
            if '-----BEGIN CERTIFICATE-----' in input_data:
                try:
                    for cert in x509.load_pem_x509_certificates(input_data.encode()):
                        certs.append(cert)
                except Exception:
                    pass
            
            # Parse private keys
            if '-----BEGIN' in input_data and 'PRIVATE KEY-----' in input_data:
                try:
                    pwd = password.encode() if password else None
                    key = serialization.load_pem_private_key(input_data.encode(), password=pwd, backend=default_backend())
                    keys.append(key)
                except Exception:
                    pass
            
            # Parse CSRs
            if '-----BEGIN CERTIFICATE REQUEST-----' in input_data:
                try:
                    csr = x509.load_pem_x509_csr(input_data.encode(), default_backend())
                    csrs.append(csr)
                except Exception:
                    pass
            
            # If nothing parsed, try as certificate only
            if not certs and not keys and not csrs:
                try:
                    # Try adding PEM headers
                    clean = input_data.replace(' ', '').replace('\n', '')
                    pem_cert = f"-----BEGIN CERTIFICATE-----\n{clean}\n-----END CERTIFICATE-----"
                    cert = x509.load_pem_x509_certificate(pem_cert.encode(), default_backend())
                    certs.append(cert)
                except Exception:
                    pass
        
        # Also parse additional key from key_pem if provided
        if key_pem:
            try:
                pwd = password.encode() if password else None
                key = serialization.load_pem_private_key(key_pem.encode(), password=pwd, backend=default_backend())
                keys.append(key)
            except Exception:
                pass
        
        # Parse chain
        chain_certs = []
        if chain_pem:
            try:
                for c in x509.load_pem_x509_certificates(chain_pem.encode()):
                    chain_certs.append(c)
            except Exception:
                pass
        
        # Validate we have something to convert
        if not certs and not keys and not csrs:
            return jsonify({'error': 'Could not parse input data. Supported formats: PEM, DER, PKCS12, PKCS7'}), 400
        
        result = {}
        
        # Convert to requested output format
        if output_format == 'pem':
            pem_parts = []
            for cert in certs:
                pem_parts.append(cert.public_bytes(serialization.Encoding.PEM).decode())
            for key in keys:
                enc = serialization.NoEncryption()
                pem_parts.append(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=enc
                ).decode())
            for csr in csrs:
                pem_parts.append(csr.public_bytes(serialization.Encoding.PEM).decode())
            
            result = {
                'format': 'pem',
                'data': '\n'.join(pem_parts),
                'filename': 'converted.pem',
                'detected_format': detected_format,
                'contents': {
                    'certificates': len(certs),
                    'private_keys': len(keys),
                    'csrs': len(csrs)
                }
            }
        
        elif output_format == 'der':
            # DER can only contain one object
            if certs:
                der_data = certs[0].public_bytes(serialization.Encoding.DER)
                filename = 'certificate.der'
            elif keys:
                der_data = keys[0].private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )
                filename = 'private_key.der'
            elif csrs:
                der_data = csrs[0].public_bytes(serialization.Encoding.DER)
                filename = 'request.der'
            else:
                return jsonify({'error': 'No data to convert to DER'}), 400
            
            result = {
                'format': 'der',
                'data': base64.b64encode(der_data).decode(),
                'filename': filename,
                'detected_format': detected_format
            }
        
        elif output_format == 'pkcs12':
            if not certs:
                return jsonify({'error': 'Certificate is required for PKCS12'}), 400
            if not keys:
                return jsonify({'error': 'Private key is required for PKCS12'}), 400
            
            # Use first cert and key
            cert = certs[0]
            key = keys[0]
            
            # Additional certs (rest of certs + chain)
            ca_certs = certs[1:] + chain_certs if len(certs) > 1 or chain_certs else None
            
            p12_pwd = pkcs12_password.encode() if pkcs12_password else None
            p12_data = serialization.pkcs12.serialize_key_and_certificates(
                name=b"certificate",
                key=key,
                cert=cert,
                cas=ca_certs,
                encryption_algorithm=serialization.BestAvailableEncryption(p12_pwd) if p12_pwd else serialization.NoEncryption()
            )
            
            result = {
                'format': 'pkcs12',
                'data': base64.b64encode(p12_data).decode(),
                'filename': 'certificate.p12',
                'detected_format': detected_format
            }
        
        elif output_format == 'pkcs7':
            if not certs:
                return jsonify({'error': 'At least one certificate is required for PKCS7'}), 400
            
            # Build PEM with all certs
            all_certs_pem = ''
            for cert in certs + chain_certs:
                all_certs_pem += cert.public_bytes(serialization.Encoding.PEM).decode()
            
            # Use OpenSSL to create PKCS7
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                f.write(all_certs_pem)
                temp_pem = f.name
            
            try:
                p7_data = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl', '-certfile', temp_pem
                ])
                result = {
                    'format': 'pkcs7',
                    'data': p7_data.decode(),
                    'filename': 'certificates.p7b',
                    'detected_format': detected_format
                }
            finally:
                os.unlink(temp_pem)
        
        else:
            return jsonify({'error': f'Unknown output format: {output_format}'}), 400
        
        return jsonify({'success': True, 'data': result})
    
    except Exception as e:
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 400
