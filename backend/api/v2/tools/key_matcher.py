"""Key matching routes"""
import base64

from flask import request
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID

from auth.unified import require_auth
from utils.response import success_response, error_response

from . import tools_bp, get_public_key_bytes, logger


@tools_bp.route('/match-keys', methods=['POST'])
@require_auth()
def match_keys():
    """Check if certificate, private key, and/or CSR match"""
    data = request.get_json() or {}
    cert_pem = data.get('certificate', '').strip()
    key_pem = data.get('private_key', '').strip()
    csr_pem = data.get('csr', '').strip()
    password = data.get('password', '')

    if not any([cert_pem, key_pem, csr_pem]):
        return error_response('At least one of certificate, private_key, or csr is required', 400)

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
                logger.warning(f"Invalid certificate data during PEM validation: {e}")
                results['items'].append({
                    'type': 'certificate',
                    'valid': False,
                    'error': 'Invalid certificate data'
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
                logger.warning(f"Invalid private key data during PEM validation: {e}")
                results['items'].append({
                    'type': 'private_key',
                    'valid': False,
                    'error': 'Invalid private key data'
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
                logger.warning(f"Invalid CSR data during PEM validation: {e}")
                results['items'].append({
                    'type': 'csr',
                    'valid': False,
                    'error': 'Invalid CSR data'
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

        return success_response(data=results)

    except Exception as e:
        logger.error(f'Failed to match keys: {e}')
        return error_response('Failed to match keys', 400)
